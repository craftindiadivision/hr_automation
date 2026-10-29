import frappe
from frappe import _
from frappe.utils import add_months, add_to_date, format_time, get_link_to_form, get_url, now_datetime, random_string, today

from hr_automation.api.link_expiry import check_email_matches, check_not_expired, stamp_sent_now

VERIFY_ROLES = ["HR Manager", "HR User", "System Manager"]


FINAL_ROUND_INTERVIEW_TYPE = "Final Round"
DOCUMENTS_ACCEPTED = "Documents Accepted"
DOCUMENTS_REJECTED = "Documents Rejected"

DEFAULT_APPOINTMENT_LETTER_TEMPLATE = "Direct Appointment"
TRAINEE_APPOINTMENT_LETTER_TEMPLATE = "Intern to Employee under Probation"

# Keyed by Appointment Letter Template name, so the letter's own template
# decides which print format matches it - not hardcoded to one template.
APPOINTMENT_LETTER_PRINT_FORMATS = {
	DEFAULT_APPOINTMENT_LETTER_TEMPLATE: "Appointment Letter",
	TRAINEE_APPOINTMENT_LETTER_TEMPLATE: "Appointment Letter Intern to Employee Under Probation",
}


def _get_or_create_token(doc, fieldname):
	token = doc.get(fieldname)
	if not token:
		token = random_string(32)
		doc.db_set(fieldname, token, update_modified=False)
	return token


def get_job_offer_print_format(doc) -> str:
	return "Intern Offer Letter" if doc.get("custom_employee_type") == "Trainee" else "Employee Offer Letter"


def get_appointment_letter_print_format(doc) -> str:
	return APPOINTMENT_LETTER_PRINT_FORMATS.get(doc.appointment_letter_template, "Appointment Letter")


@frappe.whitelist()
def send_job_offer_email(job_offer):
	doc = frappe.get_doc("Job Offer", job_offer)
	if not doc.applicant_email:
		frappe.throw(_("Applicant Email is not set on this Job Offer"))

	token = _get_or_create_token(doc, "custom_response_token")
	stamp_sent_now(doc, "custom_response_token_sent_at", "custom_response_reminder_sent")
	base_url = get_url()
	accept_url = f"{base_url}/offer-response?token={token}&response=Accepted"
	reject_url = f"{base_url}/offer-response?token={token}&response=Rejected"

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
def respond_to_offer(token: str, response: str, email: str):
	"""Called via POST from the /offer-response page, only after the visitor has
	confirmed the email the offer was sent to - the email link itself only ever
	carries the token, never the address, so a copy of the link alone isn't
	enough to act on it."""
	if response not in ("Accepted", "Rejected"):
		frappe.throw(_("Invalid response"))

	job_offer = frappe.db.get_value("Job Offer", {"custom_response_token": token}, "name")
	if not job_offer:
		frappe.throw(_("This link is invalid or has expired."), frappe.DoesNotExistError)

	doc = frappe.get_doc("Job Offer", job_offer)
	check_email_matches(doc.applicant_email, email)

	if doc.status != "Awaiting Response":
		return {"status": "already_responded", "response": doc.status}

	check_not_expired(doc.custom_response_token_sent_at)

	# The token (plus the matching email) is the proof of authorization here;
	# elevate so the status change (and the stock HRMS Job Applicant sync it
	# triggers) can write.
	frappe.set_user("Administrator")
	doc.db_set("status", response)
	doc.add_comment("Info", _("Applicant responded to the offer: {0}").format(response))

	return {"status": "recorded", "response": response}


