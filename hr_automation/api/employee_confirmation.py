import frappe
from frappe import _
from frappe.utils import today

# HRMS's standard self-rating scale is 0-5; this is the bar an Appraisal's
# Final Score must clear for confirmation to happen automatically. Adjust if
# your organisation scores on a different scale.
CONFIRMATION_MIN_SCORE = 3


CONFIRMATION_PRINT_FORMAT = "Confirmation as Employee"


def trigger_confirmation_on_appraisal_submit(doc, method=None):
	"""Appraisal on_submit: if this is the employee's Probation appraisal (its
	stage, set when the appraisal was created) and the score clears the bar,
	sets this Appraisal's Confirmation Date and the Employee's and emails the
	employee the
	Confirmation as Employee letter - a print format of
	this Appraisal, which HR can also print from here. Falls back to a clear
	alert (not a hard error, so the appraisal itself still submits) whenever
	something's missing."""
	if doc.get("custom_appraisal_stage") != "Probation":
		return

	if (doc.final_score or 0) < CONFIRMATION_MIN_SCORE:
		frappe.msgprint(
			_(
				"{0} scored {1} on their probation appraisal, below the {2} needed for confirmation, so "
				"they have not been confirmed. To extend probation, change Probation End Date on the "
				"Employee - their next appraisal and confirmed leave move with it. Otherwise, start the "
				"separation."
			).format(doc.employee_name, doc.final_score or 0, CONFIRMATION_MIN_SCORE),
			title=_("Not Confirmed"),
			indicator="orange",
		)
		return

	if frappe.db.exists(
		"Appraisal",
		{
			"employee": doc.employee,
			"docstatus": 1,
			"name": ["!=", doc.name],
			"custom_confirmation_date": ["is", "set"],
		},
	):
		# Already confirmed by another appraisal - don't reprocess on an amended/resubmitted one.
		return
	doc.db_set("custom_confirmation_date", today(), update_modified=False)
	# Employee master's own Confirmation Date
	frappe.db.set_value("Employee", doc.employee, "final_confirmation_date", today())

	email = (
		frappe.db.get_value("Employee", doc.employee, "user_id")
		or frappe.db.get_value("Employee", doc.employee, "company_email")
		or frappe.db.get_value("Employee", doc.employee, "personal_email")
	)
	if not email:
		frappe.msgprint(
			_(
				"{0} has been confirmed, but no email was found to send the letter. Print Confirmation "
				"as Employee from this Appraisal and hand it over."
			).format(doc.employee_name),
			alert=True,
			indicator="orange",
		)
		return

	company = frappe.db.get_value("Employee", doc.employee, "company")
	frappe.sendmail(
		recipients=[email],
		subject=_("Confirmation as Employee - {0}").format(company),
		message=frappe.render_template(
			"<p>Dear {{ employee_name }},</p><p>Congratulations! Please find your confirmation letter attached.</p>",
			{"employee_name": doc.employee_name},
		),
		attachments=[frappe.attach_print("Appraisal", doc.name, print_format=CONFIRMATION_PRINT_FORMAT)],
		reference_doctype="Appraisal",
		reference_name=doc.name,
	)
	frappe.msgprint(
		_("{0} has been confirmed. Confirmation letter emailed to {1}.").format(doc.employee_name, email),
		alert=True,
		indicator="green",
	)
