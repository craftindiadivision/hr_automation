function set_per_annum(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "per_annum", flt(row.per_month) * 12);
}

function calculate_salary_breakup(frm) {
	// Delegates to hr_automation.api.salary_breakup.calculate_salary_breakup - the same
	// function the automatic Appointment Letter creation (on Job Offer acceptance) uses -
	// so the formula only ever lives in one place.
	frappe.call({
		method: "hr_automation.api.salary_breakup.get_salary_breakup",
		args: { gross_salary: frm.doc.gross_salary },
		callback: function (r) {
			if (!r.message) return;
			let breakup = r.message;

			[
				["earnings", breakup.earnings],
				["employer_contribution", breakup.employer_contribution],
				["deductions", breakup.deductions],
			].forEach(([fieldname, map]) => {
				(frm.doc[fieldname] || []).forEach((row) => {
					if (row.component in map) {
						let per_month = flt(map[row.component]);
						frappe.model.set_value(row.doctype, row.name, "per_month", per_month);
						frappe.model.set_value(row.doctype, row.name, "per_annum", per_month * 12);
					}
				});
				frm.refresh_field(fieldname);
			});
		},
	});
}

const DEFAULT_EARNINGS = [
	"Basic",
	"House Rent Allowance",
	"Medical Allowance",
	"Special Allowances",
	"Conveyance Allowance",
];
const DEFAULT_EMPLOYER_CONTRIBUTION = ["ESI", "Welfare Fund", "Provident Fund"];
const DEFAULT_DEDUCTIONS = ["ESI", "Provident Fund", "Professional Tax (PT)", "TDS", "Welfare Fund"];

function set_default_salary_breakup_rows(frm) {
	if (!frm.is_new()) {
		return;
	}
	if (!frm.doc.earnings.length) {
		DEFAULT_EARNINGS.forEach((component) => frm.add_child("earnings", { component }));
	}
	if (!frm.doc.employer_contribution.length) {
		DEFAULT_EMPLOYER_CONTRIBUTION.forEach((component) =>
			frm.add_child("employer_contribution", { component })
		);
	}
	if (!frm.doc.deductions.length) {
		DEFAULT_DEDUCTIONS.forEach((component) => frm.add_child("deductions", { component }));
	}
	frm.refresh_fields();
}

function set_salary_component_queries(frm) {
	frm.set_query("component", "earnings", function () {
		return { filters: { type: "Earning" } };
	});
	frm.set_query("component", "deductions", function () {
		return { filters: { type: "Deduction" } };
	});
}

frappe.ui.form.on("Appointment Letter Earning", {
	per_month: set_per_annum,
});

frappe.ui.form.on("Appointment Letter Employer Contribution", {
	per_month: set_per_annum,
});

frappe.ui.form.on("Appointment Letter Deduction", {
	per_month: set_per_annum,
});
