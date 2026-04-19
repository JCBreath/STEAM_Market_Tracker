#!/usr/bin/env python3
"""
SQLite database for the STEAM Market Tracker library.

Schema: one row per item, keyed by hash_name.
Every scrape run upserts: new items are inserted, existing ones are updated.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")

_local = threading.local()
_write_lock = threading.Lock()   # serialise writes across threads


def _conn() -> sqlite3.Connection:
    """Per-thread SQLite connection with WAL mode for concurrent reads."""
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return _local.conn


def init() -> None:
    """Create tables and indexes if they don't exist."""
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            hash_name       TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            sell_price_text TEXT,
            sell_price_usd  REAL,
            sell_listings   INTEGER,
            item_type       TEXT,
            category_type   TEXT,
            buff_price      REAL,
            steam_price_cny REAL,
            steam_buff_ratio REAL,
            last_updated    REAL NOT NULL
        )
    """)
    for col, typedef in [
        ("buff_price",      "REAL"),
        ("steam_price_cny", "REAL"),
        ("steam_buff_ratio","REAL"),
    ]:
        try:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col} {typedef}")
        except sqlite3.OperationalError:
            pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON items(name COLLATE NOCASE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cat  ON items(category_type)")
    conn.commit()


_UPSERT_SQL = """
    INSERT INTO items
      (hash_name, name, sell_price_text, sell_price_usd,
       sell_listings, item_type, category_type, buff_price,
       steam_buff_ratio, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(hash_name) DO UPDATE SET
      name             = excluded.name,
      sell_price_text  = COALESCE(excluded.sell_price_text,  items.sell_price_text),
      sell_price_usd   = COALESCE(excluded.sell_price_usd,   items.sell_price_usd),
      sell_listings    = COALESCE(excluded.sell_listings,    items.sell_listings),
      item_type        = COALESCE(excluded.item_type,        items.item_type),
      category_type    = COALESCE(excluded.category_type,    items.category_type),
      buff_price       = COALESCE(excluded.buff_price,       items.buff_price),
      steam_buff_ratio = CASE
        WHEN COALESCE(excluded.sell_price_usd, items.sell_price_usd) IS NOT NULL
         AND COALESCE(excluded.buff_price, items.buff_price) > 0
        THEN ROUND(COALESCE(excluded.sell_price_usd, items.sell_price_usd) /
                   COALESCE(excluded.buff_price, items.buff_price), 4)
        ELSE items.steam_buff_ratio END,
      last_updated     = excluded.last_updated
"""


_BUFF_UPSERT_SQL = """
    INSERT INTO items (hash_name, name, buff_price, steam_buff_ratio, last_updated)
    VALUES (?, ?, ?, NULL, ?)
    ON CONFLICT(hash_name) DO UPDATE SET
      buff_price       = excluded.buff_price,
      steam_buff_ratio = CASE
        WHEN items.sell_price_usd IS NOT NULL AND excluded.buff_price > 0
        THEN ROUND(items.sell_price_usd / excluded.buff_price, 4)
        ELSE items.steam_buff_ratio END,
      last_updated     = excluded.last_updated
"""


def upsert_buff_prices(skins) -> int:
    """Update only buff_price (and last_updated) for matched items.
    New items are inserted with name + buff_price; all other fields stay NULL."""
    if not skins:
        return 0
    now = time.time()
    rows = [
        (
            getattr(s, "hash_name", None) or getattr(s, "name", ""),
            getattr(s, "name", ""),
            getattr(s, "buff_price", None),
            now,
        )
        for s in skins
        if getattr(s, "buff_price", None) is not None   # skip rows with no price
    ]
    if not rows:
        return 0
    with _write_lock:
        conn = _conn()
        conn.executemany(_BUFF_UPSERT_SQL, rows)
        conn.commit()
    return len(rows)


def upsert(skins, category_type: Optional[str] = None) -> int:
    """
    Upsert a list of SteamSkin (or MarketItem) objects into the database.
    Returns the number of rows processed.
    """
    if not skins:
        return 0
    now = time.time()
    rows = []
    for s in skins:
        # Support both SteamSkin (hash_name field) and MarketItem (name only)
        hname = getattr(s, "hash_name", None) or getattr(s, "name", "")
        name  = getattr(s, "name", hname)
        rows.append((
            hname,
            name,
            getattr(s, "sell_price_text", None),
            getattr(s, "sell_price_usd",  None),
            getattr(s, "sell_listings",   None),
            getattr(s, "item_type",       None),
            category_type,
            getattr(s, "buff_price",      None),
            None,   # steam_buff_ratio — computed by SQL CASE
            now,
        ))
    with _write_lock:
        conn = _conn()
        conn.executemany(_UPSERT_SQL, rows)
        conn.commit()
    return len(rows)


def stats() -> Dict:
    """Return overall database statistics."""
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    by_cat = [
        dict(r)
        for r in conn.execute(
            "SELECT category_type, COUNT(*) AS count, "
            "MAX(last_updated) AS last_updated "
            "FROM items GROUP BY category_type ORDER BY count DESC"
        ).fetchall()
    ]
    last_upd = conn.execute("SELECT MAX(last_updated) FROM items").fetchone()[0]
    return {"total": total, "by_category": by_cat, "last_updated": last_upd}


_SORT_MAP = {
    "name":          "name COLLATE NOCASE",
    "price_asc":     "sell_price_usd ASC NULLS LAST",
    "price_desc":    "sell_price_usd DESC NULLS LAST",
    "listings_desc": "sell_listings DESC NULLS LAST",
    "ratio_asc":     "steam_buff_ratio ASC NULLS LAST",
    "ratio_desc":    "steam_buff_ratio DESC NULLS LAST",
}


def query(
    search: str = "",
    category: str = "",
    limit: int = 200,
    offset: int = 0,
    sort_by: str = "name",
) -> List[Dict]:
    conn = _conn()
    clauses, params = [], []
    if search:
        clauses.append("name LIKE ?")
        params.append(f"%{search}%")
    if category:
        clauses.append("category_type = ?")
        params.append(category)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order = _SORT_MAP.get(sort_by, "name COLLATE NOCASE")
    rows = conn.execute(
        f"SELECT * FROM items {where} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return [dict(r) for r in rows]


def count(search: str = "", category: str = "") -> int:
    conn = _conn()
    clauses, params = [], []
    if search:
        clauses.append("name LIKE ?")
        params.append(f"%{search}%")
    if category:
        clauses.append("category_type = ?")
        params.append(category)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return conn.execute(f"SELECT COUNT(*) FROM items {where}", params).fetchone()[0]


_PRICE_BUCKETS = [
    ("< $1",      0,    1),
    ("$1–$5",     1,    5),
    ("$5–$10",    5,   10),
    ("$10–$50",  10,   50),
    ("$50–$100", 50,  100),
    ("$100–$500",100,  500),
    ("≥ $500",   500,  1e18),
]


def price_dist() -> List[Dict]:
    """Return item counts per price bucket."""
    conn = _conn()
    result = []
    for label, lo, hi in _PRICE_BUCKETS:
        n = conn.execute(
            "SELECT COUNT(*) FROM items WHERE sell_price_usd >= ? AND sell_price_usd < ?",
            (lo, hi),
        ).fetchone()[0]
        result.append({"label": label, "count": n})
    return result


def export_csv(path: str) -> int:
    """Export all items to a CSV file. Returns row count."""
    import csv
    rows = query(limit=999_999)
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def export_json(path: str) -> int:
    """Export all items to a JSON file. Returns row count."""
    import json
    rows = query(limit=999_999)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return len(rows)
