import frappe
from frappe.query_builder.functions import Count

ALLOWED_ROLES = ["HR Manager", "HR User", "System Manager"]


@frappe.whitelist()
def get_dashboard_data():
	frappe.only_for(ALLOWED_ROLES)

	return {
		"training": _get_training_stats(),
		"groups": _get_group_stats(),
		"survey": _get_survey_stats(),
	}


def _get_training_stats():
	# Onboarding/Buddy Training programs are auto-created per employee by the
	# joining pipeline - counting them here would make "Total Programs" grow
	# with headcount instead of reflecting actual training programs on offer.
	total_programs = frappe.db.count("Training Program", {"custom_program_type": "Regular"})
	total_events = frappe.db.count("Training Event", {"docstatus": 1})
	total_feedback = frappe.db.count("Training Feedback", {"docstatus": 1})

	TrainingEvent = frappe.qb.DocType("Training Event")

	events_by_status = (
		frappe.qb.from_(TrainingEvent)
		.select(TrainingEvent.event_status, Count(TrainingEvent.name).as_("count"))
		.where(TrainingEvent.docstatus == 1)
		.groupby(TrainingEvent.event_status)
	).run(as_dict=True)

	regular_programs = frappe.get_all(
		"Training Program", filters={"custom_program_type": "Regular"}, pluck="name"
	)
	# An empty IN () is invalid SQL, so skip the query when there are no Regular programs.
	events_by_program = []
	if regular_programs:
		events_by_program = (
			frappe.qb.from_(TrainingEvent)
			.select(TrainingEvent.training_program, Count(TrainingEvent.name).as_("count"))
			.where((TrainingEvent.docstatus == 1) & (TrainingEvent.training_program.isin(regular_programs)))
			.groupby(TrainingEvent.training_program)
			.orderby(Count(TrainingEvent.name), order=frappe.qb.desc)
			.limit(10)
		).run(as_dict=True)

	start_times = frappe.get_all(
		"Training Event", filters={"docstatus": 1}, fields=["start_time"], pluck="start_time"
	)
	month_counts = {}
	for start_time in start_times:
		if not start_time:
			continue
		month = frappe.utils.formatdate(start_time, "yyyy-MM")
		month_counts[month] = month_counts.get(month, 0) + 1
	events_by_month = [{"month": k, "count": v} for k, v in sorted(month_counts.items())]

	return {
		"total_programs": total_programs,
		"total_events": total_events,
		"total_feedback": total_feedback,
		"events_by_status": events_by_status,
		"events_by_program": events_by_program,
		"events_by_month": events_by_month,
	}


def _get_group_stats():
	completions = frappe.get_all(
		"Training Program Group Completion", fields=["is_completed", "parent_training_program"]
	)

	total_tracked = len(completions)
	certified_count = sum(1 for c in completions if c.is_completed)

	groups = frappe.get_all("Training Program", filters={"custom_is_group": 1}, fields=["name"])
	group_completion = {
		g.name: sum(
			1 for c in completions if c.parent_training_program == g.name and c.is_completed
		)
		for g in groups
	}

	recent = frappe.get_all(
		"Training Program Group Completion",
		filters={"is_completed": 1},
		fields=["employee_name", "parent_training_program", "completed_on"],
		order_by="completed_on desc",
		limit_page_length=5,
	)

	return {
		"total_groups": len(groups),
		"total_tracked": total_tracked,
		"certified_count": certified_count,
		"in_progress_count": total_tracked - certified_count,
		"group_completion": group_completion,
		"recent_certifications": recent,
	}


def _get_survey_stats():
	total_surveys = frappe.db.count("Employee Survey")
	active_surveys = frappe.db.count("Employee Survey", {"is_active": 1})
	total_recipients = frappe.db.count("Employee Survey Recipient")
	total_responses = frappe.db.count("Employee Survey Response")

	surveys = frappe.get_all(
		"Employee Survey", fields=["name", "title"], order_by="creation desc", limit_page_length=10
	)

	Recipient = frappe.qb.DocType("Employee Survey Recipient")
	recipient_counts = (
		frappe.qb.from_(Recipient)
		.select(Recipient.parent, Count(Recipient.name).as_("count"))
		.groupby(Recipient.parent)
	).run(as_dict=True)

	Response = frappe.qb.DocType("Employee Survey Response")
	response_counts = (
		frappe.qb.from_(Response)
		.select(Response.survey, Count(Response.name).as_("count"))
		.groupby(Response.survey)
	).run(as_dict=True)

	recipient_map = {r.parent: r.count for r in recipient_counts}
	response_map = {r.survey: r.count for r in response_counts}

	by_survey = [
		{
			"title": s.title,
			"invited": recipient_map.get(s.name, 0),
			"responses": response_map.get(s.name, 0),
		}
		for s in surveys
	]

	return {
		"total_surveys": total_surveys,
		"active_surveys": active_surveys,
		"total_recipients": total_recipients,
		"total_responses": total_responses,
		"by_survey": by_survey,
	}
