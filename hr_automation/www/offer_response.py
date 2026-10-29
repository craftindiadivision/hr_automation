import frappe

no_cache = 1


def get_context(context):
	"""Only ever resolves whether the token itself exists and hasn't expired -
	no applicant data is revealed here. Accepting/declining only happens
	client-side, after the visitor confirms the email the offer was sent to,
	via respond_to_offer."""
	token = frappe.form_dict.get("token")
	response = frappe.form_dict.get("response")
	context.token = token
	context.response = response if response in ("Accepted", "Rejected") else None
	context.invalid = True
	context.expired = False

	if not token or not context.response:
		return

	row = frappe.db.get_value(
		"Job Offer",
		{"custom_response_token": token},
		["status", "custom_response_token_sent_at"],
		as_dict=True,
	)
	if not row:
		return

	from hr_automation.api.link_expiry import is_expired

	context.invalid = False
	if row.status == "Awaiting Response":
		context.expired = is_expired(row.custom_response_token_sent_at)
