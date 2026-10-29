frappe.ui.form.on("Knowledge Hub", {
	refresh: function (frm) {
		render_preview(frm);
		listen_for_pdf(frm);
		hide_attachments(frm);
	},
	onload: function (frm) {
		frm.set_query("training_event", function () {
			return { filters: { event_status: "Completed" } };
		});
	},
});

function hide_attachments(frm) {
	frm.sidebar.sidebar.find(".form-attachments").hide();
}

function render_preview(frm) {
	let $wrapper = frm.get_field("pdf_preview").$wrapper;
	$wrapper.empty();

	let slides = frm.doc.slides || [];

	if (slides.length) {
		render_slide_viewer($wrapper, slides);
	} else if (frm.doc.presentation) {
		$wrapper.html(`
			<div class="text-muted" style="padding:16px;">
				${__("Preparing the preview - this can take a little while. This will update automatically once it's ready.")}
			</div>
		`);
	} else {
		$wrapper.html(`
			<div class="text-muted" style="padding:16px;">
				${__("Attach a presentation above to see a preview here.")}
			</div>
		`);
	}
}

function render_slide_viewer($wrapper, slides) {
	// Plain images, one at a time - the master PDF/PPT is never sent to the
	// browser at all. Right-click is disabled on the image as a further
	// (not foolproof, just an extra step) deterrent against casual saving.
	let $toolbar = $(`
		<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
			<button class="btn btn-xs btn-default kh-prev">${__("Prev")}</button>
			<span class="kh-page-indicator text-muted small"></span>
			<button class="btn btn-xs btn-default kh-next">${__("Next")}</button>
		</div>
	`);
	let $image_area = $(`
		<div style="border:1px solid var(--border-color);border-radius:6px;overflow:auto;
			max-height:650px;text-align:center;background:var(--subtle-fg, #f5f5f5);padding:10px;">
		</div>
	`);
	let img = document.createElement("img");
	img.style.maxWidth = "100%";
	img.style.boxShadow = "0 1px 4px rgba(0,0,0,0.15)";
	img.draggable = false;
	img.oncontextmenu = () => false;
	$image_area.append(img);
	$wrapper.append($toolbar).append($image_area);

	let index = 0;

	function show() {
		img.src = slides[index].image;
		$toolbar.find(".kh-page-indicator").text(`${index + 1} / ${slides.length}`);
	}

	$toolbar.find(".kh-prev").on("click", () => {
		if (index > 0) {
			index--;
			show();
		}
	});
	$toolbar.find(".kh-next").on("click", () => {
		if (index < slides.length - 1) {
			index++;
			show();
		}
	});

	show();
}

function listen_for_pdf(frm) {
	if ((frm.doc.slides || []).length || frm.is_new() || frm.__knowledge_hub_listening) return;
	frm.__knowledge_hub_listening = true;

	frappe.realtime.on("knowledge_hub_pdf_ready", (data) => {
		if (data.name === frm.doc.name) {
			frm.reload_doc();
		}
	});
}
