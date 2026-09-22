import frappe


@frappe.whitelist()
def get_entries():
	return frappe.get_list(
		"Knowledge Hub",
		fields=["name", "title", "description"],
		order_by="title asc",
	)
