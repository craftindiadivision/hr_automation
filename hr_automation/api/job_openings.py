import html
import json
import re

import frappe
from frappe.utils import get_url, pretty_date

DEFAULT_APPLICATION_WEB_FORM_ROUTE = "job_application"


def set_default_application_web_form_route(doc, method=None):
	"""validate hook: a published Job Opening needs an Application Web Form
	Route or its public page shows no Apply button at all - rather than rely on
	HR remembering to set this by hand on every opening, default it to our
	standard job application form the moment Publish is ticked."""
	if doc.publish and not doc.job_application_route:
		doc.job_application_route = DEFAULT_APPLICATION_WEB_FORM_ROUTE


@frappe.whitelist(allow_guest=True)
def published_jobs_js():
	"""Serve a self-contained JS widget listing published, open Job Openings.

	Meant to be loaded cross-origin via a plain <script src> tag (e.g. from a
	WordPress careers page), which needs no CORS setup since script loads
	aren't subject to the same-origin policy the way fetch()/XHR are.
	"""
	jobs = get_published_jobs()

	frappe.response["type"] = "download"
	frappe.response["filename"] = "craft-job-openings.js"
	frappe.response["filecontent"] = render_widget_script(jobs).encode("utf-8")
	frappe.response["content_type"] = "application/javascript"
	frappe.response["display_content_as"] = "inline"


def get_published_jobs():
	rows = frappe.get_all(
		"Job Opening",
		filters={"publish": 1, "status": "Open"},
		fields=[
			"job_title",
			"route",
			"company",
			"location",
			"employment_type",
			"posted_on",
			"description",
		],
		order_by="posted_on desc",
	)

	jobs = []
	for row in rows:
		jobs.append(
			{
				"title": row.job_title,
				"url": f"{get_url()}/{row.route}" if row.route else None,
				"company": row.company,
				"location": frappe.db.get_value("Branch", row.location, "branch") if row.location else None,
				"employment_type": row.employment_type,
				"posted_on": pretty_date(row.posted_on) if row.posted_on else None,
				"excerpt": strip_html(row.description, 160),
			}
		)
	return jobs


def strip_html(value, max_length=None):
	if not value:
		return ""
	text = re.sub(r"<[^>]+>", " ", value)
	text = html.unescape(text)
	text = re.sub(r"\s+", " ", text).strip()
	if max_length and len(text) > max_length:
		text = text[:max_length].rsplit(" ", 1)[0] + "..."
	return text


def render_widget_script(jobs):
	# Escape </script> so the embedded JSON can't break out of the <script> tag
	# it ends up inside on the WordPress page.
	data = json.dumps(jobs).replace("</", "<\\/")

	return f"""(function() {{
	var JOBS = {data};
	var CONTAINER_ID = "craft-job-openings";

	function el(tag, cls, html) {{
		var e = document.createElement(tag);
		if (cls) e.className = cls;
		if (html !== undefined) e.innerHTML = html;
		return e;
	}}

	function injectStyles() {{
		if (document.getElementById("craft-jobs-style")) return;
		var style = document.createElement("style");
		style.id = "craft-jobs-style";
		style.textContent = [
			".craft-jobs-grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }}",
			".craft-job-card {{ border: 1px solid #e2e2e2; border-radius: 10px; padding: 18px; background: #fff; }}",
			".craft-job-card h3 {{ margin: 0 0 6px; font-size: 1.05rem; }}",
			".craft-job-meta {{ font-size: 0.85rem; color: #666; margin-bottom: 10px; }}",
			".craft-job-excerpt {{ font-size: 0.9rem; color: #333; margin-bottom: 14px; }}",
			".craft-job-apply {{ display: inline-block; padding: 8px 16px; border-radius: 6px; background: #2b6cb0; color: #fff !important; text-decoration: none; font-size: 0.9rem; }}",
			".craft-jobs-empty {{ padding: 24px; text-align: center; color: #666; }}"
		].join("\\n");
		document.head.appendChild(style);
	}}

	function render() {{
		var container = document.getElementById(CONTAINER_ID);
		if (!container) return;
		injectStyles();

		if (!JOBS.length) {{
			container.appendChild(el("div", "craft-jobs-empty", "No open positions right now. Check back soon!"));
			return;
		}}

		var grid = el("div", "craft-jobs-grid");
		JOBS.forEach(function(job) {{
			var meta = [job.location, job.employment_type].filter(Boolean).join(" \\u00b7 ");
			var card = el("div", "craft-job-card");
			card.appendChild(el("h3", null, job.title));
			if (meta) card.appendChild(el("div", "craft-job-meta", meta));
			if (job.excerpt) card.appendChild(el("div", "craft-job-excerpt", job.excerpt));
			if (job.url) {{
				var a = el("a", "craft-job-apply", "View & Apply");
				a.href = job.url;
				a.target = "_blank";
				a.rel = "noopener";
				card.appendChild(a);
			}}
			grid.appendChild(card);
		}});
		container.appendChild(grid);
	}}

	if (document.readyState === "loading") {{
		document.addEventListener("DOMContentLoaded", render);
	}} else {{
		render();
	}}
}})();
"""
