frappe.ui.form.on("Employee Survey", {
	get_employees(frm) {
		frappe.call({
			method: "set_employees",
			doc: frm.doc,
			freeze: true,
			freeze_message: __("Fetching Employees"),
			callback: function () {
				refresh_field("recipients");
				frm.dirty();
			},
		});
	},
});
