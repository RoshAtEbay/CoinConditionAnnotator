"""Coin condition annotation tool."""

from __future__ import annotations

import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sheets

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-coins-2026-change-in-prod")

CONDITION_BUCKETS = [
    "Below Fine",
    "Fine to Very Fine",
    "Extra Fine to AU",
    "Uncirculated",
    "Cannot determine from image",
]

SERVICE_ACCOUNT_EMAIL = os.environ.get("SERVICE_ACCOUNT_EMAIL", "")


def _next_unannotated(items: list[dict], after: int = -1) -> int | None:
    for i, item in enumerate(items):
        if i <= after:
            continue
        if not str(item.get("BU_CONDITION", "")).strip():
            return i
    return None


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def setup():
    # Allow pre-loading sheet URL via ?sheet=... query param
    # so BU only needs to enter their name, not the sheet link
    prefill_sheet = request.args.get("sheet", "")
    return render_template(
        "setup.html",
        error=request.args.get("error"),
        prefill_sheet=prefill_sheet,
        service_account_email=SERVICE_ACCOUNT_EMAIL,
    )


@app.route("/load", methods=["POST"])
def load():
    sheet_url  = request.form.get("sheet_url",  "").strip()
    annotator  = request.form.get("annotator",  "").strip()

    if not sheet_url or not annotator:
        return redirect(url_for("setup", error="Please fill in both fields."))

    try:
        sheet_id = sheets.extract_sheet_id(sheet_url)
        items    = sheets.load_items(sheet_id)
    except Exception as exc:
        return redirect(url_for("setup", error=str(exc)))

    if not items:
        return redirect(url_for("setup", error="Sheet appears to be empty."))

    session["sheet_id"]  = sheet_id
    session["sheet_url"] = sheet_url
    session["annotator"] = annotator
    session["total"]     = len(items)

    first = _next_unannotated(items)
    if first is None:
        return redirect(url_for("done"))
    return redirect(url_for("annotate", idx=first))


@app.route("/annotate/<int:idx>")
def annotate(idx: int):
    sheet_id = session.get("sheet_id")
    if not sheet_id:
        return redirect(url_for("setup"))

    try:
        items = sheets.load_items(sheet_id)
    except Exception as exc:
        return redirect(url_for("setup", error=f"Could not reload sheet: {exc}"))

    total = len(items)
    if idx >= total:
        return redirect(url_for("done"))

    item     = items[idx]
    item_id  = str(item.get("ITEM_ID", "")).strip()
    item_url = str(item.get("item_url", "") or "").strip()
    if not item_url and item_id:
        item_url = f"https://www.ebay.com/itm/{item_id}"

    images    = sheets.get_images(item)
    annotated = sum(1 for it in items if str(it.get("BU_CONDITION", "")).strip())
    remaining = total - annotated

    # Find next unannotated after current
    next_idx = _next_unannotated(items, after=idx)

    return render_template(
        "annotate.html",
        item=item,
        item_id=item_id,
        item_url=item_url,
        images=images,
        idx=idx,
        total=total,
        annotated=annotated,
        remaining=remaining,
        buckets=CONDITION_BUCKETS,
        annotator=session.get("annotator"),
        next_idx=next_idx,
        error=request.args.get("error"),
    )


@app.route("/submit", methods=["POST"])
def submit():
    sheet_id  = session.get("sheet_id")
    if not sheet_id:
        return redirect(url_for("setup"))

    item_id = request.form.get("item_id", "").strip()
    idx     = int(request.form.get("idx", 0))
    skip    = request.form.get("action") == "skip"

    if not skip:
        condition = request.form.get("condition", "").strip()
        if not condition:
            return redirect(url_for("annotate", idx=idx,
                                    error="Please select a condition before saving."))
        damaged   = request.form.get("damaged") == "on"
        annotator = session.get("annotator", "")

        try:
            sheets.write_annotation(
                sheet_id=sheet_id,
                item_id=item_id,
                condition=condition,
                damaged=damaged,
                annotator=annotator,
            )
        except Exception as exc:
            # Annotation not saved — keep user on same item with error
            return redirect(url_for("annotate", idx=idx,
                                    error=f"Save failed — please try again. ({exc})"))

    # Reload sheet to get fresh state, find next unannotated
    try:
        items = sheets.load_items(sheet_id)
    except Exception:
        items = []

    next_idx = _next_unannotated(items, after=idx)
    if next_idx is None:
        return redirect(url_for("done"))
    return redirect(url_for("annotate", idx=next_idx))


@app.route("/done")
def done():
    return render_template(
        "done.html",
        annotator=session.get("annotator"),
        total=session.get("total", 0),
        sheet_url=session.get("sheet_url"),
    )


@app.route("/export", methods=["POST"])
def export():
    sheet_id = session.get("sheet_id")
    if not sheet_id:
        return jsonify({"error": "No sheet loaded. Please go back and reload."}), 400
    try:
        url = sheets.create_results_sheet(sheet_id)
        return jsonify({"url": url})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)
