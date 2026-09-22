app_name = "hr_automation"
app_title = "HR Automation"
app_publisher = " Craft Interactive Technology"
app_description = "HR Automation"
app_email = "kadeeja.craftinteractive@gmail.com"
app_license = "mit"

fixtures = [
	{
		"doctype": "Custom Field",
		"filters": [
			["dt", "in", ["Appointment Letter", "Job Applicant", "Job Offer", "Employee Separation", "Employee", "Appraisal Cycle", "Appraisal", "Training Event", "Training Program", "Training Feedback", "Training Event Employee"]]
		],
	},
	{
		"doctype": "Print Format",
		"filters": [
			[
				"name",
				"in",
				[
					"Appointment Letter Intern to Employee Under Probation",
					"Appointment Letter",
					"Confirmation as Employee",
					"Employee Offer Letter",
					"Intern Offer Letter",
					"Full and Final Settlement Letter",
					"Experience Letter",
					"Increment Letter",
					"Relieving Letter",
					"Training Program Certificate",
					"Training Program Group Certificate",
				],
			]
		],
	},
	{
		"doctype": "Appointment Letter Template",
		"filters": [["name", "in", ["Intern to Employee under Probation", "Direct Appointment"]]],
	},
	{
		"doctype": "Property Setter",
		"filters": [
			[
				"name",
				"in",
				[
					"Training Feedback-feedback-reqd",
					"Training Feedback-feedback-label",
					"Training Program-is_tree",
					"Training Program-nsm_parent_field",
				],
			]
		],
	},
	"Confidentiality and Non-Disclosure Agreement",
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "hr_automation",
# 		"logo": "/assets/hr_automation/logo.png",
# 		"title": "HR Automation",
# 		"route": "/hr_automation",
# 		"has_permission": "hr_automation.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/hr_automation/css/hr_automation.css"
# app_include_js = "/assets/hr_automation/js/hr_automation.js"

# include js, css files in header of web template
# web_include_css = "/assets/hr_automation/css/hr_automation.css"
# web_include_js = "/assets/hr_automation/js/hr_automation.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "hr_automation/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# Boot Session
# ------------
boot_session = "hr_automation.boot.boot_session"

# include js in doctype views
doctype_js = {
	"HR Policy": "public/js/hr_policy.js",
	"Appointment Letter": ["public/js/salary_breakup.js", "public/js/appointment_letter.js"],
	"Job Offer": ["public/js/salary_breakup.js", "public/js/job_offer.js"],
	"Confidentiality and Non-Disclosure Agreement": "public/js/nda.js",
	"Employee": "public/js/employee.js",
	"Employee Survey": "public/js/employee_survey.js",
	"Training Feedback": "public/js/training_feedback.js",
	"Training Event": "public/js/training_event.js",
	"Training Program": "public/js/training_program.js",
	"Knowledge Hub": "public/js/knowledge_hub.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "hr_automation/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "hr_automation.utils.jinja_methods",
# 	"filters": "hr_automation.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "hr_automation.install.before_install"
# after_install = "hr_automation.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "hr_automation.uninstall.before_uninstall"
# after_uninstall = "hr_automation.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "hr_automation.utils.before_app_install"
# after_app_install = "hr_automation.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "hr_automation.utils.before_app_uninstall"
# after_app_uninstall = "hr_automation.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "hr_automation.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "hr_automation.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

permission_query_conditions = {
	"Knowledge Hub": "hr_automation.api.knowledge_hub.get_permission_query_conditions",
}

has_permission = {
	"Knowledge Hub": "hr_automation.api.knowledge_hub.has_permission",
}

override_doctype_class = {
	"Training Program": "hr_automation.overrides.training_program.CustomTrainingProgram",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Employee Separation": {
		"validate": "hr_automation.api.employee_separation.sync_relieving_date_to_employee",
	},
	"Job Offer": {
		"on_update": "hr_automation.api.recruitment_automation.on_job_offer_status_change",
	},
	"Employee": {
		"after_insert": [
			"hr_automation.api.employee_onboarding.create_onboarding_program",
			"hr_automation.api.hr_policy.add_employee_to_all_policies",
		],
		"on_update": "hr_automation.api.employee_onboarding.create_onboarding_program",
	},
	"Training Event": {
		"on_submit": [
			"hr_automation.api.training_calendar.sync_training_event_to_calendar",
			"hr_automation.api.training_completion.on_training_event_change",
		],
		"on_update_after_submit": [
			"hr_automation.api.training_calendar.sync_training_event_to_calendar",
			"hr_automation.api.training_completion.on_training_event_change",
		],
		"on_cancel": [
			"hr_automation.api.training_calendar.remove_training_event_from_calendar",
			"hr_automation.api.training_completion.on_training_event_change",
		],
	},
	"Employee Survey Response": {
		"before_insert": "hr_automation.api.employee_survey.anonymize_survey_response",
		"after_insert": "hr_automation.api.employee_survey.remove_survey_response_tracking",
	},
	"Employee Survey": {
		"on_update": "hr_automation.api.employee_survey.notify_survey_recipients",
	},
	"Training Feedback": {
		"on_submit": "hr_automation.api.training_completion.on_training_feedback_change",
		"on_cancel": "hr_automation.api.training_completion.on_training_feedback_change",
	},
	"Knowledge Hub": {
		"on_update": "hr_automation.api.knowledge_hub.queue_conversion",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"hr_automation.api.employee_assessments.send_assessment_notifications",
		"hr_automation.api.training_calendar.send_event_reminders",
	],
}

# Testing
# -------

# before_tests = "hr_automation.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "hr_automation.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "hr_automation.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "hr_automation.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["hr_automation.utils.before_request"]
# after_request = ["hr_automation.utils.after_request"]

# Job Events
# ----------
# before_job = ["hr_automation.utils.before_job"]
# after_job = ["hr_automation.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"hr_automation.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

