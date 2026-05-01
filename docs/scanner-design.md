# Agentic Algo Trading Opportunity Scanner — Design Document

## 1. Overview

A CLI application that runs overnight (or on-demand) to scan stocks, options, and futures markets, identify trading opportunities using technical analysis and news-driven strategies, and output actionable trade ideas with clear entry/exit, risk, and stop-loss parameters. **No automated order execution** — all trades are manual.

This will be added as a new module within your existing `agentic-portfolio-manager` repo to reuse shared infrastructure (yfinance provider, LLM agent, DB layer, CLI framework).

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CLI (Typer)                          │
│  scanner run | scanner watchlist | scanner opportunities │
└────────────┬────────────────────────────────────────────┘
             │
     ┌───────▼────────┐
     │   Scheduler     │  APScheduler (cron-style overnight runs)
     └───────┬─────────┘
             │
   ┌─────────▼──────────────────────────────┐
   │         Scanner Engine                  │
   │  ┌─────────────┐  ┌──────────────────┐ │
   │  │  Technical   │  │  News/Sentiment  │ │
   │  │  Analyzer    │  │  Analyzer        │ │
   │  └──────┬───────┘  └───────┬──────────┘ │
   │         │                  │             │
   │  ┌──────▼──────────────────▼───────────┐ │
   │  │       Signal Combiner / Scorer      │ │
   │  └──────┬──────────────────────────────┘ │
   └─────────┼────────────────────────────────┘
             │
   ┌─────────▼──────────────────────────────┐
   │      Opportunity Builder                │
   │  entry / exit / stop-loss / risk calc   │
   └─────────┬──────────────────────────────┘
             │
   ┌─────────▼──────────────────────────────┐
   │      Output / Report                    │
   │  Rich table (CLI) + JSON/CSV export     │
   └────────────────────────────────────────┘
```

### Data Flow

1. **Watchlist** → tickers the user wants to track (configurable via CLI/YAML)
2. **Data Fetch** → yfinance (OHLCV, options chains, fundamentals) + Playwright scraper (Google Finance news, market movers)
3. **Technical Analysis** → pandas-ta indicators applied to each ticker
4. **News/Sentiment Analysis** → Playwright scrapes headlines → LLM (Ollama) scores sentiment and relevance
5. **Signal Combination** → weighted scoring across technical + sentiment signals
6. **Opportunity Generation** → actionable trade ideas with computed entry, exit, stop-loss, position sizing
7. **Output** → Rich CLI table + optional JSON/CSV file

---

## 3. Modules & File Structure

```
portfolio_manager/
├── scanner/
│   ├── __init__.py
│   ├── engine.py           # Main scanning orchestration
│   ├── watchlist.py         # Watchlist CRUD (YAML-backed or DB)
│   ├── technical.py         # Technical analysis strategies
│   ├── sentiment.py         # News scraping + LLM sentiment scoring
│   ├── signals.py           # Signal combination and scoring
│   ├── opportunities.py     # Opportunity model + builder (entry/exit/risk)
│   ├── scheduler.py         # APScheduler overnight cron wrapper
│   ├── scraper.py           # Playwright-based Google Finance/news scraper
│   └── report.py            # Rich tables + JSON/CSV export
├── scanner_cli.py           # Typer sub-commands for scanner
```

---

## 4. Watchlist Management

Users define tickers to scan via a YAML file (`~/.scanner_watchlist.yaml`) or CLI commands.

```yaml
# ~/.scanner_watchlist.yaml
stocks:
  - AAPL
  - MSFT
  - NVDA
  - TSLA
  - AMZN
  - META
  - GOOGL
  - SPY
  - QQQ

# Options: scanned via yfinance options chains for the above tickers
options:
  enabled: true
  min_volume: 100
  min_open_interest: 500
  dte_range: [7, 90]       # days to expiration range

# Futures proxies (ETF-based, since yfinance has limited direct futures)
futures_proxies:
  - USO     # Oil
  - GLD     # Gold
  - SLV     # Silver
  - UNG     # Natural Gas
  - TLT     # 20+ Year Treasury
  - DBA     # Agriculture
