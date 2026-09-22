frappe.pages["hr-policies"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("HR Policies"),
		single_column: true,
	});

	page.main.html(`<div class="text-muted" style="padding: 20px;">${__("Loading...")}</div>`);

	frappe.call({
		method: "hr_automation.hr_automation.page.hr_policies.hr_policies.get_policies",
		callback: (r) => render_policies(page.main, r.message || []),
	});
};

function render_policies(container, policies) {
	if (!policies.length) {
		container.html(`<div class="text-muted" style="padding: 20px;">${__("No policies have been added yet.")}</div>`);
		return;
	}

	let $list = $('<div class="list-group" style="margin-top: 10px;"></div>');
	policies.forEach((policy) => {
		let effective = policy.effective_date
			? `<span class="text-muted pull-right">${__("Effective")} ${frappe.datetime.str_to_user(policy.effective_date)}</span>`
			: "";
		$list.append(`
			<a href="/app/hr-policy/${encodeURIComponent(policy.name)}" class="list-group-item">
				<i class="fa fa-file-text-o"></i> ${frappe.utils.escape_html(policy.policy_title)}
				${effective}
			</a>
		`);
	});

	container.empty().append($list);
}
