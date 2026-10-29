import frappe

from hr_automation.api.recruitment_automation import get_status_from_feedback


def execute():
	"""Interviews still Pending / Under Review although all their feedback was
	submitted before the status automation existed."""
	for name in frappe.get_all(
		"Interview", filters={"docstatus": 0, "status": ["in", ["Pending", "Under Review"]]}, pluck="name"
	):
		if not frappe.db.exists("Interview Feedback", {"interview": name, "docstatus": 1}):
			continue
		status = get_status_from_feedback(name)
		if status in ("Cleared", "Rejected"):
			frappe.db.set_value("Interview", name, "status", status, update_modified=False)
