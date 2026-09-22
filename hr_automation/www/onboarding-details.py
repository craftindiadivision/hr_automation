import frappe

no_cache = 1


def get_context(context):
	token = frappe.form_dict.get("token")
	context.token = token
	context.valid = False
	context.submitted = False
	context.employee_name = None
	context.values = {}

	if not token:
		return

	name = frappe.db.get_value("Employee", {"custom_onboarding_details_token": token}, "name")
	if not name:
		return

	doc = frappe.get_doc("Employee", name)
	context.valid = True
	context.employee_name = doc.employee_name
	context.submitted = bool(doc.custom_onboarding_details_submitted)
	context.values = doc.as_dict()
