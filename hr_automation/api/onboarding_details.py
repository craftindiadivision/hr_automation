import frappe
from frappe import _
from frappe.utils import get_url, random_string

ONBOARDING_FIELDS = [
	"current_address",
	"permanent_address",
	"custom_aadhaar_number",
	"pan_number",
	"date_of_birth",
	"personal_email",
	"cell_number",
	"person_to_be_contacted",
	"emergency_phone_number",
	"relation",
	"provident_fund_account",
	"marital_status",
	"blood_group",
	"health_details",
	"health_insurance_provider",
	"health_insurance_no",
	"passport_number",
	"valid_upto",
	"date_of_issue",
	"place_of_issue",
]


def send_onboarding_details_email(employee_name):
	doc = frappe.get_doc("Employee", employee_name)
	email = doc.prefered_email or doc.personal_email or doc.company_email
	if not email:
		frappe.log_error(
			title="Onboarding details email skipped",
			message=f"No email found for Employee {doc.name}",
		)
		return

	token = doc.get("custom_onboarding_details_token")
	if not token:
		token = random_string(32)
		doc.db_set("custom_onboarding_details_token", token, update_modified=False)
	details_link = f"{get_url()}/onboarding-details?token={token}"

	upload_token = doc.get("custom_document_upload_token")
	if not upload_token:
		upload_token = random_string(32)
		doc.db_set("custom_document_upload_token", upload_token, update_modified=False)
	upload_link = f"{get_url()}/document-upload?token={upload_token}"

	message = frappe.render_template(
		"""
		<p>Dear {{ employee_name }},</p>
		<p>Congratulations again on joining us! Please complete your onboarding details using the
			link below so we can set up your employee records correctly.</p>
		<p><a href="{{ details_link }}">{{ details_link }}</a></p>
		<p>Please also upload your joining documents using the link below:</p>
		<p><a href="{{ upload_link }}">{{ upload_link }}</a></p>
		""",
		{"employee_name": doc.employee_name, "details_link": details_link, "upload_link": upload_link},
	)

	frappe.sendmail(
		recipients=[email],
		subject=_("Complete Your Onboarding Details"),
		message=message,
		reference_doctype="Employee",
		reference_name=doc.name,
	)


@frappe.whitelist(allow_guest=True)
def get_onboarding_form_data(token: str):
	name = frappe.db.get_value("Employee", {"custom_onboarding_details_token": token}, "name")
	if not name:
		frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)

	doc = frappe.get_doc("Employee", name)
	if doc.custom_onboarding_details_submitted:
		return {"submitted": True}

	return {
		"submitted": False,
		"employee_name": doc.employee_name,
		"values": {f: doc.get(f) for f in ONBOARDING_FIELDS},
	}


@frappe.whitelist(allow_guest=True)
def submit_onboarding_details(token: str, **kwargs):
	name = frappe.db.get_value("Employee", {"custom_onboarding_details_token": token}, "name")
	if not name:
		frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)

	frappe.set_user("Administrator")
	doc = frappe.get_doc("Employee", name)
	if doc.custom_onboarding_details_submitted:
		return {"message": "already_submitted"}

	for fieldname in ONBOARDING_FIELDS:
		if fieldname in kwargs and kwargs[fieldname]:
			doc.set(fieldname, kwargs[fieldname])

	family_parts = []
	if kwargs.get("father_name"):
		family_parts.append(f"Father's Name: {kwargs['father_name']}")
	if kwargs.get("mother_name"):
		family_parts.append(f"Mother's Name: {kwargs['mother_name']}")
	if kwargs.get("mother_occupation"):
		family_parts.append(f"Mother's Occupation: {kwargs['mother_occupation']}")
	if kwargs.get("spouse_name"):
		family_parts.append(f"Spouse: {kwargs['spouse_name']}")
	if family_parts:
		doc.family_background = "\n".join(family_parts)

	doc.custom_onboarding_details_submitted = 1
	doc.save(ignore_permissions=True)
	return {"message": "submitted"}
