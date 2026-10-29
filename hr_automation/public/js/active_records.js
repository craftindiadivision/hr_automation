// Year-wise masters (a new Salary Structure, Leave Policy, Holiday List... each
// year) and the field that marks one as currently in use. Loaded as the list
// script of each of these doctypes (green "Active" / grey "Inactive"
// indicator) and as a form script of the documents that pick them (Job Offer,
// Appointment Letter, ...), where only active ones are offered.
// Uses frappe.provide rather than top-level const because this file is
// evaluated once per doctype that includes it.
frappe.provide("hr_automation.active_records");

hr_automation.active_records.FIELDS = {
	// Existing fields
	"Salary Structure": { field: "is_active", active: (v) => v === "Yes", filter: ["=", "Yes"], submittable: true },
	"Leave Period": { field: "is_active", active: (v) => !!v, filter: ["=", 1] },
	"Income Tax Slab": { field: "disabled", active: (v) => !v, filter: ["=", 0], submittable: true },
	"Fiscal Year": { field: "disabled", active: (v) => !v, filter: ["=", 0] },
	// Added by HR Automation (custom_is_active)
	"Leave Policy": { field: "custom_is_active", active: (v) => !!v, filter: ["=", 1], submittable: true },
	"Holiday List": { field: "custom_is_active", active: (v) => !!v, filter: ["=", 1] },
	"Payroll Period": { field: "custom_is_active", active: (v) => !!v, filter: ["=", 1] },
};

// Only offer active, submitted (where applicable) records in every Link field
// on this form that points at one of the doctypes above.
hr_automation.active_records.set_link_queries = function (frm) {
	frm.meta.fields
		.filter((df) => df.fieldtype === "Link" && hr_automation.active_records.FIELDS[df.options])
		.forEach((df) => {
			frm.set_query(df.fieldname, () => {
				const config = hr_automation.active_records.FIELDS[df.options];
				const filters = { [config.field]: config.filter };
				if (config.submittable) filters.docstatus = 1;
				return { filters };
			});
		});
};

// The doctype's own list settings (if any) load before this file, so extend
// them instead of replacing them.
Object.entries(hr_automation.active_records.FIELDS).forEach(([doctype, config]) => {
	const settings = (frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {});
	if (settings.hr_automation_active_indicator) return;
	settings.hr_automation_active_indicator = true;

	settings.add_fields = [...new Set([...(settings.add_fields || []), config.field])];
	const original_get_indicator = settings.get_indicator;
	settings.get_indicator = function (doc) {
		if (config.active(doc[config.field])) {
			return [__("Active"), "green", `${config.field},=,${config.filter[1]}`];
		}
		if (original_get_indicator) return original_get_indicator(doc);
		return [__("Inactive"), "gray", `${config.field},!=,${config.filter[1]}`];
	};
});