@frappe.whitelist()
def send_onboarding_documents_link(job_offer):
	frappe.only_for(VERIFY_ROLES)

	doc = frappe.get_doc("Job Offer", job_offer)
	if doc.status != "Accepted":
		frappe.throw(_("The document link can only be sent once the offer is Accepted"))
	if not doc.applicant_email:
		frappe.throw(_("Applicant Email is not set on this Job Offer"))

	rejected = doc.custom_document_status == DOCUMENTS_REJECTED
	if rejected:
		# Reopen the upload page (it shows "Already Submitted" once used).
		doc.db_set("custom_documents_submitted", 0, update_modified=False)

	token = _get_or_create_token(doc, "custom_document_upload_token")
	stamp_sent_now(doc, "custom_document_upload_token_sent_at", "custom_upload_reminder_sent")
	upload_link = f"{get_url()}/document-upload?token={token}"

	message = frappe.render_template(
		"""
		<p>Dear {{ applicant_name }},</p>
		{% if rejected %}
		<p>Some of your joining documents need to be uploaded again{% if reason %}:</p>
		<p><i>{{ reason }}</i></p>
		<p>Please upload them{% endif %} using the link below:</p>
		{% else %}
		<p>Thank you for accepting the offer. Please upload your joining documents using the link below:</p>
		{% endif %}
		<p><a href="{{ upload_link }}">{{ upload_link }}</a></p>
		""",
		{
			"applicant_name": doc.applicant_name,
			"upload_link": upload_link,
			"rejected": rejected,
			"reason": doc.custom_document_rejection_reason,
		},
	)
	frappe.sendmail(
		recipients=[doc.applicant_email],
		subject=_("Upload Your Joining Documents - {0}").format(doc.company),
		message=message,
		reference_doctype="Job Offer",
		reference_name=doc.name,
	)

	frappe.msgprint(_("Document upload link sent to {0}").format(doc.applicant_email), alert=True)


def _resolve_upload_target(token: str):
	return frappe.db.get_value(
		"Job Offer",
		{"custom_document_upload_token": token, "status": "Accepted"},
		[
			"name",
			"custom_document_upload_token_sent_at",
			"applicant_email",
			"custom_documents_submitted",
		],
		as_dict=True,
	)


@frappe.whitelist(allow_guest=True)
def get_upload_target(token: str, email: str):
	row = _resolve_upload_target(token)
	if not row:
		frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)
	check_email_matches(row.applicant_email, email)
	if row.custom_documents_submitted:
		return {"doctype": "Job Offer", "name": row.name, "already_submitted": True}
	check_not_expired(row.custom_document_upload_token_sent_at)
	return {"doctype": "Job Offer", "name": row.name, "already_submitted": False}


@frappe.whitelist(allow_guest=True)
def upload_document_via_token():
	token = frappe.form_dict.get("token")
	email = frappe.form_dict.get("email")
	if not token:
		frappe.throw(_("Missing token"))

	target = get_upload_target(token, email)
	if target["already_submitted"]:
		frappe.throw(_("Documents have already been submitted for this link."))

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
	document_name = label or filedata.filename
	_add_onboarding_document_row("Job Offer", target["name"], document_name, file_doc.file_url)
	job_applicant = frappe.db.get_value("Job Offer", target["name"], "job_applicant")
	_add_onboarding_document_row("Job Applicant", job_applicant, document_name, file_doc.file_url)

	_notify_hr_of_document_upload(target["name"])

	return {"file_url": file_doc.file_url}


@frappe.whitelist(allow_guest=True)
def mark_documents_submitted(token: str, email: str):
	"""Called once by the browser after every selected file has uploaded
	successfully - not per-file, since several files upload in parallel and
	flagging it mid-batch would reject the others still in flight. Once set,
	the link shows "Already Submitted" instead of the upload form."""
	target = get_upload_target(token, email)
	if not target["already_submitted"]:
		# A fresh upload (e.g. after a rejection) needs HR to verify it again.
		frappe.db.set_value(
			"Job Offer", target["name"], {"custom_documents_submitted": 1, "custom_document_status": None}
		)
	return {"already_submitted": True}


