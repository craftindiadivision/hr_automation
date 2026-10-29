import frappe
from frappe import _
from frappe.utils import add_days, add_months, getdate, today

from hr_automation.api.leave_management import TRAINING_MONTHS, get_probation_end_date
from hr_automation.api.performance_feedback import FEEDBACK_LEAD_MONTHS, request_feedback
from hr_automation.api.self_appraisal import get_self_appraisal_link

# Months after joining of the Annual appraisal, which is each employee's last
# automatic one: trainees at month 15, employees at month 12.
TRAINEE_ANNUAL_MONTHS = 15
EMPLOYEE_ANNUAL_MONTHS = 12
# Appraisals that fell due longer ago than this when the schedule started
# (existing employees) are skipped, rather than all emailed at once.
CATCH_UP_DAYS = 30


def get_appraisal_stage(trainee_track, number):
	"""Stage of an employee's appraisal no. `number` (0 = first), or None once
	they've had all of them. Trainees: Training (month 3), Probation (month 9),
	Annual (month 15). Employees: Probation (month 6), Annual (month 12)."""
	stages = ("Training", "Probation", "Annual") if trainee_track else ("Probation", "Annual")
	return stages[number] if number < len(stages) else None


def get_appraisal_due_date(date_of_joining, probation_end_date, trainee_track, number):
	"""Due date of appraisal no. `number`, or None when there are no more.
	Training: 3 months after joining. Probation: the day after Probation End
	Date - so extending probation moves it. Annual: a fixed 15 (trainee) / 12
	(employee) months after joining."""
	stage = get_appraisal_stage(trainee_track, number)
	if not stage:
		return None
	if stage == "Training":
		return add_months(getdate(date_of_joining), TRAINING_MONTHS)
	if stage == "Probation":
		if not probation_end_date:
			probation_end_date = get_probation_end_date(date_of_joining, trainee_track)
		return add_days(getdate(probation_end_date), 1)
	return add_months(
		getdate(date_of_joining), TRAINEE_ANNUAL_MONTHS if trainee_track else EMPLOYEE_ANNUAL_MONTHS
	)


def set_next_appraisal_date(doc, method=None):
	"""Employee validate (after set_probation_end_date): keeps Next Appraisal
	Due in line with the joining date, Probation End Date and how many
	appraisals have been sent so far (empty once they've had them all)."""
	if not doc.date_of_joining:
		return
	doc.custom_next_appraisal_date = get_appraisal_due_date(
		doc.date_of_joining,
		doc.custom_probation_end_date,
		doc.custom_is_trainee or doc.custom_was_trainee,
		doc.custom_appraisals_notified or 0,
	)


def send_assessment_notifications():
	"""Daily job: once an employee's next appraisal is due, creates the
	Appraisal (with its stage) and emails them the self-appraisal link. The
	schedule ends with the Annual appraisal - nothing is created after it. If the
	Appraisal can't be created, nothing is sent or counted - HR is told, and
	it's retried the next day."""
	current_date = getdate(today())
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "date_of_joining": ["is", "set"]},
		fields=[
			"name",
			"employee_name",
			"date_of_joining",
			"prefered_email",
			"personal_email",
			"company_email",
			"company",
			"custom_is_trainee",
			"custom_was_trainee",
			"custom_probation_end_date",
			"custom_appraisals_notified",
			"custom_feedback_requested_for",
		],
	)
	for emp in employees:
		trainee_track = bool(emp.custom_is_trainee or emp.custom_was_trainee)
		number = emp.custom_appraisals_notified or 0
		due = get_appraisal_due_date(emp.date_of_joining, emp.custom_probation_end_date, trainee_track, number)
		if not due:
			continue  # had every appraisal on the schedule
		stage = get_appraisal_stage(trainee_track, number)
		if due > current_date:
			# A month ahead: ask the employee's manager for feedback, once per appraisal.
			if current_date >= add_months(due, -FEEDBACK_LEAD_MONTHS) and (emp.custom_feedback_requested_for or 0) <= number:
				_request_manager_feedback(emp, stage, due, number)
			continue

		frappe.db.savepoint("appraisal_notification")
		try:
			link = get_self_appraisal_link(emp.name, emp.company, stage)
			sent = _send_assessment_email(emp, link=link, **_STAGE_EMAILS[stage])
		except Exception:
			frappe.db.rollback(save_point="appraisal_notification")
			frappe.log_error(title=f"{stage} appraisal not created for {emp.name}")
			_notify_hr(
				emp.name,
				_(
					"The {0} appraisal for {1} is due but couldn't be created (see Error Log). "
					"It will be retried tomorrow."
				).format(_(stage), emp.employee_name),
			)
			continue
		if not sent:
			continue

		values = {
			"custom_appraisals_notified": number + 1,
			"custom_next_appraisal_date": get_appraisal_due_date(
				emp.date_of_joining, emp.custom_probation_end_date, trainee_track, number + 1
			),
		}
		if stage == "Training":
			# Training is over: the trainee continues on probation as an employee;
			# custom_was_trainee keeps them on the trainee schedule.
			values.update(
				{
					"custom_training_assessment_sent_on": current_date,
					"custom_is_trainee": 0,
					"custom_is_employee": 1,
					"custom_was_trainee": 1,
				}
			)
		elif stage == "Probation":
			values["custom_probation_assessment_sent_on"] = current_date
		else:
			values["custom_annual_assessment_sent_on"] = current_date
		frappe.db.set_value("Employee", emp.name, values)


