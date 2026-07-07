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
- `CURRENT_TERMS` = `TERMS_REDUCED` (3 base terms: apk, download apk, app download)
- `COUNTRY_EXTRA_TERMS` - Per-country localized terms (7 countries: BR, MX, ID, RU, TH, TR, CO)
- `CURRENT_REGIONS` = `REGIONS_FULL` (20 regions across 5 groups, CO replaced CN since Mar 6)
- `COUNTRY_GROUPS` - 5 groups of 4 regions each, staggered ~2h25min apart
- `TIMEFRAME` = `"now 4-H"` — Base terms use 4-hour window
- `TIMEFRAME_EXTRA_TERMS` = `"now 1-d"` — Localized terms use 24-hour window (more volume)
- `RATE_LIMIT_SECONDS` = 200s between requests
- `MAX_RETRIES` = 2, `MAX_BACKOFF_SECONDS` = 180
- `SHEET_NAMES` - Google Sheets tab names

**trends_scraper.py** - Core scraping logic:
- `TrendData` dataclass - Standard data structure for all scraped items
- `_build_payload()` - Accepts optional `timeframe` override (default: `config.TIMEFRAME`)
- `scrape_related_queries()` - Accepts optional `timeframe` parameter for per-term timeframe control
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
- Exports content reports to dedicated tabs (`Inf_YYYY-MM-DD_HH:MM`)
- Auto-cleanup of report tabs older than 7 days (runs after each export)

**report_generator.py** - Content team reports:
- Detects potential apps and watchlist terms from scraped data
- Generates rich-format reports exported to Google Sheets tabs
- Plain text format for logs, Slack format for notifications
- Novelty detection (new/resurgent apps) and trend velocity via Turso DB
- Cross-region correlation analysis
- Unicode-aware normalization (diacritics removal) consistent with database.py

**database.py** - Turso (SQLite cloud) integration:
- Tables: `trends` (all scraped data), `apps_seen` (novelty tracking), `run_metrics`
- `_normalize_title()` - Unicode-aware normalization with diacritics removal, suffix stripping
- Novelty detection: tracks first-seen apps, resurgent detection (>7 days gap)
- Velocity tracking: prefix-match LIKE queries to avoid false positives
- Weekly queries: top by country, new apps, cross-market (3+ countries), week comparison
- Optional — system continues working without Turso (Google Sheets only)
- Embedded replica mode: local temp file + cloud sync

**digest.py** - Daily digest (23:00 UTC cron):
- Consolidates all 10 daily runs into single HTML report
- Sections: volume comparison (vs yesterday), top 15 apps, new apps, region activity heatmap
- On Sundays: also generates weekly report and triggers tab cleanup
- `--weekly` flag to force weekly report on any day
- Output: `logs/digest_YYYY-MM-DD.html`

**weekly_report.py** - Weekly HTML report:
- Top 10 apps per market (20 countries), new apps by region, cross-market trends (3+ countries)
- Week-over-week comparison: volume, new apps, region breakdown with change percentages
- Triggered by digest.py on Sundays or via `--weekly` flag
- Output: `logs/weekly_YYYY-MM-DD.html`

**main.py** - Orchestration:
- Config validation with fail-fast before scraping
- Iterates region-first, then terms (base + country extras)
- Per-term timeframe selection: base terms use `TIMEFRAME` (4h), localized terms use `TIMEFRAME_EXTRA_TERMS` (24h)
- `extra_terms_ok` set: localized terms that already work on 4h (e.g., `apk indir`) keep the base timeframe
- Incremental scraping and export per combination
- Structured JSON metrics logged and saved per run
- Error breakdown by type in final summary

### GitHub Actions Workflow

Runs 11 times daily (5 groups × 2 runs + 1 digest), staggered ~2h25min apart:
- 00:00, 12:00 UTC → group_1 (WW, IN, US, BR)
- 02:25, 14:25 UTC → group_2 (ID, MX, PH, GB)
- 04:50, 16:50 UTC → group_3 (AU, VN, DE, RU)
- 07:15, 19:15 UTC → group_4 (TH, FR, IT, CO)
- 09:40, 21:40 UTC → group_5 (JP, TR, RO, NG)
- 23:00 UTC → digest (daily consolidation + weekly on Sundays)

Group detection uses `github.event.schedule` for deterministic cron-to-group mapping (immune to GitHub Actions scheduling delays).

On failure: Creates GitHub Issue automatically (with dedup, max 1 per 24h) + optional Slack notification.
On success: Auto-closes any open `scraping-failure` issues.

### Current Status (2026-03-16)

The system is stable with 100% success rate since Feb 3 (Run #83 onward, 0 failures).
All data exports correctly to Google Sheets + Turso DB.

**Deployment timeline:**
- Feb 13: Territory scaling (12→20 regions, 3→5 groups)
- Feb 18: Localized keywords per country (12 countries with extra terms in local language)
- Feb 20: Dual timeframe — localized terms switched to 24h window (`now 1-d`) for better data yield
- Mar 6: Removed 6 dead localized keywords (FR, IT, DE, JP, CN, RO), replaced CN with CO (Colombia)
- Mar 12: Turso DB integration, novelty detection, HTML reports, velocity tracking, daily digest
- Mar 16: Fixed deterministic group detection (github.event.schedule), velocity query precision, normalization consistency, weekly report, tab cleanup

**Active localized keywords:** `apk indir` (TR), `descargar apk` (MX, CO), `скачать apk` (RU), `baixar apk` (BR), `unduh apk` (ID), `ดาวน์โหลด apk` (TH)

Topics extraction is disabled (PyTrends bug). Interest Over Time is disabled.
Only Related Queries (Top + Rising) are active.

## Configuration

Environment variables (in `.env`):
- `GOOGLE_SHEET_ID` - Target spreadsheet ID
- `GOOGLE_CREDENTIALS_PATH` - Path to service account JSON
- `PROXIES` - Optional comma-separated proxy list
- `TURSO_DATABASE_URL` - Turso database URL (optional)
- `TURSO_AUTH_TOKEN` - Turso authentication token (optional)

GitHub Secrets required:
- `GOOGLE_CREDENTIALS` - Full JSON content of service account
- `GOOGLE_SHEET_ID` - Spreadsheet ID
- `SLACK_WEBHOOK_URL` - Optional for failure notifications
- `TURSO_DATABASE_URL` - Turso database URL
- `TURSO_AUTH_TOKEN` - Turso auth token

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
