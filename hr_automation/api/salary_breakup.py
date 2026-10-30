import frappe
from frappe.utils import flt, get_first_day, get_last_day, today
from hrms.payroll.utils import (
	COMPONENT_EVAL_GLOBALS,
	_safe_eval,
	get_component_abbr_map,
)

try:
	from hrms.payroll.utils import SALARY_SLIP_EVAL_DEFAULTS
except ImportError:
	# Not exported by every HRMS version - these are the zero defaults a Salary Slip
	# seeds its formula context with.
	SALARY_SLIP_EVAL_DEFAULTS = {
		"gross_pay": 0,
		"net_pay": 0,
		"total_deduction": 0,
		"rounded_total": 0,
		"total_working_hours": 0,
		"hour_rate": 0,
		"year_to_date": 0,
		"month_to_date": 0,
		"gross_year_to_date": 0,
		"ctc": 0,
		"total_earnings": 0,
		"income_from_other_sources": 0,
		"non_taxable_earnings": 0,
		"deductions_before_tax_calculation": 0,
		"tax_exemption_declaration": 0,
		"standard_tax_exemption_amount": 0,
		"annual_taxable_amount": 0,
		"income_tax_deducted_till_date": 0,
		"future_income_tax_deductions": 0,
		"current_month_income_tax": 0,
		"total_income_tax": 0,
	}


def _build_preview_context(base_salary):
	"""Best-effort context for evaluating a Salary Structure's component formulas
	before an Employee exists (Job Offer / Appointment Letter stage). Reuses the
	same abbreviation/default seeding a real Salary Slip starts from, but period
	and attendance-specific variables (payment_days, start_date, ...) can't be
	known yet, so they're approximated as one full, unbroken month - the best
	any pre-hire estimate can do."""
	context = frappe._dict()
	context.update(get_component_abbr_map())
	context.update(SALARY_SLIP_EVAL_DEFAULTS)
	context.base = flt(base_salary)
	context.gross_pay = flt(base_salary)
	context.ctc = flt(base_salary)
	context.payment_days = 30
	context.total_working_days = 30
	context.start_date = get_first_day(today())
	context.end_date = get_last_day(today())
	return context


def _eval_component(row, context):
	"""Mirrors Salary Slip's own eval_condition_and_formula, standalone - same
	formula sandbox (_safe_eval), same condition/formula/amount_based_on_formula
	fields a real payslip would use. A formula referencing something this
	preview context doesn't have (e.g. an Employee-specific field) is skipped
	rather than crashing the whole preview - there's no real employee yet for
	it to resolve against."""
	try:
		if row.condition and not _safe_eval(row.condition, COMPONENT_EVAL_GLOBALS.copy(), context):
			return None
		if row.amount_based_on_formula and row.formula:
			return flt(_safe_eval(row.formula, COMPONENT_EVAL_GLOBALS.copy(), context), row.precision or 2)
		return flt(row.amount)
	except Exception:
		frappe.log_error(
			title="Salary breakup preview: component skipped",
			message=f"Component {row.salary_component} could not be evaluated for preview:\n{frappe.get_traceback()}",
		)
		return None


def calculate_salary_breakup(salary_structure, gross_salary) -> dict:
	"""Live preview of a Salary Structure's actual earnings/deductions formulas
	against a target base salary - not a fixed percentage policy. Shared by the
	Appointment Letter/Job Offer Desk forms (via get_salary_breakup, called from
	salary_breakup.js) and the automatic Appointment Letter creation on Job Offer
	acceptance (apply_salary_breakup), so the two can never drift apart, and a
	change to a component's formula is reflected the next time either runs."""
	if not salary_structure:
		return {"earnings": {}, "deductions": {}}

	structure = frappe.get_doc("Salary Structure", salary_structure)
	context = _build_preview_context(gross_salary)

	earnings, deductions = {}, {}
	for fieldname, bucket in (("earnings", earnings), ("deductions", deductions)):
		for row in sorted(structure.get(fieldname), key=lambda r: r.idx):
			amount = _eval_component(row, context)
			if amount is None:
				continue
			bucket[row.salary_component] = amount
			if row.abbr:
				context[row.abbr] = amount

	return {"earnings": earnings, "deductions": deductions}


@frappe.whitelist()
def get_structure_components(salary_structure):
	structure = frappe.get_doc("Salary Structure", salary_structure)

	def rows(table):
		return [
			{
				"component": row.salary_component,
				"per_month": None if row.amount_based_on_formula else flt(row.amount),
			}
			for row in structure.get(table)
		]

	return {"earnings": rows("earnings"), "deductions": rows("deductions")}


@frappe.whitelist()
def get_salary_breakup(salary_structure, gross_salary):
	return calculate_salary_breakup(salary_structure, gross_salary)


def apply_salary_breakup(doc, gross_salary=None):
	"""Populates (or recalculates) an Appointment Letter's / Job Offer's earnings,
	deductions child tables from its assigned Salary Structure's own formulas and
	Gross Salary, using the same evaluation as the Desk form's own calculator.
	Safe on a brand-new empty doc (adds every row) or an existing one (updates
	matching rows, adds any missing)."""
	gross_salary = gross_salary if gross_salary is not None else doc.gross_salary
	breakup = calculate_salary_breakup(doc.salary_structure, gross_salary)

	for fieldname, values in (
		("earnings", breakup["earnings"]),
		("deductions", breakup["deductions"]),
	):
		existing = {row.component: row for row in doc.get(fieldname)}
		for component, amount in values.items():
			row = existing.get(component)
			if not row:
				row = doc.append(fieldname, {"component": component})
			row.per_month = amount
			row.per_annum = amount * 12
