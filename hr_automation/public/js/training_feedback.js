frappe.ui.form.on("Training Feedback", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		if (!frm.doc.training_event) return;
		frm.add_custom_button(__("Fill Feedback Form"), () => open_feedback_dialog(frm));
	},
});

function open_feedback_dialog(frm) {
	frappe.call({
		method: "hr_automation.api.training_feedback.get_feedback_questions",
		args: { training_event: frm.doc.training_event },
		callback: (r) => {
			const data = r.message || { form_exists: false, questions: [] };
			if (!data.form_exists) {
				frappe.msgprint(
					__("No feedback form has been set up for this Training Event yet. Ask HR to create a Training Feedback Form for {0}.", [frm.doc.training_event])
				);
				return;
			}
			if (!data.questions.length) {
				frappe.msgprint(__("The feedback form for this event has no questions yet."));
				return;
			}
			show_feedback_dialog(frm, data.questions);
		},
	});
}

function existing_answer(frm, question_text) {
	const row = (frm.doc.custom_answers || []).find((a) => a.question === question_text);
	return row ? row.answer : null;
}

function show_feedback_dialog(frm, questions) {
	let fields = [];

	questions.forEach((q, i) => {
		let reqd = q.is_mandatory ? 1 : 0;
		let existing = existing_answer(frm, q.question);

		if (q.question_type === "Short Answer") {
			fields.push({ fieldtype: "Data", fieldname: `q_${i}`, label: q.question, reqd, default: existing || "" });
		} else if (q.question_type === "Long Answer") {
			fields.push({
				fieldtype: "Small Text",
				fieldname: `q_${i}`,
				label: q.question,
				reqd,
				default: existing || "",
			});
		} else if (q.question_type === "Single Choice") {
			let opts = (q.options || "").split("\n").filter(Boolean);
			fields.push({
				fieldtype: "Select",
				fieldname: `q_${i}`,
				label: q.question,
				options: [""].concat(opts),
				reqd,
				default: existing || "",
			});
		} else if (q.question_type === "Yes/No") {
			fields.push({
				fieldtype: "Select",
				fieldname: `q_${i}`,
				label: q.question,
				options: ["", "Yes", "No"],
				reqd,
				default: existing || "",
			});
		} else if (q.question_type === "Rating (1-5)") {
			let default_rating = existing ? Math.max(0, Math.min(5, parseInt(existing, 10))) / 5 : 0;
			fields.push({ fieldtype: "Rating", fieldname: `q_${i}`, label: q.question, reqd, default: default_rating });
		} else if (q.question_type === "Multiple Choice") {
			let opts = (q.options || "").split("\n").filter(Boolean);
			let existing_selected = (existing || "").split(",").map((s) => s.trim());
			fields.push({ fieldtype: "Section Break", label: q.question });
			opts.forEach((opt, oi) => {
				fields.push({
					fieldtype: "Check",
					fieldname: `q_${i}_mc_${oi}`,
					label: opt,
					default: existing_selected.includes(opt) ? 1 : 0,
				});
			});
			fields.push({ fieldtype: "Section Break" });
		}
	});

	let dialog = new frappe.ui.Dialog({
		title: __("Training Feedback"),
		fields: fields,
		size: "large",
		primary_action_label: __("Save Answers"),
		primary_action(values) {
			let missing = null;
			let answers = [];

			questions.forEach((q, i) => {
				let answer;
				if (q.question_type === "Multiple Choice") {
					let opts = (q.options || "").split("\n").filter(Boolean);
					let selected = opts.filter((opt, oi) => values[`q_${i}_mc_${oi}`]);
					answer = selected.join(", ");
				} else if (q.question_type === "Rating (1-5)") {
					let v = values[`q_${i}`] || 0;
					answer = String(Math.round(v * 5));
					if (answer === "0") answer = "";
				} else {
					answer = values[`q_${i}`] || "";
				}

				if (q.is_mandatory && !answer) {
					missing = q.question;
				}
				answers.push({ question: q.question, question_type: q.question_type, answer: answer });
			});

			if (missing) {
				frappe.msgprint(__("Please answer: {0}", [missing]));
				return;
			}

			frm.clear_table("custom_answers");
			answers.forEach((a) => {
				if (!a.answer) return;
				let row = frm.add_child("custom_answers");
				row.question = a.question;
				row.question_type = a.question_type;
				row.answer = a.answer;
			});
			frm.refresh_field("custom_answers");
			frm.dirty();
			dialog.hide();
			frappe.show_alert({ message: __("Feedback captured - remember to Save."), indicator: "green" });
		},
	});

	dialog.show();
}
