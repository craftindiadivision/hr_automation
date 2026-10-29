const ONBOARDING_VERIFY_ROLES = ["HR Manager", "HR User", "System Manager"];

frappe.ui.form.on("Job Offer", {
	setup: function (frm) {
		hr_automation.active_records.set_link_queries(frm);
	},
	onload: function (frm) {
		// "Create Job Offer" on the Job Applicant pre-sets job_applicant without
		// triggering its fetch, so pull the Final Round gross salary here.
		if (frm.is_new() && frm.doc.job_applicant && !frm.doc.gross_salary) {
			frappe.db.get_value("Job Applicant", frm.doc.job_applicant, "custom_gross_salary").then((r) => {
				const gross = r.message && r.message.custom_gross_salary;
				if (gross) frm.set_value("gross_salary", gross);
			});
		}
	},
	gross_salary: function (frm) {
		calculate_salary_breakup(frm);
	},
	refresh: function (frm) {
		set_salary_component_queries(frm);
		calculate_salary_totals(frm);

		// The Employee is created automatically once onboarding is verified; the
		// core "Create Employee" button would bypass that logic.
		frm.remove_custom_button(__("Create Employee"));

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

		if (!frm.is_new() && frm.doc.status === "Accepted") {
			show_document_status(frm);
			render_onboarding(frm);
		}
	},
});

// The offer's own status stays HRMS's (the applicant's answer); the document
// review is a separate HR step, shown separately so "rejected" is never
// mistaken for the offer being rejected.
function show_document_status(frm) {
	const reason = frm.doc.custom_document_rejection_reason;
	const [message, color] =
		frm.doc.custom_document_status === "Documents Accepted"
			? [__("Documents: accepted by HR."), "green"]
			: frm.doc.custom_document_status === "Documents Rejected"
			? [
					__("Documents: rejected by HR{0} - waiting for the applicant to upload them again.", [
						reason ? ` (${frappe.utils.escape_html(reason)})` : "",
					]),
					"red",
			  ]
			: frm.doc.custom_documents_submitted
			? [__("Documents: uploaded by the applicant - waiting for HR to review."), "orange"]
			: [__("Documents: not uploaded yet."), "blue"];
	frm.dashboard.set_headline_alert(message, color);
}

function can_manage_onboarding() {
	return ONBOARDING_VERIFY_ROLES.some((role) => frappe.user_roles.includes(role));
}

function render_onboarding(frm) {
	if (!can_manage_onboarding()) return;

	if (frm.doc.status === "Accepted") {
		frm.add_custom_button(__("Send Document Upload Link"), function () {
			frappe.call({
				method: "hr_automation.api.recruitment_automation.send_onboarding_documents_link",
				args: { job_offer: frm.doc.name },
				freeze: true,
				freeze_message: __("Sending link..."),
				callback: function () {
					frm.reload_doc();
				},
			});
		});
	}

	if (
		frm.doc.status === "Accepted" &&
		frm.doc.custom_document_status === "Documents Accepted" &&
		!frm.doc.custom_appointment_letter
	) {
		frm.add_custom_button(__("Create Appointment Letter"), function () {
			frappe.call({
				method: "hr_automation.api.recruitment_automation.create_appointment_letter",
				args: { job_offer: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating Appointment Letter..."),
				callback: function (r) {
					if (r.message) {
						frappe.set_route("Form", "Appointment Letter", r.message);
					}
				},
			});
		});
	}

	if (frm.doc.custom_appointment_letter) {
		frm.add_custom_button(__("View Appointment Letter"), function () {
			frappe.set_route("Form", "Appointment Letter", frm.doc.custom_appointment_letter);
		});

		// Offline letters are handed over in person; no link is emailed.
		frappe.db.get_value("Appointment Letter", frm.doc.custom_appointment_letter, "custom_mode").then((r) => {
			if (r.message && r.message.custom_mode === "Offline") return;
			frm.add_custom_button(__("Resend Onboarding Details Link"), function () {
				frappe.call({
					method: "hr_automation.api.onboarding_details.resend_onboarding_details_link",
					args: { appointment_letter: frm.doc.custom_appointment_letter },
					freeze: true,
					freeze_message: __("Resending..."),
				});
			});
		});
	}
}
