import frappe

no_cache = 1


def get_context(context):
	context.token = frappe.form_dict.get("token")
