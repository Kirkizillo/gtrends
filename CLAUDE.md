# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Google Trends Monitor - A system that scrapes Google Trends data (Related Queries, Related Topics, Interest Over Time) and exports to Google Sheets automatically via GitHub Actions.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run full scraping (queries + topics)
python main.py --full

# Run with Interest Over Time
python main.py --full --interest

# Run for specific country group
python main.py --full --group group_1

# Test scraper without exporting
python main.py --test-scraper

# Health check (verify connectivity)
python main.py --health

# Setup Google Sheets tabs
python main.py --setup
```

## Architecture

### Data Flow
1. `TrendsScraper` (trends_scraper.py) fetches data from Google Trends via PyTrends
2. Data is deduplicated and stored as `TrendData` dataclass objects
3. `backup.py` saves JSON backup locally before export
4. `GoogleSheetsExporter` (google_sheets_exporter.py) appends data to Google Sheets

### Key Components

**config.py** - Central configuration:
- `CURRENT_TERMS` / `CURRENT_REGIONS` - What to scrape
- `COUNTRY_GROUPS` - Groups for distributed execution (group_1, group_2, group_3)
- `RATE_LIMIT_SECONDS` - Delay between requests (default: 90s)
- `SHEET_NAMES` - Google Sheets tab names

**trends_scraper.py** - Core scraping logic:
- `TrendData` dataclass - Standard data structure for all scraped items
- `_fetch_with_retry()` - Handles 429 rate limits with exponential backoff
- `_deduplicate()` - Removes duplicates before export
- Supports rotating proxies via `config.PROXIES`

**google_sheets_exporter.py** - Export logic:
- Append-only mode (preserves historical data)
- Auto-creates sheets if missing
- Maps `data_type` to sheet names

### GitHub Actions Workflow

Runs 6 times daily at different hours, each time processing a different country group:
- 00:00, 12:00 UTC → group_1 (IN, US, BR)
- 04:00, 16:00 UTC → group_2 (ID, MX, GB)
- 08:00, 20:00 UTC → group_3 (AU, VN, DE, RU)

On failure: Creates GitHub Issue automatically + optional Slack notification.

## Configuration

Environment variables (in `.env`):
- `GOOGLE_SHEET_ID` - Target spreadsheet ID
- `GOOGLE_CREDENTIALS_PATH` - Path to service account JSON
- `PROXIES` - Optional comma-separated proxy list

GitHub Secrets required:
- `GOOGLE_CREDENTIALS` - Full JSON content of service account
- `GOOGLE_SHEET_ID` - Spreadsheet ID
- `SLACK_WEBHOOK_URL` - Optional for failure notifications

## Rate Limiting

Google Trends aggressively rate-limits. The system handles this via:
1. `RATE_LIMIT_SECONDS` (90s) between normal requests
2. Exponential backoff on 429 errors (120s → 240s → 480s)
3. Session re-initialization after each retry
4. Country group distribution to reduce request density
5. User-agent rotation (20 different browsers/OS combinations)
6. Random jitter (±5%) on rate limit delays

## Development Workflow

**CRITICAL: Always push changes to GitHub after local testing**

When making changes to the scraper logic:

1. **Make changes locally** in the `trends_monitor/` directory
2. **Test with mock scraper** to verify logic without hitting Google API:
   ```bash
   python test_mock_scraper.py  # Verifies extraction logic
   python test_user_agents.py   # Verifies user-agent rotation
   ```
3. **ALWAYS commit and push** changes to GitHub after successful mock tests:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push origin main
   ```
4. GitHub Actions will pick up the changes and run with the new code

**Why this matters:**
- GitHub Actions runs the actual scraping on schedule
- Local changes won't be used by GitHub Actions until pushed
- Mock tests prove the logic works without using API quota
- Keeping local and GitHub in sync prevents confusion
