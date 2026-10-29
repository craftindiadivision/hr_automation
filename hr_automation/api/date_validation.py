import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, today

from hrms.hr.doctype.leave_application.leave_application import get_number_of_leave_days

from hr_automation.api.leave_management import get_probation_leave_allowance, get_probation_start_date

SICK_LEAVE_TYPE = "Sick Leave"
COMPENSATORY_LEAVE_TYPE = "Compensatory Off"
COMPENSATORY_WINDOW_DAYS = 60
MATERNITY_LEAVE_TYPE = "Maternity Leave"
# Allowed during probation regardless of the Probation Leave Policy (Leave
# Without Pay types are also exempt, checked via the Leave Type's Is LWP).
PROBATION_EXEMPT_LEAVE_TYPES = (COMPENSATORY_LEAVE_TYPE, MATERNITY_LEAVE_TYPE)
MATERNITY_MAX_CHILDREN = 2
MATERNITY_MIN_DAYS_WORKED = 80


def validate_not_backdated(doc, method=None):
	if not doc.is_new():
		return
	if doc.doctype == "Leave Application" and doc.leave_type == SICK_LEAVE_TYPE:
		return
	if _can_enter_past_dates():
		return
	if getdate(doc.from_date) < getdate(today()):
		frappe.throw(_("From Date cannot be before today ({0})").format(frappe.format(today(), "Date")))


def validate_leave_rules(doc, method=None):
	if not doc.is_new():
		return
	if doc.leave_type == COMPENSATORY_LEAVE_TYPE:
		_validate_compensatory_window(doc)
	elif doc.leave_type == MATERNITY_LEAVE_TYPE:
		_validate_maternity_eligibility(doc)


def _can_enter_past_dates():
	"""The role set in HR Automation Settings (e.g. HR entering on an
	employee's behalf) may use past dates on Leave Applications and Attendance
	Requests."""
	role = frappe.db.get_single_value("HR Automation Settings", "backdated_leave_role")
	return bool(role) and role in frappe.get_roles()


def validate_leave_certificate(doc, method=None):
	"""Leave Application validate: a leave type marked Is Certificate Required
	needs the Certificate attached once the leave is longer than its
	Certificate Required After (Days) - 0 means always."""
	required, after_days = frappe.db.get_value(
		"Leave Type", doc.leave_type, ["custom_certificate_required", "custom_certificate_after_days"]
	) or (0, 0)
	if not required or doc.status in ("Rejected", "Cancelled") or doc.get("custom_medical_certificate"):
		return
	if flt(doc.total_leave_days) > flt(after_days):
		frappe.throw(
			_("Attach a Certificate - {0} needs one for leave longer than {1} day(s).").format(
				doc.leave_type, f"{flt(after_days):g}"
			)
			if flt(after_days)
			else _("Attach a Certificate - {0} always needs one.").format(doc.leave_type),
			title=_("Certificate Required"),
		)


def validate_probation_leave(doc, method=None):
	"""A trainee's first 3 months (training) allow no leave at all. During
	probation only the leave types in the employee's Probation Leave Policy can
	be taken, up to the days that policy gives for the whole probation (e.g. 4
	Sick Leave). Compensatory Off, Maternity Leave and Leave Without Pay are
	always allowed. Runs on every save, not just new applications, so editing
	the dates of a draft can't sidestep it. Hooked on before_validate so these
	messages show instead of HRMS's generic allocation-period errors."""
	if doc.docstatus == 2 or doc.status in ("Rejected", "Cancelled"):
		return
	if doc.leave_type in PROBATION_EXEMPT_LEAVE_TYPES or frappe.db.get_value(
		"Leave Type", doc.leave_type, "is_lwp"
	):
		return
	employee = frappe.db.get_value(
		"Employee",
		doc.employee,
		[
			"date_of_joining",
			"custom_is_trainee",
			"custom_was_trainee",
			"custom_probation_end_date",
			"custom_probation_leave_policy",
		],
		as_dict=True,
	)
	if not employee or not employee.custom_probation_end_date:
		return
	probation_start = get_probation_start_date(
		employee.date_of_joining, employee.custom_is_trainee or employee.custom_was_trainee
	)
	probation_end = getdate(employee.custom_probation_end_date)

	if getdate(doc.from_date) < probation_start:
		frappe.throw(
			_("No leave can be taken during the 3-month training period, which ends on {0}.").format(
				frappe.format(add_days(probation_start, -1), "Date")
			),
			title=_("Not Allowed During Training"),
		)
	if getdate(doc.from_date) > probation_end:
		return
	if getdate(doc.to_date) > probation_end:
		frappe.throw(
			_(
				"Probation ends on {0}. Apply separately for the days up to {0} and for the days from {1}."
			).format(frappe.format(probation_end, "Date"), frappe.format(add_days(probation_end, 1), "Date"))
		)
	if not employee.custom_probation_leave_policy:
		return

	allowance = get_probation_leave_allowance(employee.custom_probation_leave_policy)
	if doc.leave_type not in allowance:
		frappe.throw(
			_("Only {0} can be taken during probation, which ends on {1}.").format(
				", ".join(allowance) or _("exempt leave types"), frappe.format(probation_end, "Date")
			),
			title=_("Not Allowed During Probation"),
		)

	used = frappe.db.sql(
		"""select coalesce(sum(total_leave_days), 0) from `tabLeave Application`
		where employee=%s and leave_type=%s and docstatus < 2
		and status not in ('Rejected', 'Cancelled') and name != %s
		and from_date between %s and %s""",
		(doc.employee, doc.leave_type, doc.name or "", probation_start, probation_end),
	)[0][0]
	limit = allowance[doc.leave_type]
	days = get_number_of_leave_days(
		doc.employee, doc.leave_type, doc.from_date, doc.to_date, doc.half_day, doc.half_day_date
	)
	if flt(used) + flt(days) > flt(limit):
		frappe.throw(
			_(
				"Only {0} days of {1} are allowed during probation. {2} already used or applied for, so "
				"at most {3} more can be taken until {4}."
			).format(
				f"{flt(limit):g}",
				doc.leave_type,
				f"{flt(used):g}",
				f"{max(flt(limit) - flt(used), 0):g}",
				frappe.format(probation_end, "Date"),
			),
			title=_("Probation Limit Reached"),
		)


