#!/usr/bin/env python3
"""Fetch BUFF prices for items in steam_market_730_pages_1_3059.json

This script:
1. Reads all items from steam_market_730_pages_1_3059.json
2. For each item, fetches BUFF market price via API
3. Saves progress after EVERY request (fault-tolerant)
4. Outputs to steam_market_with_buff_prices.json

Requirements:
- Chrome/Chromium browser (for initial login)
- Internet connection to BUFF API

Authentication Flow:
1. Checks for saved cookies in ~/.buff_cookies.json
2. If not found, opens browser for manual login
3. Saves cookies for future use
"""

import json
import os
import random
import re
import shutil
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
from urllib.parse import quote

import requests

# Selenium imports for browser automation (login)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_BROWSER = True
except ImportError:
    HAS_BROWSER = False
    print("[ERROR] Selenium not installed. Install with: pip install selenium webdriver-manager")


# Configuration
MIN_DELAY_SECONDS = 5.1  # Minimum delay between requests - enforce 5+ seconds
STEAM_JSON_PATH = "/home/jim/STEAM_Market_Tracker/steam_market_730_pages_1_3059.json"
OUTPUT_JSON_PATH = "/home/jim/STEAM_Market_Tracker/steam_market_with_buff_prices.json"
CHECKPOINT_PATH = "/home/jim/STEAM_Market_Tracker/steam_market_with_buff_prices.json.checkpoint"
COOKIE_FILE = os.path.expanduser("~/.buff_cookies.json")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


@dataclass
class ItemWithBuffPrice:
    """Steam item with BUFF price data."""
    # Original fields from Steam
    page: int
    item_name: str
    quantity: int
    starting_price: str
    starting_price_usd: float
    hash_name: str
    
    # BUFF fields (fetched)
    buff_sell_price_cny: Optional[float] = None
    buff_sell_num: Optional[int] = None
    buff_buy_max_price_cny: Optional[float] = None
    buff_buy_num: Optional[int] = None
    buff_quick_price_cny: Optional[float] = None
    buff_api_status: str = "pending"  # pending, success, failed, not_found
    buff_error_msg: Optional[str] = None


