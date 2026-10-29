import frappe
from frappe.utils import add_days, today


def execute():
	"""Confirmed leave now waits for the Employee's Confirmation Date (set by
	their probation appraisal). Employees whose probation was already over
	before that were confirmed - record it so their leave carries on."""
	for emp in frappe.get_all(
		"Employee",
		filters={
			"custom_probation_end_date": ["<", today()],
			"final_confirmation_date": ["is", "not set"],
		},
		fields=["name", "custom_probation_end_date"],
	):
		frappe.db.set_value(
			"Employee",
			emp.name,
			"final_confirmation_date",
			add_days(emp.custom_probation_end_date, 1),
			update_modified=False,
		)
