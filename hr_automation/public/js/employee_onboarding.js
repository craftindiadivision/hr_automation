frappe.ui.form.on("Employee Onboarding", {
	setup: function (frm) {
		hr_automation.active_records.set_link_queries(frm);
	},
	refresh: function (frm) {
		frm.remove_custom_button(__("Employee"), __("Create"));
	},
});
