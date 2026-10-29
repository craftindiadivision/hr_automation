import frappe

from hr_automation.api.leave_management import get_probation_end_date


def execute():
	"""Backfills Probation End Date for employees created before it existed."""
	if not frappe.db.has_column("Employee", "custom_probation_end_date"):
		# Fixtures (where the custom field lives) sync after patches run.
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("hr_automation")

	employees = frappe.get_all(
		"Employee",
		filters={"date_of_joining": ["is", "set"], "custom_probation_end_date": ["is", "not set"]},
		fields=["name", "date_of_joining", "custom_is_trainee", "custom_was_trainee"],
	)
	for emp in employees:
		frappe.db.set_value(
			"Employee",
			emp.name,
			"custom_probation_end_date",
			get_probation_end_date(emp.date_of_joining, emp.custom_is_trainee or emp.custom_was_trainee),
			update_modified=False,
		)
