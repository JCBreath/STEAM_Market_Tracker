#!/usr/bin/env python3
"""CS:GO market tracker for Steam Community Market + NetEase BUFF."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener

STEAM_SEARCH_URL = (
    "https://steamcommunity.com/market/search/render/"
    "?query={query}&country=US&currency=1&start={start}&count={count}"
    "&sort_column=price&sort_dir=asc&appid=730&l=english"
)
BUFF_SEARCH_URL = (
    "https://buff.163.com/api/market/goods"
    "?game=csgo&page_num={page_num}&page_size={page_size}&search={query}&sort_by=default"
)


@dataclass
class MarketItem:
    name: str
    steam_sell_price_text: Optional[str] = None
    steam_sell_price_usd: Optional[float] = None
    steam_sell_listings: Optional[int] = None
    buff_sell_price_cny: Optional[float] = None
    buff_sell_num: Optional[int] = None
    buff_buy_price_cny: Optional[float] = None
    buff_buy_num: Optional[int] = None


class MarketTracker:
    def __init__(
        self,
        timeout_seconds: float = 15.0,
        bypass_env_proxy: bool = False,
        https_proxy: str = "",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/javascript,*/*;q=0.9",
        }
        self.bypass_env_proxy = bypass_env_proxy
        self.https_proxy = https_proxy.strip()

    def _build_opener(self, disable_proxy: bool):
        if disable_proxy:
            return build_opener(ProxyHandler({}))

        if self.https_proxy:
            return build_opener(ProxyHandler({"https": self.https_proxy, "http": self.https_proxy}))

        if self.bypass_env_proxy:
            return build_opener(ProxyHandler({}))

        return build_opener()

    def _get_json(self, url: str, headers: Optional[dict] = None) -> dict:
        final_headers = dict(self.default_headers)
        if headers:
            final_headers.update(headers)

        request = Request(url, headers=final_headers, method="GET")

        opener = self._build_opener(disable_proxy=False)
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            # 常见场景：环境代理返回 Tunnel connection failed。
            # 自动再尝试一次直连，减少代理拦截导致的失败。
            if self.bypass_env_proxy or self.https_proxy:
                raise
            if "Tunnel connection failed" not in str(exc):
                raise
            direct_opener = self._build_opener(disable_proxy=True)
            with direct_opener.open(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _normalize_name(name: str) -> str:
        name = name.replace("™", "").replace("\u2122", "")
        name = re.sub(r"\s+", " ", name).strip()
        return name.lower()

    def fetch_steam_items(self, query: str, max_items: int = 100) -> List[MarketItem]:
        url = STEAM_SEARCH_URL.format(query=quote(query), start=0, count=max_items)
        payload = self._get_json(url)

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

    def fetch_buff_items(self, query: str, page_size: int = 80) -> List[MarketItem]:
        url = BUFF_SEARCH_URL.format(query=quote(query), page_num=1, page_size=page_size)
        payload = self._get_json(
            url,
            headers={
                "Referer": "https://buff.163.com/market/csgo",
                "X-Requested-With": "XMLHttpRequest",
            },
        )

        data = payload.get("data", {})
        items: List[MarketItem] = []
        for good in data.get("items", []):
            buy_max = good.get("buy_max_price")
            items.append(
                MarketItem(
                    name=good.get("market_hash_name", "").strip(),
                    buff_sell_price_cny=_to_float(good.get("sell_min_price")),
                    buff_sell_num=_to_int(good.get("sell_num")),
                    buff_buy_price_cny=_to_float(buy_max),
                    buff_buy_num=_to_int(good.get("buy_num")),
                )
            )
        return items


def _to_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def merge_items(steam_items: List[MarketItem], buff_items: List[MarketItem]) -> List[MarketItem]:
    normalized_to_item: Dict[str, MarketItem] = {}

    for item in steam_items:
        key = MarketTracker._normalize_name(item.name)
        normalized_to_item[key] = item

    for buff in buff_items:
        key = MarketTracker._normalize_name(buff.name)
        existing = normalized_to_item.get(key)
        if existing is None:
            normalized_to_item[key] = buff
            continue

        existing.buff_sell_price_cny = buff.buff_sell_price_cny
        existing.buff_sell_num = buff.buff_sell_num
        existing.buff_buy_price_cny = buff.buff_buy_price_cny
        existing.buff_buy_num = buff.buff_buy_num

    merged = list(normalized_to_item.values())
    merged.sort(key=lambda item: item.name.lower())
    return merged


def print_table(items: List[MarketItem]) -> None:
    headers = [
        "Name",
        "Steam Sell",
        "Steam Listings",
        "BUFF Sell(CNY)",
        "BUFF Sell #",
        "BUFF Buy(CNY)",
        "BUFF Buy #",
    ]
    print("\t".join(headers))
    for item in items:
        row = [
            item.name,
            item.steam_sell_price_text or "-",
            str(item.steam_sell_listings) if item.steam_sell_listings is not None else "-",
            f"{item.buff_sell_price_cny:.2f}" if item.buff_sell_price_cny is not None else "-",
            str(item.buff_sell_num) if item.buff_sell_num is not None else "-",
            f"{item.buff_buy_price_cny:.2f}" if item.buff_buy_price_cny is not None else "-",
            str(item.buff_buy_num) if item.buff_buy_num is not None else "-",
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
    parser = argparse.ArgumentParser(description="Track CS:GO skins on Steam + BUFF markets")
    parser.add_argument("query", help="Keyword, e.g. 'ak-47' or 'bloodsport'")
    parser.add_argument("--max-steam", type=int, default=100, help="Max Steam items to fetch")
    parser.add_argument("--buff-page-size", type=int, default=80, help="BUFF page size")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds")
    parser.add_argument("--no-proxy", action="store_true", help="Ignore environment proxy and use direct connection")
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
        steam_items = tracker.fetch_steam_items(args.query, max_items=args.max_steam)
    except URLError as exc:
        print(f"[WARN] Failed to fetch Steam data: {exc}")
        steam_items = []

    try:
        buff_items = tracker.fetch_buff_items(args.query, page_size=args.buff_page_size)
    except URLError as exc:
        print(f"[WARN] Failed to fetch BUFF data: {exc}")
        buff_items = []

    merged = merge_items(steam_items, buff_items)

    print_table(merged)
    print(f"\nTotal merged items: {len(merged)}")

    if args.csv_path:
        write_csv(args.csv_path, merged)
        print(f"CSV written to: {args.csv_path}")
    if args.json_path:
        write_json(args.json_path, merged)
        print(f"JSON written to: {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
