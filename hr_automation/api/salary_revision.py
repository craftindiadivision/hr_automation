"""Salary changes go through the Appraisal: the Appointment Letter's Next
Phase salary (or an increment HR enters) is the appraisal's Proposed Revised
Salary, and submitting the appraisal with a passing score starts a new Salary
Structure Assignment - the one payroll then uses."""

import frappe
from frappe import _
from frappe.utils import add_months, flt, formatdate, get_first_day, get_link_to_form, getdate, today

from hr_automation.api.employee_confirmation import CONFIRMATION_MIN_SCORE


def get_current_assignment(employee):
	"""The employee's latest submitted Salary Structure Assignment."""
	return frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1},
		["name", "salary_structure", "base", "from_date", "income_tax_slab", "payroll_payable_account", "currency"],
		as_dict=True,
		order_by="from_date desc",
	)


def apply_next_phase(appraisal, employee):
	"""Called when the scheduled appraisal is created: if the employee's
	Appointment Letter has a Next Phase salary that's due and not yet used, it
	becomes this appraisal's Proposed Revised Salary (from the Next Phase Date,
	on the Next Phase Salary Structure). One appraisal carries it - the letter
	never creates a second one."""
	letter = frappe.db.get_value(
		"Appointment Letter",
		{
			"custom_employee": employee,
			"custom_next_phase_appraisal": ["is", "not set"],
			"custom_next_phase_gross_salary": [">", 0],
			"custom_next_phase_date": ["<=", today()],
		},
		["name", "custom_next_phase_gross_salary", "custom_next_phase_salary_structure", "custom_next_phase_date"],
		as_dict=True,
	)
	if not letter or frappe.db.get_value("Appraisal", appraisal, "custom_proposed_revised_salary"):
		return
	frappe.db.set_value(
		"Appraisal",
		appraisal,
		{
			"custom_proposed_revised_salary": letter.custom_next_phase_gross_salary,
			"custom_revised_salary_structure": letter.custom_next_phase_salary_structure,
			"custom_revised_salary_from": letter.custom_next_phase_date,
		},
		update_modified=False,
	)
	frappe.db.set_value(
		"Appointment Letter", letter.name, "custom_next_phase_appraisal", appraisal, update_modified=False
	)


def revise_salary_on_appraisal_submit(doc, method=None):
	"""Appraisal on_submit: a passing appraisal with a Proposed Revised Salary
	starts a new Salary Structure Assignment (the old one stays as history)."""
	revised = flt(doc.get("custom_proposed_revised_salary"))
	if not revised:
		return
	if flt(doc.final_score) < CONFIRMATION_MIN_SCORE:
		frappe.msgprint(
			_("The score ({0}) is below {1}, so the salary was not revised.").format(
				flt(doc.final_score), CONFIRMATION_MIN_SCORE
			),
			indicator="orange",
			alert=True,
		)
		return

	current = get_current_assignment(doc.employee)
	structure = doc.get("custom_revised_salary_structure") or (current.salary_structure if current else None)
	if not structure:
		frappe.throw(_("Set the Revised Salary Structure - {0} has no current salary structure").format(doc.employee_name))
	from_date = getdate(doc.get("custom_revised_salary_from") or get_first_day(add_months(today(), 1)))
	if current and from_date <= getdate(current.from_date):
		frappe.throw(
			_("Revised Salary From must be after {0}, when the current salary ({1}) started").format(
				formatdate(current.from_date), get_link_to_form("Salary Structure Assignment", current.name)
			)
		)

	assignment = frappe.get_doc(
		{
			"doctype": "Salary Structure Assignment",
			"employee": doc.employee,
			"salary_structure": structure,
			"company": doc.company,
			"currency": (current and current.currency)
			or frappe.get_cached_value("Company", doc.company, "default_currency"),
			"from_date": from_date,
			"base": revised,
			"income_tax_slab": current.income_tax_slab if current else None,
			"payroll_payable_account": current.payroll_payable_account if current else None,
		}
	)
	assignment.insert(ignore_permissions=True)
	assignment.submit()
	doc.db_set("custom_salary_structure_assignment", assignment.name, update_modified=False)

	message = _("Salary revised for {0}: {1} → {2} from {3}.").format(
		doc.employee_name,
		_amount(current.base if current else 0),
		_amount(revised),
		formatdate(from_date),
	)
	frappe.msgprint(message, indicator="green", alert=True)
	_notify_hr(doc.employee, message)


def cancel_revision_on_appraisal_cancel(doc, method=None):
	"""Appraisal on_cancel: undo the salary revision it made - unless payroll
	has already paid that salary, in which case HR has to handle it."""
	name = doc.get("custom_salary_structure_assignment")
	if not name or frappe.db.get_value("Salary Structure Assignment", name, "docstatus") != 1:
		return
	from_date = frappe.db.get_value("Salary Structure Assignment", name, "from_date")
	if frappe.db.exists(
		"Salary Slip", {"employee": doc.employee, "docstatus": 1, "end_date": [">=", from_date]}
	):
		frappe.msgprint(
			_(
				"The revised salary ({0}) has already been paid in a submitted Salary Slip, so it was not "
				"cancelled. Cancel or replace it manually if needed."
			).format(get_link_to_form("Salary Structure Assignment", name)),
			indicator="orange",
		)
		return
	assignment = frappe.get_doc("Salary Structure Assignment", name)
	# This appraisal links to it, and is the thing being cancelled.
	assignment.flags.ignore_links = True
	assignment.cancel()
	frappe.msgprint(_("The salary revision {0} was cancelled.").format(name), alert=True)


def sync_employee_salary(doc, method=None):
	"""Salary Structure Assignment on_submit / on_cancel: the Employee master
	shows the salary payroll is using now."""
	current = get_current_assignment(doc.employee)
	frappe.db.set_value(
		"Employee",
		doc.employee,
		{
			"custom_current_gross_salary": current.base if current else 0,
			"custom_current_salary_from": current.from_date if current else None,
		},
	)


def _amount(value):
	return frappe.format(flt(value), {"fieldtype": "Currency"})


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
