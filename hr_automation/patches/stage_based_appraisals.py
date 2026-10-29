import frappe

from hr_automation.api.employee_assessments import get_appraisal_due_date


def execute():
	"""Appraisals are now created per stage (Training / Probation / Annual) in
	monthly cycles. Carry over the templates HR set on their level-based cycles,
	tag the old trainee-cycle appraisals as Training, and recompute Next
	Appraisal Due from Probation End Date."""
	if not frappe.db.has_column("Appraisal", "custom_appraisal_stage"):
		# Fixtures (where the new fields live) sync after patches run.
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("hr_automation")
	settings = frappe.get_single("HR Automation Settings")
	for cycle in frappe.get_all(
		"Appraisal Cycle",
		filters={"custom_default_appraisal_template": ["is", "set"]},
		fields=["name", "custom_trainee_only", "custom_default_appraisal_template"],
	):
		if cycle.custom_trainee_only:
			settings.training_appraisal_template = settings.training_appraisal_template or cycle.custom_default_appraisal_template
			frappe.db.set_value(
				"Appraisal", {"appraisal_cycle": cycle.name}, "custom_appraisal_stage", "Training", update_modified=False
			)
		else:
			settings.probation_appraisal_template = settings.probation_appraisal_template or cycle.custom_default_appraisal_template
			settings.annual_appraisal_template = settings.annual_appraisal_template or cycle.custom_default_appraisal_template
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)

	for emp in frappe.get_all(
		"Employee",
		filters={"date_of_joining": ["is", "set"]},
		fields=["name", "date_of_joining", "custom_probation_end_date", "custom_is_trainee", "custom_was_trainee", "custom_appraisals_notified"],
	):
		frappe.db.set_value(
			"Employee",
			emp.name,
			"custom_next_appraisal_date",
			get_appraisal_due_date(
				emp.date_of_joining,
				emp.custom_probation_end_date,
				emp.custom_is_trainee or emp.custom_was_trainee,
				emp.custom_appraisals_notified or 0,
			),
			update_modified=False,
		)
