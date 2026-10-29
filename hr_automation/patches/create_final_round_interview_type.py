import frappe

from hr_automation.api.recruitment_automation import FINAL_ROUND_INTERVIEW_TYPE


def execute():
	"""Final Round interviews capture the agreed Gross Salary. Expected skills
	are left for HR to fill in, like the other Interview Types."""
	if frappe.db.exists("Interview Type", FINAL_ROUND_INTERVIEW_TYPE):
		return
	interview_type = frappe.new_doc("Interview Type")
	interview_type.interview_type_name = FINAL_ROUND_INTERVIEW_TYPE
	interview_type.flags.ignore_mandatory = True
	interview_type.insert(ignore_permissions=True)
