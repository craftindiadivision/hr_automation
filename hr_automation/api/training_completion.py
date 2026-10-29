import frappe
from frappe import _
from frappe.utils import today


def _get_completed_event_count(employee: str, training_program: str) -> int:
	"""Count of distinct submitted Training Events (under this program) where the
	employee was marked Present AND has a submitted Training Feedback."""
	events = frappe.get_all(
		"Training Event",
		filters={"training_program": training_program, "docstatus": 1},
		pluck="name",
	)
	if not events:
		return 0

	present_events = frappe.get_all(
		"Training Event Employee",
		filters={"parent": ["in", events], "employee": employee, "attendance": "Present"},
		pluck="parent",
	)
	if not present_events:
		return 0

	feedback_events = frappe.get_all(
		"Training Feedback",
		filters={"training_event": ["in", present_events], "employee": employee, "docstatus": 1},
		pluck="training_event",
	)

	return len(set(present_events) & set(feedback_events))


def recompute_program_completion(employee: str, training_program: str):
	"""Recalculates and persists this employee's completion for a single Training
	Program. The required count is that program's own Number of Events - if it
	hasn't been set, the program isn't considered completable yet."""
	required = frappe.db.get_value("Training Program", training_program, "custom_number_of_events") or 0
	completed = _get_completed_event_count(employee, training_program)
	is_done = required > 0 and completed >= required

	existing = frappe.db.get_value(
		"Training Program Completion",
		{"employee": employee, "training_program": training_program},
		"name",
	)
	if existing:
		doc = frappe.get_doc("Training Program Completion", existing)
	else:
		doc = frappe.new_doc("Training Program Completion")
		doc.employee = employee
		doc.training_program = training_program

	was_done = doc.is_completed
	doc.progress = f"{completed} / {required}"
	doc.is_completed = 1 if is_done else 0
	if is_done and not was_done:
		doc.completed_on = today()
	elif not is_done:
		doc.completed_on = None

	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)

	if is_done != was_done:
		_update_certificates_issued(
			"Training Program", "Training Program Completion", "training_program", training_program
		)

	if is_done and not was_done:
		from hr_automation.api.employee_onboarding import handle_training_stage_completion

		handle_training_stage_completion(employee, training_program)

	# If this program belongs to a group (e.g. LEAP's Lead/Excel/Ace/Perform),
	# also recompute the group-level rollup for this employee.
	parent_program = frappe.db.get_value(
		"Training Program", training_program, "custom_parent_training_program"
	)
	if parent_program:
		recompute_group_completion(employee, parent_program)

	return doc


def recompute_group_completion(employee: str, parent_program: str):
	"""Recalculates and persists this employee's completion for an entire group of
	Training Programs (e.g. LEAP - a Training Program with "Is Group" checked), by
	checking whether every program under that parent is individually complete for
	them."""
	programs = frappe.get_all(
		"Training Program",
		filters={"custom_parent_training_program": parent_program},
		pluck="name",
	)
	if not programs:
		return

	existing = frappe.db.get_value(
		"Training Program Group Completion",
		{"employee": employee, "parent_training_program": parent_program},
		"name",
	)
	if existing:
		doc = frappe.get_doc("Training Program Group Completion", existing)
	else:
		doc = frappe.new_doc("Training Program Group Completion")
		doc.employee = employee
		doc.parent_training_program = parent_program

	was_done = doc.is_completed
	doc.set("programs", [])
	all_complete = True

	for program in programs:
		completion = frappe.db.get_value(
			"Training Program Completion",
			{"employee": employee, "training_program": program},
			["progress", "is_completed", "completed_on"],
			as_dict=True,
		)
		if not completion:
			all_complete = False
			doc.append("programs", {"training_program": program, "progress": None, "completed": 0})
			continue

		if not completion.is_completed:
			all_complete = False
		doc.append(
			"programs",
			{
				"training_program": program,
				"progress": completion.progress,
				"completed": completion.is_completed,
				"completed_on": completion.completed_on,
			},
		)

	doc.is_completed = 1 if all_complete else 0
	if all_complete and not was_done:
		doc.completed_on = today()
	elif not all_complete:
		doc.completed_on = None

	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)

	if all_complete != was_done:
		_update_certificates_issued(
			"Training Program", "Training Program Group Completion", "parent_training_program", parent_program
		)

	return doc


