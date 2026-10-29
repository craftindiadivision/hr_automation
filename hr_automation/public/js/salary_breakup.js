function set_per_annum(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "per_annum", flt(row.per_month) * 12);

	if (row.parentfield === "earnings" || row.parentfield === "deductions") {
		calculate_salary_totals(frm, "earnings", "deductions");
	} else if (
		row.parentfield === "custom_next_phase_earnings" ||
		row.parentfield === "custom_next_phase_deductions"
	) {
		calculate_salary_totals(frm, "custom_next_phase_earnings", "custom_next_phase_deductions");
	}
}

function calculate_salary_totals(frm, earnings_field = "earnings", deductions_field = "deductions") {
	// Job Offer and Appointment Letter only - they're the only doctypes with the
	// total_earnings/total_deductions/net_pay fields this writes to. Appointment
	// Letter has both a main and a "next phase" set of these fields, prefixed to
	// match whichever earnings/deductions table this call is about.
	if (frm.doctype !== "Job Offer" && frm.doctype !== "Appointment Letter") return;

	let prefix = earnings_field.startsWith("custom_next_phase_") ? "custom_next_phase_" : "";
	let sum = (rows, fieldname) => (rows || []).reduce((total, row) => total + flt(row[fieldname]), 0);

	let earnings_month = sum(frm.doc[earnings_field], "per_month");
	let earnings_annum = sum(frm.doc[earnings_field], "per_annum");
	let deductions_month = sum(frm.doc[deductions_field], "per_month");
	let deductions_annum = sum(frm.doc[deductions_field], "per_annum");

	frm.set_value(`${prefix}total_earnings_per_month`, earnings_month);
	frm.set_value(`${prefix}total_earnings_per_annum`, earnings_annum);
	frm.set_value(`${prefix}total_deductions_per_month`, deductions_month);
	frm.set_value(`${prefix}total_deductions_per_annum`, deductions_annum);
	frm.set_value(`${prefix}net_pay_per_month`, earnings_month - deductions_month);
	frm.set_value(`${prefix}net_pay_per_annum`, earnings_annum - deductions_annum);
}

function calculate_salary_breakup(
	frm,
	gross_field = "gross_salary",
	earnings_field = "earnings",
	deductions_field = "deductions",
	structure_field = "salary_structure"
) {
	// Delegates to hr_automation.api.salary_breakup.calculate_salary_breakup - the same
	// function the automatic Appointment Letter creation (on Job Offer acceptance) uses -
	// so the formula only ever lives in one place. Evaluates the actual Salary
	// Structure's own component formulas, not a fixed percentage policy.
	if (!frm.doc[structure_field]) return;

	frappe.call({
		method: "hr_automation.api.salary_breakup.get_salary_breakup",
		args: { salary_structure: frm.doc[structure_field], gross_salary: frm.doc[gross_field] },
		callback: function (r) {
			if (!r.message) return;
			let breakup = r.message;

			[
				[earnings_field, breakup.earnings],
				[deductions_field, breakup.deductions],
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
			calculate_salary_totals(frm, earnings_field, deductions_field);
		},
	});
}

function set_salary_component_queries(frm, earnings_field = "earnings", deductions_field = "deductions") {
	frm.set_query("component", earnings_field, function () {
		return { filters: { type: "Earning" } };
	});
	frm.set_query("component", deductions_field, function () {
		return { filters: { type: "Deduction" } };
	});
}

function apply_salary_structure(
	frm,
	structure_field = "salary_structure",
	gross_field = "gross_salary",
	earnings_field = "earnings",
	deductions_field = "deductions"
) {
	if (!frm.doc[structure_field]) return;

	frappe.call({
		method: "hr_automation.api.salary_breakup.get_structure_components",
		args: { salary_structure: frm.doc[structure_field] },
		callback: function (r) {
			if (!r.message) return;
			[earnings_field, deductions_field].forEach((fieldname, i) => {
				let key = i === 0 ? "earnings" : "deductions";
				frm.clear_table(fieldname);
				r.message[key].forEach((row) => {
					let per_month = flt(row.per_month);
					frm.add_child(fieldname, {
						component: row.component,
						per_month: per_month,
						per_annum: per_month * 12,
					});
				});
				frm.refresh_field(fieldname);
			});
			if (frm.doc[gross_field])
				calculate_salary_breakup(frm, gross_field, earnings_field, deductions_field, structure_field);
		},
	});
}

frappe.ui.form.on("Job Offer", {
	salary_structure: function (frm) {
		apply_salary_structure(frm);
	},
});

frappe.ui.form.on("Appointment Letter", {
	salary_structure: function (frm) {
		apply_salary_structure(frm);
	},
});

frappe.ui.form.on("Appointment Letter Earning", {
	per_month: set_per_annum,
});

frappe.ui.form.on("Appointment Letter Deduction", {
	per_month: set_per_annum,
});
