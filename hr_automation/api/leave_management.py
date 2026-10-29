import frappe
from frappe import _
from frappe.utils import add_days, add_months, getdate, today

# Trainees: 3 months training (no leave) + 6 months probation.
# Direct employees: 6 months probation from joining.
TRAINING_MONTHS = 3
PROBATION_MONTHS = 6


def get_probation_start_date(date_of_joining, is_trainee):
	"""First day of probation leave: joining date, or 3 months later for a trainee."""
	return add_months(getdate(date_of_joining), TRAINING_MONTHS if is_trainee else 0)


def get_probation_end_date(date_of_joining, is_trainee):
	"""Last day of probation, e.g. joining 1 Apr 2026 as a trainee -> 31 Dec 2026."""
	months = PROBATION_MONTHS + (TRAINING_MONTHS if is_trainee else 0)
	return add_days(add_months(getdate(date_of_joining), months), -1)


def set_probation_end_date(doc, method=None):
	"""Employee validate: fills in Probation End Date from the joining date and
	trainee/employee type. Left alone once set, so HR can extend probation by
	editing it - only recomputed if the joining date itself changes."""
	if not doc.date_of_joining:
		return
	if doc.custom_probation_end_date and (doc.is_new() or not doc.has_value_changed("date_of_joining")):
		return
	doc.custom_probation_end_date = get_probation_end_date(
		doc.date_of_joining, doc.custom_is_trainee or doc.custom_was_trainee
	)


def get_probation_leave_allowance(policy) -> dict:
	"""{leave_type: days} from a probation Leave Policy, e.g. {"Sick Leave": 4}."""
	rows = frappe.get_all(
		"Leave Policy Detail",
		filters={"parent": policy, "parenttype": "Leave Policy"},
		fields=["leave_type", "annual_allocation"],
	)
	return {row.leave_type: row.annual_allocation for row in rows}


def assign_probation_leave_policy(employee: str):
	"""Assigns the employee's Probation Leave Policy (picked on the Job Offer and
	copied to the Employee) from probation start to Probation End Date. Does
	nothing before probation starts - a trainee's first 3 months have no leave -
	or if it is already assigned, so it is safe to call repeatedly."""
	emp = frappe.db.get_value(
		"Employee",
		employee,
		[
			"company",
			"date_of_joining",
			"custom_is_trainee",
			"custom_was_trainee",
			"custom_probation_end_date",
			"custom_probation_leave_policy",
		],
		as_dict=True,
	)
	if not emp.custom_probation_leave_policy or not emp.custom_probation_end_date:
		return
	start = get_probation_start_date(emp.date_of_joining, emp.custom_is_trainee or emp.custom_was_trainee)
	end = getdate(emp.custom_probation_end_date)
	if start > getdate(today()) or start > end or _has_assignment_between(employee, start, end):
		return

	frappe.get_doc(
		{
			"doctype": "Leave Policy Assignment",
			"employee": employee,
			"leave_policy": emp.custom_probation_leave_policy,
			"company": emp.company,
			"effective_from": start,
			"effective_to": end,
		}
	).insert(ignore_permissions=True).submit()


def allocate_probation_leave():
	"""Daily job: assigns the Probation Leave Policy on the day probation starts -
	3 months after joining for trainees; for direct employees onboarding has
	usually done it already, unless they joined after onboarding completed."""
	current_date = getdate(today())
	employees = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			"custom_probation_leave_policy": ["is", "set"],
			"custom_probation_end_date": [">=", current_date],
		},
		pluck="name",
	)
	for employee in employees:
		frappe.db.savepoint("probation_leave")
		try:
			assign_probation_leave_policy(employee)
		except Exception:
			frappe.db.rollback(save_point="probation_leave")
			frappe.log_error(title=f"Probation leave not allocated for {employee}")


