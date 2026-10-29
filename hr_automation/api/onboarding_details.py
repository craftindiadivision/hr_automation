import frappe
from frappe import _
from frappe.utils import get_url

from hr_automation.api.link_expiry import check_email_matches, check_not_expired, stamp_sent_now
from hr_automation.api.recruitment_automation import _get_or_create_token

ONBOARDING_FIELDS = [
	"current_address",
	"permanent_address",
	"custom_aadhaar_number",
	"pan_number",
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
	"family_background",
]


# Asked on the web form (and the Offline Appointment Letter tab) but stored
# together in the Job Applicant's Family Background.
FAMILY_FIELDS = {
	"father_name": "Father's Name",
	"mother_name": "Mother's Name",
	"spouse_name": "Spouse",
}
# The Offline Appointment Letter's Onboarding Details tab: custom_ob_<field>.
LETTER_FIELD_PREFIX = "custom_ob_"


def apply_onboarding_details(applicant, values):
	"""Saves onboarding answers onto the Job Applicant - shared by the emailed
	web form (Online) and the Appointment Letter's Onboarding Details tab (Offline)."""
	for fieldname in ONBOARDING_FIELDS:
		if values.get(fieldname):
			applicant.set(fieldname, values[fieldname])

	family_parts = [f"{label}: {values[key]}" for key, label in FAMILY_FIELDS.items() if values.get(key)]
	if family_parts:
		applicant.family_background = "\n".join(family_parts)

	applicant.custom_onboarding_details_submitted = 1
	applicant.save(ignore_permissions=True)


def apply_letter_onboarding_details(letter):
	"""Offline Appointment Letter: the Onboarding Details tab replaces the
	emailed form, so its required answers must be filled before the letter is
	issued; they're then saved onto the Job Applicant."""
	missing = [
		df.label
		for df in letter.meta.fields
		if df.fieldname.startswith(LETTER_FIELD_PREFIX) and df.mandatory_depends_on and not letter.get(df.fieldname)
	]
	if missing:
		frappe.throw(
			_("Fill these in the Onboarding Details tab before issuing the letter: {0}").format(", ".join(missing)),
			title=_("Onboarding Details Missing"),
		)
	values = {
		key: letter.get(LETTER_FIELD_PREFIX + key) for key in [*ONBOARDING_FIELDS, *FAMILY_FIELDS]
	}
	apply_onboarding_details(frappe.get_doc("Job Applicant", letter.job_applicant), values)


@frappe.whitelist()
def get_applicant_onboarding_details(job_applicant: str) -> dict:
	"""Pre-fills an Offline Appointment Letter's Onboarding Details tab from
	whatever the Job Applicant already has, including the family names that
	live inside Family Background."""
	frappe.has_permission("Job Applicant", "read", job_applicant, throw=True)
	applicant = frappe.get_doc("Job Applicant", job_applicant)
	values = {fieldname: applicant.get(fieldname) for fieldname in ONBOARDING_FIELDS}
	labels = {label: key for key, label in FAMILY_FIELDS.items()}
	for line in (applicant.family_background or "").splitlines():
		label, _sep, value = line.partition(": ")
		if label in labels and value:
			values[labels[label]] = value
	values.pop("family_background", None)
	return values


def get_onboarding_details_link_if_pending(job_applicant):
	applicant = frappe.get_doc("Job Applicant", job_applicant)
	if applicant.custom_onboarding_details_submitted:
		return None
	token = _get_or_create_token(applicant, "custom_onboarding_details_token")
	stamp_sent_now(applicant, "custom_onboarding_details_token_sent_at", "custom_onboarding_reminder_sent")
	return f"{get_url()}/onboarding-details?token={token}"


