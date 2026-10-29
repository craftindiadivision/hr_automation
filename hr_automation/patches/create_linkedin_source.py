import frappe

from hr_automation.api.job_openings import LINKEDIN_SOURCE


def execute():
	"""Applicants from a tracked LinkedIn link are tagged with this Source."""
	if not frappe.db.exists("Job Applicant Source", LINKEDIN_SOURCE):
		frappe.get_doc({"doctype": "Job Applicant Source", "source_name": LINKEDIN_SOURCE}).insert(ignore_permissions=True)
