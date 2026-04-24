# agentic-portfolio-manager

A simple, investor-friendly command-line + TUI portfolio manager, powered by an
agentic daily-brief loop.

- Multi-asset: **stocks, ETFs, mutual funds, bonds, options**
- Multi-market: **USA, Singapore (SGX), India (NSE/BSE)**
- Data: `yfinance` (primary) + `google-finance-scraper` (secondary)
- Agentic daily brief via a **local Ollama** model (with extractive fallback)
- Storage: SQLite (no server to run)
- Interfaces: `typer` CLI + `textual` TUI. No web UI.

## Install

```bash
pip install -e ".[dev]"
```

Optional (for the daily brief): install [Ollama](https://ollama.ai) and pull a
small model:

```bash
ollama pull llama3.2
```

## Quick start

```bash
# Add some holdings (market is inferred from the suffix)
portfolio add AAPL --qty 10 --cost 150        # USA stock
portfolio add D05.SI --qty 100 --cost 33.50   # DBS, Singapore
portfolio add RELIANCE.NS --qty 20 --cost 2800 # Reliance, India NSE
portfolio add VOO --qty 5 --cost 420 --kind etf
portfolio add AAPL240119C00150000 --qty 1 --cost 12.5 --kind option

# See your positions and current value in each native currency + USD
portfolio list
portfolio value

# Refresh quotes / fetch news / produce the daily agentic brief
portfolio refresh
portfolio news
portfolio brief

# Launch the TUI
portfolio tui
```

## Configuration

Environment variables (all optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORTFOLIO_DB` | `~/.agentic-portfolio/portfolio.db` | SQLite path |
| `PORTFOLIO_BASE_CCY` | `USD` | Reporting currency for totals |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.2` | Model used for summarization |

## Design

See [`portfolio_manager/`](portfolio_manager/). The package is split into:

- `providers/` — pluggable market-data backends (yfinance, google-finance-scraper)
- `assets/` — per-asset-class logic (stock, etf, mutual_fund, bond, option)
- `markets.py` — ticker ↔ market/currency normalization
- `agent/` — the Ollama-backed daily brief agent (with extractive fallback)
- `cli.py` — Typer-based CLI entry point
- `tui.py` — Textual TUI

## License

MIT
