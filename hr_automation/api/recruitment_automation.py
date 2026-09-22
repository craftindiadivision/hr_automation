import frappe
from frappe import _
from frappe.utils import get_url, random_string


def _get_or_create_token(doc, fieldname):
	token = doc.get(fieldname)
	if not token:
		token = random_string(32)
		doc.db_set(fieldname, token, update_modified=False)
	return token


def get_job_offer_print_format(doc) -> str:
	return "Intern Offer Letter" if doc.get("custom_employee_type") == "Trainee" else "Employee Offer Letter"


@frappe.whitelist()
def send_job_offer_email(job_offer):
	doc = frappe.get_doc("Job Offer", job_offer)
	if not doc.applicant_email:
		frappe.throw(_("Applicant Email is not set on this Job Offer"))

	token = _get_or_create_token(doc, "custom_response_token")
	base_url = get_url()
	accept_url = (
		f"{base_url}/api/method/hr_automation.api.recruitment_automation."
		f"respond_to_offer?token={token}&response=Accepted"
	)
	reject_url = (
		f"{base_url}/api/method/hr_automation.api.recruitment_automation."
		f"respond_to_offer?token={token}&response=Rejected"
	)

	message = frappe.render_template(
		"""
		<p>Dear {{ applicant_name }},</p>
		<p>Please find attached your offer letter for {{ designation }} at {{ company }}.</p>
		<p>Please let us know your response:</p>
		<p>
			<a href="{{ accept_url }}" style="padding:8px 16px;background:#2e7d32;color:#fff;
				text-decoration:none;border-radius:4px;">Accept Offer</a>
			&nbsp;&nbsp;
			<a href="{{ reject_url }}" style="padding:8px 16px;background:#c62828;color:#fff;
				text-decoration:none;border-radius:4px;">Decline Offer</a>
		</p>
		""",
		{
			"applicant_name": doc.applicant_name,
			"designation": doc.designation,
			"company": doc.company,
			"accept_url": accept_url,
			"reject_url": reject_url,
		},
	)

	frappe.sendmail(
		recipients=[doc.applicant_email],
		subject=_("Job Offer - {0} at {1}").format(doc.designation, doc.company),
		message=message,
		attachments=[
			frappe.attach_print("Job Offer", doc.name, print_format=get_job_offer_print_format(doc))
		],
		reference_doctype="Job Offer",
		reference_name=doc.name,
	)
	frappe.msgprint(_("Offer email sent to {0}").format(doc.applicant_email), alert=True)


@frappe.whitelist(allow_guest=True)
def respond_to_offer(token: str, response: str):
	if response not in ("Accepted", "Rejected"):
		frappe.throw(_("Invalid response"))

	job_offer = frappe.db.get_value("Job Offer", {"custom_response_token": token}, "name")
	if not job_offer:
		frappe.respond_as_web_page(
			_("Invalid Link"), _("This link is invalid or has expired."), http_status_code=404
		)
		return

	doc = frappe.get_doc("Job Offer", job_offer)
	if doc.status in ("Accepted", "Rejected"):
		frappe.respond_as_web_page(
			_("Already Responded"),
			_("This offer has already been marked as {0}.").format(doc.status),
			http_status_code=200,
		)
		return

	# The token is the proof of authorization here; elevate briefly so the
	# status change (and the stock HRMS Job Applicant sync it triggers) can write.
	frappe.set_user("Administrator")
	doc.db_set("status", response)
	doc.add_comment("Info", _("Applicant responded to the offer: {0}").format(response))

	# db_set() only calls the doctype's own on_change method, not the
	# doc_events hooks below, so trigger this directly.
	create_employee_if_accepted(doc)

	frappe.respond_as_web_page(
		_("Thank You"),
		_("Your response ({0}) has been recorded.").format(response),
		http_status_code=200,
		success=(response == "Accepted"),
	)


def on_job_offer_status_change(doc, method=None):
	"""Auto-create the Employee once a Job Offer is Accepted (desk-based status edits).
	The Appointment Letter is deliberately NOT created here - see
	_create_appointment_letter_after_first_upload, which fires once the candidate
	has uploaded at least one document via their onboarding-details link."""
	if not doc.has_value_changed("status"):
		return
	create_employee_if_accepted(doc)


DEFAULT_APPOINTMENT_LETTER_TEMPLATE = "Direct Appointment"
TRAINEE_APPOINTMENT_LETTER_TEMPLATE = "Intern to Employee under Probation"

