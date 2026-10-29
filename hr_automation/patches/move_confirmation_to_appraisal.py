import frappe


def execute():
	"""Confirmation Date / Revised Salary now live on the Appraisal (custom_confirmation_date,
	custom_proposed_revised_salary); drop the unused Appointment Letter fields."""
	for name in ['Appointment Letter-confirmation_date', 'Appointment Letter-revised_salary']:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
