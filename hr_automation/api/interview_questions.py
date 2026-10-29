import json

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from hrms.hr.doctype.job_applicant.job_applicant import schedule_interview as hrms_schedule_interview


@frappe.whitelist()
def get_template_questions(template: str) -> list[str]:
	"""Questions of an Interview Questions template, in order."""
	frappe.has_permission("Interview Questions", "read", template, throw=True)
	return frappe.get_all(
		"Interview Question",
		filters={"parent": template, "parenttype": "Interview Questions"},
		pluck="question",
		order_by="idx asc",
	)


@frappe.whitelist()
def schedule_interview(
	job_applicant: str,
	interview_type: str,
	scheduled_on: str,
	from_time: str | None = None,
	to_time: str | None = None,
	interviewers: str | list | None = None,
	interview_questions: str | None = None,
	questions: str | list | None = None,
) -> str:
	"""The Job Applicant's Schedule Interview dialog: HRMS's own scheduling, plus
	the chosen Interview Questions template and its (possibly edited) questions
	copied onto the new Interview."""
	name = hrms_schedule_interview(job_applicant, interview_type, scheduled_on, from_time, to_time, interviewers)

	if isinstance(questions, str):
		questions = json.loads(questions)
	questions = [row.get("question").strip() for row in questions or [] if (row.get("question") or "").strip()]
	if interview_questions or questions:
		interview = frappe.get_doc("Interview", name)
		interview.custom_interview_questions = interview_questions
		for question in questions:
			interview.append("custom_questions", {"question": question})
		interview.save(ignore_permissions=True)
	return name


@frappe.whitelist()
def create_interview_feedback(data: str | dict, interview_name: str, interviewer: str, job_applicant: str):
	"""The Interview's Submit Feedback dialog: same as HRMS's
	create_interview_feedback, plus the interviewer's answer to each of the
	interview's questions."""
	if isinstance(data, str):
		data = json.loads(data)
	data = frappe._dict(data)

	if frappe.session.user != interviewer:
		frappe.throw(_("Only Interviewer Are allowed to submit Interview Feedback"))

	feedback = frappe.new_doc("Interview Feedback")
	feedback.interview = interview_name
	feedback.interviewer = interviewer
	feedback.job_applicant = job_applicant
	for row in data.skill_set or []:
		feedback.append("skill_assessment", frappe._dict(row))
	for row in data.question_answers or []:
		if row.get("question"):
			feedback.append(
				"custom_question_answers", {"question": row.get("question"), "answer": row.get("answer")}
			)
	feedback.feedback = data.feedback
	feedback.result = data.result
	feedback.save()
	feedback.submit()

	frappe.msgprint(
		_("Interview Feedback {0} submitted successfully").format(
			get_link_to_form("Interview Feedback", feedback.name)
		)
	)
