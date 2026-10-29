import frappe

from hr_automation.api.salary_revision import get_current_assignment


def execute():
	"""Fill the Employee master's Current Gross Salary / Current Salary From."""
	if not frappe.db.has_column("Employee", "custom_current_gross_salary"):
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("hr_automation")
	for employee in frappe.get_all("Employee", pluck="name"):
		current = get_current_assignment(employee)
		if current:
			frappe.db.set_value(
				"Employee",
				employee,
				{"custom_current_gross_salary": current.base, "custom_current_salary_from": current.from_date},
				update_modified=False,
			)
