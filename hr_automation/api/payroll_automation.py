import frappe
from frappe import _
from frappe.utils import add_days, formatdate, get_first_day, getdate, today


def auto_create_monthly_payroll_entry():
	"""Scheduled daily, but only acts on the 1st of the month: creates a Draft
	Payroll Entry for the PREVIOUS calendar month (now fully complete), with
	employees populated the same way the desk's "Get Employee Details" does.
	Never submits anything - HR still reviews and submits it by hand. Skips a
	company if an entry for that exact period already exists, so a scheduler
	retry/misfire never creates a duplicate."""
	if getdate(today()).day != 1:
		return

	previous_month_end = add_days(get_first_day(today()), -1)
	start_date = get_first_day(previous_month_end)
	end_date = previous_month_end

	for company in frappe.get_all("Company", pluck="name"):
		_create_payroll_entry_for_company(company, start_date, end_date)


def _create_payroll_entry_for_company(company, start_date, end_date):
	if frappe.db.exists(
		"Payroll Entry",
		{"company": company, "start_date": start_date, "end_date": end_date, "docstatus": ["!=", 2]},
	):
		return

	# No hardcoded account/currency defaults here - copy them from this company's
	# own most recent Payroll Entry, so the automation always matches however
	# this company's payroll is actually configured, on any site it's deployed to.
	template = frappe.db.get_value(
		"Payroll Entry",
		{"company": company, "docstatus": ["!=", 2]},
		["currency", "exchange_rate", "payroll_payable_account", "cost_center", "payroll_frequency"],
		as_dict=True,
		order_by="creation desc",
	)
	if not template:
		frappe.log_error(
			title="Auto payroll entry skipped",
			message=(
				f"No prior Payroll Entry found for {company} to copy currency/payable account/cost "
				"center settings from. Create the first Payroll Entry manually, then automation can "
				"take over from the next month."
			),
		)
		return

	entry = frappe.new_doc("Payroll Entry")
	entry.company = company
	entry.posting_date = today()
	entry.start_date = start_date
	entry.end_date = end_date
	entry.currency = template.currency
	entry.exchange_rate = template.exchange_rate
	entry.payroll_payable_account = template.payroll_payable_account
	entry.cost_center = template.cost_center
	entry.payroll_frequency = template.payroll_frequency or "Monthly"

	try:
		entry.fill_employee_details()
	except Exception:
		frappe.log_error(
			title="Auto payroll entry skipped - no employees found",
			message=f"{company}, {start_date} to {end_date}:\n\n{frappe.get_traceback()}",
		)
		return

	entry.insert(ignore_permissions=True)
	_create_draft_salary_slips(entry)


def _create_draft_salary_slips(entry):
	from hrms.payroll.doctype.payroll_entry.payroll_entry import create_salary_slips_for_employees

	employees = [emp.employee for emp in entry.employees]
	if not employees:
		return

	args = frappe._dict(
		{
			"salary_slip_based_on_timesheet": entry.salary_slip_based_on_timesheet,
			"payroll_frequency": entry.payroll_frequency,
			"start_date": entry.start_date,
			"end_date": entry.end_date,
			"company": entry.company,
			"posting_date": entry.posting_date,
			"deduct_tax_for_unsubmitted_tax_exemption_proof": entry.deduct_tax_for_unsubmitted_tax_exemption_proof,
			"payroll_entry": entry.name,
			"exchange_rate": entry.exchange_rate,
			"currency": entry.currency,
		}
	)
	# Calling the core helper directly rather than entry.create_salary_slips() -
	# that method backgrounds the job past 30 employees for the desk UI's sake,
	# but this runs inside a scheduled job with no one watching a spinner, so it
	# always runs synchronously here and the notification email stays accurate.
	create_salary_slips_for_employees(employees, args, publish_progress=False)

	slips = frappe.get_all(
		"Salary Slip", filters={"payroll_entry": entry.name, "docstatus": ["!=", 2]}, pluck="name"
	)
	if slips:
		_notify_salary_slips_created(entry, len(slips))


def _notify_salary_slips_created(entry, slip_count):
	recipients = _get_notification_recipients()
	if not recipients:
		frappe.log_error(
			title="Salary Slips created, but no notification recipients configured",
			message=(
				f"{slip_count} Draft Salary Slip(s) created for {entry.company}, {entry.start_date} to "
				f"{entry.end_date}, but HR Automation Settings has no Assessment Notification Recipients "
				"configured to email. Add at least one row there."
			),
		)
		return

	frappe.sendmail(
		recipients=recipients,
		subject=_("Salary Slips created for {0} - {1} to {2}").format(
			entry.company, formatdate(entry.start_date), formatdate(entry.end_date)
		),
		message=frappe.render_template(
			"""
			<p>Draft Salary Slips have been created for {{ count }} employee(s) of {{ company }},
			for the period {{ start_date }} to {{ end_date }}.</p>
			<p>Please verify and submit them from the desk.</p>
			""",
			{
				"company": entry.company,
				"start_date": formatdate(entry.start_date),
				"end_date": formatdate(entry.end_date),
				"count": slip_count,
			},
		),
		reference_doctype="Payroll Entry",
		reference_name=entry.name,
	)


def _get_notification_recipients():
	settings = frappe.get_single("HR Automation Settings")
	return [row.user_email for row in settings.assessment_notification_recipients if row.user_email]
