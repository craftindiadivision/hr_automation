import frappe


def sync_relieving_date_to_employee(doc, method=None):
	if not doc.relieving_date or not doc.employee:
		return

	employee_relieving_date = frappe.db.get_value("Employee", doc.employee, "relieving_date")
	if not employee_relieving_date:
		frappe.db.set_value("Employee", doc.employee, "relieving_date", doc.relieving_date)
