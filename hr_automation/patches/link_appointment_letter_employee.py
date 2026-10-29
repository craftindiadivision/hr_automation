import frappe


def execute():
	"""Appointment Letters now link their Employee directly (no Employee Onboarding)."""
	if not frappe.db.has_column("Appointment Letter", "custom_employee"):
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("hr_automation")
	for letter in frappe.get_all("Appointment Letter", fields=["name", "job_applicant"]):
		employee = frappe.db.get_value("Employee", {"job_applicant": letter.job_applicant}, "name")
		if employee:
			frappe.db.set_value("Appointment Letter", letter.name, "custom_employee", employee, update_modified=False)
