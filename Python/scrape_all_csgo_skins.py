#!/usr/bin/env python3
"""
Scrape ALL CS:GO weapon skins from Steam Community Market.

This script fetches comprehensive weapon skin data from Steam, including:
- All weapon types (rifles, pistols, SMGs, etc.)
- All wear conditions (Factory New, Minimal Wear, etc.)
- Prices and listing counts
- StatTrak variants

Usage:
    python scrape_all_csgo_skins.py --output skins.csv
    python scrape_all_csgo_skins.py --output skins.json --max-items 1000
"""

import requests
import time
import json
import csv
import argparse
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from urllib.parse import urlencode
import random

# Steam API endpoints
STEAM_MARKET_SEARCH_URL = "https://steamcommunity.com/market/search/render/"

# CS:GO App ID
CSGO_APP_ID = 730

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
]

# Weapon categories to filter (exclude stickers, cases, graffiti, etc.)
WEAPON_KEYWORDS = [
    "AK-47", "M4A4", "M4A1-S", "AWP", "Desert Eagle", "USP-S", "Glock-18",
    "P2000", "P250", "Five-SeveN", "Tec-9", "CZ75-Auto", "Dual Berettas",
    "R8 Revolver", "MP9", "MAC-10", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon",
    "Nova", "XM1014", "Sawed-Off", "MAG-7", "M249", "Negev",
    "FAMAS", "Galil AR", "AUG", "SG 553", "SSG 08", "G3SG1", "SCAR-20",
    # Knives
    "Karambit", "Bayonet", "M9 Bayonet", "Butterfly Knife", "Flip Knife",
    "Gut Knife", "Falchion Knife", "Bowie Knife", "Huntsman Knife",
    "Shadow Daggers", "Ursus Knife", "Navaja Knife", "Stiletto Knife",
    "Talon Knife", "Classic Knife", "Paracord Knife", "Survival Knife",
    "Nomad Knife", "Skeleton Knife", "Kukri Knife",
    # Gloves
    "Gloves", "Hand Wraps", "Sport Gloves", "Driver Gloves", "Moto Gloves",
    "Specialist Gloves", "Hydra Gloves", "Bloodhound Gloves", "Broken Fang Gloves",
]


@dataclass
class SteamSkin:
    """Data class for a CS:GO weapon skin."""
    name: str
    sell_price_usd: Optional[float] = None
    sell_price_text: Optional[str] = None
    sell_listings: Optional[int] = None
    asset_url: Optional[str] = None
    hash_name: Optional[str] = None
    item_type: Optional[str] = None  # Weapon, Knife, Gloves, etc.


