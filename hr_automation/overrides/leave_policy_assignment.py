from frappe.utils import date_diff, flt

from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import LeavePolicyAssignment


class CustomLeavePolicyAssignment(LeavePolicyAssignment):
	"""HRMS only pro-rates by date of joining. Assignments created after
	probation (hr_automation.api.leave_management) start mid leave year, long
	after joining, so they set flags.pro_rate_within = (period_from, period_to)
	and get pro-rated by the share of the leave year they cover instead, e.g.
	1 Jan - 31 Mar 2027 of a 2026-27 year: 12 x 90/365 = 3 days."""

	def get_new_leaves(self, annual_allocation, leave_details, date_of_joining):
		period = self.flags.get("pro_rate_within")
		if not period or leave_details.is_earned_leave or leave_details.is_compensatory:
			return super().get_new_leaves(annual_allocation, leave_details, date_of_joining)

		period_from, period_to = period
		covered_days = date_diff(self.effective_to, self.effective_from) + 1
		period_days = date_diff(period_to, period_from) + 1
		leaves = flt(annual_allocation) * covered_days / period_days
		# Nearest half day, halves rounded up
		return min(int(leaves * 2 + 0.5) / 2, flt(annual_allocation))
