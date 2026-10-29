import frappe
from frappe.utils import add_days, getdate, today

from hr_automation.api.employee_assessments import CATCH_UP_DAYS, get_appraisal_due_date


def execute():
	"""New appraisal schedule (trainee 3, +6, then yearly; employee 6, then
	yearly): start each existing employee at their next appraisal - ones that
	fell due more than CATCH_UP_DAYS ago are skipped instead of all being
	emailed at once - and fill in Latest Appraisal Date."""
	if not frappe.db.has_column("Employee", "custom_appraisals_notified"):
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("hr_automation")

	cutoff = add_days(getdate(today()), -CATCH_UP_DAYS)
	for emp in frappe.get_all(
		"Employee",
		filters={"date_of_joining": ["is", "set"]},
		fields=["name", "date_of_joining", "custom_is_trainee", "custom_was_trainee"],
	):
		trainee_track = bool(emp.custom_is_trainee or emp.custom_was_trainee)
		number = 0
		due = get_appraisal_due_date(emp.date_of_joining, None, trainee_track, number)
		while due and due < cutoff:
			number += 1
			due = get_appraisal_due_date(emp.date_of_joining, None, trainee_track, number)
		dates = frappe.get_all("Appraisal", filters={"employee": emp.name, "docstatus": 1}, pluck="modified")
		frappe.db.set_value(
			"Employee",
			emp.name,
			{
				"custom_appraisals_notified": number,
				"custom_next_appraisal_date": due,
				"custom_latest_appraisal_date": max((getdate(d) for d in dates), default=None),
			},
			update_modified=False,
		)
