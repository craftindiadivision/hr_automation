// Certificate: shown - and mandatory - only when the leave type is marked
// "Is Certificate Required" and the leave is longer than its "Certificate
// Required After (Days)" (0 = always). The server checks the same rule on save.
frappe.ui.form.on("Leave Application", {
	refresh: (frm) => update_certificate_field(frm),
	leave_type: (frm) => update_certificate_field(frm),
	total_leave_days: (frm) => update_certificate_field(frm),
});

function update_certificate_field(frm) {
	if (!frm.doc.leave_type) {
		frm.toggle_display("custom_medical_certificate", false);
		frm.toggle_reqd("custom_medical_certificate", false);
		return;
	}
	frappe.db
		.get_value("Leave Type", frm.doc.leave_type, ["custom_certificate_required", "custom_certificate_after_days"])
		.then((r) => {
			const rule = r.message || {};
			const needed =
				!!rule.custom_certificate_required &&
				flt(frm.doc.total_leave_days) > flt(rule.custom_certificate_after_days);
			frm.toggle_display("custom_medical_certificate", needed);
			frm.toggle_reqd("custom_medical_certificate", needed);
		});
}
