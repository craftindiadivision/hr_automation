import frappe
from frappe.utils import add_days, formatdate, today


def create_onboarding_program(doc, method=None):
	"""Hook: Employee after_insert / on_update. The moment a joining date is
	given, enrolls the employee into an Onboarding Training Program for that
	date, named from HR Automation Settings - employees who join on the same
	day share one program and its events, rather than getting a separate one
	each. If no Onboarding Event Names are configured yet, nothing is created
	(no invented number of generic events) - configure at least one row in
	Settings, then save this Employee again."""
	if not doc.date_of_joining or doc.custom_onboarding_training_program:
		return

	before = doc.get_doc_before_save()
	if before and before.date_of_joining:
		# Already had a joining date before this save - this isn't the moment
		# it was "given", so don't retroactively enroll existing employees.
		return

	names = _get_pipeline_event_names("onboarding_event_names")
	if not names:
		frappe.log_error(
			title="Onboarding program not created",
			message=(
				f"Employee {doc.name} has a Joining Date but no Onboarding Event Names are "
				"configured in HR Automation Settings. Add at least one row there, then save "
				"this Employee again."
			),
		)
		return

	program_name = f"Onboarding - {doc.date_of_joining}"
	if not frappe.db.exists("Training Program", program_name):
		_create_training_program(
			program_name,
			doc.company,
			f"Auto-created onboarding program for employees joining on {formatdate(doc.date_of_joining)}.",
			len(names),
			"Onboarding",
		)
		_populate_scheduled_sessions(program_name, doc.date_of_joining, names)

	frappe.db.set_value(
		"Employee", doc.name, "custom_onboarding_training_program", program_name, update_modified=False
	)


def handle_training_stage_completion(employee: str, training_program: str):
	"""Called whenever an employee's completion of a Training Program is
	recomputed - advances them to the next stage of the joining pipeline if
	this program was one of its steps (Onboarding -> Buddy Training -> LEAP)."""
	stage = frappe.db.get_value(
		"Employee",
		employee,
		["custom_onboarding_training_program", "custom_buddy_training_program"],
		as_dict=True,
	)
	if not stage:
		return

	if stage.custom_onboarding_training_program == training_program:
		_create_buddy_training_program(employee)
	elif stage.custom_buddy_training_program == training_program:
		_mark_leap_ready(employee)


def _create_buddy_training_program(employee: str):
	emp = frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "company", "custom_buddy_training_program"],
		as_dict=True,
	)
	if emp.custom_buddy_training_program:
		return

	names = _get_pipeline_event_names("buddy_training_event_names")
	if not names:
		frappe.log_error(
			title="Buddy Training program not created",
			message=(
				f"Employee {employee} completed Onboarding but no Buddy Training Event Names are "
				"configured in HR Automation Settings. Add at least one row there, then call "
				"handle_training_stage_completion again (e.g. resubmit their last onboarding feedback)."
			),
		)
		return

	program_name = f"Buddy Training - {employee}"
	_create_training_program(
		program_name,
		emp.company,
		f"Auto-created {len(names)}-day buddy training program for {emp.employee_name}.",
		len(names),
		"Buddy Training",
	)
	_populate_scheduled_sessions(program_name, today(), names)

	frappe.db.set_value(
		"Employee", employee, "custom_buddy_training_program", program_name, update_modified=False
	)


def _mark_leap_ready(employee: str):
	frappe.db.set_value(
		"Employee",
		employee,
		{"custom_leap_ready": 1, "custom_leap_ready_on": today()},
		update_modified=False,
	)


PROGRAM_TYPE_EVENT_FIELDS = {
	"Onboarding": "onboarding_event_names",
	"Buddy Training": "buddy_training_event_names",
}


@frappe.whitelist()
def get_pipeline_event_names(program_type: str) -> list[str]:
	"""Used by the Training Program form to suggest Topics on the Scheduled
	Sessions table from HR Automation Settings, for the two program types that
	have a configured event list. Any other program_type gets no suggestions -
	Topic stays free text."""
	fieldname = PROGRAM_TYPE_EVENT_FIELDS.get(program_type)
	if not fieldname:
		return []
	return _get_pipeline_event_names(fieldname)


def _get_pipeline_event_names(fieldname: str) -> list[str]:
	"""One row per event from the given table field on HR Automation Settings,
	in order. No number is invented if it's empty - callers decide what to do
	when there's nothing configured."""
	settings = frappe.get_single("HR Automation Settings")
	rows = settings.get(fieldname) or []
	return [row.event_name.strip() for row in rows if row.event_name and row.event_name.strip()]


def _create_training_program(name, company, description, number_of_events, program_type):
	program = frappe.get_doc(
		{
			"doctype": "Training Program",
			"training_program": name,
			"company": company,
			"description": description,
			"custom_number_of_events": number_of_events,
			"custom_program_type": program_type,
		}
	)
	program.insert(ignore_permissions=True)
	return program


def _populate_scheduled_sessions(training_program, start_date, labels):
	"""Fills in the Training Program's own Scheduled Sessions table - one row
	per configured event name - instead of creating the events directly. HR
	reviews/adjusts the rows and clicks "Create Events" themselves, same as
	for any other Training Program; this is the only path events are ever
	created through, for every program type."""
	program = frappe.get_doc("Training Program", training_program)
	for i, label in enumerate(labels):
		event_date = add_days(start_date, i)
		program.append(
			"custom_scheduled_sessions",
			{
				"start_date": event_date,
				"end_date": event_date,
				"topic": label,
			},
		)
	program.save(ignore_permissions=True)
