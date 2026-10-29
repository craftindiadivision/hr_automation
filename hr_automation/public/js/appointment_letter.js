// Mode sits in its own band at the top: blue for Online (emails go out),
// orange for Offline (handed over in person, no emails), red until chosen.
function highlight_mode(frm) {
	const field = frm.fields_dict.custom_mode;
	if (!field) return;
	const color = { Online: "blue", Offline: "orange" }[frm.doc.custom_mode] || "red";
	field.$wrapper.css({
		"background-color": `var(--bg-${color})`,
		"border-left": `4px solid var(--${color}-500)`,
		"border-radius": "var(--border-radius-md)",
		padding: "8px 12px",
	});
}

// Online: the applicant first fills the onboarding-details form (emailed
// link); only then can the letter be sent. Offline: issue straight away once
// the Onboarding Details tab is filled.
function add_send_buttons(frm) {
	if (!frm.doc.custom_mode) {
		frm.set_intro(__("Select the Mode (Online or Offline) to continue."), "red");
		return;
	}
	if (frm.doc.custom_mode === "Offline") {
		frm.add_custom_button(__("Issue Appointment Letter"), () => send_letter(frm)).addClass("btn-primary");
		return;
	}
	frappe.db
		.get_value("Job Applicant", frm.doc.job_applicant, [
			"custom_onboarding_details_submitted",
			"custom_onboarding_details_token_sent_at",
		])
		.then((r) => {
			const applicant = r.message || {};
			if (applicant.custom_onboarding_details_submitted) {
				// Normally sent automatically on submission; this is the fallback if that failed.
				frm.set_intro(
					__("Onboarding details received, but the letter wasn't sent automatically. Send it now."),
					"orange"
				);
				frm.add_custom_button(__("Send Appointment Letter"), () => send_letter(frm)).addClass("btn-primary");
				return;
			}
			const sent_on = applicant.custom_onboarding_details_token_sent_at;
			frm.set_intro(
				sent_on
					? __("Waiting for {0} to submit their onboarding details (link sent on {1}). The letter will be emailed automatically after that.", [
							frm.doc.applicant_name,
							frappe.datetime.str_to_user(sent_on),
					  ])
					: __(
							"Step 1: send the onboarding details link. The letter is emailed automatically once they submit it."
					  ),
				"orange"
			);
			frm.add_custom_button(
				sent_on ? __("Resend Onboarding Details Link") : __("Send Onboarding Details Link"),
				() => {
					if (frm.is_dirty()) frappe.throw(__("Save the Appointment Letter first"));
					frappe.call({
						method: "hr_automation.api.onboarding_details.resend_onboarding_details_link",
						args: { appointment_letter: frm.doc.name },
						freeze: true,
						freeze_message: __("Sending email..."),
						callback: () => frm.reload_doc(),
					});
				}
			).addClass("btn-primary");
		});
}

function send_letter(frm) {
	if (frm.is_dirty()) frappe.throw(__("Save the Appointment Letter first"));
	const offline = frm.doc.custom_mode === "Offline";
	frappe.call({
		method: "hr_automation.api.recruitment_automation.send_appointment_letter_email",
		args: { appointment_letter: frm.doc.name },
		freeze: true,
		freeze_message: offline ? __("Issuing...") : __("Sending email..."),
		callback: function (r) {
			frappe.show_alert({
				message:
					r.message && r.message.emailed
						? __("Appointment Letter emailed.")
						: __(
								"Appointment Letter issued. Set Appointment Status to Accepted once the candidate accepts."
						  ),
				indicator: "green",
			});
			if (r.message && r.message.employee) {
				frappe.msgprint({
					title: __("Employee Created"),
					indicator: "green",
					message: __("Employee {0} has been created for this appointment.", [
						`<a href="/app/employee/${r.message.employee}">${r.message.employee}</a>`,
					]),
				});
			}
			frm.reload_doc();
		},
	});
}

function show_appointment_status(frm) {
	const status = frm.doc.custom_appointment_status;
	if (status === "Accepted") {
		frm.set_intro(__("The candidate has accepted. The Employee has been created."), "green");
	} else if (status === "Rejected") {
		frm.set_intro(__("The candidate has declined this appointment."), "red");
	} else if (frm.doc.custom_mode === "Offline") {
		frm.set_intro(
			__(
				"Letter issued. When the candidate accepts, set Appointment Status to Accepted and save - the Employee is created then."
			),
			"orange"
		);
	}
}

// Offline letters collect the onboarding details on the letter itself; start
// from whatever the Job Applicant already has, without overwriting HR's input.
function prefill_onboarding_details(frm) {
	if (frm.doc.custom_mode !== "Offline" || !frm.doc.job_applicant || frm.doc.custom_letter_sent_on) return;
	frappe.call({
		method: "hr_automation.api.onboarding_details.get_applicant_onboarding_details",
		args: { job_applicant: frm.doc.job_applicant },
		callback: (r) => {
			Object.entries(r.message || {}).forEach(([fieldname, value]) => {
				const target = "custom_ob_" + fieldname;
				if (value && frm.fields_dict[target] && !frm.doc[target]) frm.set_value(target, value);
			});
		},
	});
}

function calculate_next_phase_date(frm) {
	if (!frm.doc.appointment_date || !frm.doc.custom_next_phase_duration) {
		frm.set_value("custom_next_phase_date", null);
		return;
	}
	let months = parseInt(frm.doc.custom_next_phase_duration, 10);
	frm.set_value("custom_next_phase_date", frappe.datetime.add_months(frm.doc.appointment_date, months));
}

frappe.ui.form.on("Appointment Letter", {
	setup: function (frm) {
		hr_automation.active_records.set_link_queries(frm);
	},
	gross_salary: function (frm) {
		calculate_salary_breakup(frm);
	},
	appointment_date: calculate_next_phase_date,
	custom_mode: function (frm) {
		highlight_mode(frm);
		prefill_onboarding_details(frm);
	},
	custom_next_phase_duration: calculate_next_phase_date,
	custom_next_phase_gross_salary: function (frm) {
		calculate_salary_breakup(
			frm,
			"custom_next_phase_gross_salary",
			"custom_next_phase_earnings",
			"custom_next_phase_deductions",
			"custom_next_phase_salary_structure"
		);
	},
	custom_next_phase_salary_structure: function (frm) {
		apply_salary_structure(
			frm,
			"custom_next_phase_salary_structure",
			"custom_next_phase_gross_salary",
			"custom_next_phase_earnings",
			"custom_next_phase_deductions"
		);
	},
	refresh: function (frm) {
		set_salary_component_queries(frm);
		set_salary_component_queries(frm, "custom_next_phase_earnings", "custom_next_phase_deductions");
		calculate_salary_totals(frm);
		calculate_salary_totals(frm, "custom_next_phase_earnings", "custom_next_phase_deductions");

		highlight_mode(frm);

		if (!frm.is_new() && !frm.doc.custom_letter_sent_on) add_send_buttons(frm);
		else if (frm.doc.custom_letter_sent_on) show_appointment_status(frm);
	},
});
