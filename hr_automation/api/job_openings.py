import html
import ipaddress
import json
import re
from urllib.parse import urlparse

import frappe
from frappe import _
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


LINKEDIN_SOURCE = "LinkedIn"
SOURCE_PARAM = "source"
SOURCE_COOKIE = "hr_applicant_source"
SOURCE_COOKIE_DAYS = 7


def _is_local_address(url: str) -> bool:
	"""True for addresses only this computer or network can reach."""
	host = urlparse(url).hostname or ""
	try:
		ip = ipaddress.ip_address(host)
		return ip.is_loopback or ip.is_private
	except ValueError:
		return host == "localhost" or host.endswith((".local", ".localhost", ".test", ".craft"))


@frappe.whitelist()
def get_linkedin_message(job_opening: str) -> str:
	"""The post to paste into LinkedIn: hiring headline, apply now, and the link
	to this opening's public page. The link carries ?source=LinkedIn, so
	applicants who arrive through it are recorded as coming from LinkedIn."""
	frappe.has_permission("Job Opening", "read", job_opening, throw=True)
	job = frappe.get_doc("Job Opening", job_opening)
	if not job.publish or job.status != "Open" or not job.route:
		frappe.throw(_("Publish the opening (and keep it Open) before posting it on LinkedIn"))

	location = frappe.db.get_value("Branch", job.location, "branch") if job.location else None
	details = " · ".join(x for x in (job.company, location, job.employment_type) if x)
	link = get_url(f"/{job.route}?{SOURCE_PARAM}={LINKEDIN_SOURCE}")
	if _is_local_address(link):
		frappe.msgprint(
			_(
				"The link in this post starts with {0}, which only works on this computer, so people on "
				"LinkedIn won't be able to open it. Set the site's public address first (host_name in the "
				"site config), then copy the post again."
			).format(frappe.bold(urlparse(link).netloc)),
			title=_("Link won't open for others"),
			indicator="orange",
		)
	return f"We're hiring: {job.job_title}\n{details}\nApply now: {link}"


def remember_applicant_source():
	"""before_request: someone opening a job page (or the application form) from
	a tracked link (?source=LinkedIn) has that source remembered for a week, so
	it is still known when they submit the application."""
	source = frappe.form_dict.get(SOURCE_PARAM)
	if not source or not frappe.request or not frappe.request.path.startswith(("/jobs/", "/job_application")):
		return
	if frappe.db.exists("Job Applicant Source", source):
		frappe.local.cookie_manager.set_cookie(SOURCE_COOKIE, source, max_age=SOURCE_COOKIE_DAYS * 24 * 3600)


def set_applicant_source_from_link(doc, method=None):
	"""Job Applicant before_insert: an applicant who arrived through a tracked
	link gets the remembered Source. Only an existing Job Applicant Source is
	accepted, and a Source already set is never replaced."""
	if doc.source:
		return
	request = getattr(frappe.local, "request", None)  # none in scripts, imports, background jobs
	source = request.cookies.get(SOURCE_COOKIE) if request else None
	if source and frappe.db.exists("Job Applicant Source", source):
		doc.source = source
