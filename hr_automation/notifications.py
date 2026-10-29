def get_notification_config():
	return {
		"for_doctype": {
			"Employee Onboarding": {"docstatus": ["!=", 2]},
			"Training Assessment": {"docstatus": ["!=", 2]},
		}
	}
