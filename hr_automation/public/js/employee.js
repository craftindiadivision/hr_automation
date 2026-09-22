const VERIFY_ROLES = ["HR Manager", "HR User", "System Manager"];

frappe.ui.form.on("Employee", {
	refresh: function (frm) {
		if (!frm.is_new()) {
			render_employee_documents(frm);
		}
	},
});

function can_verify() {
	return VERIFY_ROLES.some((role) => frappe.user_roles.includes(role));
}

function render_employee_documents(frm) {
	let requests = [
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "File",
				filters: { attached_to_doctype: "Employee", attached_to_name: frm.doc.name },
				fields: ["file_name", "file_url", "creation"],
				order_by: "creation desc",
				limit_page_length: 0,
			},
		}),
	];

	let existing_letter = null;

	if (frm.doc.job_applicant) {
		requests.push(
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Appointment Letter",
					filters: { job_applicant: frm.doc.job_applicant },
					fields: ["name"],
					limit_page_length: 1,
				},
			}).then((r) => {
				let letters = r.message || [];
				if (!letters.length) return { message: [] };
				existing_letter = letters[0].name;
				return frappe.call({
					method: "frappe.client.get_list",
					args: {
						doctype: "File",
						filters: { attached_to_doctype: "Appointment Letter", attached_to_name: letters[0].name },
						fields: ["file_name", "file_url", "creation"],
						order_by: "creation desc",
						limit_page_length: 0,
					},
				});
			})
		);
	}

	Promise.all(requests).then(function (results) {
		let files = [];
		results.forEach((r) => {
			files = files.concat(r.message || []);
		});
		files.sort((a, b) => new Date(b.creation) - new Date(a.creation));

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

		let show_verify = files.length && frm.doc.job_applicant && can_verify();
		if (show_verify) {
			if (existing_letter) {
				html += `
					<div style="margin-top:12px;">
						<button class="btn btn-sm btn-default" id="verify-documents-btn">${__("Verified")}</button>
					</div>`;
			} else {
				html += `
					<div style="margin-top:12px;">
						<button class="btn btn-sm btn-primary" id="verify-documents-btn">${__("Verify")}</button>
					</div>`;
			}
		}

		frm.set_df_property("custom_documents_html", "options", html);
		frm.refresh_field("custom_documents_html");

		if (show_verify) {
			frm.get_field("custom_documents_html").$wrapper.find("#verify-documents-btn").on("click", () => {
				if (existing_letter) {
					frappe.set_route("Form", "Appointment Letter", existing_letter);
					return;
				}
				frappe.call({
					method: "hr_automation.api.recruitment_automation.verify_and_create_appointment_letter",
					args: { employee: frm.doc.name },
					freeze: true,
					freeze_message: __("Verifying..."),
					callback: function (r) {
						if (r.message) {
							frappe.set_route("Form", "Appointment Letter", r.message);
						}
					},
				});
			});
		}
	});
}
