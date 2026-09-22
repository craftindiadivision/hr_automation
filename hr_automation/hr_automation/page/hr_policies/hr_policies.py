import frappe


@frappe.whitelist()
def get_policies():
	"""Every HR Policy the current user is allowed to see (the doctype's own
	permission rules already restrict plain employees to published policies)."""
	return frappe.get_list(
		"HR Policy",
		fields=["name", "policy_title", "effective_date"],
		order_by="policy_title asc",
	)
