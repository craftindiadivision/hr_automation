frappe.ui.form.on("Job Offer", {
	gross_salary: function (frm) {
		calculate_salary_breakup(frm);
	},
	onload: function (frm) {
		set_default_salary_breakup_rows(frm);
	},
	refresh: function (frm) {
		set_salary_component_queries(frm);

		if (!frm.is_new() && frm.doc.docstatus === 1 && frm.doc.status === "Awaiting Response") {
			frm.add_custom_button(__("Send Offer to Applicant"), function () {
				frappe.call({
					method: "hr_automation.api.recruitment_automation.send_job_offer_email",
					args: { job_offer: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending email..."),
					callback: function () {
						frm.reload_doc();
					},
				});
			});
		}
	},
});
