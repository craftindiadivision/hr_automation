import frappe
from frappe import _
from frappe.model.document import Document


class KnowledgeHub(Document):
	def validate(self):
		if self.training_event and frappe.db.get_value("Training Event", self.training_event, "event_status") != "Completed":
			frappe.throw(_("{0} is not marked as a Completed Training Event.").format(self.training_event))

	def on_update(self):
		# Only attendees of the linked event may ever see this record - a public
		# attachment would let anyone with the raw URL bypass that entirely.
		if not self.presentation:
			return

		file_name = frappe.db.get_value(
			"File",
			{"file_url": self.presentation, "attached_to_doctype": self.doctype, "attached_to_name": self.name},
			"name",
		)
		if not file_name:
			return

		file_doc = frappe.get_doc("File", file_name)
		if not file_doc.is_private:
			file_doc.is_private = 1
			file_doc.save(ignore_permissions=True)
			frappe.db.set_value(self.doctype, self.name, "presentation", file_doc.file_url, update_modified=False)
