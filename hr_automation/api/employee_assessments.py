import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from hr_automation.api.self_appraisal import get_self_appraisal_link


def send_assessment_notifications():
	"""Daily job: notify employees/trainees of upcoming assessments based on date_of_joining."""
	_notify_trainee_training_complete()
	_notify_probation_assessment()
	_notify_annual_assessment()


def _get_due_employees(extra_filters, sent_field):
	filters = {
		"status": "Active",
		"date_of_joining": ["is", "set"],
		sent_field: ["is", "not set"],
		**extra_filters,
	}
	return frappe.get_all(
		"Employee",
		filters=filters,
		fields=[
			"name",
			"employee_name",
			"date_of_joining",
			"prefered_email",
			"personal_email",
			"company_email",
			"company",
		],
	)


def _notify_trainee_training_complete():
	"""Trainees: 3 months after joining, the training period is complete.
	Once notified, the employee is automatically switched from Trainee to Employee,
	but custom_was_trainee keeps a permanent record so the 9/15-month (not 6/12-month)
	schedule still applies to their later assessments."""
	cutoff = getdate(today())
	for emp in _get_due_employees({"custom_is_trainee": 1}, "custom_training_assessment_sent_on"):
		if add_months(getdate(emp.date_of_joining), 3) > cutoff:
			continue
		if _send_assessment_email(
			emp,
			subject=_("Congratulations on Completing Your Internship with CIT"),
			message_template=_THREE_MONTH_MESSAGE_TEMPLATE,
		):
			frappe.db.set_value(
				"Employee",
				emp.name,
				{
					"custom_training_assessment_sent_on": cutoff,
					"custom_is_trainee": 0,
					"custom_is_employee": 1,
					"custom_was_trainee": 1,
				},
			)


def _notify_probation_assessment():
	"""Employees who were never trainees: 6 months after joining.
	Employees who came up through the trainee track: 6 months after their 3-month
	training assessment (i.e. 9 months after joining), tracked via custom_was_trainee
	since custom_is_trainee is cleared once they're auto-converted at 3 months."""
	cutoff = getdate(today())

	for emp in _get_due_employees(
		{"custom_is_employee": 1, "custom_was_trainee": 0}, "custom_probation_assessment_sent_on"
	):
		if add_months(getdate(emp.date_of_joining), 6) > cutoff:
			continue
		if _send_assessment_email(
			emp,
			subject=_("Congratulations on Completing 6 months with Craft Interactive Technologies Pvt Ltd!"),
			message=_SIX_MONTH_MESSAGE,
			include_appraisal_link=True,
		):
			frappe.db.set_value("Employee", emp.name, "custom_probation_assessment_sent_on", cutoff)

	for emp in _get_due_employees({"custom_was_trainee": 1}, "custom_probation_assessment_sent_on"):
		if add_months(getdate(emp.date_of_joining), 9) > cutoff:
			continue
		if _send_assessment_email(
			emp,
			subject=_("Congratulations on Completing 6 months with Craft Interactive Technologies Pvt Ltd!"),
			message=_SIX_MONTH_MESSAGE,
			include_appraisal_link=True,
		):
			frappe.db.set_value("Employee", emp.name, "custom_probation_assessment_sent_on", cutoff)


def _notify_annual_assessment():
	"""Employees who were never trainees: 12 months after joining.
	Employees who came up through the trainee track: 12 months after their 3-month
	training assessment (i.e. 15 months after joining), same reasoning as the
	9-month probation assessment - their appraisal cycle counts from when
	training ended, not from their original joining date."""
	cutoff = getdate(today())

	for emp in _get_due_employees(
		{"custom_is_employee": 1, "custom_was_trainee": 0}, "custom_annual_assessment_sent_on"
	):
		if add_months(getdate(emp.date_of_joining), 12) > cutoff:
			continue
		if _send_assessment_email(
			emp,
			subject=_("Upcoming Assessment"),
			body=_("Your assessment will be there."),
			include_appraisal_link=True,
		):
			frappe.db.set_value("Employee", emp.name, "custom_annual_assessment_sent_on", cutoff)

	for emp in _get_due_employees({"custom_was_trainee": 1}, "custom_annual_assessment_sent_on"):
		if add_months(getdate(emp.date_of_joining), 15) > cutoff:
			continue
		if _send_assessment_email(
			emp,
			subject=_("Upcoming Assessment"),
			body=_("Your assessment will be there."),
			include_appraisal_link=True,
		):
			frappe.db.set_value("Employee", emp.name, "custom_annual_assessment_sent_on", cutoff)


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

_THREE_MONTH_MESSAGE_TEMPLATE = """
<p>Dear {{ employee_name }}</p>
<p>Congratulations on successfully completing your internship with CIT</p>
<p>As the next step, your internship program and overall suitability for continued employment will
	be reviewed. Based on this assessment, the company will decide whether to absorb you as an
	employee or conclude the engagement.</p>
<p>HR will contact you shortly for a one-to-one discussion to review your learning, contribution,
	and potential opportunities with the company.</p>
<p>We wish you all the best for your professional journey.</p>
<p>Hr Department</p>
"""


def _send_assessment_email(
	emp, subject, body=None, message=None, message_template=None, include_appraisal_link=False
):
	email = emp.prefered_email or emp.personal_email or emp.company_email
	if not email:
		frappe.log_error(
			title="Assessment notification skipped",
			message=f"Employee {emp.name} has no email on file (checked preferred/personal/company email).",
		)
		return False

	if message_template is not None:
		message = frappe.render_template(message_template, {"employee_name": emp.employee_name})
	elif message is None:
		message = frappe.render_template(
			"<p>Dear {{ employee_name }},</p><p>{{ body }}</p>",
			{"employee_name": emp.employee_name, "body": body},
		)

	if include_appraisal_link:
		link = get_self_appraisal_link(emp.name, emp.company)
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
