import frappe
from frappe import _
from frappe.utils import get_url, getdate, now_datetime, random_string, today

from hr_automation.api.link_expiry import check_not_expired

SURVEY_EMAIL_TEMPLATE = """
<p>Hi,</p>
<p>You're invited to take part in a survey: <b>{{ title }}</b></p>
{% if introduction %}<p>{{ introduction }}</p>{% endif %}
<p>
	<a href="{{ survey_url }}" style="padding:8px 16px;background:#2e7d32;color:#fff;
		text-decoration:none;border-radius:4px;">Take the Survey</a>
</p>
<p style="color:#777;font-size:12px;">This survey is completely anonymous - your response is not linked
	to your name or email in any way. The link above only confirms you're an invited employee.</p>
"""


def _resolve_employee_email(employee: str) -> str | None:
	if not employee:
		return None
	return (
		frappe.db.get_value("Employee", employee, "user_id")
		or frappe.db.get_value("Employee", employee, "company_email")
		or frappe.db.get_value("Employee", employee, "personal_email")
	)


def notify_survey_recipients(doc, method=None):
	"""on_update hook: emails each not-yet-notified recipient a link unique to them.
	The link only proves 'this is an invited employee' - it is never stored on, or
	linked to, the response they submit, so the response itself stays anonymous.

	Recipients with no resolvable email are left un-notified (not marked as sent)
	so they can be retried once an email is available - same if sendmail itself
	fails for one recipient, the rest still get processed."""
	if not doc.is_active:
		return

	pending = [row for row in doc.recipients if not row.notified]
	if not pending:
		return

	skipped_no_email = []

	for row in pending:
		email = row.email or _resolve_employee_email(row.employee)
		if not email:
			skipped_no_email.append(row.employee_name or row.employee)
			continue
		if email != row.email:
			row.db_set("email", email, update_modified=False)

		if not row.token:
			row.token = random_string(32)
			row.db_set("token", row.token, update_modified=False)

		survey_url = get_url(f"/survey?token={row.token}")
		message = frappe.render_template(
			SURVEY_EMAIL_TEMPLATE,
			{"title": doc.title, "introduction": doc.introduction, "survey_url": survey_url},
		)
		try:
			frappe.sendmail(
				recipients=[email],
				subject=_("You're invited: {0}").format(doc.title),
				message=message,
				reference_doctype="Employee Survey",
				reference_name=doc.name,
			)
		except Exception:
			frappe.log_error(
				title="Employee Survey invite failed",
				message=frappe.get_traceback(),
			)
			continue

		row.db_set("notified", 1, update_modified=False)
		row.db_set("notified_on", now_datetime(), update_modified=False)

	if skipped_no_email:
		frappe.msgprint(
			_("Could not find an email address for: {0}. They were not marked as notified.").format(
				", ".join(skipped_no_email)
			),
			alert=True,
			indicator="orange",
		)


def _resolve_recipient(token: str) -> dict:
	"""Resolves a token to its recipient row - used only to gate access (has this
	link already been used?) and to know which survey it belongs to. Never
	exposed to, or stored on, the response itself."""
	if not token:
		frappe.throw(_("Invalid or expired link."), frappe.DoesNotExistError)

	recipient = frappe.db.get_value(
		"Employee Survey Recipient",
		{"token": token},
		["name", "parent", "responded", "notified_on"],
		as_dict=True,
	)
	if not recipient:
		frappe.throw(_("Invalid or expired link."), frappe.DoesNotExistError)
	if not recipient.responded:
		check_not_expired(recipient.notified_on)

	return recipient


def _get_active_survey(survey_name: str) -> dict:
	doc = frappe.db.get_value(
		"Employee Survey",
		survey_name,
		["name", "title", "introduction", "is_active", "closes_on"],
		as_dict=True,
	)
	if not doc or not doc.is_active:
		frappe.throw(_("This survey is not available."), frappe.DoesNotExistError)

	if doc.closes_on and getdate(doc.closes_on) < getdate(today()):
		frappe.throw(_("This survey has closed."))

	return doc


@frappe.whitelist(allow_guest=True)
def get_survey(token: str):
	"""Public shape of a survey (title + questions) for rendering the form."""
	recipient = _resolve_recipient(token)
	if recipient.responded:
		return {"already_submitted": True}

	doc = _get_active_survey(recipient.parent)

	questions = frappe.get_all(
		"Employee Survey Question",
		filters={"parent": doc.name},
		fields=["name", "question", "question_type", "options", "is_mandatory", "idx"],
		order_by="idx",
	)
	return {
		"already_submitted": False,
		"title": doc.title,
		"introduction": doc.introduction,
		"questions": questions,
	}


@frappe.whitelist(allow_guest=True)
def submit_response(token: str, answers):
	"""Records a fully anonymous response - no employee/user/session identifier, and
	no trace of which recipient's token was used, is ever stored on the response.
	The token's own recipient row is flagged separately so the same link can't be
	used twice - that flag never touches the response document itself."""
	if isinstance(answers, str):
		answers = frappe.parse_json(answers)

	recipient = _resolve_recipient(token)
	if recipient.responded:
		frappe.throw(_("A response has already been submitted using this link."))

	doc = _get_active_survey(recipient.parent)

	questions = frappe.get_all(
		"Employee Survey Question",
		filters={"parent": doc.name},
		fields=["name", "question", "question_type", "is_mandatory"],
		order_by="idx",
	)
	answers_by_question = {a.get("question"): a.get("answer") for a in answers}

	response = frappe.new_doc("Employee Survey Response")
	response.survey = doc.name

	for q in questions:
		answer = answers_by_question.get(q.name)
		if isinstance(answer, list):
			answer = ", ".join([a for a in answer if a])

		if q.is_mandatory and not answer:
			frappe.throw(_("Please answer: {0}").format(q.question))

		if not answer:
			continue

		response.append(
			"answers",
			{"question": q.question, "question_type": q.question_type, "answer": answer},
		)

	response.insert(ignore_permissions=True)

	frappe.db.set_value(
		"Employee Survey Recipient",
		recipient.name,
		{"responded": 1, "responded_on": now_datetime()},
		update_modified=False,
	)

	return {"success": True}


def anonymize_survey_response(doc, method=None):
	"""before_insert hook: always attribute the response to Guest, even if the
	submitter happened to have an active logged-in session at the time."""
	doc.owner = "Guest"
	doc.modified_by = "Guest"


def remove_survey_response_tracking(doc, method=None):
	"""after_insert hook: defensive cleanup. Frappe's own insert() flow can create a
	Document Follow record tying frappe.session.user to a newly created document
	(if that user has 'follow created documents' enabled), independent of the
	owner field we already scrubbed. Delete any such record for this response."""
	frappe.db.delete("Document Follow", {"ref_doctype": "Employee Survey Response", "ref_docname": doc.name})
