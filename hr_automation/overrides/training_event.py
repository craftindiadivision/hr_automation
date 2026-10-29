def get_dashboard_for_training_event(data):
	data["non_standard_fieldnames"].update({"Training Assessment": "training_event"})
	data["non_standard_fieldnames"].pop("Training Result", None)

	for group in data["transactions"]:
		group["items"] = [item for item in group["items"] if item != "Training Result"]
	data["transactions"] = [group for group in data["transactions"] if group["items"]]

	feedback_group = next((g for g in data["transactions"] if "Training Feedback" in g["items"]), None)
	if feedback_group:
		feedback_group["items"].append("Training Assessment")
	else:
		data["transactions"].append({"items": ["Training Assessment"]})
	return data
