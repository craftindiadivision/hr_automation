import frappe


def boot_session(bootinfo):
	bootinfo.employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