def allocate_regular_leave():
	"""Daily job. Gives every Active, confirmed employee (Confirmation Date set
	by their probation appraisal) the Leave Policy of the current Leave Period
	(custom_leave_policy on Leave Period):
	- once confirmed: pro-rated from the day after probation ended to the end
	  of the leave year
	- on the first day of a new leave year: the full policy
	Skips anyone who already has an assignment covering those dates, so it is
	safe to run every day and picks up anything missed (e.g. a Leave Period
	that HR created late)."""
	current_date = getdate(today())
	periods = {}
	missing_period_companies = set()

	employees = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			"custom_probation_end_date": ["<", current_date],
			"final_confirmation_date": ["is", "set"],
		},
		fields=["name", "company", "custom_probation_end_date"],
	)
	for emp in employees:
		if emp.company not in periods:
			periods[emp.company] = _get_leave_period(emp.company, current_date)
		period = periods[emp.company]
		if not period or not period.custom_leave_policy:
			missing_period_companies.add(emp.company)
			continue

		start = max(
			getdate(period.from_date),
			add_days(getdate(emp.custom_probation_end_date), 1),
			_day_after_existing_allocations(emp.name, period),
		)
		if start > getdate(period.to_date) or _has_assignment_between(emp.name, start, period.to_date):
			continue

		frappe.db.savepoint("regular_leave")
		try:
			_create_regular_assignment(emp, period, start)
		except Exception:
			frappe.db.rollback(save_point="regular_leave")
			frappe.log_error(title=f"Regular leave not allocated for {emp.name}")

	for company in missing_period_companies:
		_notify_missing_leave_period(company, current_date)


def _get_leave_period(company, date):
	periods = frappe.get_all(
		"Leave Period",
		filters={
			"company": company,
			"is_active": 1,
			"from_date": ["<=", date],
			"to_date": [">=", date],
		},
		fields=["name", "from_date", "to_date", "custom_leave_policy"],
		limit=1,
	)
	return periods[0] if periods else None


def _day_after_existing_allocations(employee, period):
	"""Leave already allocated some other way (e.g. by hand, or under an older
	leave year) for this period's leave types is kept, and the new allocation
	starts after it ends - otherwise HRMS rejects the overlapping allocation."""
	leave_types = frappe.get_all(
		"Leave Policy Detail",
		filters={"parent": period.custom_leave_policy, "parenttype": "Leave Policy"},
		pluck="leave_type",
	)
	last_to_date = frappe.get_all(
		"Leave Allocation",
		filters={
			"employee": employee,
			"docstatus": 1,
			"leave_type": ["in", leave_types],
			"to_date": [">=", period.from_date],
			"from_date": ["<=", period.to_date],
		},
		pluck="to_date",
		order_by="to_date desc",
		limit=1,
	)
	return add_days(getdate(last_to_date[0]), 1) if last_to_date else getdate(period.from_date)


def _has_assignment_between(employee, from_date, to_date):
	return frappe.db.exists(
		"Leave Policy Assignment",
		{
			"employee": employee,
			"docstatus": 1,
			"effective_from": ["<=", to_date],
			"effective_to": [">=", from_date],
		},
	)


def _create_regular_assignment(emp, period, start):
	# Carry forward only from a previous regular allocation - when the previous
	# allocation is the probation one (probation ended the day before `start`),
	# unused probation leave lapses. Whether a given leave type actually carries
	# over is still controlled by "Is Carry Forward" on the Leave Type.
	carry_forward = add_days(getdate(emp.custom_probation_end_date), 1) < start
	assignment = frappe.get_doc(
		{
			"doctype": "Leave Policy Assignment",
			"employee": emp.name,
			"leave_policy": period.custom_leave_policy,
			"company": emp.company,
			"effective_from": start,
			"effective_to": period.to_date,
			"carry_forward": 1 if carry_forward else 0,
		}
	)
	# Read by CustomLeavePolicyAssignment.get_new_leaves to pro-rate by the
	# part of the leave year this assignment covers.
	assignment.flags.pro_rate_within = (getdate(period.from_date), getdate(period.to_date))
	assignment.insert(ignore_permissions=True)
	assignment.submit()


def _notify_missing_leave_period(company, date):
	message = _(
		"No active Leave Period with a Leave Policy covers {0} for company {1}, so confirmed "
		"employees could not be given their leave. Create the Leave Period and set its Leave Policy; "
		"the daily job will then allocate it automatically."
	).format(frappe.format(date, "Date"), company)
	frappe.log_error(title="Leave Period missing for regular leave", message=message)

	settings = frappe.get_single("HR Automation Settings")
	recipients = [row.user_email for row in settings.assessment_notification_recipients if row.user_email]
	if recipients:
		frappe.sendmail(
			recipients=recipients,
			subject=_("Action needed: Leave Period not set up for {0}").format(company),
			message=message,
		)
