import frappe
from frappe import _
from frappe.utils import get_url, now_datetime, random_string

from hr_automation.api.link_expiry import check_email_matches, check_not_expired

FEEDBACK_EMAIL_TEMPLATE = """
<p>Hi {{ employee_name }},</p>
<p>Please share your feedback for <b>{{ event_name }}</b>:</p>
<p>
	<a href="{{ feedback_url }}" style="padding:8px 16px;background:#0b6cf0;color:#fff;
		text-decoration:none;border-radius:4px;">Give Feedback</a>
</p>
"""

ALLOWED_ROLES = ["HR Manager", "HR User", "System Manager"]


@frappe.whitelist()
def get_feedback_questions(training_event: str):
	"""Used by the Desk 'Fill Feedback Form' dialog on Training Feedback."""
	form_name = frappe.db.get_value("Training Event", training_event, "custom_feedback_form")
	if not form_name:
		return {"form_exists": False, "questions": []}

	questions = frappe.get_all(
		"Training Feedback Question",
		filters={"parent": form_name, "parenttype": "Training Feedback Form"},
		fields=["name", "question", "question_type", "options", "is_mandatory", "idx"],
		order_by="idx",
	)
	return {"form_exists": True, "questions": questions}


@frappe.whitelist()
def send_feedback_requests(training_event: str, feedback_form: str, assessment_form: str = None, resend: bool = False):
	"""Called from the Training Event's 'Send Feedback Form' dialog. Emails every
	Present attendee a personal link to the chosen feedback form. Each employee is
	emailed once; resend=True re-emails only those who haven't responded yet. If an Assessment Form is also chosen, it's stored on the
	event so an assessment gets emailed automatically the moment each employee
	submits their feedback."""
	frappe.only_for(ALLOWED_ROLES)

	event = frappe.get_doc("Training Event", training_event)
	if event.docstatus != 1:
		frappe.throw(_("Training Event must be submitted first."))
	if not frappe.db.exists("Training Feedback Form", feedback_form):
		frappe.throw(_("Feedback form not found."))
	if assessment_form and not frappe.db.exists("Training Assessment Form", assessment_form):
		frappe.throw(_("Assessment form not found."))

	event.db_set("custom_feedback_form", feedback_form, update_modified=False)
	if assessment_form:
		event.db_set("custom_assessment_form", assessment_form, update_modified=False)

	sent_count = 0
	for row in event.employees:
		if row.attendance != "Present" or row.status == "Feedback Submitted":
			continue
		if row.status == "Invited" and not resend:
			continue

		if not row.custom_feedback_token:
			row.custom_feedback_token = random_string(32)
			frappe.db.set_value(
				"Training Event Employee", row.name, "custom_feedback_token", row.custom_feedback_token
			)

		email = (
			frappe.db.get_value("Employee", row.employee, "user_id")
			or frappe.db.get_value("Employee", row.employee, "company_email")
			or frappe.db.get_value("Employee", row.employee, "personal_email")
		)
		if not email:
			continue

		feedback_url = get_url(f"/training-feedback?token={row.custom_feedback_token}")
		message = frappe.render_template(
			FEEDBACK_EMAIL_TEMPLATE,
			{"employee_name": row.employee_name, "event_name": event.event_name, "feedback_url": feedback_url},
		)
		frappe.sendmail(
			recipients=[email],
			subject=_("Feedback requested: {0}").format(event.event_name),
			message=message,
			reference_doctype="Training Event",
			reference_name=event.name,
		)
		frappe.db.set_value(
			"Training Event Employee",
			row.name,
			{"status": "Invited", "custom_feedback_token_sent_at": now_datetime()},
			update_modified=False,
		)
		sent_count += 1

	return {"sent_count": sent_count}


def _resolve_feedback_token(token: str, email: str) -> dict:
	row = frappe.db.get_value(
		"Training Event Employee",
		{"custom_feedback_token": token},
		["name", "parent", "employee", "employee_name", "status", "custom_feedback_token_sent_at"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Invalid or expired link."), frappe.DoesNotExistError)

	stored_email = (
		frappe.db.get_value("Employee", row.employee, "user_id")
		or frappe.db.get_value("Employee", row.employee, "company_email")
		or frappe.db.get_value("Employee", row.employee, "personal_email")
	)
	check_email_matches(stored_email, email)

	if row.status != "Feedback Submitted":
		check_not_expired(row.custom_feedback_token_sent_at)
	return row


@frappe.whitelist(allow_guest=True)
def get_feedback_by_token(token: str, email: str):
	row = _resolve_feedback_token(token, email)

	if row.status == "Feedback Submitted":
		return {"already_submitted": True}

	event = frappe.db.get_value(
		"Training Event", row.parent, ["event_name", "custom_feedback_form"], as_dict=True
	)
	if not event.custom_feedback_form:
		frappe.throw(_("No feedback form is set up for this training yet."))

	questions = frappe.get_all(
		"Training Feedback Question",
		filters={"parent": event.custom_feedback_form, "parenttype": "Training Feedback Form"},
		fields=["name", "question", "question_type", "options", "is_mandatory", "idx"],
		order_by="idx",
	)
	return {
		"already_submitted": False,
		"event_name": event.event_name,
		"employee_name": row.employee_name,
		"questions": questions,
	}


@frappe.whitelist(allow_guest=True)
def submit_feedback_by_token(token: str, email: str, answers):
	if isinstance(answers, str):
		answers = frappe.parse_json(answers)

	row = _resolve_feedback_token(token, email)
	if row.status == "Feedback Submitted":
		frappe.throw(_("Feedback has already been submitted for this training."))

	form_name = frappe.db.get_value("Training Event", row.parent, "custom_feedback_form")
	if not form_name:
		frappe.throw(_("No feedback form is set up for this training yet."))

	questions = frappe.get_all(
		"Training Feedback Question",
		filters={"parent": form_name, "parenttype": "Training Feedback Form"},
		fields=["name", "question", "question_type", "is_mandatory"],
		order_by="idx",
	)
	answers_by_question = {a.get("question"): a.get("answer") for a in answers}

	fb = frappe.new_doc("Training Feedback")
	fb.employee = row.employee
	fb.training_event = row.parent

	for q in questions:
		answer = answers_by_question.get(q.name)
		if isinstance(answer, list):
			answer = ", ".join([a for a in answer if a])

		if q.is_mandatory and not answer:
			frappe.throw(_("Please answer: {0}").format(q.question))

		if not answer:
			continue

		fb.append(
			"custom_answers",
			{"question": q.question, "question_type": q.question_type, "answer": answer},
		)

	fb.insert(ignore_permissions=True)
	fb.submit()

	frappe.db.set_value(
		"Training Event Employee", row.name, "status", "Feedback Submitted", update_modified=False
	)

	from hr_automation.api.training_assessment import send_assessment_if_configured

	send_assessment_if_configured(row.parent, row.employee, row.employee_name, row.name)

	return {"success": True}
