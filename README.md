# CoinConditionAnnotator

Browser-based coin condition annotation tool. BU annotators visit a URL, sign in with Google, and grade coins one at a time. Annotations write directly back to the Google Sheet in real time — no installs, no server.

**Live:** https://roshatebay.github.io/CoinConditionAnnotator/

---

## Setup (one-time, Roshan does this)

### 1. Google Cloud credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project (or use existing)
3. Enable **Google Sheets API**
4. Go to **APIs & Services → Credentials**
5. Create **OAuth 2.0 Client ID** → type: **Web application**
6. Add authorized origin: `https://roshatebay.github.io`
7. Copy the **Client ID**

### 2. Add credentials to the app

Open `index.html` and fill in:

```js
const CONFIG = {
  clientId: 'YOUR_CLIENT_ID_HERE.apps.googleusercontent.com',
  apiKey:   '',  // leave empty — not needed for write operations
};
```

### 3. Deploy to GitHub Pages

- Push to `main`
- Go to repo Settings → Pages → Source: main branch, root folder
- Site live at `https://roshatebay.github.io/CoinConditionAnnotator/`

### 4. Prepare each Google Sheet

The sheet Sri pulls should have these columns (the tool adds BU columns automatically if missing):

**Sri should include:**
- `ITEM_ID` — eBay item number
- `item_url` — eBay listing URL (auto-generated if missing)
- `picture_url`, `picture_url_2`, `picture_url_3`, `picture_url_4` — image URLs
- `SELLER_CONDITION` — original seller condition (hidden from annotator in UI; needed for over-reporting comparison)

**Tool adds automatically:**
- `BU_CONDITION`
- `BU_DAMAGED`
- `BU_ANNOTATOR`
- `BU_ANNOTATED_AT`

---

## Sending to BU (Kyle's team)

**Simple URL with sheet pre-loaded:**

```
https://roshatebay.github.io/CoinConditionAnnotator/?sheet=SHEET_ID
```

Replace `SHEET_ID` with the ID from the Google Sheet URL (`/spreadsheets/d/SHEET_ID/`).

BU annotators just:
1. Open the link
2. Enter their name
3. Click "Sign in with Google" (uses their eBay Google account)
4. Start annotating

**Important:** Sri needs to share the Google Sheet with each annotator so they have edit access.

---

## Condition buckets

As specified by Kyle Klosinski (Nov 10, 2026 meeting):

1. Below Fine
2. Fine to Very Fine
3. Extra Fine to AU
4. Uncirculated
5. Cannot determine from image *(dashed border)*

Plus: **Cleaned / Damaged / Problem Coin** checkbox — captured even though this bucket doesn't exist on eBay yet.

---

## How progress is preserved

Every annotation writes immediately to the Google Sheet via the Sheets API (with 3 retries). If a save fails, the annotator sees an error and stays on the same coin — they can try again. Progress never advances without a confirmed save.

Annotators can close the tab and resume later — the tool skips already-annotated rows on load.

---

## `server/` folder

Contains the original Flask version for self-hosting if needed. Not used for the GitHub Pages deployment.
