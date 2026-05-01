"""Scanner engine — orchestrates data fetch, analysis, and opportunity generation."""

from __future__ import annotations

import logging
import os

import pandas as pd

from .opportunities import (
    Direction,
    InstrumentType,
    Opportunity,
    OptionDetail,
    build_opportunity,
)
from .options_analysis import OptionsSignal, analyze_options
from .scraper import scrape_news_for_ticker
from .sentiment import analyze_sentiment
from .signals import combine_signals
from .technical import SignalDirection, TechnicalSignal, run_technicals
from .watchlist import Watchlist

log = logging.getLogger(__name__)


class ScannerEngine:
    def __init__(
        self,
        watchlist: Watchlist | None = None,
        min_score: float = 60.0,
        portfolio_size: float = 100_000.0,
        max_risk_pct: float = 5.0,
        scrape_news: bool = True,
    ) -> None:
        self.watchlist = watchlist or Watchlist.load()
        self.min_score = float(os.environ.get("SCANNER_MIN_SCORE", str(min_score)))
        self.portfolio_size = float(os.environ.get("SCANNER_PORTFOLIO_SIZE", str(portfolio_size)))
        self.max_risk_pct = float(os.environ.get("SCANNER_MAX_RISK_PCT", str(max_risk_pct)))
        self.scrape_news = scrape_news

    def _fetch_ohlcv(self, ticker: str, period: str = "6mo") -> pd.DataFrame | None:
        import yfinance as yf

        try:
            df = yf.download(ticker, period=period, progress=False)
            if df.empty:
                return None
            # Flatten multi-level columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
        except Exception as exc:
            log.warning("Failed to fetch OHLCV for %s: %s", ticker, exc)
            return None

    def _get_yahoo_headlines(self, ticker: str) -> list[str]:
        import yfinance as yf

        try:
            news = yf.Ticker(ticker).news or []
            headlines: list[str] = []
            for entry in news[:10]:
                content = entry.get("content") if isinstance(entry, dict) else None
                src = content if isinstance(content, dict) else entry
                title = src.get("title", "")
                if title:
                    headlines.append(title)
            return headlines
        except Exception:
            return []

    def _volume_score(self, df: pd.DataFrame) -> float:
        """Compute a simple volume score (0–100) based on recent vs average volume."""
        if "Volume" not in df.columns or len(df) < 20:
            return 50.0
        avg = df["Volume"].rolling(20).mean().iloc[-1]
        latest = df["Volume"].iloc[-1]
        if pd.isna(avg) or avg == 0:
            return 50.0
        ratio = latest / avg
        return min(100.0, max(0.0, 50.0 + (ratio - 1.0) * 30))

    def _determine_timeframe(self, signals: list[TechnicalSignal]) -> str:
        """Heuristic timeframe based on which signals fired."""
        names = {s.name for s in signals if s.direction != SignalDirection.NEUTRAL}
        if names & {"EMA Crossover", "ADX Trend"}:
            return "2-6 weeks"
        if names & {"RSI Reversal", "Stochastic"}:
            return "3-10 days"
        if names & {"Bollinger Squeeze"}:
            return "1-3 weeks"
        return "1-4 weeks"

    def _target_stop_pcts(self, signals: list[TechnicalSignal]) -> tuple[float, float]:
        """Pick target/stop percentages based on signal strength."""
        high_conf = [s for s in signals if s.confidence > 0.6 and s.direction != SignalDirection.NEUTRAL]
        if len(high_conf) >= 3:
            return 10.0, 4.0
        if len(high_conf) >= 1:
            return 7.0, 5.0
        return 5.0, 5.0

    def scan_ticker(self, ticker: str) -> list[Opportunity]:
        """Run the full analysis pipeline for a single ticker."""
        df = self._fetch_ohlcv(ticker)
        if df is None or len(df) < 30:
            log.info("Skipping %s — insufficient data", ticker)
            return []

        current_price = float(df["Close"].iloc[-1])

        # Technical analysis
        tech_signals = run_technicals(df)

        # News + sentiment
        scraped_articles = scrape_news_for_ticker(ticker) if self.scrape_news else []
        yahoo_headlines = self._get_yahoo_headlines(ticker)
        sentiment = analyze_sentiment(ticker, scraped_articles, yahoo_headlines)

        # Volume score
        vol_score = self._volume_score(df)

        # Options analysis (if enabled)
        options_signal: OptionsSignal | None = None
        opt_score = 50.0
        if self.watchlist.options.enabled:
            try:
                options_signal = analyze_options(ticker, current_price)
                opt_score = options_signal.score
            except Exception as exc:
                log.debug("Options analysis skipped for %s: %s", ticker, exc)

        # Combine signals
        composite = combine_signals(ticker, tech_signals, sentiment, vol_score, opt_score)

        opportunities: list[Opportunity] = []

        # Stock opportunity
        if composite.score >= self.min_score and composite.direction != SignalDirection.NEUTRAL:
            target_pct, stop_pct = self._target_stop_pcts(tech_signals)
            timeframe = self._determine_timeframe(tech_signals)
            tech_summary = "; ".join(
                f"{s.name}: {s.detail}" for s in tech_signals if s.direction != SignalDirection.NEUTRAL
            )[:200]
            sent_summary = (
                f"{sentiment.overall_score:+.2f} — {sentiment.catalyst_summary}"
                if sentiment else "N/A"
            )

            direction = Direction.LONG if composite.direction == SignalDirection.BULLISH else Direction.SHORT
            opp = build_opportunity(
                ticker=ticker,
                current_price=current_price,
                direction=direction,
                instrument=InstrumentType.STOCK,
                strategy=composite.strategy_label,
                timeframe=timeframe,
                target_pct=target_pct,
                stop_pct=stop_pct,
                technical_summary=tech_summary,
                sentiment_summary=sent_summary,
                catalysts=sentiment.catalyst_summary if sentiment else "",
                score=composite.score,
                portfolio_size=self.portfolio_size,
                max_risk_pct=self.max_risk_pct,
                wheel_candidate=options_signal.wheel_candidate if options_signal else False,
                wheel_notes=options_signal.wheel_notes if options_signal else "",
            )
            opportunities.append(opp)

        # Options opportunities
        if (
            options_signal
            and self.watchlist.options.enabled
            and composite.direction != SignalDirection.NEUTRAL
        ):
            direction = Direction.LONG if composite.direction == SignalDirection.BULLISH else Direction.SHORT

            # Near-term options from unusual activity
            for ua in options_signal.unusual_activity[:2]:
                opt_type = InstrumentType.CALL_OPTION if ua["type"] == "call" else InstrumentType.PUT_OPTION
                premium = ua.get("last_price") or (current_price * 0.03)
                iv_val = ua.get("implied_volatility")
                detail = OptionDetail(
                    strike=ua["strike"],
                    expiration="nearest",
                    dte=30,
                    premium=premium,
                    iv=iv_val,
                    iv_rank=options_signal.iv_rank,
                    open_interest=ua.get("open_interest"),
                    volume=ua.get("volume"),
                )
                target_pct, stop_pct = 80.0, 50.0
                score_bump = min(15, ua.get("ratio", 1) * 3)
                opp = build_opportunity(
                    ticker=ticker,
                    current_price=current_price,
                    direction=direction,
                    instrument=opt_type,
                    strategy=f"Unusual Activity ({ua['type'].title()} Vol={ua['volume']})",
                    timeframe="1-4 weeks",
                    target_pct=target_pct,
                    stop_pct=stop_pct,
                    technical_summary=f"Vol/OI ratio: {ua['ratio']}x",
                    sentiment_summary=sentiment.catalyst_summary if sentiment else "",
                    catalysts="Unusual options flow detected",
                    score=min(100, composite.score + score_bump),
                    portfolio_size=self.portfolio_size,
                    max_risk_pct=self.max_risk_pct,
                    option_detail=detail,
                )
                opportunities.append(opp)

            # LEAPS opportunities
            if options_signal.leaps_available and self.watchlist.options.include_leaps:
                for leap in options_signal.leaps_candidates[:2]:
                    detail = OptionDetail(
                        strike=leap["strike"],
                        expiration=leap["expiration"],
                        dte=leap["dte"],
                        premium=leap.get("last_price"),
                        iv=leap.get("iv"),
                        iv_rank=options_signal.iv_rank,
                        volume=leap.get("volume"),
                        open_interest=leap.get("open_interest"),
                        is_leap=True,
                    )
                    opp = build_opportunity(
                        ticker=ticker,
                        current_price=current_price,
                        direction=Direction.LONG,
                        instrument=InstrumentType.CALL_OPTION,
                        strategy=f"LEAPS {leap['expiration']} ${leap['strike']}",
                        timeframe=f"{leap['dte']} days",
                        target_pct=100.0,
                        stop_pct=50.0,
                        technical_summary="Long-dated call for leveraged upside",
                        sentiment_summary=sentiment.catalyst_summary if sentiment else "",
                        catalysts="LEAPS — reduced theta decay, long-term thesis",
                        score=max(composite.score - 5, 50),
                        portfolio_size=self.portfolio_size,
                        max_risk_pct=self.max_risk_pct,
                        option_detail=detail,
                    )
                    opportunities.append(opp)

        return opportunities

    def scan_all(self) -> list[Opportunity]:
        """Scan every ticker in the watchlist."""
        all_opps: list[Opportunity] = []
        for ticker in self.watchlist.stocks:
            log.info("Scanning %s...", ticker)
            try:
                opps = self.scan_ticker(ticker)
                all_opps.extend(opps)
            except Exception as exc:
                log.error("Scan failed for %s: %s", ticker, exc)
        return sorted(all_opps, key=lambda o: o.score, reverse=True)
