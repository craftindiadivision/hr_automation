import frappe


def execute():
	"""Job Offer: the Documents Verified checkbox became the Document
	Verification select (Documents Accepted / Documents Rejected)."""
	if not frappe.db.has_column("Job Offer", "custom_document_status"):
		# Fixtures (where the new field lives) sync after patches run.
		from frappe.utils.fixtures import sync_fixtures

		sync_fixtures("hr_automation")
	if frappe.db.has_column("Job Offer", "custom_documents_verified"):
		frappe.db.sql(
			"""update `tabJob Offer` set custom_document_status = 'Documents Accepted'
			where custom_documents_verified = 1 and ifnull(custom_document_status, '') = ''"""
		)
	if frappe.db.exists("Custom Field", "Job Offer-custom_documents_verified"):
		frappe.delete_doc("Custom Field", "Job Offer-custom_documents_verified", ignore_permissions=True)
