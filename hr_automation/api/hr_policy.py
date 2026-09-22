import frappe
from frappe import _


def add_employee_to_all_policies(doc, method=None):
	"""Hook: Employee after_insert. Every HR Policy keeps one acknowledgement row
	per employee, so a newly created employee needs to be appended to every
	policy that already exists."""
	for name in frappe.get_all("HR Policy", pluck="name"):
		policy = frappe.get_doc("HR Policy", name)
		if any(row.employee == doc.name for row in policy.employee_acknowledgements):
			continue
		policy.append("employee_acknowledgements", {"employee": doc.name})
		policy.save(ignore_permissions=True)


@frappe.whitelist()
def acknowledge(hr_policy: str):
	"""Lets the current user tick their own row only - there is no general
	write access to this table, so this is the only way any row ever changes."""
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	if not employee:
		frappe.throw(_("No Employee record is linked to your account."))

	doc = frappe.get_doc("HR Policy", hr_policy)
	row = next((r for r in doc.employee_acknowledgements if r.employee == employee), None)
	if not row:
		frappe.throw(_("You are not listed for acknowledgement on this policy."))

	if row.acknowledged:
		return {"already": True}

	frappe.db.set_value(
		"HR Policy Acknowledgement",
		row.name,
		{"acknowledged": 1, "acknowledged_on": frappe.utils.now_datetime()},
		update_modified=False,
	)
	frappe.db.commit()
	return {"success": True}