def _add_onboarding_document_row(parenttype: str, parent: str, document_name: str, file_url: str):
	row_count = frappe.db.count(
		"Job Offer Document", {"parent": parent, "parentfield": "custom_onboarding_documents"}
	)
	row = frappe.get_doc(
		{
			"doctype": "Job Offer Document",
			"name": frappe.generate_hash(length=10),
			"parent": parent,
			"parenttype": parenttype,
			"parentfield": "custom_onboarding_documents",
			"idx": row_count + 1,
			"document_name": document_name,
			"file": file_url,
			"uploaded_on": now_datetime(),
		}
	)
	row.db_insert()


def _notify_hr_of_document_upload(job_offer: str):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
	from frappe.utils.user import get_users_with_role

	users = set()
	for role in ("HR Manager", "HR User"):
		users.update(get_users_with_role(role))
	users.discard("Administrator")
	if not users:
		return

	applicant_name = frappe.db.get_value("Job Offer", job_offer, "applicant_name")
	notification_doc = {
		"type": "Alert",
		"document_type": "Job Offer",
		"document_name": job_offer,
		"subject": _("{0} has uploaded their joining documents - please review.").format(applicant_name),
		"from_user": "Administrator",
	}
	enqueue_create_notification(list(users), notification_doc)


def _has_uploaded_documents(job_offer: str) -> bool:
	return bool(
		frappe.db.exists("File", {"attached_to_doctype": "Job Offer", "attached_to_name": job_offer})
	)


def send_selection_email(doc, method=None):
	"""Job Applicant on_update: when the applicant becomes Accepted (e.g. via
	"Mark as Accepted" after a cleared Final Round), tells them they've cleared
	the interviews, that the selection is subject to verification, and that the
	offer will follow shortly. Sent once, on the change to Accepted."""
	if doc.status != "Accepted" or not doc.has_value_changed("status") or not doc.email_id:
		return

	company = (
		frappe.db.get_value("Job Opening", doc.job_title, "company") if doc.job_title else None
	) or frappe.defaults.get_global_default("company")
	position = doc.designation or (
		frappe.db.get_value("Job Opening", doc.job_title, "job_title") if doc.job_title else None
	)
	frappe.sendmail(
		recipients=[doc.email_id],
		subject=_("Interview Outcome - {0}").format(company) if company else _("Interview Outcome"),
		message=frappe.render_template(
			_SELECTION_MESSAGE,
			{"applicant_name": doc.applicant_name, "position": position, "company": company},
		),
		reference_doctype="Job Applicant",
		reference_name=doc.name,
	)


_SELECTION_MESSAGE = """
<p>Dear {{ applicant_name }},</p>
<p>Thank you for the time and effort you invested throughout our interview process{% if position %} for
	the position of <b>{{ position }}</b>{% endif %}. We are pleased to inform you that you have
	<b>successfully cleared all rounds of the interview</b>.</p>
<p>Please note that your selection is subject to the verification of your documents and the details
	you have shared with us. Our HR team will share your formal job offer with you shortly, along with
	the next steps.</p>
<p>Should you have any questions in the meantime, please feel free to reply to this email.</p>
<p>Congratulations once again. We look forward to the possibility of you joining
	{% if company %}<b>{{ company }}</b>{% else %}our team{% endif %}.</p>
<p>Warm regards,<br>
	Human Resources{% if company %}<br>{{ company }}{% endif %}</p>
"""


def send_interview_scheduled_emails(doc, method=None):
	"""Interview after_insert: tells each interviewer (with a link to the
	Interview) and the applicant which interview is scheduled, and when."""
	details = {
		"interview_type": doc.interview_type or _("Interview"),
		"date": frappe.format(doc.scheduled_on, "Date"),
		"from_time": format_time(doc.from_time, "hh:mm a"),
		"to_time": format_time(doc.to_time, "hh:mm a"),
	}
	applicant = frappe.db.get_value(
		"Job Applicant", doc.job_applicant, ["applicant_name", "email_id"], as_dict=True
	)
	subject = _("{0} scheduled on {1} at {2}").format(details["interview_type"], details["date"], details["from_time"])

	interviewers = [row.interviewer for row in doc.interview_details if row.interviewer]
	if interviewers:
		frappe.sendmail(
			recipients=interviewers,
			subject=subject,
			message=frappe.render_template(
				_INTERVIEWER_SCHEDULED_MESSAGE,
				{**details, "applicant_name": applicant.applicant_name, "link": get_url(doc.get_url())},
			),
			reference_doctype="Interview",
			reference_name=doc.name,
		)

	if applicant.email_id:
		frappe.sendmail(
			recipients=[applicant.email_id],
			subject=subject,
			message=frappe.render_template(
				_APPLICANT_SCHEDULED_MESSAGE, {**details, "applicant_name": applicant.applicant_name}
			),
			reference_doctype="Interview",
			reference_name=doc.name,
		)


