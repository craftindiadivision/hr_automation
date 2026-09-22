import frappe
from frappe import _
from frappe.utils import add_days, format_datetime, today


def send_event_reminders():
	"""Daily job: emails every participant of a Training Event starting
	tomorrow. Google Calendar's own reminder (send_reminder=1, set when the
	event was synced) isn't guaranteed to fire a full day ahead - depends on
	that calendar account's own settings - so this is a fixed, independent
	reminder sent directly by us, one day before, every time."""
	tomorrow = add_days(today(), 1)

	events = frappe.get_all(
		"Training Event",
		filters={
			"docstatus": 1,
			"start_time": ["between", [f"{tomorrow} 00:00:00", f"{tomorrow} 23:59:59"]],
			"custom_reminder_sent": 0,
		},
		pluck="name",
	)

	for event_name in events:
		doc = frappe.get_doc("Training Event", event_name)
		_send_reminder_for_event(doc)
		doc.db_set("custom_reminder_sent", 1, update_modified=False)


def _send_reminder_for_event(doc):
	recipients = []
	seen_emails = set()

	employee_names = [row.employee for row in doc.employees if row.employee]
	if employee_names:
		for emp in frappe.get_all(
			"Employee",
			filters={"name": ["in", employee_names]},
			fields=["employee_name", "user_id", "company_email", "personal_email"],
		):
			email = emp.user_id or emp.company_email or emp.personal_email
			if email and email not in seen_emails:
				seen_emails.add(email)
				recipients.append({"email": email, "name": emp.employee_name})

	if doc.trainer_email and doc.trainer_email not in seen_emails:
		seen_emails.add(doc.trainer_email)
		recipients.append({"email": doc.trainer_email, "name": doc.trainer_name or "Trainer"})

	if not recipients:
		return

	when = format_datetime(doc.start_time, "EEEE, d MMMM 'at' h:mm a")
	meet_line = (
		f'<p>Meet link: <a href="{doc.custom_google_meet_link}">{doc.custom_google_meet_link}</a></p>'
		if doc.custom_google_meet_link
		else ""
	)

	for recipient in recipients:
		message = frappe.render_template(
			"""
			<p>Hi {{ name }},</p>
			<p>Reminder: <b>{{ event_name }}</b> is scheduled for tomorrow.</p>
			<p>{{ when }}{% if location %} &middot; {{ location }}{% endif %}</p>
			{{ meet_line }}
			""",
			{
				"name": recipient["name"],
				"event_name": doc.event_name,
				"when": when,
				"location": doc.location,
				"meet_line": meet_line,
			},
		)
		frappe.sendmail(
			recipients=[recipient["email"]],
			subject=_("Reminder: {0} is tomorrow").format(doc.event_name),
			message=message,
			reference_doctype="Training Event",
			reference_name=doc.name,
		)


def sync_training_event_to_calendar(doc, method=None):
	"""Push a submitted Training Event into the configured Google Calendar as an
	Event with all enrolled employees as attendees. Google's own calendar
	notification settings (on the connected account) control when reminder
	emails go out before the event."""
	google_calendar = frappe.db.get_single_value("HR Automation Settings", "training_google_calendar")
	if not google_calendar:
		return

	participants = _get_event_participants(doc)
	if not participants:
		return

	if doc.custom_google_calendar_event and frappe.db.exists("Event", doc.custom_google_calendar_event):
		event = frappe.get_doc("Event", doc.custom_google_calendar_event)
	else:
		event = frappe.new_doc("Event")

	event.subject = f"Training: {doc.event_name}"
	event.starts_on = doc.start_time
	event.ends_on = doc.end_time
	event.description = doc.introduction or doc.course or ""
	event.event_type = "Public"
	event.send_reminder = 1
	event.sync_with_google_calendar = 1
	event.google_calendar = google_calendar
	event.add_video_conferencing = 1
	event.event_participants = []
	for participant in participants:
		event.append("event_participants", participant)

	if event.is_new():
		event.insert(ignore_permissions=True)
		doc.db_set("custom_google_calendar_event", event.name, update_modified=False)
	else:
		event.save(ignore_permissions=True)

	# Google Calendar generates the Meet link synchronously during insert/save above
	# (via frappe's own Event.after_insert / Event.on_update hooks) - read it back.
	meet_link = frappe.db.get_value("Event", event.name, "google_meet_link")
	if meet_link:
		doc.db_set("custom_google_meet_link", meet_link, update_modified=False)


def remove_training_event_from_calendar(doc, method=None):
	if doc.custom_google_calendar_event and frappe.db.exists("Event", doc.custom_google_calendar_event):
		frappe.delete_doc("Event", doc.custom_google_calendar_event, ignore_permissions=True, force=True)
		frappe.db.set_value("Training Event", doc.name, "custom_google_calendar_event", None)


def _get_event_participants(doc) -> list[dict]:
	participants = []
	seen_emails = set()

	employee_names = [row.employee for row in doc.employees if row.employee]
	if employee_names:
		employee_rows = frappe.get_all(
			"Employee",
			filters={"name": ["in", employee_names]},
			fields=["name", "user_id", "company_email", "personal_email"],
		)
		for emp in employee_rows:
			email = emp.user_id or emp.company_email or emp.personal_email
			if email and email not in seen_emails:
				seen_emails.add(email)
				participants.append(
					{"reference_doctype": "Employee", "reference_docname": emp.name, "email": email}
				)

	if doc.trainer_email and doc.trainer_email not in seen_emails:
		seen_emails.add(doc.trainer_email)
		participants.append(
			{
				"reference_doctype": "Training Event",
				"reference_docname": doc.name,
				"email": doc.trainer_email,
			}
		)

	return participants
