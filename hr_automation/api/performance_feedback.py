"""Team lead feedback ahead of each appraisal: a month before the appraisal is
due, a Pre-Appraisal Feedback is created and the employee's Reports To gets a
link to write what's going well and what to improve (free text - not the
appraisal template). The employee is emailed it straight away, giving them a
month to act on it before the appraisal."""

import frappe
from frappe import _
from frappe.utils import add_days, escape_html, formatdate, get_url, getdate, now_datetime, random_string, today

from hr_automation.api.link_expiry import check_email_matches

FEEDBACK_LEAD_MONTHS = 1
REQUEST_ROLES = ("HR Manager", "HR User", "System Manager")


def request_feedback(employee, stage, due_date):
	"""Called by the daily appraisal job a month before the appraisal."""
	doc = frappe.get_doc(
		{
			"doctype": "Pre-Appraisal Feedback",
			"employee": employee,
			"appraisal_stage": stage,
			"appraisal_due_date": getdate(due_date),
			"reviewer": frappe.db.get_value("Employee", employee, "reports_to"),
			"status": "Requested",
		}
	).insert(ignore_permissions=True)
	_send_request(doc)
	return doc.name


def send_pending_requests():
	"""Daily job: a Pre-Appraisal Feedback created while the employee had no
	Reports To (so nothing could be sent) is sent automatically as soon as
	Reports To is set, as long as the appraisal date hasn't passed."""
	for name in frappe.get_all(
		"Pre-Appraisal Feedback",
		filters={"status": "Requested", "requested_on": ["is", "not set"], "appraisal_due_date": [">=", today()]},
		pluck="name",
	):
		doc = frappe.get_doc("Pre-Appraisal Feedback", name)
		reports_to = frappe.db.get_value("Employee", doc.employee, "reports_to")
		if not reports_to:
			continue
		doc.reviewer = reports_to
		doc.save(ignore_permissions=True)
		_send_request(doc)


@frappe.whitelist()
def send_feedback_request(name: str):
	"""Resend Request button - e.g. once Reports To has been set. If the
	appraisal date has passed, the link stays open for another week."""
	frappe.only_for(REQUEST_ROLES)
	doc = frappe.get_doc("Pre-Appraisal Feedback", name)
	if doc.status == "Submitted":
		frappe.throw(_("Feedback has already been submitted"))
	doc.reviewer = frappe.db.get_value("Employee", doc.employee, "reports_to")
	if getdate(doc.appraisal_due_date) < getdate(today()):
		doc.appraisal_due_date = add_days(today(), 7)
	doc.save(ignore_permissions=True)
	if _send_request(doc):
		frappe.msgprint(_("Feedback request sent."), alert=True, indicator="green")


def _send_request(doc):
	reviewer = _get_reviewer(doc.reviewer)
	if not reviewer:
		_notify_hr(
			doc.name,
			_(
				"{0} has no Reports To, so nobody was asked for feedback before their appraisal. Set Reports To "
				"on the Employee, then use Resend Request on this Pre-Appraisal Feedback."
			).format(doc.employee_name),
		)
		return False
	if not reviewer.email:
		_notify_hr(
			doc.name,
			_("Feedback for {0} couldn't be requested: their team lead {1} has no email address.").format(
				doc.employee_name, reviewer.employee_name
			),
		)
		return False

	doc.db_set({"token": doc.token or random_string(32), "requested_on": now_datetime()}, update_modified=False)
	link = f"{get_url()}/performance-feedback?token={doc.token}"
	frappe.sendmail(
		recipients=[reviewer.email],
		subject=_("Feedback needed for {0} before their appraisal").format(doc.employee_name),
		message=frappe.render_template(
			"""
			<p>Dear {{ reviewer }},</p>
			<p><b>{{ employee }}</b>'s {{ stage }} appraisal is on <b>{{ due }}</b>. Please share your feedback
				on their work - what is going well and what they should improve. It will be sent to them
				straight away, so they have time to work on it before the appraisal.</p>
			<p><a href="{{ link }}">{{ link }}</a></p>
			<p>HR Team</p>
			""",
			{
				"reviewer": reviewer.employee_name,
				"employee": doc.employee_name,
				"stage": (doc.appraisal_stage or "").lower(),
				"due": formatdate(doc.appraisal_due_date),
				"link": link,
			},
		),
		reference_doctype="Pre-Appraisal Feedback",
		reference_name=doc.name,
	)
	return True


