frappe.ui.form.on("Training Program", {
	refresh(frm) {
		setup_topic_suggestions(frm);

		if (frm.is_new()) return;

		const allowed_roles = ["HR Manager", "HR User", "System Manager"];
		if (!allowed_roles.some((role) => frappe.user_roles.includes(role))) return;

		if (frm.doc.custom_has_certificate && frm.doc.custom_certificates_issued) {
			frm.add_custom_button(__("Download All Certificates"), () => {
				window.open(
					"/api/method/hr_automation.api.training_completion.download_all_certificates" +
						"?training_program=" +
						encodeURIComponent(frm.doc.name)
				);
			});
		}

		const is_completed =
			frm.doc.custom_number_of_events > 0 &&
			frm.doc.custom_completed_events >= frm.doc.custom_number_of_events;
		if (is_completed) return;

		frm.add_custom_button(__("Create Events"), () => {
			frappe.call({
				method: "hr_automation.api.training_completion.create_events_from_schedule",
				args: { training_program: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating events..."),
				callback(r) {
					frappe.msgprint(__("{0} event(s) created as drafts.", [r.message.created]));
					frm.reload_doc();
				},
			});
		});
	},
	custom_program_type(frm) {
		setup_topic_suggestions(frm);
	},
});

function setup_topic_suggestions(frm) {
	let grid = frm.fields_dict.custom_scheduled_sessions?.grid;
	if (!grid) return;

	let program_type = frm.doc.custom_program_type;
	let is_pipeline_type = program_type === "Onboarding" || program_type === "Buddy Training";
	let fieldtype = is_pipeline_type ? "Autocomplete" : "Data";

	// Regular training gets a plain free-text Topic - only Onboarding/Buddy
	// Training have a configured list worth suggesting from.
	// update_docfield_property silently skips the "new row" template when the
	// table has zero rows yet, so that has to be set directly too.
	let template_field = grid.docfields.find((d) => d.fieldname === "topic");
	if (template_field) template_field.fieldtype = fieldtype;

	grid.update_docfield_property("topic", "fieldtype", fieldtype);
	grid.refresh();

	if (!is_pipeline_type) return;

	frappe.call({
		method: "hr_automation.api.employee_onboarding.get_pipeline_event_names",
		args: { program_type },
		callback: function (r) {
			let names = r.message || [];
			grid.get_field("topic").df.get_data = function () {
				return names.map((name) => ({ value: name, label: name }));
			};
		},
	});
}
