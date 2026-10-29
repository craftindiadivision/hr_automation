import frappe
from frappe import _
from frappe.utils import add_days, formatdate, getdate, now_datetime, today

from hr_automation.api.leave_management import assign_probation_leave_policy
from hr_automation.api.onboarding_details import ONBOARDING_FIELDS


def create_onboarding_program(doc, method=None):
	"""Hook: Employee after_insert / on_update. Enrolls the employee into the
	Onboarding Training Program for their joining date, named from HR Automation
	Settings - employees who join on the same day share one program and its
	events. Changing the joining date moves them to the matching program and
	drops them from that program's upcoming events. If no Onboarding Event Names
	are configured yet, nothing is created (no invented number of generic events)."""
	if not doc.date_of_joining or doc.custom_buddy_training_program:
		return

	before = doc.get_doc_before_save()
	if before and before.date_of_joining == doc.date_of_joining:
		return
	old_program = before.custom_onboarding_training_program if before else None

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

	if old_program and old_program != program_name:
		_remove_employee_from_upcoming_events(doc.name, old_program)

	frappe.db.set_value(
		"Employee", doc.name, "custom_onboarding_training_program", program_name, update_modified=False
	)


def _remove_employee_from_upcoming_events(employee: str, training_program: str):
	events = frappe.get_all(
		"Training Event",
		filters={
			"training_program": training_program,
			"docstatus": ["!=", 2],
			"start_time": [">", now_datetime()],
		},
		pluck="name",
	)
	if events:
		frappe.db.delete("Training Event Employee", {"parent": ["in", events], "employee": employee})


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


def create_employee_on_completion(doc, method=None):
	"""Employee Onboarding on_update_after_submit - only for onboardings created
	before the Appointment Letter took over (create_employee_from_appointment_letter)."""
	if doc.boarding_status != "Completed" or not doc.has_value_changed("boarding_status"):
		return
	employee = create_employee(
		frappe._dict(
			job_applicant=doc.job_applicant,
			job_offer=doc.job_offer,
			company=doc.company,
			employee_name=doc.employee_name,
			designation=doc.designation,
			department=doc.department,
			grade=doc.employee_grade,
			date_of_joining=doc.date_of_joining,
			holiday_list=doc.holiday_list,
			salary_structure=doc.salary_structure,
			gross_salary=doc.gross_salary,
			shift_type=doc.shift_type,
			leave_policy=doc.leave_policy,
		)
	)
	frappe.db.set_value("Employee Onboarding", doc.name, "employee", employee, update_modified=False)


def create_employee_from_appointment_letter(letter) -> str:
	"""Called when an Appointment Letter is Accepted (no Employee Onboarding
	any more): creates the Employee and everything that goes with joining."""
	employee = create_employee(
		frappe._dict(
			job_applicant=letter.job_applicant,
			job_offer=letter.custom_job_offer,
			company=letter.company,
			employee_name=letter.applicant_name,
			designation=letter.designation,
			date_of_joining=letter.appointment_date,
			holiday_list=letter.custom_holiday_list,
			salary_structure=letter.salary_structure,
			gross_salary=letter.gross_salary,
			shift_type=letter.shift_type,
			leave_policy=letter.leave_policy,
		)
	)
	frappe.db.set_value("Appointment Letter", letter.name, "custom_employee", employee, update_modified=False)
	return employee


def check_ready_for_employee(
	job_applicant,
	holiday_list,
	leave_policy,
	date_of_joining=None,
	salary_structure=None,
	gross_salary=None,
	shift_type=None,
	for_letter=False,
):
	"""What create_employee needs - checked before an Appointment Letter goes
	out, since an Online acceptance creates the Employee with nobody watching."""
	missing = [
		label
		for label, value in (
			(_("Holiday List"), holiday_list),
			(_("Probation Leave Policy"), leave_policy),
			# The Appointment Letter must carry everything the Employee's
			# assignments are made from, so none is silently skipped.
			*(
				(
					(_("Salary Structure"), salary_structure),
					(_("Gross Salary"), gross_salary),
					(_("Shift Type"), shift_type),
				)
				if for_letter
				else ()
			),
		)
		if not value
	]
	if missing:
		names = ", ".join(missing[:-1]) + _(" and ") + missing[-1] if len(missing) > 1 else missing[0]
		frappe.throw(_("Set {0} on the Appointment Letter first").format(names))
	if date_of_joining:
		from_date, to_date = frappe.db.get_value("Holiday List", holiday_list, ["from_date", "to_date"])
		if not (getdate(from_date) <= getdate(date_of_joining) <= getdate(to_date)):
			frappe.throw(
				_("Holiday List {0} runs from {1} to {2} and doesn't cover the joining date {3}. Pick the right year's Holiday List.").format(
					holiday_list, formatdate(from_date), formatdate(to_date), formatdate(date_of_joining)
				)
			)
	dob, gender = frappe.db.get_value("Job Applicant", job_applicant, ["custom_date_of_birth", "custom_gender"])
	if not dob or not gender:
		frappe.throw(
			_("Job Applicant {0} is missing Date of Birth and/or Gender. Fill these in on the Job Applicant first.").format(
				job_applicant
			)
		)