```

**CLI commands:**
```
scanner watchlist show
scanner watchlist add TICKER
scanner watchlist remove TICKER
```

---

## 5. Technical Analysis Strategies

Using **pandas-ta** (150+ indicators, no C dependencies unlike TA-Lib). Each strategy produces a signal: `BULLISH`, `BEARISH`, or `NEUTRAL` with a confidence score (0.0–1.0).

### 5.1 Strategies Implemented

| # | Strategy | Indicators Used | Horizon | Signal Logic |
|---|----------|----------------|---------|--------------|
| 1 | **EMA Crossover** | EMA(20), EMA(50), EMA(200) | Days–Weeks | Fast crosses above slow → bullish |
| 2 | **RSI Reversal** | RSI(14) | Days | RSI < 30 → oversold (bullish); RSI > 70 → overbought (bearish) |
| 3 | **MACD Momentum** | MACD(12,26,9) | Days–Weeks | MACD crosses signal line; histogram divergence |
| 4 | **Bollinger Squeeze** | BB(20,2), Keltner(20,1.5) | Days–Weeks | Squeeze release + direction = breakout signal |
| 5 | **Volume Profile** | VWAP, OBV, Volume SMA | Days | Volume surge + price breakout confirmation |
| 6 | **Support/Resistance** | Pivot Points, recent highs/lows | Weeks–Months | Price near support = potential long; near resistance = potential short |
| 7 | **ADX Trend Strength** | ADX(14), +DI, -DI | Weeks | ADX > 25 + DI cross = strong trend entry |
| 8 | **Stochastic Divergence** | Stoch(14,3,3) | Days | Price makes new low but stochastic doesn't → bullish divergence |

### 5.2 Options-Specific Signals

| Signal | Logic |
|--------|-------|
| **IV Rank/Percentile** | Current IV vs. 52-week range; high IV = sell premium, low IV = buy premium |
| **Put/Call Ratio** | Elevated PCR on a stock near support → contrarian bullish |
| **Unusual Options Activity** | Volume >> Open Interest for a specific strike → institutional interest |

---

## 6. News & Sentiment Analysis (LLM-Powered)

### 6.1 News Scraping (Playwright)

**Sources scraped via browser automation:**
- Google Finance → ticker-specific news feed (`https://www.google.com/finance/quote/TICKER:EXCHANGE`)
- Google News → broader market search (`https://news.google.com/search?q=TICKER+stock`)
- Yahoo Finance → news tab from yfinance API (no scraping needed)

**Scraper behavior:**
- Runs headless Playwright (Chromium)
- Extracts: headline, source, publish date, snippet, URL
- Deduplicates by headline similarity
- Caches results in SQLite to avoid re-scraping within 6 hours

### 6.2 LLM Sentiment Scoring (Ollama)

Each headline batch (per ticker) is sent to the local Ollama LLM with a structured prompt:

```
Analyze the following financial news headlines for {TICKER}.
For each headline, provide:
1. sentiment: bullish | bearish | neutral
2. impact: high | medium | low
3. timeframe: immediate | short-term (days) | medium-term (weeks) | long-term (months)
4. brief reasoning (1 sentence)

Then provide an overall sentiment score from -1.0 (very bearish) to +1.0 (very bullish)
and a catalyst summary.

Headlines:
{headlines}
```

**Fallback:** If Ollama is unavailable, use a simple keyword-based heuristic (upgrade/beat/surge → bullish, downgrade/miss/decline → bearish) — similar to the extractive fallback pattern in your existing portfolio manager.

### 6.3 Market-Wide Sentiment Scan

In addition to per-ticker analysis:
- Scrape Google Finance main page for "Market Trends", "Most Active", "Gainers/Losers"
- Feed market-wide context to LLM for macro sentiment assessment
- Factor this into opportunity confidence scores

---

## 7. Signal Combination & Scoring

Each ticker gets a composite **Opportunity Score** (0–100):

```
score = (
    w_tech   * technical_score    +   # default 0.50
    w_sent   * sentiment_score    +   # default 0.30
    w_volume * volume_score       +   # default 0.10
    w_options* options_flow_score     # default 0.10
)
```

Weights are configurable in `~/.scanner_config.yaml`. Only opportunities scoring above a threshold (default: 60) are surfaced.

---

## 8. Opportunity Output Format

