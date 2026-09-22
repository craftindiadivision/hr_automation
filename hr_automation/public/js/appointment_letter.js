frappe.ui.form.on("Appointment Letter", {
	gross_salary: function (frm) {
		calculate_salary_breakup(frm);
	},
	onload: function (frm) {
		set_default_salary_breakup_rows(frm);
	},
	refresh: function (frm) {
		set_salary_component_queries(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Send Appointment Letter"), function () {
				frappe.call({
					method: "hr_automation.api.recruitment_automation.send_appointment_letter_email",
					args: { appointment_letter: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending email..."),
					callback: function () {
						frappe.show_alert({ message: __("Appointment Letter emailed."), indicator: "green" });
					},
				});
			}).addClass("btn-primary");

			render_uploaded_documents(frm);
		}
	},
});

function render_uploaded_documents(frm) {
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "File",
			filters: {
				attached_to_doctype: "Appointment Letter",
				attached_to_name: frm.doc.name,
			},
			fields: ["file_name", "file_url", "creation"],
			order_by: "creation desc",
			limit_page_length: 0,
		},
		callback: function (r) {
			let files = r.message || [];
			let html;
			if (!files.length) {
				html = `<div class="text-muted">No documents uploaded yet.</div>`;
			} else {
				html = files
					.map(
						(f) => `
					<div style="display:flex;justify-content:space-between;align-items:center;
						padding:8px 0;border-bottom:1px solid var(--border-color);">
						<a href="${f.file_url}" target="_blank">${frappe.utils.escape_html(f.file_name)}</a>
						<span class="text-muted small">${frappe.datetime.comment_when(f.creation)}</span>
					</div>`
					)
					.join("");
			}
			frm.set_df_property("uploaded_documents_html", "options", html);
			frm.refresh_field("uploaded_documents_html");
		},
	});
}
