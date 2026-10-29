// show_feedback_dialog replaces HRMS's (frm.events uses the last registered
// handler): same dialog, plus an answer for each of the interview's questions.
frappe.ui.form.on("Interview", {
	show_feedback_dialog: async function (frm, data) {
		const fields = await frm.events.get_fields_for_feedback();
		const questions = (frm.doc.custom_questions || []).map((row) => ({ question: row.question }));

		const d = new frappe.ui.Dialog({
			title: __("Submit Feedback"),
			fields: [
				{
					fieldname: "skill_set",
					fieldtype: "Table",
					label: __("Skill Assessment"),
					cannot_add_rows: false,
					in_editable_grid: true,
					reqd: 1,
					fields: fields,
					data: data,
				},
				{
					fieldname: "question_answers",
					fieldtype: "Table",
					label: __("Interview Questions"),
					cannot_add_rows: true,
					cannot_delete_rows: true,
					in_editable_grid: true,
					hidden: !questions.length,
					data: questions,
					fields: [
						{
							fieldname: "question",
							fieldtype: "Small Text",
							label: __("Question"),
							in_list_view: 1,
							read_only: 1,
						},
						{ fieldname: "answer", fieldtype: "Small Text", label: __("Answer"), in_list_view: 1 },
					],
				},
				{
					fieldname: "result",
					fieldtype: "Select",
					options: ["", "Cleared", "Rejected"],
					label: __("Result"),
					reqd: 1,
				},
				{ fieldname: "feedback", fieldtype: "Small Text", label: __("Feedback") },
			],
			size: "large",
			minimizable: true,
			static: true,
			primary_action: function (values) {
				frappe
					.call({
						method: "hr_automation.api.interview_questions.create_interview_feedback",
						args: {
							data: values,
							interview_name: frm.doc.name,
							interviewer: frappe.session.user,
							job_applicant: frm.doc.job_applicant,
						},
					})
					.then(() => frm.reload_doc());
				d.hide();
			},
		});
		d.show();
		d.get_close_btn().show();
	},
	custom_interview_questions: function (frm) {
		frm.clear_table("custom_questions");
		if (!frm.doc.custom_interview_questions) return frm.refresh_field("custom_questions");
		frappe.call({
			method: "hr_automation.api.interview_questions.get_template_questions",
			args: { template: frm.doc.custom_interview_questions },
			callback: (r) => {
				(r.message || []).forEach((question) => frm.add_child("custom_questions", { question }));
				frm.refresh_field("custom_questions");
			},
		});
	},
});
