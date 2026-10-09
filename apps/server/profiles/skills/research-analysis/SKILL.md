---
name: research-analysis
description: Investigate screening failures, volatility, market breadth, aligned financial ratios and institutional concentration using approved deterministic research tools.
---

Run `python research_tools.py analyses` to discover approved analyses and `python research_tools.py inspect ANALYSIS_ID` to inspect measurements, operands, source dates and gaps. For screening questions, inspect the original checks and filter_evidence, then optionally run `python research_tools.py screen ANALYSIS_ID` with relevant explicit thresholds: --min-rs21 (21-session excess price change versus SPY, percent), --max-volatility (20-session annualized volatility, percent), --max-abs-pivot-atr (absolute distance from pivot, ATR units), --min-confirmed-days (0 through 5), and --limit (1 through 50). Missing values never pass a numeric filter. Explain original eligibility separately from conversational filters; the supplied observation set is bounded, not the whole universe.

Selected-symbol context can include exact original failures for a named company that disappeared from a newer candidate/watchlist. Read its saved reason and filter_evidence before claiming that failure reasons are unavailable. Do not treat a new addition to a watchlist as a new stock listing or IPO. Extra filters should explain tradeoffs, not relabel their matches as originally eligible candidates.

Use the precomputed financial series only where dates and units align. Cite filing dates and the exact authorized source_id. Unknown denominators, missing comparable periods and incomplete debt stay explicit. Holdings weights describe the full reported non-option SH subset, not total assets or current trades. Overlap requires the same reported quarter and exact security identifiers. Read market_freshness; newly synchronized filings do not refresh prices. Ask relevant follow-up questions conversationally rather than repeating every measurement.

For a visual, run `python research_tools.py list`, inspect an approved dataset, and return chart_requests. Never generate numbers, executable content, network requests, credential reads, portfolio writes or schedule changes. The tool contract is provider-neutral; the current account-authenticated backend is Codex.
