import frappe
from frappe import _
from frappe.utils import now_datetime, time_diff_in_hours

LINK_VALIDITY_HOURS = 24


def check_not_expired(sent_at):
	"""Raises a clear, distinct error once more than LINK_VALIDITY_HOURS have
	passed since the link was (re)sent. Call this only after an "already
	submitted/responded" check, so a completed action never gets reported as
	expired - it's a different, perfectly fine terminal state.

	A missing sent_at (data from before this check existed) is treated as not
	expired, so it fails open rather than silently locking out old links."""
	if sent_at and time_diff_in_hours(now_datetime(), sent_at) > LINK_VALIDITY_HOURS:
		frappe.throw(_("This link has expired. Please contact HR."), title=_("Link Expired"))


def is_expired(sent_at) -> bool:
	return bool(sent_at and time_diff_in_hours(now_datetime(), sent_at) > LINK_VALIDITY_HOURS)


def stamp_sent_now(doc, sent_at_field: str, reminder_field: str | None = None):
	"""Resets the 24-hour validity window to start now - called every time a link
	is actually (re)sent, even when the token string itself is being reused, so a
	resend revives an old unclicked copy of the email rather than leaving it dead.
	If reminder_field is given, also clears it, so a resend gets its own fresh
	stale-pending-action reminder instead of being silently skipped as "already
	reminded" from a previous, now-irrelevant send."""
	doc.db_set(sent_at_field, now_datetime(), update_modified=False)
	if reminder_field:
		doc.db_set(reminder_field, 0, update_modified=False)


def check_email_matches(stored_email, provided_email):
	"""The recipient's email is never embedded in the link itself (that would
	defeat the point) - the visitor must type it in. Only once it matches the
	address the link was actually sent to does any real data get returned."""
	if (
		not stored_email
		or not provided_email
		or stored_email.strip().lower() != provided_email.strip().lower()
	):
		frappe.throw(
			_("The email address you entered doesn't match our records for this link."),
			title=_("Email Verification Failed"),
		)
