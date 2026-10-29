import frappe


def execute():
	"""Employee Promotion automation was reverted - drop its fields."""
	for name in ['Appraisal-custom_promote_to_designation', 'Appraisal-custom_employee_promotion', 'Employee Promotion-custom_appraisal', 'Employee Promotion-custom_revised_salary_structure', 'Employee Promotion-custom_salary_structure_assignment']:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
