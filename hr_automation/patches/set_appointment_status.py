import frappe


def execute():
	"""Letters that already have an Employee Onboarding were accepted."""
	if not frappe.db.has_column("Appointment Letter", "custom_appointment_status"):
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("hr_automation")
	for letter in frappe.get_all(
		"Employee Onboarding",
		filters={"custom_appointment_letter": ["is", "set"], "docstatus": ["!=", 2]},
		pluck="custom_appointment_letter",
	):
		frappe.db.set_value("Appointment Letter", letter, "custom_appointment_status", "Accepted", update_modified=False)
	frappe.db.sql(
		"""update `tabAppointment Letter` set custom_appointment_status = 'Pending'
		where ifnull(custom_appointment_status, '') = ''"""
	)
