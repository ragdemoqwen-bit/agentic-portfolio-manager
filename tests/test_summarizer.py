from portfolio_manager.agent.summarizer import ExtractiveSummarizer


def test_extractive_summarizer_includes_headlines():
    ctx = "\n".join(
        [
            "Portfolio daily brief — 2026-04-24",
            "Holdings:",
            "- AAPL (stock, USD): qty=10 cost=USD 150.00 price=USD 200.00 day=+2.56%",
            "",
            "Recent headlines:",
            "AAPL:",
            "- Apple beats Q2 estimates (Reuters)",
            "- Apple unveils new iPad (Bloomberg)",
        ]
    )
    out = ExtractiveSummarizer().summarize(ctx)
    assert "Apple beats Q2 estimates" in out
    assert "Apple unveils new iPad" in out
    assert "extractive" in out.lower()


def test_extractive_summarizer_handles_no_headlines():
    ctx = "Portfolio summary: no data"
    out = ExtractiveSummarizer().summarize(ctx)
    assert "No fresh headlines" in out