Each opportunity is a structured record:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        📊 TRADE OPPORTUNITY: NVDA                                │
├──────────────┬───────────────────────────────────────────────────────────────────┤
│ Score        │ 82 / 100                                                         │
│ Direction    │ LONG                                                             │
│ Instrument   │ Stock (or: Call Option Jan 2025 $500 Strike)                     │
│ Strategy     │ EMA Crossover + Bullish Sentiment Catalyst                       │
│ Timeframe    │ 2–4 weeks                                                        │
├──────────────┼───────────────────────────────────────────────────────────────────┤
│ Entry Price  │ $875.50 (current) — enter on pullback to $860–$870               │
│ Target Price │ $950.00 (+8.5%)                                                  │
│ Stop Loss    │ $830.00 (-5.2%)                                                  │
│ Risk/Reward  │ 1 : 1.63                                                         │
├──────────────┼───────────────────────────────────────────────────────────────────┤
│ Risk Exposure│ Risking $45.50/share. At 100 shares = $4,550 max loss            │
│ Position Size│ Suggested: 100 shares ($87,550) for $100K portfolio              │
│              │ (4.5% portfolio risk)                                             │
├──────────────┼───────────────────────────────────────────────────────────────────┤
│ Technicals   │ EMA(20) crossed above EMA(50), RSI=58, MACD bullish crossover    │
│ Sentiment    │ +0.72 — "NVDA reports record data center revenue" (Reuters)      │
│ Catalysts    │ AI spending cycle, upcoming earnings in 3 weeks                   │
├──────────────┼───────────────────────────────────────────────────────────────────┤
│ Scanned At   │ 2026-05-01 02:00 UTC                                             │
└──────────────┴───────────────────────────────────────────────────────────────────┘
```

### Options Opportunity Example

```
│ Instrument   │ AAPL Call — Jun 2026 $200 Strike                                 │
│ Strategy     │ Low IV + Bullish RSI Reversal                                    │
│ Entry Price  │ $4.50 (premium per contract)                                     │
│ Target Price │ $8.00 (premium target when stock hits $205)                      │
│ Stop Loss    │ $2.00 (premium stop)                                             │
│ Risk/Reward  │ 1 : 1.40                                                         │
│ Risk Exposure│ Risking $250/contract (1 contract = 100 shares)                  │
│ IV Rank      │ 22nd percentile (cheap options)                                  │
│ Greeks       │ Delta: 0.45 | Theta: -0.08 | Vega: 0.12                          │
│ DTE          │ 45 days                                                          │
```

---

## 9. Overnight / Scheduled Scanning

### Using APScheduler

```python
# Default: run at 1:00 AM UTC daily (after US market close)
scanner schedule set --cron "0 1 * * *"
scanner schedule set --cron "0 1 * * 1-5"  # weekdays only

# Manual run
scanner run                    # scan entire watchlist now
scanner run --ticker AAPL      # scan single ticker
scanner run --sector tech      # scan by sector (future)
```

**How it works:**
- APScheduler runs in the foreground as a long-lived process (suitable for `tmux`, `screen`, `systemd`, or Docker)
- On each trigger: fetches data → runs analysis → writes opportunities to SQLite + prints to console
- Optional: export to JSON/CSV file in a configurable output directory

### Persistence

Opportunities are stored in SQLite (same DB as the portfolio manager) so you can:
```
scanner opportunities             # list latest scan results
scanner opportunities --date 2026-04-30
scanner opportunities --ticker NVDA
scanner opportunities --min-score 70
scanner opportunities --export csv
scanner opportunities --export json
```

---

## 10. Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python 3.10+ | Matches existing repo |
| **CLI Framework** | Typer + Rich | Already used in portfolio manager |
| **Market Data** | yfinance | Already integrated; supports OHLCV, options chains, news |
| **News Scraping** | Playwright (headless Chromium) | JavaScript-rendered Google Finance pages |
| **Technical Analysis** | pandas-ta | 150+ indicators, pure Python (no TA-Lib C deps), actively maintained |
| **LLM** | Ollama (local) | Already integrated in portfolio manager; private, free, no API key |
| **Scheduling** | APScheduler | Mature, cron-style triggers, lightweight |
| **Database** | SQLite + SQLAlchemy | Already used in portfolio manager |
| **Data Processing** | pandas + numpy | Standard for financial data |
| **Output** | Rich tables + JSON/CSV | Beautiful CLI output + machine-readable export |

### New Dependencies (additions to pyproject.toml)

```toml
"pandas-ta>=0.3.14b",
"apscheduler>=3.10.0",
"playwright>=1.40.0",
"numpy>=1.26.0",
```

---

## 11. CLI Command Tree

```
portfolio scanner run [--ticker TICKER] [--all]
    → Run the scanner now (full watchlist or single ticker)

