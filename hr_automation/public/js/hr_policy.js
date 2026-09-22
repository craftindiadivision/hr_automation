frappe.ui.form.on("HR Policy", {
	refresh: function (frm) {
		if (frm.is_new()) return;

		let my_row = (frm.doc.employee_acknowledgements || []).find(
			(row) => row.employee === frappe.boot.employee
		);

		if (my_row && !my_row.acknowledged) {
			frm.add_custom_button(__("Mark as Read"), function () {
				frappe.call({
					method: "hr_automation.api.hr_policy.acknowledge",
					args: { hr_policy: frm.doc.name },
					freeze: true,
					callback: function () {
						frappe.show_alert({ message: __("Thanks - marked as read."), indicator: "green" });
						frm.reload_doc();
					},
				});
			}).addClass("btn-primary");
		} else if (my_row && my_row.acknowledged) {
			frm.dashboard.set_headline_alert(
				`<div class="text-muted">${__("You acknowledged this policy on")} ${frappe.datetime.str_to_user(my_row.acknowledged_on)}</div>`
			);
		}
	},
});
