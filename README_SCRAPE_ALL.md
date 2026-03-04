# CS:GO Weapon Skins Scraper - Complete Market Data

## Overview

`scrape_all_csgo_skins.py` is a comprehensive scraper that fetches **ALL weapon skins** from the Steam Community Market for CS:GO. Unlike the query-based tracker, this script systematically collects the entire market catalog.

## Features

✅ **Complete Market Coverage** - Scrapes all CS:GO weapon skins (rifles, pistols, SMGs, knives, gloves, etc.)  
✅ **Smart Filtering** - Automatically excludes non-weapon items (stickers, cases, graffiti, keys, etc.)  
✅ **Item Classification** - Auto-categorizes items into types (Rifle, Pistol, SMG, Knife, Gloves, Shotgun, Heavy)  
✅ **Anti-Blocking Protection** - Randomized delays, rotating user agents, and retry logic  
✅ **Progress Tracking** - Real-time progress updates during scraping  
✅ **Multiple Export Formats** - Save as CSV or JSON  
✅ **Resumable** - Start from any offset to continue interrupted scrapes  
✅ **Statistics** - Automatic statistics generation (price ranges, item counts by type, etc.)

## Installation

Already set up! Uses the same `py310` conda environment:

```bash
cd /home/jim/STEAM_Market_Tracker
conda activate py310
```

## Usage Examples

### 1. Scrape ALL weapon skins (this will take hours!)

```bash
python Python/scrape_all_csgo_skins.py --output all_skins.csv
```

**⚠️ Warning:** Steam Market has 30,000+ items total. Filtering for weapons typically yields 10,000-15,000 items. With 2-4 second delays, this can take **8-12 hours** to complete!

### 2. Quick test with limited items

```bash
python Python/scrape_all_csgo_skins.py --max-items 100 --output sample.csv
```

### 3. Save as JSON instead of CSV

```bash
python Python/scrape_all_csgo_skins.py --max-items 500 --output skins.json
```

### 4. Resume from a specific offset

If scraping was interrupted, you can resume:

```bash
python Python/scrape_all_csgo_skins.py --start-offset 5000 --output resume.csv
```

### 5. Faster scraping (but riskier - may trigger rate limits)

```bash
python Python/scrape_all_csgo_skins.py --delay-min 1.0 --delay-max 2.0 --output fast.csv
```

### 6. Statistics only (no file output)

```bash
python Python/scrape_all_csgo_skins.py --max-items 1000 --stats-only
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--output, -o` | Output file path (CSV or JSON) | `csgo_skins.csv` |
| `--max-items, -m` | Maximum items to collect | All items |
| `--start-offset, -s` | Starting pagination offset | 0 |
| `--delay-min` | Minimum delay between requests (seconds) | 2.0 |
| `--delay-max` | Maximum delay between requests (seconds) | 4.0 |
| `--stats-only` | Only show statistics, don't save file | False |

## Output Format

### CSV Columns:
- `name` - Full item name (e.g., "AK-47 | Redline (Field-Tested)")
- `sell_price_usd` - Current sell price in USD (float)
- `sell_price_text` - Formatted price string (e.g., "$5.23")
- `sell_listings` - Number of active listings
- `asset_url` - Steam CDN image URL
- `hash_name` - URL-safe hash name for API calls
- `item_type` - Weapon category (Rifle, Pistol, SMG, Knife, Gloves, etc.)

## Item Filtering

The script automatically filters out:
- ❌ Stickers
- ❌ Cases & Keys
- ❌ Graffiti & Pins
- ❌ Music Kits
- ❌ Patches
- ❌ Autograph Capsules
- ❌ Souvenir Packages

And **keeps** only:
- ✅ Weapon Skins (all types)
- ✅ Knives (all variants)
- ✅ Gloves (all types)
- ✅ StatTrak™ variants

## Performance Estimates

| Items | Estimated Time | API Requests |
|-------|----------------|--------------|
| 100 | ~5 minutes | ~10 |
| 500 | ~25 minutes | ~50 |
| 1,000 | ~50 minutes | ~100 |
| 5,000 | ~4 hours | ~500 |
| 15,000 (full) | ~10-12 hours | ~1,500 |

**Note:** Times assume 2-4 second delays. Actual time varies based on network speed and Steam's response times.

## Example Output

```
Starting scrape of CS:GO weapon skins from Steam Market...
Fetching 100 items per page with 2.0-4.0s delay

Total items in market: 30,575
Offset     0 | Page items: 100 | Weapon skins:  45 | Total collected:    45 | Requests: 1
Offset   100 | Page items: 100 | Weapon skins:  52 | Total collected:    97 | Requests: 2
Offset   200 | Page items: 100 | Weapon skins:  48 | Total collected:   145 | Requests: 3
...

================================================================================
STATISTICS
================================================================================

Items by type:
  Rifle          : 3,245
  Pistol         : 1,892
  Knife          :   856
  SMG            :   743
  Gloves         :   234
  Shotgun        :   187
  Heavy          :    95

Price statistics:
  Items with prices: 7,252
  Min price:  $0.03
  Max price:  $15,432.00
  Avg price:  $24.56

✓ Saved 7,252 skins to: all_skins.csv
```

## Use Cases

1. **Market Analysis** - Analyze pricing trends across all weapon types
2. **Investment Research** - Find undervalued skins by comparing prices
3. **Inventory Planning** - See which skins have high listing counts
4. **Data Science** - Build models for price prediction
5. **Portfolio Tracking** - Monitor market changes over time

## Recommended Workflow

### For Quick Testing:
```bash
python Python/scrape_all_csgo_skins.py --max-items 100 --output test.csv
```

### For Complete Database:
```bash
# Run overnight or during downtime
nohup python Python/scrape_all_csgo_skins.py --output full_market.csv > scrape.log 2>&1 &

# Check progress
tail -f scrape.log
```

### For Daily Updates:
```bash
# Get top 1000 items each day
python Python/scrape_all_csgo_skins.py --max-items 1000 --output "daily_$(date +%Y%m%d).csv"
```

## Tips

- **Start small** - Test with `--max-items 100` first
- **Be patient** - Full scrape takes hours due to anti-blocking delays
- **Save progress** - Use `--start-offset` to resume if interrupted
- **Check logs** - Monitor for rate limiting or errors
- **Export JSON** - Better for programmatic analysis
- **Export CSV** - Better for Excel/spreadsheet analysis

## Comparison with csgo_market_tracker.py

| Feature | scrape_all_csgo_skins.py | csgo_market_tracker.py |
|---------|-------------------------|------------------------|
| Use case | Bulk market data collection | Search-based comparison |
| Coverage | All weapon skins | Specific search query |
| BUFF data | ❌ No | ✅ Yes |
| Steam data | ✅ Yes | ✅ Yes |
| Runtime | Hours (full scrape) | Seconds (per query) |
| Output | Single market snapshot | Merged Steam+BUFF prices |

## Troubleshooting

**Problem:** Script stops with HTTP errors  
**Solution:** Increase delays with `--delay-min 3.0 --delay-max 5.0`

**Problem:** Too slow  
**Solution:** Use `--max-items` to limit scope, or reduce delays (risky)

**Problem:** Want to resume  
**Solution:** Note the last offset from logs, use `--start-offset <number>`

**Problem:** Getting blocked  
**Solution:** Wait 15-30 minutes before retrying, increase delays

## Support

For issues or questions:
1. Check the scrape.log for error messages
2. Verify conda environment is activated: `conda activate py310`
3. Test with small `--max-items` first
4. Review the main tracker README for general Steam API tips
