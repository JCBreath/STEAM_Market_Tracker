# STEAM Market Tracker

A web-based tool for tracking CS:GO skin prices on the Steam Community Market, with BUFF.163 price import and Steam/BUFF ratio analysis.

## Features

- **Build Library** — scrape Steam Market by category (weapons, knives, gloves, stickers, etc.) and store results in a local SQLite database with resume/checkpoint support
- **BUFF Import** — import BUFF.163 CSV exports to populate `buff_price`; the `USD/BUFF` ratio is computed automatically
- **Database Browser** — paginated table with filters (price range, listing count, ratio, category) and sorting; cookie-persisted filter state
- **Steam Search** — keyword search against the Steam Market API with live results
- **Bulk Scrape** — paginate through all CS:GO market listings and save to CSV/JSONL
- **Charts** — category distribution and price bucket charts via Chart.js
- **Real-time logs** — Server-Sent Events stream job progress and log lines to the browser

## Project Structure

```
STEAM_Market_Tracker/
├── server.py          # FastAPI server — API routes, job runners, SSE
├── db.py              # SQLite layer — upsert, query, stats, export
├── scraper/
│   ├── __init__.py
│   ├── search.py      # Steam keyword search (MarketTracker)
│   └── bulk.py        # Paginated full-market scraper (SteamMarketScraper)
└── static/
    ├── index.html     # App shell — 5-tab bottom-nav layout
    ├── app.css        # Styles
    └── app.js         # All frontend logic
```

Runtime-generated (gitignored):
```
library.db             # SQLite database
library_checkpoint.json
output/                # Exported CSV/JSON files
```

## Requirements

```
pip install fastapi "uvicorn[standard]" requests
```

Python 3.10+ required (uses `match`-free code but relies on `tuple[...]` type hints).

## Usage

```bash
cd STEAM_Market_Tracker
python server.py
```

Open **http://localhost:8000** in a browser.

### Tabs

| Tab | Purpose |
|-----|---------|
| 数据库 | Browse and filter the local database; export to CSV/JSON |
| 构建 | Select categories and build/resume the Steam price library |
| 导入 | Import a BUFF.163 CSV to add `buff_price` to existing records |
| 搜索 | Live Steam keyword search; optional bulk full-market scrape |
| 文件 | Download or delete output files; view job history |

### BUFF CSV Import

Export your BUFF.163 inventory/market data as CSV, then use the **导入** tab to map columns. The tool auto-detects common column names (`f_Strong`, `商品名称`, `hash_name`, etc.) and writes only the `buff_price` field — Steam data is never overwritten.

### Build Library

1. Select one or more categories in the **构建** tab.
2. Click **开始构建**. Progress is streamed live; the job can be stopped and resumed.
3. A checkpoint file (`library_checkpoint.json`) is written after each page so scraping can continue from where it left off.

## API

The server exposes a JSON API under `/api/`:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/categories` | CS:GO category tree |
| `GET` | `/api/db/stats` | Row counts by category |
| `GET` | `/api/db/items` | Paginated + filtered item query |
| `GET` | `/api/db/price_dist` | Price bucket distribution |
| `POST` | `/api/db/import_csv` | Import BUFF CSV (multipart) |
| `POST` | `/api/db/export` | Export database to CSV or JSON |
| `GET` | `/api/library/checkpoint` | Resume checkpoint info |
| `POST` | `/api/jobs/library` | Start a library build job |
| `POST` | `/api/jobs/search` | Start a search job |
| `POST` | `/api/jobs/bulk` | Start a bulk scrape job |
| `GET` | `/api/jobs/{id}/events` | SSE stream for a job |
| `DELETE` | `/api/jobs/{id}` | Stop a running job |
| `GET` | `/api/files` | List output files |
| `GET` | `/api/files/{name}` | Download an output file |
| `DELETE` | `/api/files/{name}` | Delete an output file |

## Notes

- Requests to Steam are rate-limited by a configurable random delay (default 2–4 s). HTTP 429 responses trigger exponential backoff.
- The scraper always uses **currency=1 (USD)**. The `USD/BUFF` ratio is `sell_price_usd / buff_price` (Steam USD ÷ BUFF CNY) — useful as a relative cross-market comparison, not a literal exchange rate.
- The SQLite database uses WAL mode for concurrent reads during active scrape jobs.