_INTERVIEWER_SCHEDULED_MESSAGE = """
<p>Hello,</p>
<p>The <b>{{ interview_type }}</b> with <b>{{ applicant_name }}</b> has been scheduled for you on
	<b>{{ date }}</b> from <b>{{ from_time }}</b> to <b>{{ to_time }}</b>.</p>
<p>Interview: <a href="{{ link }}">{{ link }}</a></p>
<p>HR Team</p>
"""

_APPLICANT_SCHEDULED_MESSAGE = """
<p>Dear {{ applicant_name }},</p>
<p>Your <b>{{ interview_type }}</b> is scheduled on <b>{{ date }}</b> from <b>{{ from_time }}</b>
	to <b>{{ to_time }}</b>.</p>
<p>All the best.</p>
<p>HR Team</p>
"""


def validate_final_round_gross_salary(doc, method=None):
	"""Interview before_submit: a Final Round can't be submitted as Cleared
	without the agreed Gross Salary. Not required earlier - the interview is
	scheduled before it happens, and feedback may mark it Cleared first."""
	if (
		doc.interview_type == FINAL_ROUND_INTERVIEW_TYPE
		and doc.status == "Cleared"
		and not doc.custom_gross_salary
	):
		frappe.throw(_("Enter the Gross Salary for the Final Round interview"), frappe.MandatoryError)


def update_interview_status_from_feedback(doc, method=None):
	"""Interview Feedback on_submit / on_cancel: updates the (not yet submitted)
	Interview's status from its feedback. update_modified=False so an Interview
	form that was open while the feedback came in can still be saved/submitted."""
	if frappe.db.get_value("Interview", doc.interview, "docstatus") != 0:
		return
	frappe.db.set_value(
		"Interview", doc.interview, "status", get_status_from_feedback(doc.interview), update_modified=False
	)


def set_interview_status_from_feedback(doc, method=None):
	"""Interview validate: a Pending / Under Review interview whose feedback is
	all in takes its result, so submitting it never fails on a stale status
	(e.g. feedback given before this automation existed, or a form not reloaded
	after the feedback dialog). A status HR set to Cleared/Rejected is kept."""
	if doc.is_new() or doc.status not in ("Pending", "Under Review"):
		return
	status = get_status_from_feedback(doc.name)
	if status in ("Cleared", "Rejected"):
		doc.status = status


def get_status_from_feedback(interview: str) -> str:
	"""Once every interviewer on the interview has given a result: Rejected if
	any of them rejected, else Cleared. Until then, Under Review. With one
	interviewer the status simply follows their result."""
	results = frappe.get_all(
		"Interview Feedback",
		filters={"interview": interview, "docstatus": 1},
		fields=["interviewer", "result"],
	)
	interviewers = set(
		frappe.get_all(
			"Interview Detail", filters={"parent": interview, "parenttype": "Interview"}, pluck="interviewer"
		)
	)
	given = {row.interviewer for row in results if row.result}
	if not given or interviewers - given:
		return "Under Review"
	if any(row.result == "Rejected" for row in results):
		return "Rejected"
	return "Cleared"