def _validate_compensatory_window(doc):
	if not _find_available_compensatory_request(doc.employee, getdate(doc.from_date)):
		frappe.throw(
			_(
				"Compensatory leave must be taken within {0} days of the work it was earned for, "
				"and each earned day can only be used once. No unused compensatory credit covers this date."
			).format(COMPENSATORY_WINDOW_DAYS)
		)


def _find_available_compensatory_request(employee, from_date):
	"""An approved Compensatory Leave Request is a single credit: once a Leave
	Application has consumed it (on submit), it can't back a second one. Picks
	the request whose window expires soonest, so older credits get used first."""
	candidates = frappe.get_all(
		"Compensatory Leave Request",
		filters={
			"employee": employee,
			"docstatus": 1,
			"work_end_date": ["<=", from_date],
			"custom_consumed_by_leave_application": ["in", ("", None)],
		},
		fields=["name", "work_end_date"],
		order_by="work_end_date asc",
	)
	for row in candidates:
		if from_date <= add_days(getdate(row.work_end_date), COMPENSATORY_WINDOW_DAYS):
			return row.name
	return None


def consume_compensatory_request_on_submit(doc, method=None):
	"""Leave Application on_submit: permanently claims the specific
	Compensatory Leave Request this application used, so it can never back a
	second application. Only runs once, at submit - not on every draft save,
	which validate_leave_rules already re-checks without consuming anything."""
	if doc.leave_type != COMPENSATORY_LEAVE_TYPE:
		return
	request_name = _find_available_compensatory_request(doc.employee, getdate(doc.from_date))
	if request_name:
		frappe.db.set_value(
			"Compensatory Leave Request", request_name, "custom_consumed_by_leave_application", doc.name
		)


def release_compensatory_request_on_cancel(doc, method=None):
	"""Leave Application on_cancel: frees up the Compensatory Leave Request it
	had claimed, so the credit becomes available again."""
	if doc.leave_type != COMPENSATORY_LEAVE_TYPE:
		return
	frappe.db.set_value(
		"Compensatory Leave Request",
		{"custom_consumed_by_leave_application": doc.name},
		"custom_consumed_by_leave_application",
		None,
	)


def _validate_maternity_eligibility(doc):
	children = frappe.db.get_value("Employee", doc.employee, "custom_number_of_children") or 0
	if children >= MATERNITY_MAX_CHILDREN:
		frappe.throw(_("Maternity leave is only available for employees with fewer than {0} children").format(MATERNITY_MAX_CHILDREN))

	from_date = getdate(doc.from_date)
	attendance = frappe.get_all(
		"Attendance",
		filters={
			"employee": doc.employee,
			"docstatus": 1,
			"attendance_date": ["between", [add_months(from_date, -12), add_days(from_date, -1)]],
		},
		fields=["status"],
	)
	days_worked = sum(
		1 if row.status in ("Present", "Work From Home") else 0.5 if row.status == "Half Day" else 0
		for row in attendance
	)
	if days_worked < MATERNITY_MIN_DAYS_WORKED:
		frappe.throw(
			_("Maternity leave needs {0} days worked in the previous 12 months. Found {1}.").format(
				MATERNITY_MIN_DAYS_WORKED, days_worked
			)
		)

