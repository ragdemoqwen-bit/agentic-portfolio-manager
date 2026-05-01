# Testing: Algo-Trading Opportunity Scanner

## Overview
The scanner module (`portfolio_manager/scanner/`) provides CLI commands under `portfolio scanner` for stock/options opportunity scanning using technical analysis, LLM sentiment, and options flow analysis.

## CLI Commands
```bash
# Scan a single ticker (skip web scraping)
portfolio scanner run --ticker AAPL --no-scrape --min-score 0

# Scan full watchlist
portfolio scanner run --no-scrape --min-score 0

# Manage watchlist
portfolio scanner watchlist show
portfolio scanner watchlist add PLTR
portfolio scanner watchlist remove PLTR

# View saved opportunities from DB
portfolio scanner opportunities --ticker AAPL --limit 10

# Export to JSON or CSV
portfolio scanner run --ticker AAPL --no-scrape --min-score 0 --export json
portfolio scanner run --ticker AAPL --no-scrape --min-score 0 --export csv

# Overnight scheduler
portfolio scanner schedule --cron "0 1 * * 1-5" --tz UTC
```

## Environment Setup
- Dependencies: `pip install -e ".[dev]"` installs pandas-ta, apscheduler, numpy, pyyaml
- Optional: `pip install -e ".[scraper]"` for Playwright-based news scraping
- Database: SQLite at `~/.agentic-portfolio/portfolio.db`
- Watchlist config: YAML at `~/.agentic-portfolio/scanner_watchlist.yaml`
- Export dir: `~/.agentic-portfolio/scanner_output/`

## Devin Secrets Needed
All are optional — scanner works without any of them using heuristic fallback:
- `OPENROUTER_API_KEY` — for OpenRouter LLM sentiment analysis
- `GEMINI_API_KEY` — for Google Gemini LLM sentiment analysis
- Ollama: No key needed, but requires local Ollama server running at `http://localhost:11434`

## Testing Strategy

### Core Flow (always test)
1. **Watchlist CRUD**: show → add ticker → verify appears → add again (idempotent) → remove → verify gone → remove non-existent (graceful)
2. **Single-ticker scan**: `run --ticker <TICKER> --no-scrape --min-score 0` — verify opportunities have valid score (0-100), direction (LONG/SHORT), entry/target/stop prices, R:R ratio
3. **Invalid ticker**: `run --ticker ZZZZNOTREAL --no-scrape --min-score 0` — should not crash, exit code 0, "Saved 0 opportunities"
4. **DB persistence**: After scanning, `opportunities --ticker <TICKER>` should return previously saved results
5. **JSON export**: Verify file created, parseable JSON, correct schema (ticker, score, direction, entry_price, target_price, stop_loss, risk_reward, wheel_candidate, option_detail)

### Options-Specific Tests
- LEAPS: Check `option_detail.is_leap=true` and `option_detail.dte >= 180`
- Wheel: Check `wheel_candidate=true` for blue-chip stocks with notes about CSP→CC strategy

### Regression
- `pytest -q` — all existing tests should pass
- `ruff check portfolio_manager/` — lint should be clean

## Known Issues & Workarounds

### yfinance Dividend Yield
yfinance's `info["dividendYield"]` may return unrealistic values (e.g., 89% for MSFT). The code formats with `{div_yield:.1%}` which is correct for decimal input, but yfinance sometimes returns already-percentage values. This is a data-source quirk, not a code bug. A sanity check (cap or divide) might be needed.

### No LLM Available
When no LLM keys are set and no local Ollama is running, sentiment analysis falls back to keyword heuristic. Verify by checking output contains "Heuristic keyword analysis (no LLM available)".

### Playwright Not Installed
Use `--no-scrape` flag to skip web scraping. Without it, the scanner will attempt to use Playwright and may fail if not installed.

### yfinance Rate Limiting
Scanning many tickers in quick succession may trigger yfinance rate limits. Use `--ticker` for individual scans during testing. Full watchlist scans are better for overnight/scheduled runs.

## Testing Tips
- This is a CLI-only module — no browser/GUI recording needed. Collect shell outputs as evidence.
- Use `--min-score 0` to see all opportunities regardless of quality (useful for testing).
- YAML watchlist file is at `~/.agentic-portfolio/scanner_watchlist.yaml` — can delete to reset to defaults.
- SQLite DB is at `~/.agentic-portfolio/portfolio.db` — shared with portfolio manager.
- Market data requires internet access and is subject to market hours/availability.