def create_employee(values) -> str:
	"""Creates the Employee (with the onboarding details and uploaded documents)
	plus their Holiday List, Salary Structure and Shift assignments and
	probation leave. Returns the existing Employee if there already is one."""
	existing = frappe.db.get_value("Employee", {"job_applicant": values.job_applicant}, "name")
	if existing:
		return existing

	check_ready_for_employee(values.job_applicant, values.holiday_list, values.leave_policy, values.date_of_joining)
	applicant = frappe.get_doc("Job Applicant", values.job_applicant)
	offer_type = (
		frappe.db.get_value("Job Offer", values.job_offer, "custom_employee_type") if values.job_offer else None
	)
	documents = frappe.get_all(
		"Job Offer Document",
		filters={"parent": values.job_offer, "parentfield": "custom_onboarding_documents"},
		fields=["document_name", "file", "uploaded_on"],
		order_by="idx asc",
	)

	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": values.employee_name,
			"employee_name": values.employee_name,
			"company": values.company,
			"department": values.department,
			"designation": values.designation,
			"grade": values.grade,
			"date_of_birth": applicant.custom_date_of_birth,
			"gender": applicant.custom_gender,
			"date_of_joining": values.date_of_joining,
			"job_applicant": values.job_applicant,
			"personal_email": applicant.get("personal_email") or applicant.email_id,
			"status": "Active",
			"custom_is_trainee": 1 if offer_type == "Trainee" else 0,
			"custom_is_employee": 1 if offer_type == "Employee" else 0,
			"custom_probation_leave_policy": values.leave_policy,
			"custom_onboarding_documents": documents,
		}
	)
	for fieldname in ONBOARDING_FIELDS:
		value = applicant.get(fieldname)
		if value and fieldname != "personal_email":
			employee.set(fieldname, value)
	employee.insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "Holiday List Assignment",
			"applicable_for": "Employee",
			"assigned_to": employee.name,
			"employee_company": values.company,
			"holiday_list": values.holiday_list,
			"from_date": values.date_of_joining,
			"naming_series": "HR-HLA-.YYYY.-",
		}
	).insert(ignore_permissions=True).submit()

	create_salary_structure_assignment(values, employee.name)
	create_shift_assignment(values, employee.name)
	# Probation leave only (a trainee's starts after 3 months, via the daily
	# allocate_probation_leave); the confirmed policy of each leave year is
	# assigned once probation ends - see leave_management.allocate_regular_leave.
	assign_probation_leave_policy(employee.name)
	return employee.name


def create_salary_structure_assignment(doc, employee: str):
	if not doc.salary_structure:
		return

	frappe.get_doc(
		{
			"doctype": "Salary Structure Assignment",
			"employee": employee,
			"salary_structure": doc.salary_structure,
			"company": doc.company,
			"currency": frappe.get_cached_value("Company", doc.company, "default_currency"),
			"from_date": frappe.db.get_value("Employee", employee, "date_of_joining"),
			"base": doc.gross_salary,
		}
	).insert(ignore_permissions=True).submit()


def create_shift_assignment(doc, employee: str):
	if not doc.shift_type:
		return

	date_of_joining = frappe.db.get_value("Employee", employee, "date_of_joining")
	frappe.get_doc(
		{
			"doctype": "Shift Assignment",
			"employee": employee,
			"shift_type": doc.shift_type,
			"company": doc.company,
			"start_date": date_of_joining,
			"end_date": _get_current_fiscal_year_end_date(doc.company, date_of_joining),
		}
	).insert(ignore_permissions=True).submit()


def _get_current_fiscal_year_end_date(company, date_of_joining):
	from erpnext.accounts.utils import get_fiscal_year

	fiscal_year = get_fiscal_year(date=date_of_joining, company=company, as_dict=True, verbose=0)
	return fiscal_year.year_end_date