class BuffPriceFetcher:
    """Fetches BUFF prices for Steam items with cookie-based authentication."""
    
    def __init__(self, cookie_file: str = COOKIE_FILE):
        self.cookie_file = cookie_file
        self.cookies: Optional[Dict[str, str]] = None
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
        })
        
    def get_headers(self) -> Dict[str, str]:
        """Generate random headers."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Referer": "https://buff.163.com/market/csgo",
        }
    
    def load_cookies_or_login(self) -> bool:
        """Load cookies from file or prompt user to login via browser.
        
        Returns:
            True if cookies loaded successfully, False otherwise
        """
        # Try loading existing cookies
        if os.path.exists(self.cookie_file):
            try:
                with open(self.cookie_file, 'r') as f:
                    cookie_data = json.load(f)
                    
                # Handle different cookie formats
                if isinstance(cookie_data, list):
                    self.cookies = {c['name']: c['value'] for c in cookie_data if 'name' in c and 'value' in c}
                elif isinstance(cookie_data, dict):
                    self.cookies = cookie_data
                
                print(f"[SUCCESS] Loaded {len(self.cookies)} cookies from: {self.cookie_file}")
                
                # Validate cookies by making test request
                if self._test_cookies():
                    print("[SUCCESS] Cookies are valid!")
                    return True
                else:
                    print("[WARNING] Cookies expired or invalid. Need to re-login.")
                    self.cookies = None
            except Exception as e:
                print(f"[WARNING] Failed to load cookies: {e}")
        
        # No valid cookies, prompt user to login
        print("\n" + "="*70)
        print("BUFF LOGIN REQUIRED")
        print("="*70)
        print("No valid BUFF cookies found. You need to login to BUFF.163.com")
        print("")
        print("Options:")
        print("  1. [RECOMMENDED] Export cookies from browser and save to:")
        print(f"     {self.cookie_file}")
        print("     Guide: https://github.com/EditThisCookie/Edit-This-Cookie")
        print("")
        print("  2. Open browser automatically (requires Chrome/Chromium)")
        print("")
        choice = input("Choose option (1 or 2): ").strip()
        
        if choice == "1":
            print(f"\nAfter exporting cookies, save them to: {self.cookie_file}")
            print("Then run this script again.")
            return False
        elif choice == "2":
            return self._browser_login()
        else:
            print("[ERROR] Invalid choice")
            return False
    
    def _test_cookies(self) -> bool:
        """Test if cookies are valid by making a simple API request."""
        try:
            url = "https://buff.163.com/api/market/goods"
            params = {
                'game': 'csgo',
                'page_num': 1,
                'page_size': 1,
            }
            headers = self.get_headers()
            
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                cookies=self.cookies,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('code') == 'OK'
            return False
        except:
            return False
    
    def _browser_login(self) -> bool:
        """Open browser for user to login, then extract cookies."""
        if not HAS_BROWSER:
            print("[ERROR] Browser automation not available. Install with:")
            print("  pip install selenium webdriver-manager")
            return False
        
        driver = None
        try:
            # Find Chrome binary
            chrome_bin = (
                shutil.which('google-chrome-stable') or
                shutil.which('google-chrome') or
                shutil.which('chromium-browser') or
                shutil.which('chromium')
            )
            
            if not chrome_bin:
                print("[ERROR] Chrome/Chromium not found in PATH")
                return False
            
            print(f"[INFO] Using browser: {chrome_bin}")
            
            # Set up Chrome
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
            
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            
            # Navigate to BUFF
            print("[INFO] Opening BUFF website...")
            driver.set_page_load_timeout(30)
            driver.get("https://buff.163.com/market/csgo")
            
            print("\n" + "="*70)
            print("BROWSER OPENED - PLEASE LOGIN")
            print("="*70)
            print("1. Complete login in the browser window")
            print("2. Verify you can see the BUFF market page")
            print("3. Waiting 60 seconds for you to login...")
            print("="*70)
            
            # Auto-wait 60 seconds with countdown
            for i in range(60, 0, -1):
                print(f"\r[Countdown] {i}s remaining...", end="", flush=True)
                time.sleep(1)
            
            print("\n✓ Continuing after 60 seconds...\n")
            
            # Extract cookies
            cookies = driver.get_cookies()
            self.cookies = {cookie['name']: cookie['value'] for cookie in cookies}
            
            # Save cookies
            with open(self.cookie_file, 'w') as f:
                json.dump(self.cookies, f, indent=2)
            print(f"[SUCCESS] Saved {len(self.cookies)} cookies to: {self.cookie_file}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Browser login failed: {e}")
            return False
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def fetch_buff_price(self, item_name: str, delay_min: float = 2.0, delay_max: float = 4.0) -> Dict:
        """Fetch BUFF price for a single item.
        
        Args:
            item_name: Item name to search
            delay_min: Minimum delay before request
            delay_max: Maximum delay before request
        
        Returns:
            Dict with BUFF price data
        """
        # Sleep before request (rate limiting)
        sleep_time = max(MIN_DELAY_SECONDS, random.uniform(delay_min, delay_max))
        time.sleep(sleep_time)
        
        result = {
            'buff_sell_price_cny': None,
            'buff_sell_num': None,
            'buff_buy_max_price_cny': None,
            'buff_buy_num': None,
            'buff_quick_price_cny': None,
            'buff_api_status': 'failed',
            'buff_error_msg': None
        }
        
        try:
            url = "https://buff.163.com/api/market/goods"
            params = {
                'game': 'csgo',
                'search': item_name,
                'page_num': 1,
                'page_size': 10,  # Get top 10 results
            }
            
            headers = self.get_headers()
            
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                cookies=self.cookies,
                timeout=15
            )
            
            if response.status_code != 200:
                result['buff_error_msg'] = f"HTTP {response.status_code}"
                return result
            
            data = response.json()
            
            if data.get('code') != 'OK':
                result['buff_error_msg'] = data.get('error', 'API error')
                return result
            
            # Parse items
            items = data.get('data', {}).get('items', [])
            
            if not items:
                result['buff_api_status'] = 'not_found'
                result['buff_error_msg'] = 'No items found'
                return result
            
            # Find exact match (or best match)
            best_match = self._find_best_match(item_name, items)
            
            if best_match:
                result['buff_sell_price_cny'] = self._to_float(best_match.get('sell_min_price'))
                result['buff_sell_num'] = self._to_int(best_match.get('sell_num'))
                result['buff_buy_max_price_cny'] = self._to_float(best_match.get('buy_max_price'))
                result['buff_buy_num'] = self._to_int(best_match.get('buy_num'))
                result['buff_quick_price_cny'] = self._to_float(best_match.get('quick_price'))
                result['buff_api_status'] = 'success'
            else:
                result['buff_api_status'] = 'not_found'
                result['buff_error_msg'] = 'No exact match found'
            
            return result
            
        except Exception as e:
            result['buff_error_msg'] = str(e)[:100]
            return result
    
    def _find_best_match(self, query: str, items: List[Dict]) -> Optional[Dict]:
        """Find best matching item from BUFF results."""
        query_norm = self._normalize_name(query)
        
        # Try exact match first
        for item in items:
            item_name = item.get('market_hash_name', '') or item.get('name', '')
            if self._normalize_name(item_name) == query_norm:
                return item
        
        # Try partial match
        for item in items:
            item_name = item.get('market_hash_name', '') or item.get('name', '')
            if query_norm in self._normalize_name(item_name):
                return item
        
        # Return first item as fallback
        return items[0] if items else None
    
    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize item name for comparison."""
        name = name.replace("™", "").replace("\u2122", "")
        name = re.sub(r"\s+", " ", name).strip()
        return name.lower()
    
    @staticmethod
    def _to_float(value) -> Optional[float]:
        """Convert to float safely."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def _to_int(value) -> Optional[int]:
        """Convert to int safely."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None