def _update_certificates_issued(program_doctype, completion_doctype, program_fieldname, training_program):
	count = frappe.db.count(completion_doctype, {program_fieldname: training_program, "is_completed": 1})
	frappe.db.set_value(
		program_doctype, training_program, "custom_certificates_issued", count, update_modified=False
	)


def on_training_feedback_change(doc, method=None):
	"""Hook: Training Feedback on_submit / on_cancel."""
	if not doc.employee or not doc.training_event:
		return

	if method == "on_cancel":
		# The row was flipped to "Feedback Submitted" when this was submitted -
		# with the feedback cancelled, that's no longer true.
		frappe.db.set_value(
			"Training Event Employee",
			{"parent": doc.training_event, "employee": doc.employee},
			"status",
			"Invited",
			update_modified=False,
		)

	training_program = frappe.db.get_value("Training Event", doc.training_event, "training_program")
	if training_program:
		recompute_program_completion(doc.employee, training_program)
		sync_program_employee_events(training_program)


def on_training_event_change(doc, method=None):
	"""Hook: Training Event on_submit / on_update_after_submit / on_cancel."""
	if doc.training_program:
		sync_program_employee_events(doc.training_program)
		recompute_completed_events(doc.training_program)


def recompute_completed_events(training_program: str):
	"""Recalculates and persists custom_completed_events for a Training Program:
	for a leaf, the count of its own submitted Training Events; for a group
	(e.g. LEAP), the sum of its children's counts. Once this catches up to
	custom_number_of_events, the program's own Status flips to Completed - and
	since a group's total is just the sum of its children, that happens for the
	group too once every program under it has individually caught up."""
	is_group, parent = frappe.db.get_value(
		"Training Program", training_program, ["custom_is_group", "custom_parent_training_program"]
	)

	if is_group:
		children = frappe.get_all(
			"Training Program",
			filters={"custom_parent_training_program": training_program},
			pluck="name",
		)
		count = sum(
			frappe.db.get_value("Training Program", child, "custom_completed_events") or 0
			for child in children
		)
	else:
		count = frappe.db.count("Training Event", {"training_program": training_program, "docstatus": 1})

	frappe.db.set_value(
		"Training Program", training_program, "custom_completed_events", count, update_modified=False
	)
	_sync_program_status(training_program)

	if parent:
		recompute_completed_events(parent)


def _sync_program_status(training_program: str):
	"""Flips a Training Program's own Status between Scheduled and Completed
	based on whether Completed Events has caught up to Number of Events. Never
	touches a program that's been manually set to Cancelled."""
	number_of_events, completed_events, current_status = frappe.db.get_value(
		"Training Program",
		training_program,
		["custom_number_of_events", "custom_completed_events", "status"],
	)
	if current_status == "Cancelled":
		return

	is_done = (number_of_events or 0) > 0 and (completed_events or 0) >= number_of_events
	new_status = "Completed" if is_done else "Scheduled"
	if new_status != current_status:
		frappe.db.set_value(
			"Training Program", training_program, "status", new_status, update_modified=False
		)


