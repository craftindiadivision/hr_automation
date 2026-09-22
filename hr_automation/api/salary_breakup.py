import frappe
from frappe.utils import flt

EARNING_COMPONENTS = [
	"Basic",
	"House Rent Allowance",
	"Conveyance Allowance",
	"Medical Allowance",
	"Special Allowances",
]
EMPLOYER_CONTRIBUTION_COMPONENTS = ["Provident Fund", "ESI", "Welfare Fund"]
DEDUCTION_COMPONENTS = ["Provident Fund", "ESI", "Professional Tax (PT)", "TDS", "Welfare Fund"]


def _professional_tax(basic: float) -> float:
	annual_basis = basic * 6
	if annual_basis < 12000:
		annual_pt = 0
	elif annual_basis <= 17999:
		annual_pt = 320
	elif annual_basis <= 29999:
		annual_pt = 450
	elif annual_basis <= 44999:
		annual_pt = 600
	elif annual_basis <= 99999:
		annual_pt = 750
	elif annual_basis <= 124999:
		annual_pt = 1000
	else:
		annual_pt = 1250
	return annual_pt / 6


def calculate_salary_breakup(gross_salary) -> dict:
	"""Standard CIT salary breakup formula. Single source of truth shared by the
	Appointment Letter/Job Offer Desk forms (via get_salary_breakup, called from
	salary_breakup.js) and the automatic Appointment Letter creation on Job Offer
	acceptance (apply_salary_breakup) - so the two can never drift apart."""
	g = flt(gross_salary)

	basic = g * 0.45
	hra = basic * 0.4
	conveyance = 800
	medical = 1250
	special = g - (basic + hra + conveyance + medical)

	pf = 1800 if basic > 15000 else basic * 0.12
	esi = 0 if g > 21000 else g * 0.0075
	welfare_fund = 50
	professional_tax = _professional_tax(basic)
	tds = g * 0.05 if g > 100000 else 0

	return {
		"earnings": {
			"Basic": basic,
			"House Rent Allowance": hra,
			"Conveyance Allowance": conveyance,
			"Medical Allowance": medical,
			"Special Allowances": special,
		},
		"employer_contribution": {
			"Provident Fund": pf,
			"ESI": esi,
			"Welfare Fund": welfare_fund,
		},
		"deductions": {
			"Provident Fund": pf,
			"ESI": esi,
			"Welfare Fund": welfare_fund,
			"Professional Tax (PT)": professional_tax,
			"TDS": tds,
		},
	}


@frappe.whitelist()
def get_salary_breakup(gross_salary):
	return calculate_salary_breakup(gross_salary)


def apply_salary_breakup(doc, gross_salary=None):
	"""Populates (or recalculates) an Appointment Letter's / Job Offer's earnings,
	employer_contribution and deductions child tables from Gross Salary, using the
	same formula as the Desk form's own calculator. Safe on a brand-new empty doc
	(adds every row) or an existing one (updates matching rows, adds any missing)."""
	gross_salary = gross_salary if gross_salary is not None else doc.gross_salary
	breakup = calculate_salary_breakup(gross_salary)

	for fieldname, values in (
		("earnings", breakup["earnings"]),
		("employer_contribution", breakup["employer_contribution"]),
		("deductions", breakup["deductions"]),
	):
		existing = {row.component: row for row in doc.get(fieldname)}
		for component, amount in values.items():
			row = existing.get(component)
			if not row:
				row = doc.append(fieldname, {"component": component})
			row.per_month = amount
			row.per_annum = amount * 12
