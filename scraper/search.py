#!/usr/bin/env python3
"""CS:GO market tracker for Steam Community Market."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

STEAM_SEARCH_URL = (
    "https://steamcommunity.com/market/search/render/"
    "?query={query}&country=US&currency=1&start={start}&count={count}"
    "&sort_column=price&sort_dir=asc&appid=730&l=english&norender=1"
)


@dataclass
class MarketItem:
    name: str
    steam_sell_price_text: Optional[str] = None
    steam_sell_price_usd: Optional[float] = None
    steam_sell_listings: Optional[int] = None


class MarketTracker:
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ]

    def __init__(
        self,
        timeout_seconds: float = 15.0,
        bypass_env_proxy: bool = False,
        https_proxy: str = "",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.bypass_env_proxy = bypass_env_proxy
        self.https_proxy = https_proxy.strip()
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        if not self.bypass_env_proxy and self.https_proxy:
            session.proxies.update({
                "http": self.https_proxy,
                "https": self.https_proxy
            })
        return session

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }

    def _get_json(self, url: str, delay: float = 1.5) -> dict:
        time.sleep(delay + random.uniform(-0.5, 0.5))
        try:
            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout_seconds
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[DEBUG] Request failed: {e}")
            raise

    def fetch_steam_items(self, query: str, max_items: int = 100) -> List[MarketItem]:
        url = STEAM_SEARCH_URL.format(query=quote(query), start=0, count=max_items)
        try:
            payload = self._get_json(url)
            return self._parse_steam_items(payload)
        except Exception as e:
            print(f"[WARN] Failed to fetch Steam data: {e}")
            return []

    def _parse_steam_items(self, payload: dict) -> List[MarketItem]:
        items: List[MarketItem] = []
        for result in payload.get("results", []):
            cents = result.get("sell_price")
            items.append(
                MarketItem(
                    name=result.get("hash_name", "").strip(),
                    steam_sell_price_text=result.get("sell_price_text"),
                    steam_sell_price_usd=(cents / 100.0 if isinstance(cents, int) else None),
                    steam_sell_listings=result.get("sell_listings"),
                )
            )
        return items


def print_table(items: List[MarketItem]) -> None:
    headers = ["Name", "Steam Sell", "Steam Listings"]
    print("\t".join(headers))
    for item in items:
        row = [
            item.name,
            item.steam_sell_price_text or "-",
            str(item.steam_sell_listings) if item.steam_sell_listings is not None else "-",
        ]
        print("\t".join(row))


def write_csv(path: str, items: List[MarketItem]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(MarketItem(name="")).keys()))
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def write_json(path: str, items: List[MarketItem]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(i) for i in items], f, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track CS:GO skins on Steam Market")
    parser.add_argument("query", help="Keyword, e.g. 'ak-47' or 'bloodsport'")
    parser.add_argument("--max-steam", type=int, default=100, help="Max Steam items to fetch")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds")
    parser.add_argument("--no-proxy", action="store_true", help="Ignore environment proxy")
    parser.add_argument("--proxy", default="", help="Explicit HTTP/HTTPS proxy, e.g. http://127.0.0.1:7890")
    parser.add_argument("--csv", dest="csv_path", default="", help="Optional CSV output path")
    parser.add_argument("--json", dest="json_path", default="", help="Optional JSON output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tracker = MarketTracker(
        timeout_seconds=args.timeout,
        bypass_env_proxy=args.no_proxy,
        https_proxy=args.proxy,
    )

    try:
        items = tracker.fetch_steam_items(args.query, max_items=args.max_steam)
    except Exception as exc:
        print(f"[WARN] Failed to fetch Steam data: {exc}")
        items = []

    print_table(items)
    print(f"\nTotal items: {len(items)}")

    if args.csv_path:
        write_csv(args.csv_path, items)
        print(f"CSV written to: {args.csv_path}")
    if args.json_path:
        write_json(args.json_path, items)
        print(f"JSON written to: {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
