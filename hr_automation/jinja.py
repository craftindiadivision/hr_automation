import base64

import frappe

_logo_data_uri = None


def get_logo_data_uri() -> str:
	"""The company logo shipped with the app, inlined into print formats so PDFs
	don't download it over the network - that download goes through the site's
	host_name, which breaks whenever that address is unreachable (e.g. an
	expired tunnel), and the file differs per site. (Cached in a module global:
	Frappe only registers plain functions as Jinja methods, not lru_cache wrappers.)"""
	global _logo_data_uri
	if _logo_data_uri is None:
		with open(frappe.get_app_path("hr_automation", "public", "images", "craft_logo.png"), "rb") as f:
			_logo_data_uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
	return _logo_data_uri
