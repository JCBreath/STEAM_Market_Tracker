#!/usr/bin/env python3
"""
Web server for STEAM Market Tracker.

Install extras:
    pip install fastapi "uvicorn[standard]"

Run:
    python server.py
Then open http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

# ── Path setup ──────────────────────────────────────────────────────────────

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "Python"))

# ── Thread-local stdout router ──────────────────────────────────────────────
# Replaces sys.stdout once; each job thread registers its own Queue so that
# print() inside the scrapers is captured per-job without interference.

_REAL_STDOUT = sys.stdout
_thread_local = threading.local()


class _StdoutRouter:
    def __init__(self) -> None:
        self._local = threading.local()

    def write(self, text: str) -> int:
        q: Optional[Queue] = getattr(_thread_local, "queue", None)
        if q is not None:
            buf = getattr(self._local, "buf", "")
            buf += text
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.rstrip("\r")
                if line:
                    q.put({"type": "log", "text": line})
            self._local.buf = buf
        else:
            _REAL_STDOUT.write(text)
        return len(text)

    def flush(self) -> None:
        buf = getattr(self._local, "buf", "")
        if buf:
            q: Optional[Queue] = getattr(_thread_local, "queue", None)
            if q is not None and buf.strip():
                q.put({"type": "log", "text": buf.strip()})
                self._local.buf = ""
        _REAL_STDOUT.flush()

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        return _REAL_STDOUT.fileno()


sys.stdout = _StdoutRouter()


def _set_queue(q: Optional[Queue]) -> None:
    _thread_local.queue = q


# ── Module imports (after stdout patching) ──────────────────────────────────

try:
    from csgo_market_tracker import MarketItem, MarketTracker, write_csv, write_json
    from scrape_all_csgo_skins import SteamMarketScraper, SteamSkin, append_to_csv
except ImportError as exc:
    _REAL_STDOUT.write(f"[ERROR] Import failed: {exc}\n")
    _REAL_STDOUT.write("[ERROR] Run server.py from inside STEAM_Market_Tracker/\n")
    sys.exit(1)

import re as _re

import db as _db
_db.init()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

# ── Output directory ────────────────────────────────────────────────────────

OUTPUT_DIR = os.path.join(_HERE, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHECKPOINT_PATH = os.path.join(_HERE, "library_checkpoint.json")


def _load_checkpoint() -> Optional[Dict]:
    try:
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_checkpoint(data: Dict) -> None:
    data["updated_at"] = time.time()
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _clear_checkpoint() -> None:
    try:
        os.remove(CHECKPOINT_PATH)
    except FileNotFoundError:
        pass

# ── CS:GO category tree ──────────────────────────────────────────────────────
# type_tag maps to Steam's category_730_Type[] filter value.
# weapons list maps to category_730_Weapon[] filter values.

CATEGORIES = [
    {
        "group": "Weapons",
        "items": [
            {
                "id": "pistol", "name": "Pistol", "type_tag": "CSGO_Type_Pistol",
                "approx": 450,
                "weapons": [
                    {"id": "weapon_deagle",       "name": "Desert Eagle"},
                    {"id": "weapon_elite",         "name": "Dual Berettas"},
                    {"id": "weapon_fiveseven",     "name": "Five-SeveN"},
                    {"id": "weapon_glock",         "name": "Glock-18"},
                    {"id": "weapon_hkp2000",       "name": "P2000"},
                    {"id": "weapon_p250",          "name": "P250"},
                    {"id": "weapon_usp_silencer",  "name": "USP-S"},
                    {"id": "weapon_cz75a",         "name": "CZ75-Auto"},
                    {"id": "weapon_tec9",          "name": "Tec-9"},
                    {"id": "weapon_revolver",      "name": "R8 Revolver"},
                ],
            },
            {
                "id": "smg", "name": "SMG", "type_tag": "CSGO_Type_SMG",
                "approx": 280,
                "weapons": [
                    {"id": "weapon_mac10",  "name": "MAC-10"},
                    {"id": "weapon_mp9",    "name": "MP9"},
                    {"id": "weapon_mp7",    "name": "MP7"},
                    {"id": "weapon_mp5sd",  "name": "MP5-SD"},
                    {"id": "weapon_ump45",  "name": "UMP-45"},
                    {"id": "weapon_p90",    "name": "P90"},
                    {"id": "weapon_bizon",  "name": "PP-Bizon"},
                ],
            },
            {
                "id": "rifle", "name": "Rifle", "type_tag": "CSGO_Type_Rifle",
                "approx": 520,
                "weapons": [
                    {"id": "weapon_ak47",          "name": "AK-47"},
                    {"id": "weapon_m4a1",          "name": "M4A4"},
                    {"id": "weapon_m4a1_silencer", "name": "M4A1-S"},
                    {"id": "weapon_famas",         "name": "FAMAS"},
                    {"id": "weapon_galilar",       "name": "Galil AR"},
                    {"id": "weapon_aug",           "name": "AUG"},
                    {"id": "weapon_sg556",         "name": "SG 553"},
                ],
            },
            {
                "id": "sniper", "name": "Sniper Rifle", "type_tag": "CSGO_Type_SniperRifle",
                "approx": 180,
                "weapons": [
                    {"id": "weapon_awp",    "name": "AWP"},
                    {"id": "weapon_ssg08",  "name": "SSG 08"},
                    {"id": "weapon_scar20", "name": "SCAR-20"},
                    {"id": "weapon_g3sg1",  "name": "G3SG1"},
                ],
            },
            {
                "id": "shotgun", "name": "Shotgun", "type_tag": "CSGO_Type_Shotgun",
                "approx": 120,
                "weapons": [
                    {"id": "weapon_nova",     "name": "Nova"},
                    {"id": "weapon_xm1014",   "name": "XM1014"},
                    {"id": "weapon_sawedoff", "name": "Sawed-Off"},
                    {"id": "weapon_mag7",     "name": "MAG-7"},
                ],
            },
            {
                "id": "machinegun", "name": "Machine Gun", "type_tag": "CSGO_Type_Machinegun",
                "approx": 60,
                "weapons": [
                    {"id": "weapon_m249",  "name": "M249"},
                    {"id": "weapon_negev", "name": "Negev"},
                ],
            },
        ],
    },
    {
        "group": "Equipment",
        "items": [
            {
                "id": "knife", "name": "Knife", "type_tag": "CSGO_Type_Knife",
                "approx": 1200,
                "weapons": [
                    {"id": "weapon_knife_karambit",    "name": "Karambit"},
                    {"id": "weapon_knife_m9_bayonet",  "name": "M9 Bayonet"},
                    {"id": "weapon_bayonet",           "name": "Bayonet"},
                    {"id": "weapon_knife_butterfly",   "name": "Butterfly Knife"},
                    {"id": "weapon_knife_flip",        "name": "Flip Knife"},
                    {"id": "weapon_knife_gut",         "name": "Gut Knife"},
                    {"id": "weapon_knife_tactical",    "name": "Huntsman Knife"},
                    {"id": "weapon_knife_falchion",    "name": "Falchion Knife"},
                    {"id": "weapon_knife_bowie",       "name": "Bowie Knife"},
                    {"id": "weapon_knife_shadow_dagger","name": "Shadow Daggers"},
                    {"id": "weapon_knife_ursus",       "name": "Ursus Knife"},
                    {"id": "weapon_knife_gypsy_jackknife","name": "Navaja Knife"},
                    {"id": "weapon_knife_stiletto",    "name": "Stiletto Knife"},
                    {"id": "weapon_knife_talon",       "name": "Talon Knife"},
                    {"id": "weapon_knife_classic",     "name": "Classic Knife"},
                    {"id": "weapon_knife_paracord",    "name": "Paracord Knife"},
                    {"id": "weapon_knife_survival_bowie","name": "Survival Knife"},
                    {"id": "weapon_knife_nomad",       "name": "Nomad Knife"},
                    {"id": "weapon_knife_skeleton",    "name": "Skeleton Knife"},
                    {"id": "weapon_knife_kukri",       "name": "Kukri Knife"},
                ],
            },
            {
                "id": "gloves", "name": "Gloves", "type_tag": "CSGO_Type_Gloves",
                "approx": 200,
                "weapons": [
                    {"id": "weapon_bloodhound_gloves",    "name": "Bloodhound Gloves"},
                    {"id": "weapon_driver_gloves",        "name": "Driver Gloves"},
                    {"id": "weapon_hand_wraps",           "name": "Hand Wraps"},
                    {"id": "weapon_moto_gloves",          "name": "Moto Gloves"},
                    {"id": "weapon_specialist_gloves",    "name": "Specialist Gloves"},
                    {"id": "weapon_sport_gloves",         "name": "Sport Gloves"},
                    {"id": "weapon_hydra_gloves",         "name": "Hydra Gloves"},
                    {"id": "weapon_broken_fang_gloves",   "name": "Broken Fang Gloves"},
                ],
            },
        ],
    },
    {
        "group": "Cosmetics",
        "items": [
            {
                "id": "sticker", "name": "Sticker", "type_tag": "CSGO_Type_Sticker",
                "approx": 8000, "weapons": [],
            },
            {
                "id": "patch", "name": "Patch", "type_tag": "CSGO_Type_Patch",
                "approx": 200, "weapons": [],
            },
            {
                "id": "graffiti", "name": "Graffiti", "type_tag": "CSGO_Type_Spray",
                "approx": 500, "weapons": [],
            },
            {
                "id": "music_kit", "name": "Music Kit", "type_tag": "CSGO_Type_MusicKit",
                "approx": 100, "weapons": [],
            },
        ],
    },
    {
        "group": "Other",
        "items": [
            {
                "id": "container", "name": "Container", "type_tag": "CSGO_Type_WeaponCase",
                "approx": 300, "weapons": [],
            },
            {
                "id": "agent", "name": "Agent", "type_tag": "Type_CustomPlayer",
                "approx": 150, "weapons": [],
            },
            {
                "id": "collectible", "name": "Collectible", "type_tag": "CSGO_Type_Collectible",
                "approx": 50, "weapons": [],
            },
        ],
    },
]

# ── Job data model ───────────────────────────────────────────────────────────


@dataclass
class Job:
    id: str
    type: str          # "search" | "bulk"
    status: str        # "running" | "done" | "error" | "stopped"
    params: Dict[str, Any]
    log: List[str] = field(default_factory=list)
    progress: Dict[str, Any] = field(default_factory=dict)
    items: List[Dict] = field(default_factory=list)
    output_file: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: Optional[str] = None
    _queue: Queue = field(default_factory=Queue)
    _stop: threading.Event = field(default_factory=threading.Event)


JOBS: Dict[str, Job] = {}

# ── Progress parsing for bulk output lines ──────────────────────────────────

_PROG_RE = _re.compile(
    r"Offset\s+(\d+)\s*\|.*?Total collected:\s*([\d,]+)\s*\|.*?Requests:\s*(\d+)"
)
_TOTAL_RE = _re.compile(r"Total items in market:\s*([\d,]+)")


def _parse_progress(job: Job, text: str) -> None:
    m = _TOTAL_RE.search(text)
    if m:
        job.progress["total_market"] = int(m.group(1).replace(",", ""))
    m = _PROG_RE.search(text)
    if m:
        job.progress["offset"] = int(m.group(1))
        job.progress["collected"] = int(m.group(2).replace(",", ""))
        job.progress["requests"] = int(m.group(3))
        total = job.progress.get("total_market", 0)
        if total > 0:
            job.progress["percent"] = round(
                job.progress["collected"] / total * 100, 1
            )


# ── Job runners ──────────────────────────────────────────────────────────────


class _StopJob(Exception):
    pass


def _run_search(job: Job) -> None:
    _set_queue(job._queue)
    try:
        p = job.params
        tracker = MarketTracker(
            timeout_seconds=p.get("timeout", 15.0),
            bypass_env_proxy=p.get("no_proxy", False),
            https_proxy=p.get("proxy", ""),
        )
        print(f"Searching Steam for: {p['query']!r}  (max {p.get('max_items', 100)})")
        items = tracker.fetch_steam_items(p["query"], max_items=p.get("max_items", 100))
        job.items = [asdict(i) for i in items]
        print(f"Done — {len(items)} items found.")

        if p.get("save_csv"):
            slug = p["query"].replace(" ", "_").replace("/", "-")[:30]
            fname = f"search_{slug}_{int(time.time())}.csv"
            write_csv(os.path.join(OUTPUT_DIR, fname), items)
            job.output_file = fname
            print(f"Saved CSV → {fname}")

        if p.get("save_json"):
            slug = p["query"].replace(" ", "_").replace("/", "-")[:30]
            fname = f"search_{slug}_{int(time.time())}.json"
            write_json(os.path.join(OUTPUT_DIR, fname), items)
            job.output_file = fname
            print(f"Saved JSON → {fname}")

        job._queue.put({"type": "items", "items": job.items})
        job.status = "done"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        print(f"[ERROR] {exc}")
    finally:
        _set_queue(None)
        job.finished_at = time.time()
        job._queue.put({"type": "done", "status": job.status})


def _run_bulk(job: Job) -> None:
    _set_queue(job._queue)
    try:
        p = job.params
        raw = (p.get("output_file") or "").strip() or f"bulk_{int(time.time())}"
        if not any(raw.endswith(ext) for ext in (".csv", ".json", ".jsonl")):
            raw += ".csv"
        fpath = os.path.join(OUTPUT_DIR, raw)
        job.output_file = raw
        fmt = "jsonl" if raw.endswith((".json", ".jsonl")) else "csv"

        scraper = SteamMarketScraper(
            delay_min=p.get("delay_min", 2.0),
            delay_max=p.get("delay_max", 4.0),
            max_429_retries=p.get("max_429_retries", 8),
            retry_backoff_base=p.get("retry_backoff_base", 15.0),
        )

        orig_delay = scraper._delay

        def _guarded_delay():
            if job._stop.is_set():
                raise _StopJob()
            orig_delay()

        scraper._delay = _guarded_delay

        try:
            skins = scraper.fetch_all_skins(
                max_items=p.get("max_items"),
                start_offset=p.get("start_offset", 0),
                output_file=fpath,
                save_format=fmt,
            )
            job.items = [asdict(s) for s in skins]
            job.status = "done"
        except _StopJob:
            job.status = "stopped"
            print("Job stopped by user.")
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        print(f"[ERROR] {exc}")
    finally:
        _set_queue(None)
        job.finished_at = time.time()
        job._queue.put({"type": "done", "status": job.status})


def _run_library(job: Job) -> None:
    """
    Scrape category by category, upsert every page into SQLite.
    Supports resume: skips completed categories and continues a partial category
    from where it left off using a checkpoint file.
    """
    _set_queue(job._queue)
    try:
        p = job.params
        resume = p.get("resume", True)

        tag_to_name = {
            cat["type_tag"]: cat["name"]
            for grp in CATEGORIES for cat in grp["items"]
        }

        # ── Load or create checkpoint ────────────────────────────────────
        cp = None
        if resume:
            cp = _load_checkpoint()
            if cp:
                # Validate the checkpoint belongs to the same tag set
                saved_tags = cp.get("params", {}).get("selected_type_tags", [])
                requested = p.get("selected_type_tags", [])
                if set(saved_tags) != set(requested):
                    print("[WARN] Checkpoint tag set differs — ignoring checkpoint.")
                    cp = None

        if cp:
            tags = cp["params"]["selected_type_tags"]   # preserve original order
            completed = set(cp.get("completed_tags", []))
            resume_tag = cp.get("current_tag")          # tag that was interrupted
            resume_offset = cp.get("current_offset", 0) # next offset to fetch
            done_cats = len(completed)
            print(f"Resuming build: {done_cats}/{len(tags)} categories already done.")
            if resume_tag:
                print(f"  Continuing '{tag_to_name.get(resume_tag, resume_tag)}' "
                      f"from offset {resume_offset}.")
        else:
            tags = p.get("selected_type_tags", [])
            if not tags:
                print("[ERROR] No categories selected.")
                job.status = "error"
                job.error = "No categories selected"
                return
            completed = set()
            resume_tag = None
            resume_offset = 0
            done_cats = 0
            _clear_checkpoint()
            cp = {
                "started_at": time.time(),
                "params": {k: p[k] for k in ("selected_type_tags",
                           "delay_min", "delay_max")},
                "completed_tags": [],
                "current_tag": None,
                "current_offset": 0,
            }
            _save_checkpoint(cp)
            print(f"Fresh build: {len(tags)} categories selected.")

        total_cats = len(tags)
        job.progress.update({
            "total_cats": total_cats,
            "done_cats": done_cats,
            "current_cat": "",
            "cat_index": done_cats,
            "collected": _db.count(),
            "percent": round(done_cats / total_cats * 100, 1) if total_cats else 0,
        })
        print(f"Database currently holds {_db.count():,} items.\n")

        # ── Main scraping loop ───────────────────────────────────────────
        for idx, tag in enumerate(tags):
            if job._stop.is_set():
                break

            if tag in completed:
                print(f"[{idx+1}/{total_cats}] Skip (done): "
                      f"{tag_to_name.get(tag, tag)}")
                continue

            cat_name = tag_to_name.get(tag, tag)
            start_offset = resume_offset if tag == resume_tag else 0
            resume_tag = None   # only apply once

            # Update checkpoint: mark this tag as in-progress
            cp["current_tag"] = tag
            cp["current_offset"] = start_offset
            _save_checkpoint(cp)

            job.progress.update({
                "current_cat": cat_name,
                "cat_index": idx + 1,
            })
            print(f"\n[{idx+1}/{total_cats}] ━━━ {cat_name}"
                  + (f" (resume offset {start_offset})" if start_offset else "")
                  + " ━━━")

            scraper = SteamMarketScraper(
                delay_min=p.get("delay_min", 2.0),
                delay_max=p.get("delay_max", 4.0),
                max_429_retries=p.get("max_429_retries", 8),
                retry_backoff_base=p.get("retry_backoff_base", 15.0),
            )
            orig_delay = scraper._delay

            def _guarded(orig=orig_delay):
                if job._stop.is_set():
                    raise _StopJob()
                orig()

            scraper._delay = _guarded
            cat_total = 0

            def on_page(skins, offset, _tag=tag):
                nonlocal cat_total
                _db.upsert(skins, category_type=_tag)
                cat_total += len(skins)
                # Checkpoint: next_offset = offset + page size
                cp["current_offset"] = offset + 10
                _save_checkpoint(cp)
                job.progress["collected"] = _db.count()
                job._queue.put({"type": "progress", "progress": dict(job.progress)})

            try:
                scraper.fetch_all_skins(
                    category_type=tag,
                    start_offset=start_offset,
                    on_page=on_page,
                )
                # Mark category complete in checkpoint
                completed.add(tag)
                cp["completed_tags"] = list(completed)
                cp["current_tag"] = None
                cp["current_offset"] = 0
                _save_checkpoint(cp)

                job.progress["done_cats"] = len(completed)
                job.progress["percent"] = round(len(completed) / total_cats * 100, 1)
                db_total = _db.count()
                job.progress["collected"] = db_total
                print(f"✓ {cat_name}: {cat_total} items  (DB total: {db_total:,})")
            except _StopJob:
                raise
            except Exception as exc:
                print(f"[WARN] {cat_name} failed: {exc} — skipping")

        final = _db.count()
        job.progress["collected"] = final
        if job._stop.is_set():
            job.status = "stopped"
            print("\nBuild paused — checkpoint saved, run again to resume.")
        else:
            job.status = "done"
            _clear_checkpoint()
            print(f"\n{'='*60}")
            print(f"Library complete. Database: {final:,} items total.")
    except _StopJob:
        job.status = "stopped"
        print("Build paused — checkpoint saved.")
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        print(f"[ERROR] {exc}")
    finally:
        _set_queue(None)
        job.finished_at = time.time()
        job._queue.put({"type": "done", "status": job.status})


# ── FastAPI ──────────────────────────────────────────────────────────────────

app = FastAPI(title="STEAM Market Tracker")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class LibraryParams(BaseModel):
    output_file: str = ""
    selected_type_tags: List[str] = []
    delay_min: float = 2.0
    delay_max: float = 4.0
    max_429_retries: int = 8
    retry_backoff_base: float = 15.0
    resume: bool = True   # if True, load checkpoint and skip completed categories


class SearchParams(BaseModel):
    query: str
    max_items: int = 100
    timeout: float = 15.0
    no_proxy: bool = False
    proxy: str = ""
    save_csv: bool = False
    save_json: bool = False


class BulkParams(BaseModel):
    output_file: str = ""
    max_items: Optional[int] = None
    start_offset: int = 0
    delay_min: float = 2.0
    delay_max: float = 4.0
    max_429_retries: int = 8
    retry_backoff_base: float = 15.0


def _summary(job: Job) -> Dict:
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "params": job.params,
        "progress": job.progress,
        "output_file": job.output_file,
        "item_count": len(job.items),
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "error": job.error,
    }


@app.get("/api/categories")
def get_categories():
    return CATEGORIES


# ── Database endpoints ───────────────────────────────────────────────────────

@app.get("/api/db/stats")
def db_stats():
    return _db.stats()


@app.get("/api/db/items")
def db_items(
    search: str = Query(""),
    category: str = Query(""),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    return {
        "items": _db.query(search=search, category=category, limit=limit, offset=offset),
        "total": _db.count(search=search, category=category),
    }


@app.post("/api/db/export")
def db_export(fmt: str = "csv"):
    """Export the full database to a file in output/."""
    fname = f"library_export_{int(time.time())}.{fmt}"
    fpath = os.path.join(OUTPUT_DIR, fname)
    if fmt == "json":
        n = _db.export_json(fpath)
    else:
        n = _db.export_csv(fpath)
    return {"file": fname, "rows": n}


@app.get("/api/library/checkpoint")
def get_checkpoint():
    cp = _load_checkpoint()
    if not cp:
        return {"exists": False}
    done = len(cp.get("completed_tags", []))
    total = len(cp.get("params", {}).get("selected_type_tags", []))
    return {
        "exists": True,
        "done_cats": done,
        "total_cats": total,
        "percent": round(done / total * 100, 1) if total else 0,
        "current_tag": cp.get("current_tag"),
        "current_offset": cp.get("current_offset", 0),
        "updated_at": cp.get("updated_at"),
        "params": cp.get("params", {}),
    }


@app.delete("/api/library/checkpoint")
def clear_checkpoint_route():
    _clear_checkpoint()
    return {"ok": True}


@app.post("/api/jobs/library")
def create_library_job(params: LibraryParams):
    jid = uuid.uuid4().hex[:8]
    job = Job(
        id=jid, type="library", status="running", params=params.dict(),
        progress={"total_cats": 0, "done_cats": 0, "current_cat": "",
                  "collected": 0, "percent": 0, "cat_index": 0},
    )
    JOBS[jid] = job
    threading.Thread(target=_run_library, args=(job,), daemon=True).start()
    return {"id": jid}


@app.post("/api/jobs/search")
def create_search(params: SearchParams):
    jid = uuid.uuid4().hex[:8]
    job = Job(id=jid, type="search", status="running", params=params.dict())
    JOBS[jid] = job
    threading.Thread(target=_run_search, args=(job,), daemon=True).start()
    return {"id": jid}


@app.post("/api/jobs/bulk")
def create_bulk(params: BulkParams):
    jid = uuid.uuid4().hex[:8]
    job = Job(
        id=jid,
        type="bulk",
        status="running",
        params=params.dict(),
        progress={"collected": 0, "total_market": 0, "percent": 0, "requests": 0},
    )
    JOBS[jid] = job
    threading.Thread(target=_run_bulk, args=(job,), daemon=True).start()
    return {"id": jid}


@app.get("/api/jobs")
def list_jobs():
    return [_summary(j) for j in sorted(JOBS.values(), key=lambda j: -j.created_at)]


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    return {**_summary(job), "log": job.log, "items": job.items}


@app.delete("/api/jobs/{jid}")
def stop_job(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    job._stop.set()
    if job.status == "running":
        job.status = "stopped"
    return {"ok": True}


@app.get("/api/jobs/{jid}/events")
async def job_events(jid: str):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")

    async def generate():
        try:
            while True:
                # Drain all pending queue entries
                while not job._queue.empty():
                    try:
                        ev = job._queue.get_nowait()
                        if ev["type"] == "log":
                            _parse_progress(job, ev["text"])
                            job.log.append(ev["text"])
                            yield f"data: {json.dumps(ev)}\n\n"
                            # Send updated progress alongside every log line
                            if job.type in ("bulk", "library") and job.progress:
                                prog_ev = {"type": "progress", "progress": dict(job.progress)}
                                yield f"data: {json.dumps(prog_ev)}\n\n"
                        else:
                            yield f"data: {json.dumps(ev)}\n\n"
                        if ev["type"] == "done":
                            return
                    except Empty:
                        break

                if job.status != "running" and job._queue.empty():
                    yield f"data: {json.dumps({'type': 'done', 'status': job.status})}\n\n"
                    return

                await asyncio.sleep(0.15)
        except GeneratorExit:
            pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/files")
def list_files():
    files = []
    for fname in os.listdir(OUTPUT_DIR):
        fp = os.path.join(OUTPUT_DIR, fname)
        if os.path.isfile(fp):
            s = os.stat(fp)
            files.append({"name": fname, "size": s.st_size, "modified": s.st_mtime})
    files.sort(key=lambda f: -f["modified"])
    return files


@app.get("/api/files/{filename:path}")
def download_file(filename: str):
    fp = os.path.join(OUTPUT_DIR, filename)
    if not os.path.isfile(fp):
        raise HTTPException(404, "File not found")
    return FileResponse(fp, filename=filename)


@app.delete("/api/files/{filename:path}")
def delete_file(filename: str):
    fp = os.path.join(OUTPUT_DIR, filename)
    if not os.path.isfile(fp):
        raise HTTPException(404, "File not found")
    os.remove(fp)
    return {"ok": True}


@app.get("/")
def root():
    return FileResponse(os.path.join(_HERE, "index.html"))


if __name__ == "__main__":
    _REAL_STDOUT.write("Starting STEAM Market Tracker server at http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