# Keyed by Appointment Letter Template name, so the letter's own template
# decides which print format matches it - not hardcoded to one template.
APPOINTMENT_LETTER_PRINT_FORMATS = {
	DEFAULT_APPOINTMENT_LETTER_TEMPLATE: "Appointment Letter",
	TRAINEE_APPOINTMENT_LETTER_TEMPLATE: "Appointment Letter Intern to Employee Under Probation",
}


def get_appointment_letter_print_format(doc) -> str:
	return APPOINTMENT_LETTER_PRINT_FORMATS.get(doc.appointment_letter_template, "Appointment Letter")


def create_appointment_letter_if_accepted(doc):
	if doc.status != "Accepted":
		return
	if doc.get("custom_appointment_letter"):
		return
	if frappe.db.exists("Appointment Letter", {"job_applicant": doc.job_applicant}):
		return

	template = (
		TRAINEE_APPOINTMENT_LETTER_TEMPLATE
		if doc.get("custom_employee_type") == "Trainee"
		else DEFAULT_APPOINTMENT_LETTER_TEMPLATE
	)

	try:
		from hrms.hr.doctype.appointment_letter.appointment_letter import get_appointment_letter_details

		details = get_appointment_letter_details(template)
		intro = details[0]
		content = details[1]["description"]

		letter = frappe.new_doc("Appointment Letter")
		letter.job_applicant = doc.job_applicant
		letter.applicant_name = doc.applicant_name
		letter.company = doc.company
		letter.appointment_date = doc.offer_date
		letter.custom_job_offer = doc.name
		letter.appointment_letter_template = template
		letter.introduction = intro.get("introduction")
		letter.closing_notes = intro.get("closing_notes")
		letter.gross_salary = doc.gross_salary
		for row in content:
			letter.append("terms", {"title": row.get("title"), "description": row.get("description")})

		from hr_automation.api.salary_breakup import apply_salary_breakup

		apply_salary_breakup(letter, doc.gross_salary)

		letter.insert(ignore_permissions=True)

		doc.db_set("custom_appointment_letter", letter.name)
	except Exception:
		# Don't let a letter-provisioning glitch block the applicant's response from
		# being recorded; HR can create the Appointment Letter manually if this fails.
		frappe.log_error(
			title="Auto-creation of Appointment Letter failed",
			message=frappe.get_traceback(),
		)


def create_employee_if_accepted(doc):
	if doc.status != "Accepted":
		return
	if frappe.db.exists("Employee", {"job_applicant": doc.job_applicant}):
		return

	applicant = frappe.db.get_value(
		"Job Applicant", doc.job_applicant, ["custom_date_of_birth", "custom_gender"], as_dict=True
	)
	if not applicant or not applicant.custom_date_of_birth or not applicant.custom_gender:
		frappe.log_error(
			title="Employee auto-creation skipped",
			message=(
				f"Job Offer {doc.name}: Job Applicant {doc.job_applicant} is missing Date of "
				"Birth and/or Gender, so the Employee master was not auto-created. Fill these in "
				"on the Job Applicant, then create the Employee manually from the Job Offer."
			),
		)
		return

	try:
		from hrms.hr.doctype.job_offer.job_offer import make_employee

		employee = make_employee(doc.name)

		date_of_joining = doc.offer_date
		if doc.get("custom_appointment_letter"):
			appointment_date = frappe.db.get_value(
				"Appointment Letter", doc.custom_appointment_letter, "appointment_date"
			)
			if appointment_date:
				date_of_joining = appointment_date

		employee.date_of_birth = applicant.custom_date_of_birth
		employee.gender = applicant.custom_gender
		employee.date_of_joining = date_of_joining
		employee.job_applicant = doc.job_applicant
		if doc.get("custom_employee_type") == "Trainee":
			employee.custom_is_trainee = 1
		elif doc.get("custom_employee_type") == "Employee":
			employee.custom_is_employee = 1
		employee.insert(ignore_permissions=True)

		from hr_automation.api.onboarding_details import send_onboarding_details_email

		send_onboarding_details_email(employee.name)
	except Exception:
		# Don't let an employee-provisioning glitch block the applicant's response from
		# being recorded; HR can create the Employee manually from the Job Offer if this fails.
		frappe.log_error(
			title="Auto-creation of Employee failed",
			message=frappe.get_traceback(),
		)


