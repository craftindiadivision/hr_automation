import frappe
from frappe import _
from frappe.utils import get_url, random_string


def get_next_appraisal_cycle_for_employee(employee):
	"""Find the lowest-Level Appraisal Cycle this employee doesn't already have an appraisal in.
	Cycles marked custom_trainee_only are skipped for employees who were never on the trainee
	track, so a direct-hire employee never gets routed through a trainee-only cycle."""
	employee_track = frappe.db.get_value(
		"Employee", employee, ["custom_is_trainee", "custom_was_trainee"], as_dict=True
	)
	eligible_for_trainee_cycles = bool(
		employee_track and (employee_track.custom_is_trainee or employee_track.custom_was_trainee)
	)

	cycles = frappe.get_all(
		"Appraisal Cycle",
		filters={"custom_level": ["is", "set"], "status": ["!=", "Completed"]},
		fields=["name", "custom_level", "custom_default_appraisal_template", "custom_trainee_only"],
		order_by="custom_level asc",
	)
	for cycle in cycles:
		if cycle.custom_trainee_only and not eligible_for_trainee_cycles:
			continue
		if not frappe.db.exists(
			"Appraisal", {"employee": employee, "appraisal_cycle": cycle.name, "docstatus": ["!=", 2]}
		):
			return cycle
	return None


def get_self_appraisal_link(employee, company):
	"""Find/create the employee's next-level Appraisal and return a guest self-appraisal link for it.
	Returns None if no leveled Appraisal Cycle is configured/available - callers should just
	omit the link in that case rather than fail the notification."""
	cycle = get_next_appraisal_cycle_for_employee(employee)
	if not cycle:
		return None
	if not cycle.custom_default_appraisal_template:
		frappe.log_error(
			title="Self-appraisal link skipped",
			message=f"Appraisal Cycle {cycle.name} has no Default Appraisal Template set.",
		)
		return None

	appraisal_name = frappe.db.get_value(
		"Appraisal",
		{"employee": employee, "appraisal_cycle": cycle.name, "docstatus": ["!=", 2]},
		"name",
	)
	if not appraisal_name:
		try:
			appraisal = frappe.new_doc("Appraisal")
			appraisal.employee = employee
			appraisal.company = company
			appraisal.appraisal_cycle = cycle.name
			appraisal.appraisal_template = cycle.custom_default_appraisal_template
			appraisal.set_kras_and_rating_criteria()
			appraisal.insert(ignore_permissions=True)
			appraisal_name = appraisal.name
		except Exception:
			frappe.log_error(title="Self-appraisal auto-creation failed", message=frappe.get_traceback())
			return None

	token = frappe.db.get_value("Appraisal", appraisal_name, "custom_self_appraisal_token")
	if not token:
		token = random_string(32)
		frappe.db.set_value(
			"Appraisal", appraisal_name, "custom_self_appraisal_token", token, update_modified=False
		)

	return f"{get_url()}/self-appraisal?token={token}"


@frappe.whitelist(allow_guest=True)
def submit_self_appraisal(token: str, ratings, reflections: str = None):
	name = frappe.db.get_value("Appraisal", {"custom_self_appraisal_token": token}, "name")
	if not name:
		frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)

	if isinstance(ratings, str):
		ratings = frappe.parse_json(ratings)

	frappe.set_user("Administrator")
	doc = frappe.get_doc("Appraisal", name)
	if doc.custom_self_appraisal_submitted:
		return {"message": "already_submitted"}

	rating_map = {r.get("name"): r.get("rating") for r in ratings}
	for row in doc.self_ratings:
		if row.name in rating_map and rating_map[row.name] is not None:
			row.rating = rating_map[row.name]
	if reflections is not None:
		doc.reflections = reflections
	doc.custom_self_appraisal_submitted = 1
	doc.save(ignore_permissions=True)
	return {"message": "submitted"}