def store_final_round_gross_salary(doc, method=None):
	"""Interview on_submit: a Cleared Final Round interview records the agreed
	Gross Salary on the Job Applicant, from where a new Job Offer picks it up
	(Job Offer.gross_salary fetches job_applicant.custom_gross_salary)."""
	if doc.interview_type != FINAL_ROUND_INTERVIEW_TYPE or doc.status != "Cleared":
		return
	frappe.db.set_value("Job Applicant", doc.job_applicant, "custom_gross_salary", doc.custom_gross_salary)


@frappe.whitelist()
def create_appointment_letter(job_offer):
	frappe.only_for(VERIFY_ROLES)

	doc = frappe.get_doc("Job Offer", job_offer)
	if doc.status != "Accepted":
		frappe.throw(_("The Appointment Letter can only be created for an Accepted offer"))
	if not _has_uploaded_documents(doc.name):
		frappe.throw(_("Upload at least one document before creating the Appointment Letter"))
	if doc.custom_document_status != DOCUMENTS_ACCEPTED:
		frappe.throw(_("Set Document Verification to Documents Accepted before creating the Appointment Letter"))

	letter = _get_or_create_appointment_letter(doc)
	return letter.name


def _get_or_create_appointment_letter(doc):
	if doc.get("custom_appointment_letter"):
		return frappe.get_doc("Appointment Letter", doc.custom_appointment_letter)

	existing = frappe.db.get_value("Appointment Letter", {"job_applicant": doc.job_applicant}, "name")
	if existing:
		doc.db_set("custom_appointment_letter", existing)
		return frappe.get_doc("Appointment Letter", existing)

	template = (
		TRAINEE_APPOINTMENT_LETTER_TEMPLATE
		if doc.get("custom_employee_type") == "Trainee"
		else DEFAULT_APPOINTMENT_LETTER_TEMPLATE
	)

	from hrms.hr.doctype.appointment_letter.appointment_letter import get_appointment_letter_details

	details = get_appointment_letter_details(template)
	intro = details[0]
	content = details[1]["description"]

	letter = frappe.new_doc("Appointment Letter")
	letter.job_applicant = doc.job_applicant
	letter.applicant_name = doc.applicant_name
	letter.company = doc.company
	letter.appointment_date = doc.offer_date
	# Next Phase lines up with the first scheduled appraisal (trainee: end of
	# training, employee: end of probation), which carries the next-phase salary.
	letter.custom_next_phase_duration = "3 Months" if doc.get("custom_employee_type") == "Trainee" else "6 Months"
	letter.custom_next_phase_date = add_months(doc.offer_date, int(letter.custom_next_phase_duration.split()[0]))
	letter.custom_job_offer = doc.name
	letter.appointment_letter_template = template
	letter.introduction = intro.get("introduction")
	letter.closing_notes = intro.get("closing_notes")
	letter.salary_structure = doc.salary_structure
	letter.gross_salary = doc.gross_salary
	letter.shift_type = doc.shift_type
	letter.custom_holiday_list = doc.get("custom_holiday_list") or frappe.get_cached_value(
		"Company", doc.company, "default_holiday_list"
	)
	letter.leave_policy = doc.leave_policy
	for row in content:
		letter.append("terms", {"title": row.get("title"), "description": row.get("description")})

	from hr_automation.api.salary_breakup import apply_salary_breakup

	apply_salary_breakup(letter, doc.gross_salary)
	# Mode (Online/Offline) is HR's choice on the letter itself; it's required
	# before the letter is saved again or sent/issued.
	letter.flags.ignore_mandatory = True
	letter.insert(ignore_permissions=True)

	doc.db_set("custom_appointment_letter", letter.name)
	return letter


