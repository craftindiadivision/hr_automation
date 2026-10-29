import frappe


def execute():
	"""Manager feedback moved from the Appraisal to its own Pre-Appraisal Feedback."""
	for name in ['Appraisal-custom_feedback_due_by', 'Appraisal-custom_feedback_requested_on', 'Appraisal-custom_performance_feedback', 'Appraisal-custom_feedback_token']:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
