import frappe
from frappe.query_builder.functions import IfNull

ALLOWED_ROLES = ["HR Manager", "HR User", "System Manager"]


def _is_root(value) -> bool:
	return str(value).lower() in ("1", "true", "yes")


@frappe.whitelist()
def get_children(doctype: str = None, parent: str = None, is_root=False, **filters):
	"""Returns direct reports of `parent` (or top-level employees when is_root)."""
	frappe.only_for(ALLOWED_ROLES)

	reports_to = "" if _is_root(is_root) else (parent or "")

	Employee = frappe.qb.DocType("Employee")
	employees = (
		frappe.qb.from_(Employee)
		.select(
			Employee.name.as_("value"),
			Employee.employee_name.as_("title"),
		)
		.where(IfNull(Employee.reports_to, "") == reports_to)
		.where(Employee.status == "Active")
		.orderby(Employee.employee_name)
	).run(as_dict=True)

	for emp in employees:
		emp["expandable"] = bool(
			frappe.db.exists("Employee", {"reports_to": emp["value"], "status": "Active"})
		)

	return employees


def _get_files(doctype: str, name: str, source: str) -> list[dict]:
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": name},
		fields=["name", "file_name", "file_url", "is_private", "creation"],
	)
	for f in files:
		f["source"] = source
	return files


@frappe.whitelist()
def get_employee_attachments(employee: str):
	frappe.only_for(ALLOWED_ROLES)

	if not frappe.db.exists("Employee", employee):
		frappe.throw(frappe._("Employee {0} not found").format(employee))
	job_applicant = frappe.db.get_value("Employee", employee, "job_applicant")

	files = _get_files("Employee", employee, "Employee")

	if job_applicant:
		files += _get_files("Job Applicant", job_applicant, "Job Application")

		appointment_letters = frappe.get_all(
			"Appointment Letter", filters={"job_applicant": job_applicant}, pluck="name"
		)
		for appointment_letter in appointment_letters:
			files += _get_files("Appointment Letter", appointment_letter, "Appointment Letter")

	files.sort(key=lambda f: f["creation"], reverse=True)
	return files
