import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, get_url, getdate, now_datetime, random_string, today

from hr_automation.api.link_expiry import check_email_matches, check_not_expired
from hr_automation.api.salary_revision import apply_next_phase


# Template for each appraisal stage, set in HR Automation Settings.
STAGE_TEMPLATE_FIELDS = {
	"Training": "training_appraisal_template",
	"Probation": "probation_appraisal_template",
	"Annual": "annual_appraisal_template",
}


def get_self_appraisal_link(employee, company, stage):
	"""Finds/creates the employee's Appraisal for this stage and returns a guest
	self-appraisal link to it. Raises if the Appraisal can't be created, so the
	caller can hold the notification and tell HR instead of sending a broken one."""
	appraisal_name = get_or_create_stage_appraisal(employee, company, stage)

	token = frappe.db.get_value("Appraisal", appraisal_name, "custom_self_appraisal_token")
	if not token:
		token = random_string(32)
		frappe.db.set_value(
			"Appraisal", appraisal_name, "custom_self_appraisal_token", token, update_modified=False
		)
	# Stamped every time this is called (it's only ever called right before the
	# email is actually sent) so a resend restarts the 24-hour validity window.
	frappe.db.set_value(
		"Appraisal", appraisal_name, "custom_self_appraisal_token_sent_at", now_datetime(), update_modified=False
	)

	return f"{get_url()}/self-appraisal?token={token}"


def get_or_create_stage_appraisal(employee, company, stage) -> str:
	"""The employee's open (draft) Appraisal covering today is reused; otherwise
	a new one is created in this month's Appraisal Cycle with the stage's
	template. One cycle per month keeps HRMS's "no overlapping appraisals per
	employee" rule satisfied, since an employee's appraisals are months apart."""
	current_date = getdate(today())
	draft = _get_open_appraisal(employee, current_date)
	if draft:
		if not frappe.db.get_value("Appraisal", draft, "custom_appraisal_stage"):
			frappe.db.set_value("Appraisal", draft, "custom_appraisal_stage", stage, update_modified=False)
		apply_next_phase(draft, employee)
		return draft

	template = frappe.db.get_single_value("HR Automation Settings", STAGE_TEMPLATE_FIELDS[stage])
	if not template:
		frappe.throw(_("Set the {0} Appraisal Template in HR Automation Settings").format(_(stage)))

	appraisal = frappe.new_doc("Appraisal")
	appraisal.employee = employee
	appraisal.company = company
	appraisal.appraisal_cycle = get_monthly_appraisal_cycle(company, current_date)
	appraisal.start_date, appraisal.end_date = frappe.db.get_value(
		"Appraisal Cycle", appraisal.appraisal_cycle, ["start_date", "end_date"]
	)
	appraisal.appraisal_template = template
	appraisal.custom_appraisal_stage = stage
	appraisal.set_kras_and_rating_criteria()
	appraisal.insert(ignore_permissions=True)
	apply_next_phase(appraisal.name, employee)
	return appraisal.name


def _get_open_appraisal(employee, date):
	"""A draft Appraisal of this employee whose cycle covers `date` (Appraisals
	made from the form often have no dates of their own, so go by the cycle)."""
	for row in frappe.get_all(
		"Appraisal", filters={"employee": employee, "docstatus": 0}, fields=["name", "appraisal_cycle"]
	):
		start, end, status = frappe.db.get_value(
			"Appraisal Cycle", row.appraisal_cycle, ["start_date", "end_date", "status"]
		)
		if status != "Completed" and getdate(start) <= date <= getdate(end):
			return row.name
	return None


def get_monthly_appraisal_cycle(company, date) -> str:
	"""This month's Appraisal Cycle for the company, created on first use."""
	start, end = get_first_day(date), get_last_day(date)
	existing = frappe.db.get_value(
		"Appraisal Cycle",
		{"company": company, "start_date": start, "end_date": end, "status": ["!=", "Completed"]},
		"name",
	)
	if existing:
		return existing

	cycle_name = _("Appraisals - {0}").format(start.strftime("%b %Y"))
	if frappe.db.exists("Appraisal Cycle", cycle_name):
		cycle_name += f" - {frappe.get_cached_value('Company', company, 'abbr')}"
	cycle = frappe.get_doc(
		{
			"doctype": "Appraisal Cycle",
			"cycle_name": cycle_name,
			"company": company,
			"start_date": start,
			"end_date": end,
			"status": "In Progress",
			# Same evaluation method HR already uses on their own cycles.
			"kra_evaluation_method": frappe.db.get_value(
				"Appraisal Cycle", {"company": company}, "kra_evaluation_method", order_by="creation desc"
			)
			or "Automated Based on Goal Progress",
		}
	)
	cycle.insert(ignore_permissions=True)
	return cycle.name


def _resolve_appraisal_by_token(token: str, email: str):
	name = frappe.db.get_value("Appraisal", {"custom_self_appraisal_token": token}, "name")
	if not name:
		frappe.throw(_("Invalid or expired link"), frappe.DoesNotExistError)

	# The token is the proof of authorization here; elevate so Guest can read
	# (and, for submit, later save) a document it has no standing permission on.
	frappe.set_user("Administrator")
	doc = frappe.get_doc("Appraisal", name)
	stored_email = (
		frappe.db.get_value("Employee", doc.employee, "user_id")
		or frappe.db.get_value("Employee", doc.employee, "company_email")
		or frappe.db.get_value("Employee", doc.employee, "personal_email")
	)
	check_email_matches(stored_email, email)
	return doc


@frappe.whitelist(allow_guest=True)
def get_self_appraisal_by_token(token: str, email: str):
	doc = _resolve_appraisal_by_token(token, email)
	if doc.custom_self_appraisal_submitted:
		return {"submitted": True, "employee_name": doc.employee_name}
	check_not_expired(doc.custom_self_appraisal_token_sent_at)

	return {
		"submitted": False,
		"employee_name": doc.employee_name,
		"reflections": doc.reflections or "",
		"ratings": [
			{
				"name": row.name,
				"criteria": row.criteria,
				"weightage": row.per_weightage,
				"rating": row.rating or 0,
			}
			for row in doc.self_ratings
		],
	}


@frappe.whitelist(allow_guest=True)
def submit_self_appraisal(token: str, email: str, ratings, reflections: str = None):
	if isinstance(ratings, str):
		ratings = frappe.parse_json(ratings)

	doc = _resolve_appraisal_by_token(token, email)
	if doc.custom_self_appraisal_submitted:
		return {"message": "already_submitted"}
	check_not_expired(doc.custom_self_appraisal_token_sent_at)

	rating_map = {r.get("name"): r.get("rating") for r in ratings}
	for row in doc.self_ratings:
		if row.name in rating_map and rating_map[row.name] is not None:
			row.rating = rating_map[row.name]
	if reflections is not None:
		doc.reflections = reflections
	doc.custom_self_appraisal_submitted = 1
	doc.save(ignore_permissions=True)
	return {"message": "submitted"}