def load_steam_items(json_path: str) -> List[Dict]:
    """Load items from Steam JSON file."""
    with open(json_path, 'r') as f:
        data = json.load(f)
    return data['items']


def load_checkpoint(checkpoint_path: str) -> Dict:
    """Load checkpoint if exists."""
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, 'r') as f:
            return json.load(f)
    return None


def save_progress(output_path: str, checkpoint_path: str, items: List[Dict], 
                  total_items: int, current_index: int):
    """Save progress after each request."""
    output_data = {
        "meta": {
            "source_file": "steam_market_730_pages_1_3059.json",
            "total_items": total_items,
            "processed_items": current_index + 1,
            "last_processed_index": current_index,
            "generated_at_epoch": int(time.time()),
        },
        "items": items
    }
    
    # Save both output and checkpoint
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    with open(checkpoint_path, 'w') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def main(login_method: str = None):
    print("="*70)
    print("BUFF Price Fetcher for Steam Market Items")
    print("="*70)
    print(f"Input:  {STEAM_JSON_PATH}")
    print(f"Output: {OUTPUT_JSON_PATH}")
    print("="*70 + "\n")
    
    # Load Steam items
    print("[1/4] Loading Steam items...")
    steam_items = load_steam_items(STEAM_JSON_PATH)
    print(f"      Loaded {len(steam_items)} items from Steam JSON")
    
    # Initialize fetcher
    print("\n[2/4] Setting up BUFF API access...")
    fetcher = BuffPriceFetcher()
    
    # Auto-login if method specified via CLI args
    if login_method is None:
        if not fetcher.load_cookies_or_login():
            print("\n[ERROR] Cannot proceed without valid BUFF authentication")
            print("        Please login and try again.")
            return 1
    else:
        # Auto-login with specified method
        print(f"      Using login method: {login_method}")
        if login_method == "browser":
            if not fetcher._browser_login():
                print("\n[ERROR] Browser login failed")
                return 1
        elif login_method == "cookie":
            if not os.path.exists(COOKIE_FILE):
                print(f"\n[ERROR] Cookie file not found: {COOKIE_FILE}")
                print("        Please export cookies from browser first")
                return 1
            if not fetcher.load_cookies_or_login():
                print("\n[ERROR] Cookie loading failed")
                return 1
        else:
            print(f"\n[ERROR] Unknown login method: {login_method}")
            return 1
    
    # Check for existing progress
    print("\n[3/4] Checking for existing progress...")
    checkpoint = load_checkpoint(CHECKPOINT_PATH)
    start_index = 0
    processed_items = []
    
    if checkpoint:
        start_index = checkpoint['meta']['last_processed_index'] + 1
        processed_items = checkpoint['items']
        print(f"      Found checkpoint: resuming from item {start_index}")
    else:
        print(f"      No checkpoint found, starting from beginning")
    
    # Process items
    print(f"\n[4/4] Fetching BUFF prices...")
    print(f"      Processing items {start_index} to {len(steam_items)-1}")
    print(f"      Delay: {MIN_DELAY_SECONDS}s - 6.0s per request (enforced ≥5s)")
    print(f"      Estimated time: ~{(len(steam_items) - start_index) * 5.5 / 60:.1f} minutes")
    print(f"      ⚠️  WARNING: Stop on first failure (no save if error)")
    print("="*70 + "\n")
    
    for i in range(start_index, len(steam_items)):
        item = steam_items[i]
        item_name = item['item_name']
        
        print(f"[{i+1}/{len(steam_items)}] Fetching: {item_name[:60]}...")
        
        # Fetch BUFF price
        buff_data = fetcher.fetch_buff_price(
            item_name,
            delay_min=5.2,
            delay_max=5.8
        )
        
        # Check for critical failure
        status = buff_data['buff_api_status']
        if status == 'failed':
            error_msg = buff_data.get('buff_error_msg', 'Unknown error')
            print(f"           ✗ CRITICAL ERROR: {error_msg}")
            print(f"\n❌ STOPPED ON FIRST FAILURE - NO PROGRESS SAVED")
            print(f"   Error item: {item_name}")
            print(f"   Fix the issue and retry")
            return 1
        
        # Merge data
        item_with_buff = {**item, **buff_data}
        processed_items.append(item_with_buff)
        
        # Log result
        if status == 'success':
            price = buff_data['buff_sell_price_cny']
            print(f"           ✓ Success: ¥{price} CNY")
        elif status == 'not_found':
            print(f"           ⚠ Not found on BUFF (skipped)")
        else:
            error = buff_data.get('buff_error_msg', 'Unknown error')
            print(f"           ✗ Failed: {error}")
        
        # Only save progress on success (no checkpoint on failure)
        save_progress(OUTPUT_JSON_PATH, CHECKPOINT_PATH, processed_items, 
                      len(steam_items), i)
        print(f"           ✓ Saved progress ({i+1}/{len(steam_items)} items)")
    
    print("="*70)
    print("COMPLETED!")
    print("="*70)
    print(f"Processed: {len(processed_items)} items")
    print(f"Output saved to: {OUTPUT_JSON_PATH}")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch BUFF prices for Steam items")
    parser.add_argument(
        "--login",
        choices=["browser", "cookie"],
        help="Login method: 'browser' to use Chrome, 'cookie' to use saved cookies"
    )
    parser.add_argument(
        "--skip-login",
        action="store_true",
        help="Skip login check (assume cookies already exist)"
    )
    
    args = parser.parse_args()
    
    if args.skip_login:
        login_method = "cookie"
    else:
        login_method = args.login
    
    exit(main(login_method))
