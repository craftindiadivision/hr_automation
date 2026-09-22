frappe.pages["knowledge-hub-home"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Knowledge Hub Library"),
		single_column: true,
	});

	page.main.html(`<div class="text-muted" style="padding: 20px;">${__("Loading...")}</div>`);

	frappe.call({
		method: "hr_automation.hr_automation.page.knowledge_hub_home.knowledge_hub_home.get_entries",
		callback: (r) => render_entries(page.main, r.message || []),
	});
};

function render_entries(container, entries) {
	if (!entries.length) {
		container.html(`<div class="text-muted" style="padding: 20px;">${__("Nothing has been added yet.")}</div>`);
		return;
	}

	let $list = $('<div class="list-group" style="margin-top: 10px;"></div>');
	entries.forEach((entry) => {
		let description = entry.description
			? `<div class="text-muted small">${frappe.utils.escape_html(entry.description)}</div>`
			: "";
		$list.append(`
			<a href="/app/knowledge-hub/${encodeURIComponent(entry.name)}" class="list-group-item">
				<i class="fa fa-file-powerpoint-o"></i> ${frappe.utils.escape_html(entry.title)}
				${description}
			</a>
		`);
	});

	container.empty().append($list);
}
