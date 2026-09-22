frappe.pages["training-survey-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Training & Survey Dashboard"),
		single_column: true,
	});

	page.add_inner_button(__("Refresh"), () => load(page));

	load(page);
};

function load(page) {
	page.main.html(`<div class="text-muted" style="padding:20px;">${__("Loading...")}</div>`);
	frappe.call({
		method: "hr_automation.api.dashboard.get_dashboard_data",
		callback: (r) => render(page, r.message),
	});
}

function statCard(label, value, color) {
	return `
		<div class="col-sm-3" style="margin-bottom: 16px;">
			<div style="border:1px solid #eee;border-radius:8px;padding:16px;border-top:3px solid ${color};">
				<div style="font-size:12px;color:#888;text-transform:uppercase;letter-spacing:.5px;">${label}</div>
				<div style="font-size:28px;font-weight:700;margin-top:4px;">${value}</div>
			</div>
		</div>
	`;
}

function sectionTitle(text) {
	return `<h4 style="margin:28px 0 14px;">${text}</h4>`;
}

function emptyState(text) {
	return `<div class="text-muted" style="padding:30px;text-align:center;border:1px dashed #ddd;border-radius:8px;">${text}</div>`;
}

function render(page, data) {
	const t = data.training,
		g = data.groups,
		s = data.survey;

	let html = `<div class="row">`;
	html += statCard(__("Training Programs"), t.total_programs, "#7c3aed");
	html += statCard(__("Training Events"), t.total_events, "#2e7d32");
	html += statCard(__("Feedback Collected"), t.total_feedback, "#0b6cf0");
	html += statCard(__("Groups Certified"), g.certified_count, "#e67e22");
	html += `</div><div class="row">`;
	html += statCard(__("Groups In Progress"), g.in_progress_count, "#999");
	html += statCard(__("Surveys"), `${s.active_surveys} / ${s.total_surveys}`, "#7c3aed");
	html += statCard(__("Survey Invitations"), s.total_recipients, "#2e7d32");
	html += statCard(__("Survey Responses"), s.total_responses, "#0b6cf0");
	html += `</div>`;

	html += sectionTitle(__("Training"));
	html += `<div class="row">
		<div class="col-sm-6"><div id="chart-events-status"></div></div>
		<div class="col-sm-6"><div id="chart-events-program"></div></div>
	</div>
	<div class="row">
		<div class="col-sm-12"><div id="chart-events-month"></div></div>
	</div>`;

	html += sectionTitle(__("Program Group Completion"));
	html += `<div class="row">
		<div class="col-sm-6"><div id="chart-group-completion"></div></div>
		<div class="col-sm-6"><div id="chart-group-certified"></div></div>
	</div>
	<div id="group-recent" style="margin-top:10px;"></div>`;

	html += sectionTitle(__("Employee Survey"));
	html += `<div id="chart-survey-responses"></div>`;

	page.main.html(html);

	// --- Training: events by status ---
	if (t.events_by_status.length) {
		new frappe.Chart("#chart-events-status", {
			title: __("Events by Status"),
			data: {
				labels: t.events_by_status.map((d) => d.event_status || __("Not Set")),
				datasets: [{ values: t.events_by_status.map((d) => d.count) }],
			},
			type: "donut",
			height: 220,
			colors: ["#2e7d32", "#0b6cf0", "#e67e22", "#c62828"],
		});
	} else {
		$("#chart-events-status").html(emptyState(__("No submitted Training Events yet.")));
	}

	// --- Training: events by program ---
	if (t.events_by_program.length) {
		new frappe.Chart("#chart-events-program", {
			title: __("Events by Program"),
			data: {
				labels: t.events_by_program.map((d) => d.training_program),
				datasets: [{ name: __("Events"), values: t.events_by_program.map((d) => d.count) }],
			},
			type: "bar",
			height: 220,
			colors: ["#7c3aed"],
		});
	} else {
		$("#chart-events-program").html(emptyState(__("No submitted Training Events yet.")));
	}

	// --- Training: events by month ---
	if (t.events_by_month.length) {
		new frappe.Chart("#chart-events-month", {
			title: __("Events Over Time"),
			data: {
				labels: t.events_by_month.map((d) => d.month),
				datasets: [{ name: __("Events"), values: t.events_by_month.map((d) => d.count) }],
			},
			type: "line",
			height: 220,
			colors: ["#0b6cf0"],
			lineOptions: { regionFill: 1 },
		});
	} else {
		$("#chart-events-month").html(emptyState(__("No submitted Training Events yet.")));
	}

	// --- Groups: completion per group ---
	const groupNames = Object.keys(g.group_completion);
	if (groupNames.length && g.total_tracked) {
		new frappe.Chart("#chart-group-completion", {
			title: __("Employees Certified per Group"),
			data: {
				labels: groupNames,
				datasets: [{ name: __("Certified"), values: groupNames.map((k) => g.group_completion[k]) }],
			},
			type: "bar",
			height: 220,
			colors: ["#2e7d32"],
		});
	} else {
		$("#chart-group-completion").html(emptyState(__("No program groups set up yet.")));
	}

	// --- Groups: certified vs in progress ---
	if (g.total_tracked) {
		new frappe.Chart("#chart-group-certified", {
			title: __("Certified vs In Progress"),
			data: {
				labels: [__("Certified"), __("In Progress")],
				datasets: [{ values: [g.certified_count, g.in_progress_count] }],
			},
			type: "donut",
			height: 220,
			colors: ["#e67e22", "#ccc"],
		});
	} else {
		$("#chart-group-certified").html(emptyState(__("No employees are being tracked yet.")));
	}

	// --- Groups: recent certifications list ---
	if (g.recent_certifications.length) {
		let rows = g.recent_certifications
			.map(
				(c) => `
			<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #f0f0f0;">
				<span>${frappe.utils.escape_html(c.employee_name)} <span class="text-muted">(${frappe.utils.escape_html(c.parent_training_program)})</span></span>
				<span class="text-muted">${frappe.datetime.str_to_user(c.completed_on)}</span>
			</div>`
			)
			.join("");
		$("#group-recent").html(`<h5>${__("Recently Certified")}</h5>${rows}`);
	}

	// --- Survey: invited vs responses per survey ---
	if (s.by_survey.length) {
		new frappe.Chart("#chart-survey-responses", {
			title: __("Invited vs Responses (last 10 surveys)"),
			data: {
				labels: s.by_survey.map((d) => d.title),
				datasets: [
					{ name: __("Invited"), values: s.by_survey.map((d) => d.invited) },
					{ name: __("Responses"), values: s.by_survey.map((d) => d.responses) },
				],
			},
			type: "bar",
			height: 260,
			colors: ["#7c3aed", "#2e7d32"],
		});
	} else {
		$("#chart-survey-responses").html(emptyState(__("No surveys created yet.")));
	}
}
