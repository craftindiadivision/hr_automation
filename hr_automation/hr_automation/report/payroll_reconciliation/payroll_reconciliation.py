# Copyright (c) 2026, Craft Interactive Technology and contributors
# For license information, please see license.txt

"""Month-on-month payroll reconciliation: explains how last month's total net
pay became this month's - joiners, leavers, and each employee whose pay went
up or down (with the likely reason) - so payroll can be checked before it's
submitted. Draft Salary Slips can be included (the usual case, since the
check happens before payroll is submitted)."""

import frappe
from frappe import _
from frappe.utils import add_months, flt, formatdate, getdate

MONTHS = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]
NEW_JOINER, LEFT, NOT_PAID_LAST, NOT_PAID_THIS, INCREASED, DECREASED, NO_CHANGE = (
	"New Joiner",
	"Left",
	"Not Paid Last Month",
	"Not Paid This Month",
	"Increased",
	"Decreased",
	"No Change",
)
CHANGE_ORDER = {
	NEW_JOINER: 0,
	LEFT: 1,
	NOT_PAID_LAST: 2,
	NOT_PAID_THIS: 3,
	INCREASED: 4,
	DECREASED: 5,
	NO_CHANGE: 6,
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	this_start = getdate(f"{filters.year}-{MONTHS.index(filters.month) + 1:02d}-01")
	last_start = add_months(this_start, -1)

	last = _get_slips(filters.company, last_start, include_draft=filters.include_draft)
	this = _get_slips(filters.company, this_start, include_draft=filters.include_draft)
	rows = _compare(last, this, this_start)

	return (
		_columns(last_start, this_start),
		rows,
		None,
		_chart(rows, last, this),
		_summary(rows, last, this, last_start, this_start),
	)


def _get_slips(company, month_start, include_draft):
	"""One row per employee for the month (several slips - e.g. an amended one -
	are added together)."""
	docstatus = (0, 1) if include_draft else (1,)
	rows = frappe.db.sql(
		"""
		select employee, employee_name, department, designation,
			sum(net_pay) as net_pay, sum(gross_pay) as gross_pay,
			sum(total_deduction) as total_deduction,
			sum(payment_days) as payment_days, max(total_working_days) as working_days
		from `tabSalary Slip`
		where company = %s and start_date = %s and docstatus in %s
		group by employee
		""",
		(company, month_start, docstatus),
		as_dict=True,
	)
	return {row.employee: row for row in rows}


def _compare(last, this, this_start):
	employees = frappe.get_all(
		"Employee",
		filters={"name": ["in", list(set(last) | set(this)) or [""]]},
		fields=["name", "date_of_joining", "relieving_date", "status"],
	)
	employees = {e.name: e for e in employees}

	rows = []
	for employee in set(last) | set(this):
		before, after = last.get(employee), this.get(employee)
		slip = after or before
		before_net, after_net = flt(before.net_pay if before else 0), flt(after.net_pay if after else 0)
		difference = after_net - before_net

		emp = employees.get(employee)
		if not before:
			# A real joiner joined last month or this month; anyone else simply
			# wasn't paid last month (e.g. missing from that payroll).
			joined = emp and emp.date_of_joining and getdate(emp.date_of_joining) >= add_months(this_start, -1)
			change = NEW_JOINER if joined else NOT_PAID_LAST
		elif not after:
			left = emp and (emp.relieving_date or emp.status != "Active")
			change = LEFT if left else NOT_PAID_THIS
		elif abs(difference) < 0.5:
			change = NO_CHANGE
		else:
			change = INCREASED if difference > 0 else DECREASED

		rows.append(
			{
				"change_type": change,
				"employee": employee,
				"employee_name": slip.employee_name,
				"department": slip.department,
				"designation": slip.designation,
				"last_net_pay": before_net,
				"this_net_pay": after_net,
				"difference": difference,
				"last_payment_days": before.payment_days if before else None,
				"this_payment_days": after.payment_days if after else None,
				"reason": _reason(change, before, after, emp),
			}
		)
	rows.sort(key=lambda r: (CHANGE_ORDER[r["change_type"]], -abs(r["difference"])))
	return rows


def _reason(change, before, after, employee):
	if change == NEW_JOINER:
		return _("Joined on {0}").format(formatdate(employee.date_of_joining))
	if change == NOT_PAID_LAST:
		return _("Not a new joiner, but had no salary slip last month - check last month's payroll")
	if change == LEFT:
		if employee.relieving_date:
			return _("Relieved on {0}").format(formatdate(employee.relieving_date))
		return _("Employee status: {0}").format(_(employee.status))
	if change == NOT_PAID_THIS:
		return _("Still active but has no salary slip this month - check this month's payroll")
	if change == NO_CHANGE:
		return ""

	reasons = []
	if flt(before.payment_days) != flt(after.payment_days):
		reasons.append(
			_("Payment days {0} → {1}").format(_days(before.payment_days), _days(after.payment_days))
		)
	gross_before, gross_after = flt(before.gross_pay), flt(after.gross_pay)
	if abs(gross_after - gross_before) >= 0.5:
		reasons.append(_("Gross pay {0} → {1}").format(_amount(gross_before), _amount(gross_after)))
	if abs(flt(after.total_deduction) - flt(before.total_deduction)) >= 0.5:
		reasons.append(
			_("Deductions {0} → {1}").format(_amount(before.total_deduction), _amount(after.total_deduction))
		)
	return "; ".join(reasons)


def _days(value):
	return f"{flt(value):g}"


def _amount(value):
	return frappe.format(flt(value), {"fieldtype": "Currency"})


def _columns(last_start, this_start):
	last_label, this_label = last_start.strftime("%b %Y"), this_start.strftime("%b %Y")
	return [
		{"label": _("Change"), "fieldname": "change_type", "fieldtype": "Data", "width": 110},
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 130},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 130},
		{"label": _("Net Pay ({0})").format(last_label), "fieldname": "last_net_pay", "fieldtype": "Currency", "width": 140},
		{"label": _("Net Pay ({0})").format(this_label), "fieldname": "this_net_pay", "fieldtype": "Currency", "width": 140},
		{"label": _("Difference"), "fieldname": "difference", "fieldtype": "Currency", "width": 130},
		{"label": _("Payment Days ({0})").format(last_label), "fieldname": "last_payment_days", "fieldtype": "Float", "precision": 1, "width": 120},
		{"label": _("Payment Days ({0})").format(this_label), "fieldname": "this_payment_days", "fieldtype": "Float", "precision": 1, "width": 120},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Data", "width": 320},
	]