class SteamMarketScraper:
    """Scraper for Steam Community Market CS:GO weapon skins."""
    
    def __init__(
        self,
        delay_min: float = 2.0,
        delay_max: float = 4.0,
        max_429_retries: int = 8,
        retry_backoff_base: float = 15.0,
    ):
        """
        Initialize the scraper.
        
        Args:
            delay_min: Minimum delay between requests (seconds)
            delay_max: Maximum delay between requests (seconds)
            max_429_retries: Max retries on HTTP 429 before stopping
            retry_backoff_base: Base backoff in seconds for 429 retries
        """
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.max_429_retries = max_429_retries
        self.retry_backoff_base = retry_backoff_base
        self.session = requests.Session()
        self.total_requests = 0
        
    def _get_headers(self) -> Dict[str, str]:
        """Get randomized headers for requests."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://steamcommunity.com/market/",
            "Origin": "https://steamcommunity.com",
            "Connection": "keep-alive",
        }
    
    def _delay(self):
        """Add randomized delay to avoid rate limiting."""
        delay = random.uniform(self.delay_min, self.delay_max)
        jitter = random.uniform(-0.3, 0.3)
        time.sleep(delay + jitter)
    
    def _is_weapon_skin(self, name: str) -> bool:
        """Check if item is a weapon skin (not sticker, case, etc.)."""
        name_lower = name.lower()
        
        # Exclude non-weapon items
        exclude_keywords = [
            "sticker", "case", "key", "pin", "music kit", "graffiti",
            "patch", "pass", "coin", "trophy", "autograph", "package",
            "capsule", "souvenir package", "gift", "tag"
        ]
        
        for keyword in exclude_keywords:
            if keyword in name_lower:
                return False
        
        # Check if it contains weapon keywords
        for weapon in WEAPON_KEYWORDS:
            if weapon.lower() in name_lower:
                return True
        
        # Also check for pattern like "| " which indicates a skin
        if " | " in name:
            return True
            
        return False
    
    def _determine_item_type(self, name: str) -> str:
        """Determine the type of item (Rifle, Pistol, Knife, etc.)."""
        name_lower = name.lower()
        
        # Knives
        knife_keywords = ["karambit", "bayonet", "butterfly", "flip", "gut", 
                         "falchion", "bowie", "huntsman", "shadow daggers",
                         "ursus", "navaja", "stiletto", "talon", "classic knife",
                         "paracord", "survival", "nomad", "skeleton", "kukri"]
        for keyword in knife_keywords:
            if keyword in name_lower:
                return "Knife"
        
        # Gloves
        if "gloves" in name_lower or "hand wraps" in name_lower:
            return "Gloves"
        
        # Rifles
        rifle_keywords = ["ak-47", "m4a4", "m4a1-s", "awp", "famas", "galil ar",
                         "aug", "sg 553", "ssg 08", "g3sg1", "scar-20"]
        for keyword in rifle_keywords:
            if keyword in name_lower:
                return "Rifle"
        
        # Pistols
        pistol_keywords = ["desert eagle", "usp-s", "glock-18", "p2000", "p250",
                          "five-seven", "tec-9", "cz75-auto", "dual berettas", "r8 revolver"]
        for keyword in pistol_keywords:
            if keyword in name_lower:
                return "Pistol"
        
        # SMGs
        smg_keywords = ["mp9", "mac-10", "mp7", "mp5-sd", "ump-45", "p90", "pp-bizon"]
        for keyword in smg_keywords:
            if keyword in name_lower:
                return "SMG"
        
        # Shotguns
        shotgun_keywords = ["nova", "xm1014", "sawed-off", "mag-7"]
        for keyword in shotgun_keywords:
            if keyword in name_lower:
                return "Shotgun"
        
        # Heavy
        heavy_keywords = ["m249", "negev"]
        for keyword in heavy_keywords:
            if keyword in name_lower:
                return "Heavy"
        
        return "Other"
    
    def fetch_all_skins(
        self,
        max_items: int = None,
        start_offset: int = 0,
        output_file: str = None,
        save_format: str = "csv",
        category_type: str = None,
        weapon_tag: str = None,
        on_page=None,
    ) -> List[SteamSkin]:
        """on_page(skins): called after each page with that page's SteamSkin list."""
        """
        Fetch CS:GO skins from Steam Market.

        Args:
            max_items: Maximum number of items to fetch (None for all)
            start_offset: Starting offset for pagination
            output_file: File to save results incrementally
            save_format: "csv" or "jsonl"
            category_type: Steam type tag, e.g. "CSGO_Type_Pistol"
            weapon_tag: Steam weapon tag, e.g. "weapon_ak47"
        """
        all_skins = []
        count_per_page = 10
        current_offset = start_offset
        total_count = None
        first_page = True
        use_keyword_filter = (category_type is None and weapon_tag is None)

        label = category_type or weapon_tag or "all items"
        print(f"Starting scrape: {label}")
        print(f"Delay: {self.delay_min}-{self.delay_max}s per page")
        if output_file:
            print(f"Saving to: {output_file}")
        print()

        rate_limit_retries = 0
        while True:
            if max_items and len(all_skins) >= max_items:
                print(f"\nReached max_items limit ({max_items})")
                break

            # Build request parameters as list of tuples to support [] keys
            params = [
                ("appid", CSGO_APP_ID),
                ("norender", 1),
                ("count", count_per_page),
                ("start", current_offset),
                ("sort_column", "popular"),
                ("sort_dir", "desc"),
                ("currency", 1),
            ]
            if category_type:
                params.append(("category_730_Type[]", f"tag_{category_type}"))
            if weapon_tag:
                params.append(("category_730_Weapon[]", f"tag_{weapon_tag}"))

            try:
                if self.total_requests > 0:
                    self._delay()

                response = self.session.get(
                    STEAM_MARKET_SEARCH_URL, params=params,
                    headers=self._get_headers(), timeout=15
                )
                self.total_requests += 1
                
                if response.status_code == 429:
                    rate_limit_retries += 1
                    if rate_limit_retries > self.max_429_retries:
                        print(
                            f"[ERROR] HTTP 429 at offset {current_offset} after "
                            f"{self.max_429_retries} retries"
                        )
                        break
                    backoff = self.retry_backoff_base * (2 ** (rate_limit_retries - 1))
                    backoff = min(backoff, 600.0)
                    print(
                        f"[WARN] HTTP 429 at offset {current_offset}; retry "
                        f"{rate_limit_retries}/{self.max_429_retries} after {backoff:.1f}s"
                    )
                    time.sleep(backoff + random.uniform(0.0, 1.0))
                    continue

                if response.status_code != 200:
                    print(f"[ERROR] HTTP {response.status_code} at offset {current_offset}")
                    break

                rate_limit_retries = 0
                
                data = response.json()
                
                # Check for success
                if not data.get("success"):
                    print(f"[ERROR] API returned success=false at offset {current_offset}")
                    break
                
                # Get total count
                if total_count is None:
                    total_count = data.get("total_count", 0)
                    print(f"Total items in market: {total_count:,}")
                
                # Parse results
                results = data.get("results", [])
                
                if not results:
                    print(f"\nNo more items at offset {current_offset}")
                    break
                
                # Process results
                page_skins = 0
                for item in results:
                    name = item.get("name", "")
                    hash_name = item.get("hash_name", "")
                    
                    # When no category filter given, restrict to weapon skins only
                    if use_keyword_filter and not self._is_weapon_skin(name):
                        continue
                    
                    # Parse price
                    sell_price_text = item.get("sell_price_text", "")
                    sell_price_usd = None
                    if sell_price_text:
                        try:
                            # Remove currency symbol and convert to float
                            price_str = sell_price_text.replace("$", "").replace(",", "").strip()
                            sell_price_usd = float(price_str)
                        except (ValueError, AttributeError):
                            pass
                    
                    # Create skin object
                    skin = SteamSkin(
                        name=name,
                        sell_price_usd=sell_price_usd,
                        sell_price_text=sell_price_text,
                        sell_listings=item.get("sell_listings"),
                        asset_url=item.get("asset_description", {}).get("icon_url"),
                        hash_name=hash_name,
                        item_type=self._determine_item_type(name),
                    )
                    
                    all_skins.append(skin)
                    page_skins += 1
                    
                    # Check max_items
                    if max_items and len(all_skins) >= max_items:
                        break
                
                # Progress update
                print(f"Offset {current_offset:5d} | Page items: {len(results):3d} | "
                      f"Weapon skins: {page_skins:3d} | Total collected: {len(all_skins):5d} | "
                      f"Requests: {self.total_requests}")
                
                # Incremental save / callback after each page
                if page_skins > 0:
                    page_skins_list = all_skins[-page_skins:]
                    if output_file:
                        if save_format == "csv":
                            append_to_csv(page_skins_list, output_file, write_header=first_page)
                            first_page = False
                        elif save_format in ["json", "jsonl"]:
                            append_to_jsonl(page_skins_list, output_file)
                    if on_page:
                        # Pass current_offset so callers can checkpoint resume position
                        on_page(page_skins_list, current_offset)
                
                # Move to next page
                current_offset += count_per_page
                
                # Check if we've reached the end
                if current_offset >= total_count:
                    print(f"\nReached end of market (offset {current_offset} >= total {total_count})")
                    break
                
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Request failed at offset {current_offset}: {e}")
                break
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON decode error at offset {current_offset}: {e}")
                break
            except KeyboardInterrupt:
                print(f"\n\n[INTERRUPTED] Stopping at offset {current_offset}")
                break
        
        print(f"\n{'='*80}")
        print(f"Scraping complete!")
        print(f"Total weapon skins collected: {len(all_skins):,}")
        print(f"Total API requests: {self.total_requests}")
        print(f"{'='*80}\n")
        
        return all_skins


