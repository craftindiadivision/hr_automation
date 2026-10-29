import frappe


def execute():
	"""Appointment Letters already emailed before Mode existed were Online."""
	frappe.db.sql(
		"""update `tabAppointment Letter` set custom_mode = 'Online'
		where ifnull(custom_mode, '') = '' and custom_letter_sent_on is not null"""
	)
