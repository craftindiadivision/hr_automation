frappe.pages["employee-documents"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Employee Documents"),
		single_column: true,
	});

	page.main.html(`
		<div class="row employee-documents-wrapper">
			<div class="col-md-5 employee-tree-col"></div>
			<div class="col-md-7 employee-attachments-col">
				<div class="text-muted" style="padding: 20px;">
					${__("Select an employee to view their documents")}
				</div>
			</div>
		</div>
	`);

	const attachments_col = page.main.find(".employee-attachments-col");

	new frappe.ui.Tree({
		parent: page.main.find(".employee-tree-col"),
		label: __("All Employees"),
		root_value: "",
		expandable: true,
		args: {},
		method: "hr_automation.hr_automation.page.employee_documents.employee_documents.get_children",
		on_click: (node) => {
			if (node.is_root) return;
			show_attachments(attachments_col, node.data.value, node.data.title);
		},
	});
};

function show_attachments(container, employee, employee_name) {
	container.html(`<div class="text-muted" style="padding: 20px;">${__("Loading...")}</div>`);

	frappe.call({
		method: "hr_automation.hr_automation.page.employee_documents.employee_documents.get_employee_attachments",
		args: { employee },
		callback: (r) => render_attachments(container, employee, employee_name, r.message || []),
	});
}

function render_attachments(container, employee, employee_name, files) {
	let $wrapper = $(`
		<div>
			<h4>${frappe.utils.escape_html(employee_name)}
				<a href="/app/employee/${encodeURIComponent(employee)}" class="text-muted" style="font-size: 12px;">
					${__("Open Employee")}
				</a>
			</h4>
		</div>
	`);

	if (!files.length) {
		$wrapper.append(`<div class="text-muted">${__("No attachments found for this employee")}</div>`);
	} else {
		let $list = $('<div class="list-group"></div>');
		files.forEach((file) => {
			$list.append(`
				<a href="${file.file_url}" target="_blank" class="list-group-item">
					<i class="fa fa-paperclip"></i> ${frappe.utils.escape_html(file.file_name)}
					<span class="text-muted" style="margin-left: 8px;">(${frappe.utils.escape_html(file.source)})</span>
					<span class="text-muted pull-right">${frappe.datetime.comment_when(file.creation)}</span>
				</a>
			`);
		});
		$wrapper.append($list);
	}

	container.empty().append($wrapper);
}