def validate_appointment_status(doc, method=None):
	"""Appointment Letter validate: Accepted only once the letter has gone out
	(and, Online, the applicant has submitted their details); Rejected can't
	follow an already-created Employee."""
	if not doc.has_value_changed("custom_appointment_status"):
		return
	if doc.custom_appointment_status == "Accepted":
		if not doc.custom_letter_sent_on:
			frappe.throw(_("Send or issue the Appointment Letter before marking it Accepted"))
		if doc.custom_mode == "Online" and not frappe.db.get_value(
			"Job Applicant", doc.job_applicant, "custom_onboarding_details_submitted"
		):
			frappe.throw(
				_("Online letters are accepted when the applicant submits their onboarding details form")
			)
	elif doc.custom_appointment_status == "Rejected" and doc.custom_employee:
		frappe.throw(
			_("Employee {0} has already been created for this appointment.").format(
				get_link_to_form("Employee", doc.custom_employee)
			)
		)


def on_appointment_letter_update(doc, method=None):
	"""Appointment Letter on_update: HR marking an issued letter Accepted (the
	Offline route) creates the Employee."""
	if doc.custom_appointment_status == "Accepted" and doc.custom_letter_sent_on and not doc.custom_employee:
		from hr_automation.api.employee_onboarding import create_employee_from_appointment_letter

		employee = create_employee_from_appointment_letter(doc)
		frappe.msgprint(
			_("Employee {0} has been created.").format(get_link_to_form("Employee", employee)),
			alert=True,
			indicator="green",
		)


def check_letter_ready(letter):
	"""Before an Appointment Letter goes out: everything the Employee will need
	once it's accepted must already be there."""
	from hr_automation.api.employee_onboarding import check_ready_for_employee

	check_ready_for_employee(
		letter.job_applicant,
		letter.custom_holiday_list,
		letter.leave_policy,
		letter.appointment_date,
		salary_structure=letter.salary_structure,
		gross_salary=letter.gross_salary,
		shift_type=letter.shift_type,
		for_letter=True,
	)


@frappe.whitelist()
def send_appointment_letter_email(appointment_letter):
	"""Online: emails the letter - only once the applicant has submitted the
	onboarding-details form (sent first via resend_onboarding_details_link),
	which counts as their acceptance: Appointment Status becomes Accepted and
	the Employee is created. Offline: no email - the letter is handed over in
	person and HR fills the same onboarding details on the letter's Onboarding
	Details tab; the Employee is only created once HR sets Appointment Status
	to Accepted."""
	doc = frappe.get_doc("Appointment Letter", appointment_letter)
	if doc.custom_letter_sent_on:
		frappe.throw(_("This Appointment Letter has already been sent"))
	if not doc.custom_mode:
		frappe.throw(_("Select the Mode (Online or Offline) on the Appointment Letter first"))
	check_letter_ready(doc)
	if doc.custom_mode == "Offline":
		from hr_automation.api.onboarding_details import apply_letter_onboarding_details

		apply_letter_onboarding_details(doc)
		doc.db_set("custom_letter_sent_on", now_datetime(), update_modified=False)
		# The candidate accepts (or not) in person; HR records it via Appointment
		# Status, which creates the Employee (on_appointment_letter_update).
		return {"employee": None, "emailed": False}

	applicant = frappe.db.get_value(
		"Job Applicant", doc.job_applicant, ["email_id", "custom_onboarding_details_submitted"], as_dict=True
	)
	if not applicant.custom_onboarding_details_submitted:
		frappe.throw(
			_(
				"{0} hasn't submitted their onboarding details yet. Send them the onboarding details link "
				"first; the Appointment Letter can be sent once they've filled it in."
			).format(doc.applicant_name),
			title=_("Onboarding Details Pending"),
		)
	email = applicant.email_id
	if not email:
		frappe.throw(_("No email found for Job Applicant {0}").format(doc.job_applicant))

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
	doc.db_set("custom_letter_sent_on", now_datetime(), update_modified=False)
	# Online: submitting the onboarding-details form is the applicant's acceptance.
	doc.db_set("custom_appointment_status", "Accepted", update_modified=False)
	from hr_automation.api.employee_onboarding import create_employee_from_appointment_letter

	return {"employee": create_employee_from_appointment_letter(doc), "emailed": True}


