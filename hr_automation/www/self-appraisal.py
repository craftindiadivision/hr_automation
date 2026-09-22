import frappe

no_cache = 1


def get_context(context):
	token = frappe.form_dict.get("token")
	context.token = token
	context.valid = False
	context.submitted = False
	context.employee_name = None
	context.ratings = []
	context.reflections = ""

	if not token:
		return

	name = frappe.db.get_value("Appraisal", {"custom_self_appraisal_token": token}, "name")
	if not name:
		return

	doc = frappe.get_doc("Appraisal", name)
	context.valid = True
	context.employee_name = doc.employee_name
	context.submitted = doc.docstatus == 1
	context.reflections = doc.reflections or ""
	context.ratings = [
		{
			"name": row.name,
			"criteria": row.criteria,
			"weightage": row.per_weightage,
			"rating": row.rating or 0,
		}
		for row in doc.self_ratings
	]
