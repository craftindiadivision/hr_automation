import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeSurvey(Document):
	@frappe.whitelist()
	def set_employees(self):
		"""Pull employees into the recipients list based on the selected filters.
		Only used to address invite emails - never linked to any response."""
		self.check_permission("write")

		filters = {"status": "Active"}
		if self.company:
			filters["company"] = self.company
		if self.department:
			filters["department"] = self.department
		if self.branch:
			filters["branch"] = self.branch

		employees = frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name", "user_id", "company_email", "personal_email"],
		)

		already_added = {row.employee for row in self.recipients}
		added = 0
		skipped_no_email = 0

		for emp in employees:
			if emp.name in already_added:
				continue

			email = emp.user_id or emp.company_email or emp.personal_email
			if not email:
				skipped_no_email += 1
				continue

			self.append(
				"recipients",
				{"employee": emp.name, "employee_name": emp.employee_name, "email": email},
			)
			added += 1

		if skipped_no_email:
			frappe.msgprint(
				_("Skipped {0} employee(s) with no email address on file.").format(skipped_no_email)
			)
		if not added and not skipped_no_email:
			frappe.msgprint(_("No new employees found for the selected criteria."))

		return self