def _request_manager_feedback(emp, stage, due, number):
	frappe.db.savepoint("manager_feedback")
	try:
		request_feedback(emp.name, stage, due)
	except Exception:
		frappe.db.rollback(save_point="manager_feedback")
		frappe.log_error(title=f"Manager feedback not requested for {emp.name}")
		_notify_hr(
			emp.name,
			_("Manager feedback for {0}'s {1} appraisal couldn't be requested (see Error Log).").format(
				emp.employee_name, _(stage)
			),
		)
		return
	frappe.db.set_value("Employee", emp.name, "custom_feedback_requested_for", number + 1)


def update_latest_appraisal_date(doc, method=None):
	"""Appraisal on_submit / on_cancel: Employee's Latest Appraisal Date is the
	most recent submitted Appraisal."""
	dates = frappe.get_all(
		"Appraisal", filters={"employee": doc.employee, "docstatus": 1}, pluck="modified"
	)
	if method == "on_submit":
		dates.append(today())
	latest = max((getdate(d) for d in dates), default=None)
	frappe.db.set_value("Employee", doc.employee, "custom_latest_appraisal_date", latest)


def _notify_hr(employee, subject):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
	from frappe.utils.user import get_users_with_role

	users = [u for u in get_users_with_role("HR Manager") if u != "Administrator"]
	if users:
		enqueue_create_notification(
			users,
			{
				"type": "Alert",
				"document_type": "Employee",
				"document_name": employee,
				"subject": subject,
				"from_user": "Administrator",
			},
		)


_ANNUAL_MESSAGE = """
<p>Dear {{ employee_name }},</p>
<p>It's time for your annual performance appraisal. This is an opportunity to look back on your
	achievements over the past year, the areas where you have grown, and your goals for the year ahead.</p>
<p>Please complete your self-appraisal using the link below. HR and your reporting manager will then
	review it with you.</p>
<p>HR Team</p>
"""

_SIX_MONTH_MESSAGE = """
<p>Congratulations on completing 6 months with Craft Interactive Technologies Pvt Ltd!</p>
<p>You have successfully completed 6 months of service with the organisation. This is an important
	milestone and an opportunity to reflect on your learning, contribution, and growth so far.</p>
<p>As part of our 6-Month Employee Assessment Process, you will be contacted by the HR/management
	team to discuss your performance, experience, achievements, and areas for further development.</p>
<p>Please complete the 6-Month Assessment Form attached to this notification and submit it as instructed.</p>
<p>We appreciate your contribution and look forward to your continued growth and success with us.</p>
<p>HR Team</p>
"""

_THREE_MONTH_MESSAGE = """
<p>Dear {{ employee_name }}</p>
<p>Congratulations on successfully completing your internship with CIT</p>
<p>As the next step, your internship program and overall suitability for continued employment will
	be reviewed. Based on this assessment, the company will decide whether to absorb you as an
	employee or conclude the engagement.</p>
<p>HR will contact you shortly for a one-to-one discussion to review your learning, contribution,
	and potential opportunities with the company. Please complete your self-appraisal using the link below
	before that discussion.</p>
<p>We wish you all the best for your professional journey.</p>
<p>Hr Department</p>
"""


_STAGE_EMAILS = {
	"Training": {
		"subject": _("Congratulations on Completing Your Internship with CIT"),
		"message_template": _THREE_MONTH_MESSAGE,
	},
	"Probation": {
		"subject": _("Congratulations on Completing 6 months with Craft Interactive Technologies Pvt Ltd!"),
		"message": _SIX_MONTH_MESSAGE,
	},
	"Annual": {"subject": _("Your Annual Appraisal"), "message_template": _ANNUAL_MESSAGE},
}


def _send_assessment_email(emp, subject, message=None, message_template=None, link=None):
	email = emp.prefered_email or emp.personal_email or emp.company_email
	if not email:
		frappe.log_error(
			title="Assessment notification skipped",
			message=f"Employee {emp.name} has no email on file (checked preferred/personal/company email).",
		)
		return False

	if message_template is not None:
		message = frappe.render_template(message_template, {"employee_name": emp.employee_name})
	if link:
		message += frappe.render_template(
			'<p>Please complete your self appraisal here: <a href="{{ link }}">{{ link }}</a></p>',
			{"link": link},
		)

	frappe.sendmail(
		recipients=[email],
		cc=_get_notification_cc_list(),
		subject=subject,
		message=message,
		reference_doctype="Employee",
		reference_name=emp.name,
	)
	return True


def _get_notification_cc_list():
	settings = frappe.get_single("HR Automation Settings")
	return [row.user_email for row in settings.assessment_notification_recipients if row.user_email]
