import os
import subprocess
import tempfile

import frappe

HR_ROLES = {"System Manager", "HR Manager", "HR User"}


def _attendee_condition_sql(user: str) -> str:
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return "1=0"

	employee = frappe.db.escape(employee)
	return (
		"`tabKnowledge Hub`.training_event in ("
		"select tee.parent from `tabTraining Event Employee` tee "
		f"where tee.employee = {employee} and tee.attendance = 'Present'"
		")"
	)


def get_permission_query_conditions(user):
	user = user or frappe.session.user
	if user == "Administrator" or HR_ROLES & set(frappe.get_roles(user)):
		return ""
	return _attendee_condition_sql(user)


def has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if user == "Administrator" or HR_ROLES & set(frappe.get_roles(user)):
		return True
	if ptype not in ("read", "print", "email", "report", "share"):
		return True

	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee or not doc.training_event:
		return False

	return bool(
		frappe.db.exists(
			"Training Event Employee",
			{"parent": doc.training_event, "employee": employee, "attendance": "Present"},
		)
	)


def queue_conversion(doc, method=None):
	"""Hook: Knowledge Hub on_update. A new/changed presentation is converted to
	PDF in the background (LibreOffice can take several seconds), so saving the
	record itself isn't held up waiting for it."""
	if not doc.presentation or doc.presentation == doc.last_converted_presentation:
		return

	frappe.enqueue(
		"hr_automation.api.knowledge_hub.convert_presentation_to_pdf",
		queue="short",
		doctype=doc.doctype,
		docname=doc.name,
	)


def convert_presentation_to_pdf(doctype: str, docname: str):
	doc = frappe.get_doc(doctype, docname)
	if not doc.presentation:
		return

	file_doc = frappe.get_doc(
		"File",
		{
			"file_url": doc.presentation,
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
		},
	)
	input_path = file_doc.get_full_path()

	with tempfile.TemporaryDirectory() as tmp_dir:
		try:
			subprocess.run(
				["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp_dir, input_path],
				check=True,
				timeout=120,
				capture_output=True,
			)
		except Exception:
			frappe.log_error(
				title="Presentation to PDF conversion failed",
				message=f"Knowledge Hub {docname}: {frappe.get_traceback()}",
			)
			return

		pdf_filename = os.path.splitext(os.path.basename(input_path))[0] + ".pdf"
		pdf_path = os.path.join(tmp_dir, pdf_filename)
		if not os.path.exists(pdf_path):
			frappe.log_error(
				title="Presentation to PDF conversion failed",
				message=f"Knowledge Hub {docname}: expected output not found at {pdf_path}",
			)
			return

		with open(pdf_path, "rb") as f:
			pdf_content = f.read()

		# Also render each page to a plain image. This is what viewers actually
		# see - the master PDF is never sent to their browser at all, only these.
		image_prefix = os.path.join(tmp_dir, "slide")
		try:
			subprocess.run(
				["pdftoppm", "-png", "-r", "120", pdf_path, image_prefix],
				check=True,
				timeout=120,
				capture_output=True,
			)
		except Exception:
			frappe.log_error(
				title="Presentation slide image generation failed",
				message=f"Knowledge Hub {docname}: {frappe.get_traceback()}",
			)
			return

		slide_files = sorted(f for f in os.listdir(tmp_dir) if f.startswith("slide") and f.endswith(".png"))
		slide_contents = []
		for filename in slide_files:
			with open(os.path.join(tmp_dir, filename), "rb") as f:
				slide_contents.append((filename, f.read()))

	# Replace any previously auto-generated PDF/slide images for this record before attaching new ones.
	old_pdf_url = frappe.db.get_value(doctype, docname, "presentation_pdf")
	if old_pdf_url:
		frappe.db.delete(
			"File",
			{"file_url": old_pdf_url, "attached_to_doctype": doctype, "attached_to_name": docname},
		)
	old_slide_urls = frappe.get_all(
		"Knowledge Hub Slide", filters={"parent": docname, "parenttype": doctype}, pluck="image"
	)
	for url in old_slide_urls:
		frappe.db.delete("File", {"file_url": url, "attached_to_doctype": doctype, "attached_to_name": docname})

	pdf_file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": pdf_filename,
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"attached_to_field": "presentation_pdf",
			"is_private": 1,
			"content": pdf_content,
		}
	)
	pdf_file.insert(ignore_permissions=True)

	slide_urls = []
	for filename, content in slide_contents:
		image_file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": filename,
				"attached_to_doctype": doctype,
				"attached_to_name": docname,
				"attached_to_field": "slides",
				"is_private": 1,
				"content": content,
			}
		)
		image_file.insert(ignore_permissions=True)
		slide_urls.append(image_file.file_url)

	fresh = frappe.get_doc(doctype, docname)
	fresh.set("slides", [])
	for url in slide_urls:
		fresh.append("slides", {"image": url})
	fresh.presentation_pdf = pdf_file.file_url
	fresh.last_converted_presentation = doc.presentation
	fresh.save(ignore_permissions=True)
	frappe.db.commit()
	frappe.publish_realtime("knowledge_hub_pdf_ready", {"name": docname}, doctype=doctype, docname=docname)