def sync_program_employee_events(training_program: str):
	"""Rebuilds the "Employees" tab on a Training Program: one row per employee
	per Training Event under it, with their attendance (as already marked on the
	Training Event itself) and whether they've submitted feedback for it. For a
	group (e.g. LEAP) this aggregates every event across all the programs mapped
	under it - same rollup logic as the event-count total - and recurses upward
	so a grandparent group's tab stays in sync too."""
	program = frappe.get_doc("Training Program", training_program)

	if program.custom_is_group:
		child_programs = frappe.get_all(
			"Training Program",
			filters={"custom_parent_training_program": training_program},
			pluck="name",
		)
	else:
		child_programs = [training_program]

	events = (
		frappe.get_all(
			"Training Event",
			filters={"training_program": ["in", child_programs], "docstatus": 1},
			fields=["name", "training_program", "start_time"],
		)
		if child_programs
		else []
	)

	rows = []
	if events:
		event_by_name = {event.name: event for event in events}
		event_names = list(event_by_name.keys())

		attendance_rows = frappe.get_all(
			"Training Event Employee",
			filters={"parent": ["in", event_names]},
			fields=["parent as training_event", "employee", "attendance"],
		)

		employee_names = {row.employee for row in attendance_rows if row.employee}
		employee_display = {
			employee.name: employee.employee_name
			for employee in (
				frappe.get_all(
					"Employee",
					filters={"name": ["in", list(employee_names)]},
					fields=["name", "employee_name"],
				)
				if employee_names
				else []
			)
		}

		feedback_pairs = set(
			frappe.get_all(
				"Training Feedback",
				filters={"training_event": ["in", event_names], "docstatus": 1},
				fields=["training_event", "employee"],
				as_list=True,
			)
		)

		certificate_programs = frappe.get_all(
			"Training Program",
			filters={"name": ["in", child_programs], "custom_has_certificate": 1},
			pluck="name",
		)
		certificate_ready_pairs = set(
			frappe.get_all(
				"Training Program Completion",
				filters={
					"employee": ["in", list(employee_names)],
					"training_program": ["in", certificate_programs],
					"is_completed": 1,
				},
				fields=["employee", "training_program"],
				as_list=True,
			)
			if employee_names and certificate_programs
			else []
		)

		for row in attendance_rows:
			event = event_by_name[row.training_event]
			feedback_submitted = (row.training_event, row.employee) in feedback_pairs
			status = "Completed" if row.attendance == "Present" and feedback_submitted else "Pending"
			certificate_ready = (row.employee, event.training_program) in certificate_ready_pairs
			rows.append(
				{
					"employee": row.employee,
					"employee_name": employee_display.get(row.employee),
					"training_program": event.training_program,
					"training_event": row.training_event,
					"event_date": event.start_time,
					"attendance": row.attendance,
					"feedback_submitted": 1 if feedback_submitted else 0,
					"status": status,
					"certificate_ready": 1 if certificate_ready else 0,
				}
			)

		rows.sort(key=lambda r: (r["employee_name"] or "", r["event_date"] or ""))

	program.set("custom_employee_events", [])
	for row in rows:
		program.append("custom_employee_events", row)
	program.save(ignore_permissions=True)

	if program.custom_parent_training_program:
		sync_program_employee_events(program.custom_parent_training_program)


def recompute_event_count(training_program: str):
	"""Recalculates and persists custom_number_of_events for a group Training
	Program (e.g. LEAP), as the sum of the values entered directly on the
	programs mapped under it. Leaf programs are entered manually, so there's
	nothing to compute for them - this recurses upward so a grandparent group's
	total stays correct too."""
	is_group, parent = frappe.db.get_value(
		"Training Program", training_program, ["custom_is_group", "custom_parent_training_program"]
	)
	if not is_group:
		return

	children = frappe.get_all(
		"Training Program",
		filters={"custom_parent_training_program": training_program},
		pluck="name",
	)
	total = sum(
		frappe.db.get_value("Training Program", child, "custom_number_of_events") or 0
		for child in children
	)
	frappe.db.set_value(
		"Training Program", training_program, "custom_number_of_events", total, update_modified=False
	)

	if parent:
		recompute_event_count(parent)


ALLOWED_ROLES = ["HR Manager", "HR User", "System Manager"]


@frappe.whitelist()
def get_program_groups():
	frappe.only_for(ALLOWED_ROLES)
	return frappe.get_all(
		"Training Program", filters={"custom_is_group": 1}, fields=["name"], order_by="name"
	)


@frappe.whitelist()
def get_employees(txt: str = None):
	frappe.only_for(ALLOWED_ROLES)

	filters = {"status": "Active"}
	if txt:
		filters["employee_name"] = ["like", f"%{txt}%"]

	return frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "employee_name", "designation", "department"],
		order_by="employee_name asc",
	)


@frappe.whitelist()
def get_group_status(employee: str, parent_program: str):
	frappe.only_for(ALLOWED_ROLES)

	programs = frappe.get_all(
		"Training Program",
		filters={"custom_parent_training_program": parent_program},
		fields=["name", "custom_number_of_events"],
		order_by="name",
	)

	rows = []
	for program in programs:
		completion = frappe.db.get_value(
			"Training Program Completion",
			{"employee": employee, "training_program": program.name},
			["progress", "is_completed", "completed_on"],
			as_dict=True,
		)
		required = program.custom_number_of_events or 0
		rows.append(
			{
				"training_program": program.name,
				"progress": completion.progress if completion else f"0 / {required}",
				"completed": completion.is_completed if completion else 0,
				"completed_on": completion.completed_on if completion else None,
			}
		)

	group_completion = frappe.db.get_value(
		"Training Program Group Completion",
		{"employee": employee, "parent_training_program": parent_program},
		["name", "is_completed", "completed_on"],
		as_dict=True,
	)

	return {
		"programs": rows,
		"name": group_completion.name if group_completion else None,
		"is_completed": group_completion.is_completed if group_completion else 0,
		"completed_on": group_completion.completed_on if group_completion else None,
	}


