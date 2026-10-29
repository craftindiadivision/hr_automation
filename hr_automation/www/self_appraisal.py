import frappe

no_cache = 1


def get_context(context):
	"""Only ever resolves whether the token itself exists and hasn't expired -
	no employee data (not even their name or ratings) is revealed here. The
	real content only loads client-side, after the visitor confirms the email
	the link was sent to, via get_self_appraisal_by_token."""
	token = frappe.form_dict.get("token")
	context.token = token
	context.invalid = True
	context.expired = False

	if not token:
		return

	row = frappe.db.get_value(
		"Appraisal",
		{"custom_self_appraisal_token": token},
		["custom_self_appraisal_submitted", "custom_self_appraisal_token_sent_at"],
		as_dict=True,
	)
	if not row:
		return

	from hr_automation.api.link_expiry import is_expired

	context.invalid = False
	if not row.custom_self_appraisal_submitted:
		context.expired = is_expired(row.custom_self_appraisal_token_sent_at)
