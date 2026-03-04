#!/usr/bin/env python3
"""CS:GO market tracker for Steam Community Market + NetEase BUFF.

BUFF Market Notes:
==================
BUFF (buff.163.com) implements multiple layers of anti-bot protection:
  1. Cloudflare Challenge (blocks standard HTTP requests)
  2. Session/Authentication Requirements
  3. JavaScript-Rendered Content (requires browser with JS execution)
  4. Geographic IP Restrictions

To enable BUFF data collection:
  Option 1 (Recommended): Install Chrome/Chromium on your system
            - Ubuntu/Debian: sudo apt-get install chromium-browser
            - The script will automatically use undetected-chromedriver
  
  Option 2: Use a proxy service that handles Cloudflare
            - Services like Bright Data or Oxylabs provide BUFF-compatible proxies
  
  Option 3: Run the script in Docker with Chrome/Chromium included
            - See Docker setup in repository
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import time
import random
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
import cloudscraper
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional browser automation imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_BROWSER = True
except (ImportError, Exception):
    HAS_BROWSER = False

STEAM_SEARCH_URL = (
    "https://steamcommunity.com/market/search/render/"
    "?query={query}&country=US&currency=1&start={start}&count={count}"
    "&sort_column=price&sort_dir=asc&appid=730&l=english&norender=1"
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
    # Rotating list of user agents to avoid detection
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
        self.cloudscraper_session = cloudscraper.create_scraper()  # For BUFF API

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic and smart headers."""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Proxy configuration
        if not self.bypass_env_proxy and self.https_proxy:
            session.proxies.update({
                "http": self.https_proxy,
                "https": self.https_proxy
            })
        
        return session

    def _get_headers(self) -> Dict[str, str]:
        """Generate headers that mimic a real browser."""
        return {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
        }

    def _get_json(self, url: str, headers: Optional[dict] = None, delay: float = 1.5) -> dict:
        """Fetch JSON with anti-blocking measures."""
        # Random delay to appear human-like
        time.sleep(delay + random.uniform(-0.5, 0.5))
        
        final_headers = self._get_headers()
        if headers:
            final_headers.update(headers)
        
        try:
            response = self.session.get(
                url,
                headers=final_headers,
                timeout=self.timeout_seconds
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[DEBUG] Request failed: {e}")
            raise

    @staticmethod
    def _normalize_name(name: str) -> str:
        name = name.replace("™", "").replace("\u2122", "")
        name = re.sub(r"\s+", " ", name).strip()
        return name.lower()

    def fetch_steam_items(self, query: str, max_items: int = 100) -> List[MarketItem]:
        url = STEAM_SEARCH_URL.format(query=quote(query), start=0, count=max_items)
        try:
            payload = self._get_json(url)
            return self._parse_steam_items(payload)
        except Exception as e:
            print(f"[WARN] Failed to fetch Steam data: {e}")
            return []

    def _parse_steam_items(self, payload: dict) -> List[MarketItem]:
        """Parse Steam items from payload."""
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

    def fetch_buff_items(self, query: str, page_size: int = 80, cookie_file: str = None) -> List[MarketItem]:
        """Fetch BUFF items using API with Selenium for authentication.
        
        Args:
            query: Search query string
            page_size: Number of items to fetch (max 80)
            cookie_file: Optional path to JSON file containing cookies
        
        Returns empty list if browser is not available.
        See module docstring for setup instructions.
        """
        if not HAS_BROWSER:
            self._print_buff_unavailable_message()
            return []
        
        driver = None
        try:
            # Find Chrome/Chromium binary - look for google-chrome first (most reliable)
            candidates = {
                'google-chrome-stable': shutil.which('google-chrome-stable'),
                'google-chrome': shutil.which('google-chrome'),
                'chromium-browser': shutil.which('chromium-browser'),
                'chromium': shutil.which('chromium'),
            }
            
            # Select best candidate (prefer google-chrome-stable)
            chrome_bin = candidates['google-chrome-stable'] or candidates['google-chrome'] or candidates['chromium-browser'] or candidates['chromium']
            
            # Override GOOGLE_CHROME_BIN env var with correct value
            if chrome_bin:
                os.environ['GOOGLE_CHROME_BIN'] = chrome_bin
            
            if not chrome_bin:
                self._print_buff_unavailable_message("Chrome binary not found in PATH")
                return []
            
            print(f"[INFO] Using browser: {chrome_bin}")
            
            # Set up Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument(f"user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
            # Note: Don't use headless with snap version - it crashes
            # chrome_options.add_argument("--headless")
            
            # Create Selenium driver with webdriver-manager for auto ChromeDriver management
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            
            # Check if cookies provided via file
            cookie_dict = None
            
            # Try cookie file argument first, then default location
            cookie_paths = []
            if cookie_file:
                cookie_paths.append(cookie_file)
            # Also check default location
            default_cookie_path = os.path.join(os.path.expanduser('~'), '.buff_cookies.json')
            if os.path.exists(default_cookie_path):
                cookie_paths.append(default_cookie_path)
            
            for cookie_path in cookie_paths:
                if os.path.exists(cookie_path):
                    print(f"[INFO] Loading cookies from: {cookie_path}")
                    try:
                        with open(cookie_path, 'r') as f:
                            cookie_data = json.load(f)
                            # Handle different cookie export formats
                            if isinstance(cookie_data, list):
                                cookie_dict = {c['name']: c['value'] for c in cookie_data if 'name' in c and 'value' in c}
                            elif isinstance(cookie_data, dict):
                                cookie_dict = cookie_data
                        print(f"[INFO] Loaded {len(cookie_dict)} cookies from file")
                        break  # Stop after successfully loading
                    except Exception as e:
                        print(f"[WARNING] Failed to load cookies from {cookie_path}: {e}")
                        cookie_dict = None
            
            # If no cookies from file, use browser to get them
            if not cookie_dict:
                # Navigate to BUFF search
                search_url = f"https://buff.163.com/market/csgo?search={quote(query)}"
                driver.set_page_load_timeout(20)
                driver.get(search_url)
                
                # Wait for user to clear login requirement
                print("\n" + "="*60)
                print("[WAITING] BUFF login required")
                print("="*60)
                print("Browser window has opened to BUFF market.")
                print("Please complete any login/verification steps in the browser.")
                print("Once you've logged in, press ENTER to continue...")
                print("="*60 + "\n")
                input()
                
                # Continue with page processing after user confirms login
                time.sleep(2)
                
                # Extract cookies from browser session
                cookies = driver.get_cookies()
                cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                
                # Save cookies for future use
                cookie_save_path = os.path.join(os.path.expanduser('~'), '.buff_cookies.json')
                try:
                    with open(cookie_save_path, 'w') as f:
                        json.dump(cookie_dict, f)
                    print(f"[INFO] Saved cookies to: {cookie_save_path}")
                except:
                    pass
            
            # Close browser if it was opened
            if driver:
                driver.quit()
                driver = None
            
            search_url = f"https://buff.163.com/market/csgo?search={quote(query)}"
            
            # Now use requests to call the API with cookies
            api_url = f"https://buff.163.com/api/market/goods"
            params = {
                'game': 'csgo',
                'search': query,
                'page_num': 1,
                'page_size': min(page_size, 80),  # BUFF typically limits to 80
                'sort_by': 'price.asc',
            }
            
            headers = self._get_headers()
            headers['Referer'] = search_url
            
            response = self.session.get(
                api_url,
                params=params,
                headers=headers,
                cookies=cookie_dict,
                timeout=20
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 'OK':
                    items = self._parse_buff_items(data)
                    if items:
                        print(f"[INFO] Found {len(items)} items on BUFF")
                    return items
                else:
                    print(f"[INFO] BUFF API error: {data.get('error', 'Unknown error')}")
                    return []
            else:
                print(f"[INFO] BUFF API request failed: HTTP {response.status_code}")
                return []
            
        except Exception as e:
            error_msg = str(e)[:150]
            if "not found" in error_msg.lower() or "service" in error_msg.lower():
                print(f"[INFO] BUFF browser error: {error_msg}")
            else:
                self._print_buff_unavailable_message(error_msg)
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass

    def _print_buff_unavailable_message(self, error: str = ""):
        """Print helpful message about BUFF availability."""
        if not hasattr(self, '_buff_message_shown'):
            print(f"[INFO] BUFF Market Data: NOT AVAILABLE")
            print(f"[INFO]   Reason: Chrome/Chromium browser compatibility issue")
            print(f"[INFO]")
            print(f"[INFO] Available Workarounds:")
            print(f"[INFO]   1. Use official Google Chrome (not snap version)")
            print(f"[INFO]      $ sudo apt-get install google-chrome-stable")
            print(f"[INFO]")
            print(f"[INFO]   2. Use BUFF API directly (requires authentication)")
            print(f"[INFO]      See: https://buff.163.com/api/")
            print(f"[INFO]")
            print(f"[INFO] Note: Steam Market data collection is fully functional!")
            print(f"[INFO]")
            self._buff_message_shown = True

    def _parse_buff_html_advanced(self, soup: BeautifulSoup) -> List[MarketItem]:
        """Extract BUFF market items from rendered HTML."""
        items: List[MarketItem] = []
        
        try:
            # BUFF page structure varies, try multiple selectors
            item_rows = (
                soup.select('li[data-goods_id]') or
                soup.select('.market-item-row') or
                soup.select('[class*="item"][class*="row"]')
            )
            
            for row in item_rows:
                try:
                    # Find item name/title
                    name_elem = row.select_one('.name, .goods-name, .item-name, h3, h4')
                    if not name_elem:
                        continue
                    
                    name = name_elem.get_text(strip=True)
                    if not name or len(name) < 2:
                        continue
                    
                    # Find price
                    sell_price = None
                    price_elem = row.select_one('[class*="price"]')
                    if price_elem:
                        try:
                            price_text = price_elem.get_text(strip=True)
                            price_num = re.search(r'[\d,\.]+', price_text)
                            if price_num:
                                sell_price = float(price_num.group().replace(',', ''))
                        except (ValueError, AttributeError):
                            pass
                    
                    items.append(MarketItem(name=name, buff_sell_price_cny=sell_price))
                except Exception:
                    continue
            
            return items
        except Exception as e:
            return []

    def _parse_buff_items(self, payload: dict) -> List[MarketItem]:
        """Parse BUFF items from payload."""
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
    parser.add_argument("--cookie-file", default="", help="Path to JSON file with BUFF cookies (to skip manual login)")
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
    except Exception as exc:
        print(f"[WARN] Failed to fetch Steam data: {exc}")
        steam_items = []

    try:
        cookie_file = args.cookie_file if args.cookie_file else None
        buff_items = tracker.fetch_buff_items(args.query, page_size=args.buff_page_size, cookie_file=cookie_file)
    except Exception as exc:
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
