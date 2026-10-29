// Copyright (c) 2026, Craft Interactive Technology and contributors
// For license information, please see license.txt

const PAYROLL_RECONCILIATION_COLORS = {
	"New Joiner": "green",
	Left: "red",
	"Not Paid Last Month": "yellow",
	"Not Paid This Month": "yellow",
	Increased: "blue",
	Decreased: "orange",
	"No Change": "gray",
};

frappe.query_reports["Payroll Reconciliation"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				"January", "February", "March", "April", "May", "June",
				"July", "August", "September", "October", "November", "December",
			],
			default: moment().format("MMMM"),
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: moment().year(),
			reqd: 1,
		},
		{
			fieldname: "include_draft",
			label: __("Include Draft Salary Slips"),
			fieldtype: "Check",
			default: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "change_type") {
			const color = PAYROLL_RECONCILIATION_COLORS[data.change_type] || "gray";
			return `<span class="indicator-pill ${color}">${__(data.change_type)}</span>`;
		}
		if (column.fieldname === "difference" && data.difference) {
			const color = data.difference > 0 ? "var(--green-600)" : "var(--red-600)";
			return `<span style="color: ${color}; font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