@frappe.whitelist()
def download_all_certificates(training_program: str):
	"""Merges every completed employee's certificate for a Training Program (or,
	for a group like LEAP, every completed employee's group certificate) into one
	PDF. Restricted to HR roles - the same people who could already see these
	completion records; a plain Employee has no access to this at all."""
	frappe.only_for(ALLOWED_ROLES)

	from io import BytesIO

	from pypdf import PdfWriter

	is_group, has_certificate = frappe.db.get_value(
		"Training Program", training_program, ["custom_is_group", "custom_has_certificate"]
	)
	if not has_certificate:
		frappe.throw(_("{0} is not configured to issue certificates.").format(training_program))

	if is_group:
		completions = frappe.get_all(
			"Training Program Group Completion",
			filters={"parent_training_program": training_program, "is_completed": 1},
			pluck="name",
			order_by="employee_name",
		)
		doctype = "Training Program Group Completion"
		print_format = "Training Program Group Certificate"
	else:
		completions = frappe.get_all(
			"Training Program Completion",
			filters={"training_program": training_program, "is_completed": 1},
			pluck="name",
			order_by="employee_name",
		)
		doctype = "Training Program Completion"
		print_format = "Training Program Certificate"

	if not completions:
		frappe.throw(_("No employees have completed this program yet."))

	pdf_writer = PdfWriter()
	for name in completions:
		frappe.get_print(doctype, name, print_format, as_pdf=True, output=pdf_writer)

	with BytesIO() as merged_pdf:
		pdf_writer.write(merged_pdf)
		frappe.local.response.filename = f"{training_program} - Certificates.pdf"
		frappe.local.response.filecontent = merged_pdf.getvalue()
		frappe.local.response.type = "download"


PROGRAM_TYPE_EMPLOYEE_FIELDS = {
	"Onboarding": "custom_onboarding_training_program",
	"Buddy Training": "custom_buddy_training_program",
}


def _add_pipeline_employees_to_event(program, event):
	"""Onboarding/Buddy Training events are for specific employees already
	pointed at this program (set when the program itself was created) - unlike
	a Regular training, nobody manually picks attendees for these, so a newly
	created event needs them added automatically."""
	fieldname = PROGRAM_TYPE_EMPLOYEE_FIELDS.get(program.custom_program_type)
	if not fieldname:
		return

	employees = frappe.get_all("Employee", filters={fieldname: program.name}, pluck="name")
	if not employees:
		return

	for employee in employees:
		event.append("employees", {"employee": employee})
	event.save(ignore_permissions=True)


@frappe.whitelist()
def create_events_from_schedule(training_program: str):
	"""Turns each not-yet-created row in a Training Program's Scheduled Sessions
	table into a real Training Event (as a draft - submitting is what triggers
	the Google Calendar invite). For Onboarding/Buddy Training programs, the
	employee(s) already enrolled in this program are added automatically since
	nobody manually picks attendees for those; any other program is created
	with no attendees, same as before."""
	frappe.only_for(ALLOWED_ROLES)

	program = frappe.get_doc("Training Program", training_program)
	if program.custom_number_of_events and program.custom_completed_events >= program.custom_number_of_events:
		frappe.throw(_("This Training Program is completed, so no new events can be created"))
	created = 0

	for row in program.custom_scheduled_sessions:
		if row.event_created:
			continue

		event = frappe.get_doc(
			{
				"doctype": "Training Event",
				"event_name": f"{row.topic} - {training_program}",
				"event_status": "Scheduled",
				"type": "Workshop",
				"location": "Office",
				"start_time": f"{row.start_date} {row.start_time or '10:00:00'}",
				"end_time": f"{row.end_date} {row.end_time or '17:00:00'}",
				"introduction": row.topic,
				"training_program": training_program,
			}
		)
		event.insert(ignore_permissions=True)
		_add_pipeline_employees_to_event(program, event)

		row.db_set("event_created", 1, update_modified=False)
		row.db_set("training_event", event.name, update_modified=False)
		created += 1

	if not created:
		frappe.throw(_("Nothing to create - every row already has an event, or the table is empty."))

	return {"created": created}