def _get_reviewer(reviewer):
	if not reviewer:
		return None
	row = frappe.db.get_value(
		"Employee",
		reviewer,
		["name", "employee_name", "user_id", "prefered_email", "company_email", "personal_email"],
		as_dict=True,
	)
	row.email = row.user_id or row.prefered_email or row.company_email or row.personal_email
	return row


def _resolve(token, email):
	name = frappe.db.get_value("Pre-Appraisal Feedback", {"token": token}, "name")
	if not name:
		frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)
	doc = frappe.get_doc("Pre-Appraisal Feedback", name)
	reviewer = _get_reviewer(doc.reviewer)
	check_email_matches(reviewer.email if reviewer else None, email)
	return doc, reviewer


def is_expired(doc):
	return bool(doc.appraisal_due_date) and getdate(today()) > getdate(doc.appraisal_due_date)


@frappe.whitelist(allow_guest=True)
def get_feedback_form(token: str, email: str):
	doc, reviewer = _resolve(token, email)
	if doc.status == "Submitted":
		return {"submitted": True, "employee_name": doc.employee_name}
	if is_expired(doc):
		frappe.throw(_("This link has expired. Please contact HR."))
	return {
		"submitted": False,
		"employee_name": doc.employee_name,
		"designation": frappe.db.get_value("Employee", doc.employee, "designation"),
		"stage": doc.appraisal_stage,
		"due": formatdate(doc.appraisal_due_date),
		"reviewer_name": reviewer.employee_name,
	}


@frappe.whitelist(allow_guest=True)
def submit_feedback(token: str, email: str, going_well: str, to_improve: str, other_comments: str = None):
	doc, reviewer = _resolve(token, email)
	if doc.status == "Submitted":
		return {"message": "already_submitted"}
	if is_expired(doc):
		frappe.throw(_("This link has expired. Please contact HR."))
	if not (going_well or "").strip() or not (to_improve or "").strip():
		frappe.throw(_("Please fill in what is going well and what to improve"))

	doc.going_well = going_well.strip()
	doc.to_improve = to_improve.strip()
	doc.other_comments = (other_comments or "").strip()
	doc.status = "Submitted"
	doc.submitted_on = now_datetime()
	doc.save(ignore_permissions=True)

	_email_feedback_to_employee(doc, reviewer)
	_notify_hr(doc.name, _("{0} gave feedback for {1}.").format(reviewer.employee_name, doc.employee_name))
	return {"message": "submitted"}


def _email_feedback_to_employee(doc, reviewer):
	email = frappe.db.get_value(
		"Employee", doc.employee, ["prefered_email", "company_email", "personal_email"], as_dict=True
	)
	email = email and (email.prefered_email or email.company_email or email.personal_email)
	if not email:
		return

	def paragraphs(text):
		return "".join(f"<p>{escape_html(line)}</p>" for line in (text or "").splitlines() if line.strip())

	frappe.sendmail(
		recipients=[email],
		subject=_("Feedback from {0} ahead of your appraisal").format(reviewer.employee_name),
		message=frappe.render_template(
			"""
			<p>Dear {{ employee }},</p>
			<p>Ahead of your {{ stage }} appraisal on <b>{{ due }}</b>, {{ reviewer }} has shared feedback on
				your work. Please go through it - you have time to work on these points before the appraisal.</p>
			<p><b>What is going well</b></p>{{ going_well }}
			<p><b>What to improve before the appraisal</b></p>{{ to_improve }}
			{% if other %}<p><b>Other comments</b></p>{{ other }}{% endif %}
			<p>HR Team</p>
			""",
			{
				"employee": doc.employee_name,
				"reviewer": reviewer.employee_name,
				"stage": (doc.appraisal_stage or "").lower(),
				"due": formatdate(doc.appraisal_due_date),
				"going_well": paragraphs(doc.going_well),
				"to_improve": paragraphs(doc.to_improve),
				"other": paragraphs(doc.other_comments),
			},
		),
		reference_doctype="Pre-Appraisal Feedback",
		reference_name=doc.name,
	)


def _notify_hr(name, subject):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
	from frappe.utils.user import get_users_with_role

	users = [u for u in get_users_with_role("HR Manager") if u != "Administrator"]
	if users:
		enqueue_create_notification(
			users,
			{
				"type": "Alert",
				"document_type": "Pre-Appraisal Feedback",
				"document_name": name,
				"subject": subject,
				"from_user": "Administrator",
			},
		)
