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
2. Data is deduplicated (case-insensitive, Unicode-aware) and stored as `TrendData` dataclass objects
3. `backup.py` saves JSON backup locally before export
4. `GoogleSheetsExporter` (google_sheets_exporter.py) appends data to Google Sheets incrementally
5. `ReportGenerator` (report_generator.py) generates content team reports, exported to Sheets and logs

### Key Components

**config.py** - Central configuration:
- `CURRENT_TERMS` = `TERMS_REDUCED` (3 terms: apk, download apk, app download)
- `CURRENT_REGIONS` = `REGIONS_FULL` (20 regions across 5 groups)
- `COUNTRY_GROUPS` - 5 groups of 4 regions each, staggered ~2h25min apart
- `RATE_LIMIT_SECONDS` = 200s between requests
- `MAX_RETRIES` = 2, `MAX_BACKOFF_SECONDS` = 180
- `SHEET_NAMES` - Google Sheets tab names

**trends_scraper.py** - Core scraping logic:
- `TrendData` dataclass - Standard data structure for all scraped items
- `_fetch_with_retry()` - Handles 429 rate limits with exponential backoff (capped at 180s)
- `_deduplicate()` - Case-insensitive, Unicode-aware deduplication
- `ErrorType` enum - Classifies errors (RATE_LIMIT, NO_DATA, AUTH_ERROR, NETWORK_ERROR, UNKNOWN)
- Supports rotating proxies via `config.PROXIES`
- User-agent rotation (20 different browsers/OS combinations) with random jitter

**google_sheets_exporter.py** - Export logic:
- Append-only mode (preserves historical data)
- Incremental export per term/region combination
- Auto-creates sheets if missing
- Maps `data_type` to sheet names
- Exports content reports to dedicated tabs

**report_generator.py** - Content team reports:
- Detects potential apps and watchlist terms from scraped data
- Generates rich-format reports exported to Google Sheets tabs
- Plain text format for logs, Slack format for notifications

**main.py** - Orchestration:
- Config validation with fail-fast before scraping
- Incremental scraping and export per combination
- Structured JSON metrics logged and saved per run
- Error breakdown by type in final summary

### GitHub Actions Workflow

Runs 10 times daily (5 groups × 2 runs each), staggered ~2h25min apart:
- 00:00, 12:00 UTC → group_1 (WW, IN, US, BR)
- 02:25, 14:25 UTC → group_2 (ID, MX, PH, GB)
- 04:50, 16:50 UTC → group_3 (AU, VN, DE, RU)
- 07:15, 19:15 UTC → group_4 (TH, FR, IT, CN)
- 09:40, 21:40 UTC → group_5 (JP, TR, RO, NG)

Group detection uses minute-based ranges (TOTAL_MIN) to tolerate GitHub Actions scheduling delays.

On failure: Creates GitHub Issue automatically (with dedup, max 1 per 24h) + optional Slack notification.
On success: Auto-closes any open `scraping-failure` issues.

### Current Status (2026-02-13)

The system is stable: 62 consecutive successful runs since Feb 3 (Run #83–#144).
Last failure was Run #82 on Feb 2. All data exports correctly to Google Sheets.

Topics extraction is disabled (PyTrends bug). Interest Over Time is disabled.
Only Related Queries (Top + Rising) are active.

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
1. `RATE_LIMIT_SECONDS` (200s) between normal requests
2. Exponential backoff on 429 errors, capped at `MAX_BACKOFF_SECONDS` (180s)
3. `MAX_RETRIES` = 2 (3rd retry rarely succeeds based on production data)
4. Session re-initialization after each retry
5. Country group distribution (5 groups × 2 runs/day = 10 runs) to reduce request density
6. User-agent rotation (20 different browsers/OS combinations)
7. Random jitter (±5%) on rate limit delays
8. Staggered cron schedules (~2h25min apart) to avoid collisions

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
