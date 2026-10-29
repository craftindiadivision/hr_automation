// Same colours as the Mode band on the form.
frappe.listview_settings["Appointment Letter"] = Object.assign(frappe.listview_settings["Appointment Letter"] || {}, {
	add_fields: ["custom_mode"],
	get_indicator(doc) {
		if (doc.custom_mode === "Online") return [__("Online"), "blue", "custom_mode,=,Online"];
		if (doc.custom_mode === "Offline") return [__("Offline"), "orange", "custom_mode,=,Offline"];
		return [__("Mode Not Set"), "red", "custom_mode,is,not set"];
	},
});
