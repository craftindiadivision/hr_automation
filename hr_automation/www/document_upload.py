import frappe

no_cache = 1


def get_context(context):
	"""Only ever resolves whether the token itself exists and hasn't expired -
	no real data (not even the target reference) is revealed here. The actual
	content only loads client-side, after the visitor confirms the email the
	link was sent to, via get_upload_target."""
	token = frappe.form_dict.get("token")
	context.token = token
	context.invalid = True
	context.expired = False

	if token:
		from hr_automation.api.link_expiry import is_expired
		from hr_automation.api.recruitment_automation import _resolve_upload_target

		row = _resolve_upload_target(token)
		if row:
			context.invalid = False
			if not row.custom_documents_submitted:
				context.expired = is_expired(row.custom_document_upload_token_sent_at)
