// Latest Appraisal Date as a coloured badge: green within the last year,
// orange if the last appraisal is older than that.
(() => {
	const settings = (frappe.listview_settings["Employee"] = frappe.listview_settings["Employee"] || {});
	settings.formatters = Object.assign(settings.formatters || {}, {
		custom_latest_appraisal_date(value) {
			if (!value) return "";
			const year_ago = frappe.datetime.add_months(frappe.datetime.get_today(), -12);
			const color = value >= year_ago ? "green" : "orange";
			return `<span class="indicator-pill ${color}">${frappe.datetime.str_to_user(value)}</span>`;
		},
	});
})();