def _totals(rows):
	total = {key: 0.0 for key in CHANGE_ORDER}
	count = {key: 0 for key in CHANGE_ORDER}
	for row in rows:
		total[row["change_type"]] += row["difference"]
		count[row["change_type"]] += 1
	return total, count


def _summary(rows, last, this, last_start, this_start):
	total, count = _totals(rows)
	last_net = sum(flt(r.net_pay) for r in last.values())
	this_net = sum(flt(r.net_pay) for r in this.values())
	change = this_net - last_net
	last_label, this_label = last_start.strftime("%b %Y"), this_start.strftime("%b %Y")
	return [
		{"label": _("Net Pay {0}").format(last_label), "value": last_net, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Net Pay {0}").format(this_label), "value": this_net, "datatype": "Currency", "indicator": "Blue"},
		{
			"label": _("Change"),
			"value": change,
			"datatype": "Currency",
			"indicator": "Green" if change > 0 else "Red" if change < 0 else "Gray",
		},
		{"label": _("Employees {0}").format(last_label), "value": len(last), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Employees {0}").format(this_label), "value": len(this), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Joined"), "value": count[NEW_JOINER], "datatype": "Int", "indicator": "Green"},
		{"label": _("Left"), "value": count[LEFT], "datatype": "Int", "indicator": "Red"},
		*(
			[
				{
					"label": _("Not Paid Last Month"),
					"value": count[NOT_PAID_LAST],
					"datatype": "Int",
					"indicator": "Orange",
				}
			]
			if count[NOT_PAID_LAST]
			else []
		),
		*(
			[
				{
					"label": _("Not Paid This Month"),
					"value": count[NOT_PAID_THIS],
					"datatype": "Int",
					"indicator": "Orange",
				}
			]
			if count[NOT_PAID_THIS]
			else []
		),
		{
			"label": _("Increased ({0})").format(count[INCREASED]),
			"value": total[INCREASED],
			"datatype": "Currency",
			"indicator": "Green",
		},
		{
			"label": _("Decreased ({0})").format(count[DECREASED]),
			"value": total[DECREASED],
			"datatype": "Currency",
			"indicator": "Red",
		},
	]


def _chart(rows, last, this):
	"""Bridge from last month's total to this month's."""
	total, _count = _totals(rows)
	labels = [_("Last Month"), _("Joiners"), _("Leavers")]
	values = [sum(flt(r.net_pay) for r in last.values()), total[NEW_JOINER], total[LEFT]]
	missing = total[NOT_PAID_LAST] + total[NOT_PAID_THIS]
	if missing:
		labels.append(_("Not Paid in One Month"))
		values.append(missing)
	labels += [_("Increases"), _("Decreases"), _("This Month")]
	values += [total[INCREASED], total[DECREASED], sum(flt(r.net_pay) for r in this.values())]
	return {
		"data": {"labels": labels, "datasets": [{"name": _("Net Pay"), "values": values}]},
		"type": "bar",
		"fieldtype": "Currency",
		"colors": ["#5e64ff"],
		"barOptions": {"spaceRatio": 0.4},
	}
