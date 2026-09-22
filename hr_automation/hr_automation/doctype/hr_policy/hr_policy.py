import frappe
from frappe.model.document import Document


class HRPolicy(Document):
	def before_insert(self):
		# Every current employee gets an acknowledgement row; new employees added
		# later are appended automatically via the Employee after_insert hook.
		existing = {row.employee for row in self.employee_acknowledgements}
		for employee in frappe.get_all("Employee", filters={"status": "Active"}, pluck="name"):
			if employee not in existing:
				self.append("employee_acknowledgements", {"employee": employee})
