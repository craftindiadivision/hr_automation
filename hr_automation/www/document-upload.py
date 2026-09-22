import frappe

no_cache = 1


def get_context(context):
	token = frappe.form_dict.get("token")
	context.token = token
	context.valid = False
	context.target_name = None

	if token:
		from hr_automation.api.recruitment_automation import get_upload_target

		try:
			target = get_upload_target(token)
			context.valid = True
			context.target_name = target["name"]
		except Exception:
			context.valid = False
