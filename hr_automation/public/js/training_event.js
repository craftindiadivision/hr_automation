frappe.ui.form.on("Training Event", {
	refresh(frm) {
		// Hide the core buttons that route to List > New, which bypass the
		// attendance check and the token-based "Send Feedback Form" flow below.
		// "Training Result" is also unused by this app's training feature.
		frm.remove_custom_button(__("Training Result"));
		frm.remove_custom_button(__("Training Feedback"));

		if (frm.doc.docstatus !== 1) return;

		const now = frappe.datetime.now_datetime();
		const ended = frm.doc.end_time && now > frm.doc.end_time;
		const is_completed_status = frm.doc.event_status === "Completed";

		if (ended || is_completed_status) {
			frm.add_custom_button(__("Send Feedback Form"), () => open_send_feedback_dialog(frm));
		}

		if (frm.doc.custom_assessment_form) {
			frm.add_custom_button(__("Resend Assessment"), () => {
				frappe.call({
					method: "hr_automation.api.training_assessment.resend_assessment_requests",
					args: { training_event: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending..."),
					callback(r) {
						frappe.msgprint(__("Assessment sent to {0} employee(s).", [r.message.sent_count]));
					},
				});
			});
		}
	},
});

function open_send_feedback_dialog(frm) {
	let dialog = new frappe.ui.Dialog({
		title: __("Send Feedback Form"),
		fields: [
			{
				fieldtype: "Link",
				fieldname: "feedback_form",
				label: __("Training Feedback Form"),
				options: "Training Feedback Form",
				reqd: 1,
				default: frm.doc.custom_feedback_form,
				description: __("Sent only to attendees marked Present who haven't already submitted feedback."),
			},
			{
				fieldtype: "Link",
				fieldname: "assessment_form",
				label: __("Assessment Form (optional)"),
				options: "Training Assessment Form",
				default: frm.doc.custom_assessment_form,
				description: __("If set, emailed automatically to each employee the moment they submit their feedback."),
			},
			{
				fieldtype: "Check",
				fieldname: "resend",
				label: __("Resend to employees who haven't responded yet"),
				description: __("Leave unticked to send only to employees who haven't been invited yet."),
			},
		],
		primary_action_label: __("Send"),
		primary_action(values) {
			frappe.call({
				method: "hr_automation.api.training_feedback.send_feedback_requests",
				args: {
					training_event: frm.doc.name,
					feedback_form: values.feedback_form,
					assessment_form: values.assessment_form,
					resend: values.resend,
				},
				freeze: true,
				freeze_message: __("Sending..."),
				callback(r) {
					dialog.hide();
					frappe.msgprint(__("Feedback form sent to {0} employee(s).", [r.message.sent_count]));
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}