def save_to_csv(skins: List[SteamSkin], filepath: str):
    """Save skins to CSV file."""
    if not skins:
        print("No skins to save!")
        return
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(skins[0]).keys()))
        writer.writeheader()
        for skin in skins:
            writer.writerow(asdict(skin))
    
    print(f"✓ Saved {len(skins):,} skins to: {filepath}")


def append_to_csv(skins: List[SteamSkin], filepath: str, write_header: bool = False):
    """Append skins to CSV file incrementally."""
    if not skins:
        return
    
    import os
    mode = 'w' if write_header or not os.path.exists(filepath) else 'a'
    
    with open(filepath, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(skins[0]).keys()))
        if mode == 'w' or write_header:
            writer.writeheader()
        for skin in skins:
            writer.writerow(asdict(skin))


def append_to_jsonl(skins: List[SteamSkin], filepath: str):
    """Append skins to JSON Lines file incrementally (one JSON object per line)."""
    if not skins:
        return
    
    with open(filepath, 'a', encoding='utf-8') as f:
        for skin in skins:
            json.dump(asdict(skin), f, ensure_ascii=False)
            f.write('\n')


def save_to_json(skins: List[SteamSkin], filepath: str):
    """Save skins to JSON file."""
    if not skins:
        print("No skins to save!")
        return
    
    data = [asdict(skin) for skin in skins]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved {len(skins):,} skins to: {filepath}")


