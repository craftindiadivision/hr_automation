import frappe

no_cache = 1


def get_context(context):
	"""Only ever resolves whether the token itself exists and hasn't expired -
	no applicant data (not even their name) is revealed here. The real content
	only loads client-side, after the visitor confirms the email the link was
	sent to, via get_onboarding_form_data."""
	token = frappe.form_dict.get("token")
	context.token = token
	context.invalid = True
	context.expired = False

	if not token:
		return

	name = frappe.db.get_value("Job Applicant", {"custom_onboarding_details_token": token}, "name")
	if not name:
		return

	from hr_automation.api.link_expiry import is_expired

	applicant = frappe.get_doc("Job Applicant", name)
	context.invalid = False
	if not applicant.custom_onboarding_details_submitted:
		context.expired = is_expired(applicant.custom_onboarding_details_token_sent_at)
