import frappe


def execute():
	if frappe.db.exists("Custom Field", "Appointment Letter-custom_ob_mother_occupation"):
		frappe.delete_doc("Custom Field", "Appointment Letter-custom_ob_mother_occupation", ignore_permissions=True)
