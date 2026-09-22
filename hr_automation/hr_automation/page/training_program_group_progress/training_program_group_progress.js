frappe.pages["training-program-group-progress"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Program Group Progress"),
		single_column: true,
	});

	new hr_automation_group_progress.App(page);
};

window.hr_automation_group_progress = window.hr_automation_group_progress || {};

hr_automation_group_progress.App = class {
	constructor(page) {
		this.page = page;
		this.selectedGroup = null;
		this.selectedEmployee = null;
		this.makeLayout();
		this.loadGroups();
	}

	makeLayout() {
		this.page.main.html(`
			<div class="group-progress-wrapper">
				<div class="row" style="margin-bottom: 16px;">
					<div class="col-md-4">
						<select class="form-control group-select">
							<option value="">${__("Select a Program Group...")}</option>
						</select>
					</div>
				</div>
				<div class="row group-body" style="display:none;">
					<div class="col-md-4">
						<input type="text" class="form-control employee-search"
							placeholder="${__("Search Employee")}" style="margin-bottom: 10px;">
						<div class="employee-list list-group" style="max-height: 65vh; overflow-y: auto;"></div>
					</div>
					<div class="col-md-8">
						<div class="progress-detail">
							<div class="text-muted" style="padding: 20px;">${__("Select an employee to view their progress")}</div>
						</div>
					</div>
				</div>
			</div>
		`);

		this.groupSelect = this.page.main.find(".group-select");
		this.groupBody = this.page.main.find(".group-body");
		this.employeeList = this.page.main.find(".employee-list");
		this.detail = this.page.main.find(".progress-detail");

		this.groupSelect.on("change", () => {
			this.selectedGroup = this.groupSelect.val();
			this.selectedEmployee = null;
			if (this.selectedGroup) {
				this.groupBody.show();
				this.getEmployees();
			} else {
				this.groupBody.hide();
			}
		});

		let debouncedSearch = frappe.utils.debounce(() => this.getEmployees(), 300);
		this.page.main.find(".employee-search").on("input", debouncedSearch);
	}

	loadGroups() {
		frappe.call({
			method: "hr_automation.api.training_completion.get_program_groups",
			callback: (r) => {
				(r.message || []).forEach((g) => {
					this.groupSelect.append(
						$("<option>").val(g.name).text(g.name)
					);
				});
			},
		});
	}

	getEmployees() {
		let txt = this.page.main.find(".employee-search").val();
		frappe.call({
			method: "hr_automation.api.training_completion.get_employees",
			args: { txt },
			callback: (r) => this.renderEmployees(r.message || []),
		});
	}

	renderEmployees(employees) {
		this.employeeList.empty();
		if (!employees.length) {
			this.employeeList.html(`<div class="text-muted" style="padding: 10px;">${__("No employees found")}</div>`);
			return;
		}
		employees.forEach((emp) => {
			let $item = $(`
				<a href="#" class="list-group-item employee-item">
					<strong>${frappe.utils.escape_html(emp.employee_name)}</strong><br>
					<small class="text-muted">${frappe.utils.escape_html(emp.designation || "")}</small>
				</a>
			`);
			$item.on("click", (e) => {
				e.preventDefault();
				this.employeeList.find(".employee-item").removeClass("active");
				$item.addClass("active");
				this.loadStatus(emp);
			});
			this.employeeList.append($item);
		});
	}

	loadStatus(employee) {
		this.detail.html(`<div class="text-muted" style="padding: 20px;">${__("Loading...")}</div>`);
		frappe.call({
			method: "hr_automation.api.training_completion.get_group_status",
			args: { employee: employee.name, parent_program: this.selectedGroup },
			callback: (r) => this.renderStatus(employee, r.message),
		});
	}

	renderStatus(employee, status) {
		let groupTitle = this.groupSelect.find("option:selected").text();
		let badge = status.is_completed
			? `<span class="indicator-pill green">${__("Completed")}</span>`
			: `<span class="indicator-pill orange">${__("In Progress")}</span>`;

		let html = `<h4>${frappe.utils.escape_html(employee.employee_name)} ${badge}</h4>`;

		if (status.is_completed) {
			html += `<p class="text-muted">${__("Completed on")} ${frappe.datetime.str_to_user(status.completed_on)}</p>`;
			html += `<a class="btn btn-sm btn-primary" target="_blank"
				href="/printview?doctype=Training%20Program%20Group%20Completion&name=${encodeURIComponent(status.name)}&format=Training%20Program%20Group%20Certificate">
				${__("Print Certificate")}</a>`;
		}

		html += '<div class="row" style="margin-top: 20px;">';
		status.programs.forEach((row) => {
			let rowBadge = row.completed
				? `<span class="text-success">&#10003; ${__("Completed")}</span>`
				: `<span class="text-muted">${__("In Progress")}</span>`;
			html += `
				<div class="col-sm-6" style="margin-bottom: 16px;">
					<div style="border:1px solid #eee;border-radius:6px;padding:14px;">
						<div style="font-weight:600;font-size:15px;">${frappe.utils.escape_html(row.training_program)}</div>
						<div style="font-size:22px;margin:6px 0;">${row.progress}</div>
						<div>${rowBadge}</div>
						${row.completed_on ? `<div class="text-muted" style="font-size:12px;">${frappe.datetime.str_to_user(row.completed_on)}</div>` : ""}
					</div>
				</div>
			`;
		});
		html += "</div>";

		this.detail.html(html);
	}
};
