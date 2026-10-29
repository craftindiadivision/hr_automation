// Colours the Document Verification column only - the status badge stays
// HRMS's own (the applicant's answer to the offer), so a document rejection
// is never mistaken for the offer being rejected.
(() => {
	const settings = (frappe.listview_settings["Job Offer"] = frappe.listview_settings["Job Offer"] || {});
	const colors = { "Documents Accepted": "green", "Documents Rejected": "red" };
	settings.formatters = Object.assign(settings.formatters || {}, {
		custom_document_status(value) {
			if (!value) return "";
			return `<span class="indicator-pill ${colors[value] || "gray"}">${__(value)}</span>`;
		},
	});
})();
