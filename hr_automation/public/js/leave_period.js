frappe.ui.form.on("Leave Period", {
	setup: function (frm) {
		hr_automation.active_records.set_link_queries(frm);
	},
});
