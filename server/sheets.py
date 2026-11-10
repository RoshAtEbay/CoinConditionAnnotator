"""Google Sheets read/write — service account (hosted) or OAuth (local dev)."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import gspread
from gspread.exceptions import APIError

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

IMAGE_COLS = [
    "picture_url", "picture_url_2", "picture_url_3", "picture_url_4",
    "image_url",   "image_url_2",   "image_url_3",   "image_url_4",
    "IMAGE_URL_1", "IMAGE_URL_2",   "IMAGE_URL_3",   "IMAGE_URL_4",
]
ITEM_ID_COL  = "ITEM_ID"
ANNOTATION_COLS = ["BU_CONDITION", "BU_DAMAGED", "BU_ANNOTATOR", "BU_ANNOTATED_AT"]
_MAX_RETRIES = 4
_RETRY_BACKOFF = [1, 2, 4, 8]


def _client() -> gspread.Client:
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        from google.oauth2.service_account import Credentials
        info = json.loads(sa_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(creds)

    # Local dev fallback — OAuth with credentials.json
    import pickle
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = Path("token.pickle")
    creds = None
    if token.exists():
        with open(token, "rb") as f:
            creds = __import__("pickle").load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path("credentials.json").exists():
                raise FileNotFoundError(
                    "No GOOGLE_SERVICE_ACCOUNT_JSON env var and no credentials.json. "
                    "See README."
                )
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token, "wb") as f:
            pickle.dump(creds, f)
    return gspread.authorize(creds)


def _retry(fn, *args, **kwargs):
    """Call fn with retries on transient API errors."""
    last_exc = None
    for attempt, wait in enumerate(_RETRY_BACKOFF):
        try:
            return fn(*args, **kwargs)
        except APIError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (429, 500, 503):
                last_exc = exc
                time.sleep(wait)
                continue
            raise
    raise last_exc


def extract_sheet_id(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError(f"Could not find a spreadsheet ID in: {url!r}")
    return m.group(1)


def _open(sheet_id: str) -> gspread.Spreadsheet:
    return _retry(_client().open_by_key, sheet_id)


def load_items(sheet_id: str) -> list[dict]:
    ws = _retry(_open(sheet_id).get_worksheet, 0)
    return _retry(ws.get_all_records)


def get_images(item: dict) -> list[str]:
    urls = []
    for col in IMAGE_COLS:
        v = str(item.get(col, "") or "").strip()
        if v and v.lower() not in ("none", "null", ""):
            if v not in urls:
                urls.append(v)
    return urls


def _header_col_map(ws: gspread.Worksheet) -> dict[str, int]:
    headers = _retry(ws.row_values, 1)
    return {h.strip(): i + 1 for i, h in enumerate(headers)}


def _ensure_annotation_cols(ws: gspread.Worksheet) -> dict[str, int]:
    col_map = _header_col_map(ws)
    next_col = len(col_map) + 1
    for name in ANNOTATION_COLS:
        if name not in col_map:
            _retry(ws.update_cell, 1, next_col, name)
            col_map[name] = next_col
            next_col += 1
    return col_map


def _find_row(ws: gspread.Worksheet, item_id: str) -> int | None:
    all_values = _retry(ws.get_all_values)
    if not all_values:
        return None
    headers = [h.strip() for h in all_values[0]]
    try:
        id_idx = headers.index(ITEM_ID_COL)
    except ValueError:
        raise ValueError(f"Column '{ITEM_ID_COL}' not found. Headers: {headers}")
    for row_num, row in enumerate(all_values[1:], start=2):
        if len(row) > id_idx and str(row[id_idx]).strip() == str(item_id).strip():
            return row_num
    return None


def write_annotation(
    sheet_id: str,
    item_id: str,
    condition: str,
    damaged: bool,
    annotator: str,
    timestamp: str | None = None,
) -> None:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    ws = _retry(_open(sheet_id).get_worksheet, 0)
    col_map = _ensure_annotation_cols(ws)
    row = _find_row(ws, item_id)
    if row is None:
        raise ValueError(f"ITEM_ID {item_id!r} not found in sheet")

    updates = [
        gspread.Cell(row, col_map["BU_CONDITION"],    condition),
        gspread.Cell(row, col_map["BU_DAMAGED"],      "Yes" if damaged else ""),
        gspread.Cell(row, col_map["BU_ANNOTATOR"],    annotator),
        gspread.Cell(row, col_map["BU_ANNOTATED_AT"], timestamp),
    ]
    _retry(ws.update_cells, updates)


def create_results_sheet(sheet_id: str) -> str:
    """Copy annotated rows into a new Google Sheet. Returns its URL."""
    gc = _client()
    source = _retry(gc.open_by_key, sheet_id)
    ws = _retry(source.get_worksheet, 0)
    records = _retry(ws.get_all_records)

    if not records:
        raise ValueError("Source sheet is empty.")

    result_cols = [ITEM_ID_COL, "item_url", "SELLER_CONDITION"] + ANNOTATION_COLS
    available = [c for c in result_cols if c in records[0]]
    annotated = [r for r in records if str(r.get("BU_CONDITION", "")).strip()]

    title = f"{source.title} — BU Results {datetime.now().strftime('%Y-%m-%d')}"
    new_sh = _retry(gc.create, title)
    new_ws = _retry(new_sh.get_worksheet, 0)
    _retry(new_ws.append_row, available)
    for record in annotated:
        _retry(new_ws.append_row, [record.get(c, "") for c in available])

    return f"https://docs.google.com/spreadsheets/d/{new_sh.id}"
