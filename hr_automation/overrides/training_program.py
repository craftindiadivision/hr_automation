import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet, update_nsm

from hrms.hr.doctype.training_program.training_program import TrainingProgram


class CustomTrainingProgram(NestedSet, TrainingProgram):
	"""Makes Training Program a nested-set tree, the same mechanism ERPNext uses
	for Item Group: "Is Group" marks a program as a parent (e.g. LEAP), and
	"Parent Program" links a program under one. Unlike Item Group, multiple root
	programs are allowed - most Training Programs have no group at all."""

	def validate(self):
		# validate_ledger (below) only catches a group being unchecked while it
		# still has children - it doesn't stop a non-group being picked as a
		# parent in the first place (the link filter only guards the UI), so
		# that has to be checked explicitly here.
		if self.custom_parent_training_program and not frappe.db.get_value(
			"Training Program", self.custom_parent_training_program, "custom_is_group"
		):
			frappe.throw(
				_("{0} is not marked as a group, so it cannot be used as a Parent Program").format(
					frappe.bold(self.custom_parent_training_program)
				)
			)

	def on_update(self):
		update_nsm(self)
		self.validate_ledger(group_identifier="custom_is_group")

		from hr_automation.api.training_completion import _sync_program_status, recompute_event_count

		# A leaf program's Number of Events is typed in directly. A group's is
		# always the sum of what's mapped under it, so any save that could
		# change that sum - editing a leaf's count, or moving a program to a
		# different parent - has to refresh the group(s) involved.
		if self.custom_is_group:
			recompute_event_count(self.name)
		if self.custom_parent_training_program:
			recompute_event_count(self.custom_parent_training_program)

		before = self.get_doc_before_save()
		old_parent = before.custom_parent_training_program if before else None
		if old_parent and old_parent != self.custom_parent_training_program:
			recompute_event_count(old_parent)

		# The target (Number of Events) may have just changed on this program
		# itself, so re-check whether it's now Completed (or no longer is).
		_sync_program_status(self.name)

	def on_trash(self):
		NestedSet.on_trash(self, allow_root_deletion=True)

	def after_delete(self):
		# on_trash runs before the row is actually removed, so recomputing the
		# parent's rollups there would still count this program. Has to happen
		# here instead, once it's really gone.
		if self.custom_parent_training_program:
			from hr_automation.api.training_completion import (
				recompute_completed_events,
				recompute_event_count,
			)

			recompute_event_count(self.custom_parent_training_program)
			recompute_completed_events(self.custom_parent_training_program)