portfolio scanner watchlist show
portfolio scanner watchlist add TICKER [TICKER...]
portfolio scanner watchlist remove TICKER

portfolio scanner opportunities [--date DATE] [--ticker TICKER] [--min-score N] [--export csv|json]
    → View/export identified opportunities

portfolio scanner schedule set --cron "CRON_EXPR"
portfolio scanner schedule show
portfolio scanner schedule start
    → Start the overnight scheduler (foreground process)

portfolio scanner config show
portfolio scanner config set KEY VALUE
    → View/modify scanner configuration (weights, thresholds, etc.)
```

---

## 12. Configuration

`~/.scanner_config.yaml`:

```yaml
# Signal weights (must sum to 1.0)
weights:
  technical: 0.50
  sentiment: 0.30
  volume: 0.10
  options_flow: 0.10

# Minimum score to surface an opportunity
min_score: 60

# Risk parameters
risk:
  max_portfolio_risk_pct: 5.0      # max % of portfolio to risk per trade
  default_stop_loss_pct: 5.0       # default stop-loss %
  portfolio_size: 100000           # assumed portfolio size for position sizing

# Scheduler
schedule:
  cron: "0 1 * * 1-5"             # 1 AM UTC, weekdays
  timezone: "UTC"

# LLM
llm:
  model: "llama3"                  # Ollama model name
  enabled: true
  fallback_to_heuristic: true      # use keyword scoring if Ollama unavailable

# Scraper
scraper:
  headless: true
  news_cache_hours: 6
  sources:
    - google_finance
    - yahoo_finance

# Output
output:
  dir: "~/.scanner_output"
  format: "json"                   # json | csv
```

---

## 13. Key Design Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| **Add to existing repo** vs. new repo | Reuses yfinance provider, Ollama client, DB layer, CLI structure. Reduces duplication. |
| **pandas-ta** vs. TA-Lib | No C compilation needed; easier install; 150+ indicators; actively maintained. |
| **Playwright** vs. requests+BeautifulSoup | Google Finance uses heavy JS rendering; Playwright handles this natively. |
| **APScheduler** vs. system cron | Cross-platform; no OS-level config; integrates with Python; supports in-process scheduling. |
| **Ollama (local LLM)** vs. OpenAI API | Free, private, no API key needed; already integrated in the repo. Can swap to OpenAI later. |
| **SQLite** vs. PostgreSQL | Lightweight; no server needed; already used; sufficient for single-user scanning. |
| **ETF proxies for futures** | yfinance doesn't have robust direct futures data; ETFs like USO/GLD track futures closely. |

---

## 14. Future Enhancements (Out of Scope for V1)

- Email/SMS/Telegram alerts when high-score opportunities are found
- Backtesting engine to validate strategies against historical data
- Direct broker API integration (Alpaca, IBKR) for one-click order placement
- Machine learning models trained on historical signal → outcome data
- Sector rotation scanner
- Earnings calendar integration
- Multi-timeframe analysis (daily + weekly + monthly confluence)

---

## 15. Open Questions for You

1. **Repo location**: Should this be added to `agentic-portfolio-manager` (recommended, reuses infrastructure) or a brand-new repo?
2. **LLM model preference**: Stick with Ollama/llama3, or would you prefer OpenAI GPT-4o / Anthropic Claude integration (requires API key)?
3. **Watchlist defaults**: Any specific tickers/sectors you want pre-loaded?
4. **Portfolio size**: What's the assumed portfolio size for position sizing calculations? (Default: $100K)
5. **Options depth**: Should options scanning cover all expirations, or just near-term (< 90 DTE)?
6. **Futures**: Are ETF proxies (USO, GLD, TLT) acceptable, or do you need actual futures contract data (would require a different data source)?
7. **Alert mechanism**: For V1, just CLI output + file export, or do you also want Slack/email notifications?
