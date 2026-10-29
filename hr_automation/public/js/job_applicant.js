// Replaces HRMS's Schedule Interview dialog (frm.events.show_schedule_dialog -
// the last registered handler wins) with the same fields plus an Interview
// Questions template whose questions are loaded into the dialog for review.
frappe.ui.form.on("Job Applicant", {
	show_schedule_dialog: function (frm) {
		const load_questions = (template) => {
			if (!template) return set_questions([]);
			frappe.call({
				method: "hr_automation.api.interview_questions.get_template_questions",
				args: { template },
				callback: (r) => set_questions((r.message || []).map((question) => ({ question }))),
			});
		};
		const set_questions = (rows) => {
			const field = d.fields_dict.questions;
			field.df.data = rows;
			field.grid.refresh();
		};

		const d = new frappe.ui.Dialog({
			title: __("Schedule Interview"),
			size: "large",
			fields: [
				{
					label: __("Interview Type"),
					fieldname: "interview_type",
					fieldtype: "Link",
					options: "Interview Type",
					reqd: 1,
					get_query: () => ({
						filters: frm.doc.designation ? [["designation", "in", [frm.doc.designation, ""]]] : [],
					}),
					onchange() {
						const interview_type = d.get_value("interview_type");
						if (!interview_type) return;
						frappe.call({
							method: "hrms.hr.doctype.interview.interview.get_interviewers",
							args: { interview_type },
							callback(r) {
								d.set_value(
									"interviewers",
									(r.message || []).map((i) => ({ interviewer: i.interviewer }))
								);
							},
						});
					},
				},
				{ label: __("From Time"), fieldname: "from_time", fieldtype: "Time", reqd: 1 },
				{ fieldtype: "Column Break" },
				{
					label: __("Scheduled On"),
					fieldname: "scheduled_on",
					fieldtype: "Date",
					reqd: 1,
					default: frappe.datetime.get_today(),
				},
				{ label: __("To Time"), fieldname: "to_time", fieldtype: "Time", reqd: 1 },
				{ fieldtype: "Section Break", label: __("Interviewers") },
				{ fieldname: "interviewers", fieldtype: "Table MultiSelect", options: "Interview Detail" },
				{ fieldtype: "Section Break", label: __("Interview Questions") },
				{
					label: __("Template"),
					fieldname: "interview_questions",
					fieldtype: "Link",
					options: "Interview Questions",
					get_query: () => {
						const interview_type = d.get_value("interview_type");
						return { filters: interview_type ? [["interview_type", "in", [interview_type, ""]]] : [] };
					},
					onchange() {
						load_questions(d.get_value("interview_questions"));
					},
				},
				{
					fieldname: "questions",
					fieldtype: "Table",
					label: __("Questions"),
					cannot_add_rows: false,
					in_place_edit: true,
					data: [],
					fields: [
						{
							fieldname: "question",
							fieldtype: "Small Text",
							label: __("Question"),
							in_list_view: 1,
						},
					],
				},
			],
			primary_action_label: __("Schedule"),
			primary_action(values) {
				frappe.call({
					method: "hr_automation.api.interview_questions.schedule_interview",
					args: {
						job_applicant: frm.doc.name,
						interview_type: values.interview_type,
						scheduled_on: values.scheduled_on,
						from_time: values.from_time || null,
						to_time: values.to_time || null,
						interviewers: values.interviewers || [],
						interview_questions: values.interview_questions || null,
						questions: values.questions || [],
					},
					callback(r) {
						if (r.message) {
							frappe.show_alert({
								message: __("Interview scheduled successfully"),
								indicator: "green",
							});
							d.hide();
							frm.events.get_interview_for_dashboard(frm);
						}
					},
				});
			},
		});
		d.show();
	},
});
