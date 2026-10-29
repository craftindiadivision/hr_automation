import frappe
from frappe import _
from frappe.utils import get_url, now_datetime, random_string

from hr_automation.api.link_expiry import check_email_matches, check_not_expired

ASSESSMENT_EMAIL_TEMPLATE = """
<p>Hi {{ employee_name }},</p>
<p>Thanks for your feedback on <b>{{ event_name }}</b>. Please also complete a short assessment:</p>
<p>
	<a href="{{ assessment_url }}" style="padding:8px 16px;background:#0b6cf0;color:#fff;
		text-decoration:none;border-radius:4px;">Take Assessment</a>
</p>
"""


def send_assessment_if_configured(training_event: str, employee: str, employee_name: str, event_employee_row: str):
	"""Called right after an employee's Training Feedback is submitted. If the
	event has an Assessment Form configured, emails them a personal link to it."""
	assessment_form = frappe.db.get_value("Training Event", training_event, "custom_assessment_form")
	if not assessment_form:
		return

	email = (
		frappe.db.get_value("Employee", employee, "user_id")
		or frappe.db.get_value("Employee", employee, "company_email")
		or frappe.db.get_value("Employee", employee, "personal_email")
	)
	if not email:
		return

	token = random_string(32)
	frappe.db.set_value(
		"Training Event Employee",
		event_employee_row,
		{"custom_assessment_token": token, "custom_assessment_token_sent_at": now_datetime()},
		update_modified=False,
	)

	event_name = frappe.db.get_value("Training Event", training_event, "event_name")
	assessment_url = get_url(f"/training-assessment?token={token}")
	message = frappe.render_template(
		ASSESSMENT_EMAIL_TEMPLATE,
		{"employee_name": employee_name, "event_name": event_name, "assessment_url": assessment_url},
	)
	frappe.sendmail(
		recipients=[email],
		subject=_("Assessment: {0}").format(event_name),
		message=message,
		reference_doctype="Training Event",
		reference_name=training_event,
	)


@frappe.whitelist()
def resend_assessment_requests(training_event):
	"""Manual fallback: (re)sends the assessment link to every employee who has
	submitted feedback for this event but not yet submitted an assessment -
	whether they were never sent one, or their original link has since expired."""
	from hr_automation.api.training_feedback import ALLOWED_ROLES

	frappe.only_for(ALLOWED_ROLES)

	event = frappe.get_doc("Training Event", training_event)
	if not event.custom_assessment_form:
		frappe.throw(_("No Assessment Form is set up for this event"))

	sent_count = 0
	for row in event.employees:
		if row.status != "Feedback Submitted":
			continue
		if frappe.db.exists("Training Assessment", {"employee": row.employee, "training_event": event.name}):
			continue

		email = (
			frappe.db.get_value("Employee", row.employee, "user_id")
			or frappe.db.get_value("Employee", row.employee, "company_email")
			or frappe.db.get_value("Employee", row.employee, "personal_email")
		)
		if not email:
			continue

		token = row.custom_assessment_token or random_string(32)
		frappe.db.set_value(
			"Training Event Employee",
			row.name,
			{"custom_assessment_token": token, "custom_assessment_token_sent_at": now_datetime()},
			update_modified=False,
		)

		assessment_url = get_url(f"/training-assessment?token={token}")
		message = frappe.render_template(
			ASSESSMENT_EMAIL_TEMPLATE,
			{"employee_name": row.employee_name, "event_name": event.event_name, "assessment_url": assessment_url},
		)
		frappe.sendmail(
			recipients=[email],
			subject=_("Assessment: {0}").format(event.event_name),
			message=message,
			reference_doctype="Training Event",
			reference_name=event.name,
		)
		sent_count += 1

	return {"sent_count": sent_count}


def _resolve_assessment_token(token: str, email: str) -> dict:
	row = frappe.db.get_value(
		"Training Event Employee",
		{"custom_assessment_token": token},
		["name", "parent", "employee", "employee_name", "custom_assessment_token_sent_at"],
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

	row["already_submitted"] = bool(
		frappe.db.exists("Training Assessment", {"employee": row.employee, "training_event": row.parent})
	)
	if not row["already_submitted"]:
		check_not_expired(row.custom_assessment_token_sent_at)
	return row


@frappe.whitelist(allow_guest=True)
def get_assessment_by_token(token: str, email: str):
	row = _resolve_assessment_token(token, email)

	if row.already_submitted:
		return {"already_submitted": True}

	event = frappe.db.get_value(
		"Training Event", row.parent, ["event_name", "custom_assessment_form"], as_dict=True
	)
	if not event.custom_assessment_form:
		frappe.throw(_("No assessment form is set up for this training yet."))

	questions = frappe.get_all(
		"Training Assessment Question",
		filters={"parent": event.custom_assessment_form, "parenttype": "Training Assessment Form"},
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
def submit_assessment_by_token(token: str, email: str, answers):
	if isinstance(answers, str):
		answers = frappe.parse_json(answers)

	row = _resolve_assessment_token(token, email)
	if row.already_submitted:
		frappe.throw(_("An assessment has already been submitted for this training."))

	form_name = frappe.db.get_value("Training Event", row.parent, "custom_assessment_form")
	if not form_name:
		frappe.throw(_("No assessment form is set up for this training yet."))

	questions = frappe.get_all(
		"Training Assessment Question",
		filters={"parent": form_name, "parenttype": "Training Assessment Form"},
		fields=["name", "question", "question_type", "is_mandatory"],
		order_by="idx",
	)
	answers_by_question = {a.get("question"): a.get("answer") for a in answers}

	assessment = frappe.new_doc("Training Assessment")
	assessment.employee = row.employee
	assessment.training_event = row.parent
	assessment.assessment_form = form_name

	for q in questions:
		answer = answers_by_question.get(q.name)
		if isinstance(answer, list):
			answer = ", ".join([a for a in answer if a])

		if q.is_mandatory and not answer:
			frappe.throw(_("Please answer: {0}").format(q.question))

		if not answer:
			continue

		assessment.append(
			"answers",
			{"question": q.question, "question_type": q.question_type, "answer": answer},
		)

	assessment.insert(ignore_permissions=True)
	assessment.submit()
	return {"success": True}
