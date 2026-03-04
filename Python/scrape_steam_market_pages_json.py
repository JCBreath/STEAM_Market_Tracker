#!/usr/bin/env python3
import argparse
import json
import random
import time
from pathlib import Path
from typing import Dict, List

import requests

STEAM_RENDER_URL = "https://steamcommunity.com/market/search/render/"
DEFAULT_APPID = 730
DEFAULT_START_PAGE = 1
DEFAULT_END_PAGE = 3059
DEFAULT_PAGE_SIZE = 10  # Steam URL page format uses 10 items per page
MIN_DELAY_SECONDS = 5.1

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


def build_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://steamcommunity.com/market/search?appid=730",
        "Origin": "https://steamcommunity.com",
        "Connection": "keep-alive",
    }


def page_to_start(page: int, page_size: int) -> int:
    return (page - 1) * page_size


def to_price_usd(sell_price_cents) -> float | None:
    if sell_price_cents is None:
        return None
    try:
        return round(float(sell_price_cents) / 100.0, 2)
    except (TypeError, ValueError):
        return None


def extract_items(results: List[Dict], page: int) -> List[Dict]:
    items = []
    for row in results:
        item = {
            "page": page,
            "item_name": row.get("name"),
            "quantity": row.get("sell_listings"),
            "starting_price": row.get("sell_price_text"),
            "starting_price_usd": to_price_usd(row.get("sell_price")),
            "hash_name": row.get("hash_name"),
        }
        items.append(item)
    return items


def save_checkpoint(path: Path, records: List[Dict], last_page: int, total_count: int | None) -> None:
    payload = {
        "meta": {
            "appid": DEFAULT_APPID,
            "last_saved_page": last_page,
            "total_count": total_count,
            "saved_at_epoch": int(time.time()),
        },
        "items": records,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_output_snapshot(
    output_path: Path,
    records: List[Dict],
    start_page: int,
    end_page: int,
    total_count: int | None,
    last_saved_page: int,
) -> None:
    payload = {
        "meta": {
            "appid": DEFAULT_APPID,
            "page_range": {"start": start_page, "end": end_page},
            "total_count": total_count,
            "items_collected": len(records),
            "last_saved_page": last_saved_page,
            "generated_at_epoch": int(time.time()),
            "source": "https://steamcommunity.com/market/search?appid=730#p{page}_popular_desc",
        },
        "items": records,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def scrape_pages(
    start_page: int,
    end_page: int,
    output_path: Path,
    checkpoint_every: int,
    delay_min: float,
    delay_max: float,
    max_retries: int,
) -> None:
    delay_min = max(delay_min, MIN_DELAY_SECONDS)
    delay_max = max(delay_max, delay_min)

    session = requests.Session()
    all_items: List[Dict] = []
    total_count = None

    checkpoint_path = output_path.with_suffix(output_path.suffix + ".checkpoint")

    print(f"Scraping Steam market pages {start_page} to {end_page}...")
    print(f"Output: {output_path}")

    for page in range(start_page, end_page + 1):
        start = page_to_start(page, DEFAULT_PAGE_SIZE)

        params = {
            "appid": DEFAULT_APPID,
            "norender": 1,
            "count": DEFAULT_PAGE_SIZE,
            "start": start,
            "sort_column": "popular",
            "sort_dir": "desc",
        }

        success = False
        for attempt in range(1, max_retries + 1):
            try:
                sleep_seconds = random.uniform(delay_min, delay_max)
                print(f"Sleeping {sleep_seconds:.2f}s before request for page {page} (attempt {attempt}/{max_retries})")
                time.sleep(sleep_seconds)

                response = session.get(
                    STEAM_RENDER_URL,
                    params=params,
                    headers=build_headers(),
                    timeout=20,
                )

                if response.status_code == 429:
                    backoff = min(10 * (2 ** (attempt - 1)), 180)
                    print(f"[WARN] HTTP 429 on page {page}; retry {attempt}/{max_retries} after {backoff}s")
                    time.sleep(backoff)
                    continue

                if response.status_code != 200:
                    print(f"[WARN] HTTP {response.status_code} on page {page}; retry {attempt}/{max_retries}")
                    continue

                data = response.json()
                if not data.get("success"):
                    print(f"[WARN] API success=false on page {page}; retry {attempt}/{max_retries}")
                    continue

                if total_count is None:
                    total_count = data.get("total_count")
                    if total_count:
                        max_page_from_total = (int(total_count) + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE
                        print(f"Total market items reported: {total_count} (~{max_page_from_total} pages)")

                page_items = extract_items(data.get("results", []), page)
                all_items.extend(page_items)
                print(f"Page {page}/{end_page} | scraped {len(page_items)} items | cumulative: {len(all_items)}")

                save_checkpoint(checkpoint_path, all_items, page, total_count)
                save_output_snapshot(output_path, all_items, start_page, end_page, total_count, page)
                print(f"Saved progress for request/page {page}")

                if checkpoint_every > 0 and ((page - start_page + 1) % checkpoint_every == 0):
                    print(f"Checkpoint interval reached at page {page}: {checkpoint_path}")

                success = True
                break

            except requests.RequestException as exc:
                print(f"[WARN] Request error on page {page} attempt {attempt}/{max_retries}: {exc}")
            except json.JSONDecodeError as exc:
                print(f"[WARN] JSON parse error on page {page} attempt {attempt}/{max_retries}: {exc}")

        if not success:
            print(f"[ERROR] Failed page {page} after {max_retries} attempts. Continuing to next page.")

    save_output_snapshot(output_path, all_items, start_page, end_page, total_count, end_page)
    print(f"Done. Saved {len(all_items)} items to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Steam Community Market (CS:GO appid 730) by page number and save JSON"
    )
    parser.add_argument("--start-page", type=int, default=DEFAULT_START_PAGE, help="Start page (default: 1)")
    parser.add_argument("--end-page", type=int, default=DEFAULT_END_PAGE, help="End page (default: 3059)")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("steam_market_730_pages_1_3059.json"),
        help="Output JSON file path",
    )
    parser.add_argument("--checkpoint-every", type=int, default=100, help="Save checkpoint every N pages")
    parser.add_argument("--delay-min", type=float, default=5.2, help="Minimum delay between requests (must be >5s)")
    parser.add_argument("--delay-max", type=float, default=6.5, help="Maximum delay between requests")
    parser.add_argument("--max-retries", type=int, default=6, help="Max retries per page")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.start_page < 1 or args.end_page < args.start_page:
        print("Invalid page range. Expected: start_page >= 1 and end_page >= start_page")
        return 2

    scrape_pages(
        start_page=args.start_page,
        end_page=args.end_page,
        output_path=args.output,
        checkpoint_every=args.checkpoint_every,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        max_retries=args.max_retries,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