@frappe.whitelist()
def send_appointment_letter_email(appointment_letter):
	doc = frappe.get_doc("Appointment Letter", appointment_letter)
	email = frappe.db.get_value("Job Applicant", doc.job_applicant, "email_id")
	if not email:
		frappe.log_error(
			title="Appointment Letter email skipped",
			message=f"No email found for Job Applicant {doc.job_applicant} on {doc.name}",
		)
		return

	# No second upload link here - the candidate already uploaded documents via
	# their onboarding-details link, which is what triggered this letter's
	# creation in the first place. Asking again would be redundant.
	message = frappe.render_template(
		"""
		<p>Dear {{ applicant_name }},</p>
		<p>Congratulations! Please find your appointment letter attached.</p>
		""",
		{"applicant_name": doc.applicant_name},
	)

	frappe.sendmail(
		recipients=[email],
		subject=_("Appointment Letter - {0}").format(doc.company),
		message=message,
		attachments=[
			frappe.attach_print(
				"Appointment Letter", doc.name, print_format=get_appointment_letter_print_format(doc)
			)
		],
		reference_doctype="Appointment Letter",
		reference_name=doc.name,
	)


@frappe.whitelist(allow_guest=True)
def get_upload_target(token: str):
	# Document upload only ever happens against the Employee's own token now -
	# it's the one link sent (with the onboarding-details form), and it's what
	# triggers the Appointment Letter's creation. There's no separate
	# Appointment-Letter-token upload step to resolve anymore.
	name = frappe.db.get_value("Employee", {"custom_document_upload_token": token}, "name")
	if name:
		return {"doctype": "Employee", "name": name}
	frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)


@frappe.whitelist(allow_guest=True)
def upload_document_via_token():
	token = frappe.form_dict.get("token")
	if not token:
		frappe.throw(_("Missing token"))

	target = get_upload_target(token)

	if "file" not in frappe.request.files:
		frappe.throw(_("No file uploaded"))

	filedata = frappe.request.files["file"]
	label = frappe.form_dict.get("label")
	file_name = f"{label} - {filedata.filename}" if label else filedata.filename

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": target["doctype"],
			"attached_to_name": target["name"],
			"content": filedata.stream.read(),
			"is_private": 1,
		}
	)
	file_doc.insert(ignore_permissions=True)

	if target["doctype"] == "Employee":
		_notify_hr_of_document_upload(target["name"])

	return {"file_url": file_doc.file_url}


VERIFY_ROLES = ["HR Manager", "HR User", "System Manager"]


def _notify_hr_of_document_upload(employee: str):
	"""A document upload no longer auto-creates the Appointment Letter - HR is
	notified instead, reviews the documents, and creates it deliberately via
	the "Verify" button on the Employee form."""
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
	from frappe.utils.user import get_users_with_role

	users = set()
	for role in ("HR Manager", "HR User"):
		users.update(get_users_with_role(role))
	users.discard("Administrator")
	if not users:
		return

	employee_name = frappe.db.get_value("Employee", employee, "employee_name")
	notification_doc = {
		"type": "Alert",
		"document_type": "Employee",
		"document_name": employee,
		"subject": _("{0} has uploaded their onboarding documents - please verify.").format(employee_name),
		"from_user": "Administrator",
	}
	enqueue_create_notification(list(users), notification_doc)


def _create_appointment_letter_for_employee(employee: str):
	"""Safe to call more than once: create_appointment_letter_if_accepted is a
	no-op once the letter already exists, for whichever Job Offer belongs to
	this employee's Job Applicant."""
	job_applicant = frappe.db.get_value("Employee", employee, "job_applicant")
	if not job_applicant:
		return

	job_offer_name = frappe.db.get_value(
		"Job Offer", {"job_applicant": job_applicant, "status": "Accepted"}, "name"
	)
	if not job_offer_name:
		return

	create_appointment_letter_if_accepted(frappe.get_doc("Job Offer", job_offer_name))


@frappe.whitelist()
def verify_and_create_appointment_letter(employee: str):
	"""Called from the Employee form's "Verify" button, once HR has reviewed the
	uploaded documents. Creates the Appointment Letter (if it doesn't already
	exist) and returns its name so the browser can be sent straight there."""
	frappe.only_for(VERIFY_ROLES)

	_create_appointment_letter_for_employee(employee)

	job_applicant = frappe.db.get_value("Employee", employee, "job_applicant")
	letter_name = (
		frappe.db.get_value("Appointment Letter", {"job_applicant": job_applicant}, "name")
		if job_applicant
		else None
	)
	if not letter_name:
		frappe.throw(
			_(
				"Could not create the Appointment Letter for this employee - check that they have an "
				"Accepted Job Offer, and check the Error Log for details."
			)
		)
	return letter_name