@frappe.whitelist()
def resend_onboarding_details_link(appointment_letter):
	"""Emails the applicant the onboarding-details form. For an Online letter
	this is the first step - submitting it emails them the letter itself
	(_send_letter_after_details_submitted). Also resends an expired link."""
	from hr_automation.api.recruitment_automation import VERIFY_ROLES

	frappe.only_for(VERIFY_ROLES)

	letter = frappe.get_doc("Appointment Letter", appointment_letter)
	if letter.custom_mode != "Online":
		frappe.throw(_("The onboarding details link is only emailed for Online Appointment Letters"))
	# Submitting the form accepts the appointment and creates the Employee
	# automatically, so make sure nothing it needs is missing now.
	from hr_automation.api.recruitment_automation import check_letter_ready

	check_letter_ready(letter)

	applicant = frappe.get_doc("Job Applicant", letter.job_applicant)
	if applicant.custom_onboarding_details_submitted:
		frappe.throw(_("Onboarding details have already been submitted"))

	email = applicant.email_id
	if not email:
		frappe.throw(_("No email found for Job Applicant {0}").format(applicant.name))

	link = get_onboarding_details_link_if_pending(applicant.name)

	message = frappe.render_template(
		"""
		<p>Dear {{ applicant_name }},</p>
		<p>Please complete your onboarding details using the link below. Your appointment letter
			will be emailed to you as soon as you submit them.</p>
		<p><a href="{{ details_link }}">{{ details_link }}</a></p>
		""",
		{"applicant_name": applicant.applicant_name, "details_link": link},
	)
	frappe.sendmail(
		recipients=[email],
		subject=_("Complete Your Onboarding Details"),
		message=message,
		reference_doctype="Appointment Letter",
		reference_name=letter.name,
	)
	frappe.msgprint(_("Onboarding details link sent to {0}").format(email), alert=True)


def _send_letter_after_details_submitted(applicant):
	"""Online letters wait for these details - so once they're in, email the
	Appointment Letter (accepting it and creating the Employee) right away. If that
	fails (e.g. the PDF can't be generated), the applicant's details stay saved
	and HR is told to send the letter manually instead."""
	from hr_automation.api.recruitment_automation import send_appointment_letter_email

	letter = frappe.db.get_value(
		"Appointment Letter",
		{"job_applicant": applicant.name},
		["name", "custom_mode", "custom_letter_sent_on"],
		as_dict=True,
	)
	if not letter or letter.custom_mode != "Online" or letter.custom_letter_sent_on:
		return

	frappe.db.savepoint("send_appointment_letter")
	try:
		result = send_appointment_letter_email(letter.name)
	except Exception:
		frappe.db.rollback(save_point="send_appointment_letter")
		frappe.log_error(title=f"Appointment Letter {letter.name} not sent automatically")
		_notify_hr(
			letter.name,
			_(
				"{0} submitted their onboarding details, but the Appointment Letter couldn't be sent "
				"automatically. Open it and click Send Appointment Letter."
			).format(applicant.applicant_name),
		)
		return

	_notify_hr(
		letter.name,
		_("{0} submitted their onboarding details and accepted the appointment. Appointment Letter emailed and Employee {1} created.").format(
			applicant.applicant_name, result.get("employee")
		),
	)


def _notify_hr(appointment_letter, subject):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
	from frappe.utils.user import get_users_with_role

	users = [u for u in get_users_with_role("HR Manager") if u != "Administrator"]
	if not users:
		return
	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"document_type": "Appointment Letter",
			"document_name": appointment_letter,
			"subject": subject,
			"from_user": "Administrator",
		},
	)


def _get_applicant_by_token(token: str, email: str):
	name = frappe.db.get_value("Job Applicant", {"custom_onboarding_details_token": token}, "name")
	if not name:
		frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)
	applicant = frappe.get_doc("Job Applicant", name)
	check_email_matches(applicant.email_id, email)
	return applicant


@frappe.whitelist(allow_guest=True)
def get_onboarding_form_data(token: str, email: str):
	applicant = _get_applicant_by_token(token, email)
	if applicant.custom_onboarding_details_submitted:
		return {"submitted": True, "applicant_name": applicant.applicant_name}
	check_not_expired(applicant.custom_onboarding_details_token_sent_at)

	return {
		"submitted": False,
		"applicant_name": applicant.applicant_name,
		"values": {f: applicant.get(f) for f in ONBOARDING_FIELDS},
	}


@frappe.whitelist(allow_guest=True)
def submit_onboarding_details(token: str, email: str, **kwargs):
	frappe.set_user("Administrator")
	applicant = _get_applicant_by_token(token, email)
	if applicant.custom_onboarding_details_submitted:
		return {"message": "already_submitted"}
	check_not_expired(applicant.custom_onboarding_details_token_sent_at)

	apply_onboarding_details(applicant, kwargs)
	_send_letter_after_details_submitted(applicant)

	return {"message": "submitted"}
