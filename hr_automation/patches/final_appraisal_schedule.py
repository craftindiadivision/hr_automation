import frappe
from frappe.utils import add_days, getdate, today

from hr_automation.api.employee_assessments import CATCH_UP_DAYS, get_appraisal_due_date, get_appraisal_stage


def execute():
	"""Appraisals now end with the Annual one (trainee month 15, employee month
	12). Move existing employees onto that: appraisals that fell due more than
	CATCH_UP_DAYS ago (or that the old schedule already sent) count as done, so
	nothing is re-sent; Next Appraisal Due is empty for anyone who has had them
	all. Requested Pre-Appraisal Feedback for an appraisal that no longer
	exists is removed - a submitted one is never touched."""
	cutoff = add_days(getdate(today()), -CATCH_UP_DAYS)
	for emp in frappe.get_all(
		"Employee",
		filters={"date_of_joining": ["is", "set"]},
		fields=[
			"name",
			"date_of_joining",
			"custom_probation_end_date",
			"custom_is_trainee",
			"custom_was_trainee",
			"custom_appraisals_notified",
		],
	):
		trainee_track = bool(emp.custom_is_trainee or emp.custom_was_trainee)
		total = 0
		while get_appraisal_stage(trainee_track, total):
			total += 1
		number = 0
		while number < total and get_appraisal_due_date(
			emp.date_of_joining, emp.custom_probation_end_date, trainee_track, number
		) < cutoff:
			number += 1
		# Never go back on an appraisal the daily job already sent.
		number = min(max(number, emp.custom_appraisals_notified or 0), total)
		frappe.db.set_value(
			"Employee",
			emp.name,
			{
				"custom_appraisals_notified": number,
				"custom_next_appraisal_date": get_appraisal_due_date(
					emp.date_of_joining, emp.custom_probation_end_date, trainee_track, number
				),
			},
			update_modified=False,
		)

		for feedback in frappe.get_all(
			"Pre-Appraisal Feedback",
			filters={"employee": emp.name, "status": "Requested"},
			fields=["name", "appraisal_due_date"],
		):
			due = get_appraisal_due_date(emp.date_of_joining, emp.custom_probation_end_date, trainee_track, number)
			if due and getdate(feedback.appraisal_due_date) == getdate(due):
				frappe.db.set_value("Employee", emp.name, "custom_feedback_requested_for", number + 1, update_modified=False)
			else:
				frappe.delete_doc("Pre-Appraisal Feedback", feedback.name, ignore_permissions=True, force=True)
