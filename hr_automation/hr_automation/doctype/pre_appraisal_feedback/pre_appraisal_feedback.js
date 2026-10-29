// Copyright (c) 2026, Craft Interactive Technology and contributors
// For license information, please see license.txt

frappe.ui.form.on("Pre-Appraisal Feedback", {
	refresh: function (frm) {
		if (frm.is_new() || frm.doc.status !== "Requested") return;
		if (!["HR Manager", "HR User", "System Manager"].some((role) => frappe.user_roles.includes(role))) return;
		frm.add_custom_button(__("Resend Request"), () => {
			frappe.call({
				method: "hr_automation.api.performance_feedback.send_feedback_request",
				args: { name: frm.doc.name },
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		});
	},
});
