#!/usr/bin/env python3
"""Test BUFF API connectivity and cookie validity before batch processing."""

import json
import os
import random
from typing import Dict, Optional

import requests

COOKIE_FILE = os.path.expanduser("~/.buff_cookies.json")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


class BuffAPITester:
    """Test BUFF API connectivity."""
    
    def __init__(self):
        self.session = requests.Session()
        self.cookies = None
        
    def load_cookies(self) -> bool:
        """Load cookies from file."""
        if not os.path.exists(COOKIE_FILE):
            print(f"❌ Cookie file not found: {COOKIE_FILE}")
            return False
        
        try:
            with open(COOKIE_FILE, 'r') as f:
                cookie_data = json.load(f)
            
            # Handle different cookie formats
            if isinstance(cookie_data, list):
                self.cookies = {c['name']: c['value'] for c in cookie_data if 'name' in c and 'value' in c}
            elif isinstance(cookie_data, dict):
                self.cookies = cookie_data
            else:
                print(f"❌ Invalid cookie format")
                return False
            
            print(f"✅ Loaded {len(self.cookies)} cookies from: {COOKIE_FILE}")
            return True
        except Exception as e:
            print(f"❌ Failed to load cookies: {e}")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://buff.163.com/market/csgo",
            "DNT": "1",
        }
    
    def test_api_connection(self, query: str = "AK-47 | Redline") -> bool:
        """Test BUFF API with a simple request."""
        try:
            print(f"\n📡 Testing BUFF API connection...")
            print(f"   Query: '{query}'")
            
            url = "https://buff.163.com/api/market/goods"
            # Try without sort_by first
            params = {
                'game': 'csgo',
                'search': query,
                'page_num': 1,
                'page_size': 5,
            }
            
            headers = self.get_headers()
            
            print(f"   URL: {url}")
            print(f"   Sending request with cookies...")
            
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                cookies=self.cookies,
                timeout=15
            )
            
            print(f"   Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ API returned HTTP {response.status_code}")
                return False
            
            data = response.json()
            code = data.get('code')
            
            print(f"   API Response Code: {code}")
            
            if code != 'OK':
                error_msg = data.get('error', 'Unknown error')
                print(f"❌ API error: {error_msg}")
                return False
            
            # Check response data
            items = data.get('data', {}).get('items', [])
            print(f"   Found {len(items)} items")
            
            if items:
                first_item = items[0]
                item_name = first_item.get('market_hash_name', 'N/A')
                sell_price = first_item.get('sell_min_price', 'N/A')
                print(f"\n   Sample Result:")
                print(f"   - Name: {item_name}")
                print(f"   - Price: ¥{sell_price} CNY")
                print(f"   - Sell Count: {first_item.get('sell_num', 'N/A')}")
                print(f"   - Buy Count: {first_item.get('buy_num', 'N/A')}")
            
            print(f"\n✅ API test SUCCESSFUL!")
            return True
            
        except requests.exceptions.Timeout:
            print(f"❌ Request timeout (15s)")
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection error: {e}")
            return False
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON response")
            return False
        except Exception as e:
            print(f"❌ Error: {str(e)[:200]}")
            return False
    
    def test_multiple_items(self, items: list) -> Dict:
        """Test API with multiple items."""
        print(f"\n📋 Testing {len(items)} sample items...")
        print(f"   With 5+ second delay between requests...")
        
        results = {
            'success': 0,
            'not_found': 0,
            'failed': 0,
            'errors': []
        }
        
        for i, item_name in enumerate(items[:5]):  # Test first 5 items
            print(f"\n   [{i+1}/5] Testing: {item_name[:50]}...")
            
            # 5 second delay before request
            import time
            time.sleep(5.1)
            
            try:
                url = "https://buff.163.com/api/market/goods"
                params = {
                    'game': 'csgo',
                    'search': item_name,
                    'page_num': 1,
                    'page_size': 5,
                }
                
                headers = self.get_headers()
                
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    cookies=self.cookies,
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('code') == 'OK':
                        items_found = data.get('data', {}).get('items', [])
                        if items_found:
                            price = items_found[0].get('sell_min_price', 'N/A')
                            print(f"      ✓ Found: ¥{price} CNY")
                            results['success'] += 1
                        else:
                            print(f"      ⚠ No items found")
                            results['not_found'] += 1
                    else:
                        error = data.get('error', 'Unknown')
                        print(f"      ✗ API Error: {error}")
                        results['failed'] += 1
                        results['errors'].append(error)
                else:
                    print(f"      ✗ HTTP {response.status_code}")
                    results['failed'] += 1
            except Exception as e:
                print(f"      ✗ Exception: {str(e)[:100]}")
                results['failed'] += 1
                results['errors'].append(str(e))
        
        return results


def main():
    print("="*70)
    print("BUFF API Connectivity Test")
    print("="*70)
    
    tester = BuffAPITester()
    
    # Step 1: Load cookies
    print("\n[Step 1/3] Loading cookies...")
    if not tester.load_cookies():
        print("\n❌ Cannot continue without valid cookies")
        return 1
    
    # Step 2: Test basic API connection
    print("\n[Step 2/3] Testing basic API connectivity...")
    if not tester.test_api_connection():
        print("\n❌ API connection test failed")
        print("   Possible reasons:")
        print("   - Cookies are expired or invalid")
        print("   - Network connection issue")
        print("   - BUFF API is blocking requests")
        return 1
    
    # Step 3: Test multiple items
    print("\n[Step 3/3] Testing with multiple Steam items...")
    
    # Load some items from Steam JSON
    try:
        steam_json = "/home/jim/STEAM_Market_Tracker/steam_market_730_pages_1_3059.json"
        with open(steam_json, 'r') as f:
            steam_data = json.load(f)
        
        steam_items = steam_data.get('items', [])
        if steam_items:
            item_names = [item['item_name'] for item in steam_items[:10]]
            results = tester.test_multiple_items(item_names)
            
            print("\n" + "="*70)
            print("TEST RESULTS SUMMARY")
            print("="*70)
            print(f"Success:   {results['success']}/5")
            print(f"Not Found: {results['not_found']}/5")
            print(f"Failed:    {results['failed']}/5")
            
            if results['success'] >= 1:
                print("\n✅ API is working and ready for batch processing!")
                return 0
            else:
                print("\n⚠️  API might have issues, but you can still try batch processing")
                return 0
        else:
            print("⚠️  No items found in Steam JSON")
            return 0
    except Exception as e:
        print(f"⚠️  Error loading Steam items: {e}")
        return 0


if __name__ == "__main__":
    exit(main())