def notify_next_phase_due():
	"""Daily job: notify HR Manager once an Appointment Letter's Next Phase date
	(set from Review After, relative to the Appointment Date) has arrived."""
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
	from frappe.utils.user import get_users_with_role

	letters = frappe.get_all(
		"Appointment Letter",
		filters={
			"custom_next_phase_date": today(),
			"custom_next_phase_notified": 0,
			"docstatus": ["!=", 2],
		},
		fields=["name", "applicant_name"],
	)
	if not letters:
		return

	users = [u for u in get_users_with_role("HR Manager") if u != "Administrator"]
	if not users:
		return

	for letter in letters:
		enqueue_create_notification(
			users,
			{
				"type": "Alert",
				"document_type": "Appointment Letter",
				"document_name": letter.name,
				"subject": _("{0}'s next phase review is due today.").format(letter.applicant_name),
				"from_user": "Administrator",
			},
		)
		frappe.db.set_value("Appointment Letter", letter.name, "custom_next_phase_notified", 1)


STALE_ACTION_THRESHOLD_HOURS = 12


def notify_stale_pending_actions():
	"""Hourly job: nudges HR about recruitment links sent but not yet acted on,
	once they've been pending for at least STALE_ACTION_THRESHOLD_HOURS (half of
	their 24-hour validity) - giving HR a real chance to follow up before the
	link expires. Each one nudges once; a resend resets this via stamp_sent_now,
	so a fresh link gets its own fresh reminder cycle."""
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
	from frappe.utils.user import get_users_with_role

	cutoff = add_to_date(now_datetime(), hours=-STALE_ACTION_THRESHOLD_HOURS)
	users = [u for u in get_users_with_role("HR Manager") if u != "Administrator"]
	if not users:
		return

	def notify(doctype, name, subject):
		enqueue_create_notification(
			users,
			{
				"type": "Alert",
				"document_type": doctype,
				"document_name": name,
				"subject": subject,
				"from_user": "Administrator",
			},
		)

	offers_awaiting_response = frappe.get_all(
		"Job Offer",
		filters={
			"status": "Awaiting Response",
			"custom_response_token_sent_at": ["<=", cutoff],
			"custom_response_reminder_sent": 0,
		},
		fields=["name", "applicant_name"],
	)
	for offer in offers_awaiting_response:
		notify(
			"Job Offer",
			offer.name,
			_("{0} hasn't responded to their offer yet - sent over {1} hours ago.").format(
				offer.applicant_name, STALE_ACTION_THRESHOLD_HOURS
			),
		)
		frappe.db.set_value("Job Offer", offer.name, "custom_response_reminder_sent", 1)

	offers_awaiting_documents = frappe.get_all(
		"Job Offer",
		filters={
			"status": "Accepted",
			"custom_document_upload_token_sent_at": ["<=", cutoff],
			"custom_documents_submitted": 0,
			"custom_upload_reminder_sent": 0,
		},
		fields=["name", "applicant_name"],
	)
	for offer in offers_awaiting_documents:
		notify(
			"Job Offer",
			offer.name,
			_("{0} hasn't uploaded their documents yet - link sent over {1} hours ago.").format(
				offer.applicant_name, STALE_ACTION_THRESHOLD_HOURS
			),
		)
		frappe.db.set_value("Job Offer", offer.name, "custom_upload_reminder_sent", 1)

	applicants_awaiting_onboarding_details = frappe.get_all(
		"Job Applicant",
		filters={
			"custom_onboarding_details_token_sent_at": ["<=", cutoff],
			"custom_onboarding_details_submitted": 0,
			"custom_onboarding_reminder_sent": 0,
		},
		fields=["name", "applicant_name"],
	)
	for applicant in applicants_awaiting_onboarding_details:
		notify(
			"Job Applicant",
			applicant.name,
			_("{0} hasn't submitted their onboarding details yet - sent over {1} hours ago.").format(
				applicant.applicant_name, STALE_ACTION_THRESHOLD_HOURS
			),
		)
		frappe.db.set_value("Job Applicant", applicant.name, "custom_onboarding_reminder_sent", 1)
