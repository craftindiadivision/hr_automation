import frappe

no_cache = 1


def get_context(context):
	"""Only resolves whether the token exists and is still open - nothing about
	the employee is revealed until the visitor confirms the team lead's email."""
	token = frappe.form_dict.get("token")
	context.token = token
	context.invalid = True
	context.expired = False
	if not token:
		return
	name = frappe.db.get_value("Pre-Appraisal Feedback", {"token": token}, "name")
	if not name:
		return

	from hr_automation.api.performance_feedback import is_expired

	doc = frappe.get_doc("Pre-Appraisal Feedback", name)
	context.invalid = False
	if doc.status != "Submitted":
		context.expired = is_expired(doc)
