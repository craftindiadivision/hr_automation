// Post on LinkedIn: copies a ready post - "We're hiring", the details and
// "Apply now" with the link to this job's page - to paste into LinkedIn.
// Applicants who arrive through that link are recorded with Source = LinkedIn.
frappe.ui.form.on("Job Opening", {
	refresh: function (frm) {
		if (frm.is_new() || !frm.doc.publish || frm.doc.status !== "Open") return;
		frm.add_custom_button(__("Post on LinkedIn"), () => {
			frappe.call({
				method: "hr_automation.api.job_openings.get_linkedin_message",
				args: { job_opening: frm.doc.name },
				callback: (r) => {
					const message = r.message;
					if (!message) return;
					navigator.clipboard.writeText(message).then(
						() => frappe.show_alert({ message: __("Post copied - paste it into LinkedIn"), indicator: "green" }),
						() =>
							frappe.msgprint({
								title: __("Copy this post"),
								message: `<pre style="white-space:pre-wrap">${frappe.utils.escape_html(message)}</pre>`,
							})
					);
				},
			});
		});
	},
});
