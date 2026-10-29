import frappe
from frappe import _

from hrms.hr.doctype.interview.interview import Interview

from hr_automation.api.recruitment_automation import FINAL_ROUND_INTERVIEW_TYPE


class CustomInterview(Interview):
	def show_job_applicant_update_dialog(self):
		"""HRMS asks on submit whether to update the Job Applicant. Instead: a
		Rejected interview (any round) rejects the applicant straight away; a
		Cleared one asks to mark them Accepted only for the Final Round, since
		clearing an earlier round doesn't mean the applicant is accepted."""
		if self.status == "Cleared":
			if self.interview_type == FINAL_ROUND_INTERVIEW_TYPE:
				super().show_job_applicant_update_dialog()
			return
		if self.status != "Rejected":
			return

		applicant = frappe.get_doc("Job Applicant", self.job_applicant)
		if applicant.status == "Rejected":
			return
		applicant.status = "Rejected"
		# Older applicants may lack fields made mandatory later (e.g. Date of
		# Birth); that shouldn't block recording the rejection.
		applicant.flags.ignore_mandatory = True
		applicant.save(ignore_permissions=True)
		frappe.msgprint(
			_("Job Applicant {0} has been marked as Rejected.").format(frappe.bold(applicant.applicant_name)),
			alert=True,
			indicator="red",
		)