def print_statistics(skins: List[SteamSkin]):
    """Print statistics about collected skins."""
    if not skins:
        return
    
    print("\n" + "="*80)
    print("STATISTICS")
    print("="*80)
    
    # Count by type
    type_counts = {}
    for skin in skins:
        item_type = skin.item_type or "Unknown"
        type_counts[item_type] = type_counts.get(item_type, 0) + 1
    
    print("\nItems by type:")
    for item_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {item_type:15s}: {count:5,}")
    
    # Price statistics
    prices = [s.sell_price_usd for s in skins if s.sell_price_usd is not None]
    if prices:
        print(f"\nPrice statistics:")
        print(f"  Items with prices: {len(prices):,}")
        print(f"  Min price:  ${min(prices):.2f}")
        print(f"  Max price:  ${max(prices):.2f}")
        print(f"  Avg price:  ${sum(prices)/len(prices):.2f}")
    
    # Listing statistics
    listings = [s.sell_listings for s in skins if s.sell_listings is not None]
    if listings:
        print(f"\nListing statistics:")
        print(f"  Total listings: {sum(listings):,}")
        print(f"  Avg per item:   {sum(listings)//len(listings):,}")
    
    print("="*80 + "\n")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape all CS:GO weapon skins from Steam Community Market"
    )
    parser.add_argument(
        "--output", "-o",
        default="csgo_skins.csv",
        help="Output file path (CSV or JSON based on extension)"
    )
    parser.add_argument(
        "--max-items", "-m",
        type=int,
        default=None,
        help="Maximum number of items to fetch (default: all)"
    )
    parser.add_argument(
        "--start-offset", "-s",
        type=int,
        default=0,
        help="Starting offset for pagination (default: 0)"
    )
    parser.add_argument(
        "--delay-min",
        type=float,
        default=2.0,
        help="Minimum delay between requests in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--delay-max",
        type=float,
        default=4.0,
        help="Maximum delay between requests in seconds (default: 4.0)"
    )
    parser.add_argument(
        "--max-429-retries",
        type=int,
        default=8,
        help="Maximum retries when Steam returns HTTP 429 (default: 8)"
    )
    parser.add_argument(
        "--retry-backoff-base",
        type=float,
        default=15.0,
        help="Base seconds for exponential backoff on HTTP 429 (default: 15.0)"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only print statistics, don't save to file"
    )
    
    return parser.parse_args()


def main():
    """Main function."""
    args = parse_args()
    
    # Create scraper
    scraper = SteamMarketScraper(
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        max_429_retries=args.max_429_retries,
        retry_backoff_base=args.retry_backoff_base,
    )
    
    # Determine save format (support .json, .jsonl, or .csv)
    if args.output.endswith('.json') or args.output.endswith('.jsonl'):
        save_format = "jsonl"  # Use JSON Lines for incremental saves
    else:
        save_format = "csv"
    
    # Fetch all skins with incremental saving
    skins = scraper.fetch_all_skins(
        max_items=args.max_items,
        start_offset=args.start_offset,
        output_file=args.output if not args.stats_only else None,
        save_format=save_format,
    )
    
    # Print statistics
    print_statistics(skins)
    
    # Final save handling
    if not args.stats_only and skins:
        import os
        if save_format in ["json", "jsonl"]:
            # For JSON Lines, data is already saved incrementally
            # Just confirm the file exists
            if os.path.exists(args.output):
                print(f"✓ Data saved incrementally to JSON Lines file: {args.output}")
                print(f"  (One JSON object per line - use 'jq' or load line-by-line)")
            else:
                # Fallback: create file if somehow missing
                append_to_jsonl(skins, args.output)
                print(f"✓ Saved {len(skins):,} skins to: {args.output}")
        elif save_format == "csv":
            # CSV is already saved incrementally
            if os.path.exists(args.output):
                print(f"✓ Data already saved incrementally to: {args.output}")
            else:
                # Fallback: create file if somehow missing
                save_to_csv(skins, args.output)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
