import json
from pathlib import Path

from .storage import atomic_json

FILTER_LABEL = {
    'minimum_price': 'Below minimum price', 'average_share_volume': 'Insufficient average share volume',
    'average_dollar_volume': 'Insufficient average dollar volume', 'breakout': 'No close above the prior breakout window high',
    'volume_confirmation': 'Volume confirmation missing', 'relative_strength': 'Relative strength / positive price change insufficient',
    'trend': 'Trend condition failed', 'pivot_extension': 'Too far above breakout pivot',
    'sma50_extension': 'Too far above SMA50',
}
STATUS_LABEL = {'complete': 'Screen completed', 'partial_coverage': 'Screen completed with partial coverage',
                'blocked_provider': 'Provider access blocked', 'blocked_benchmarks': 'Benchmark data blocked',
                'blocked_quality': 'Data quality blocked', 'blocked_error': 'Screen blocked by an error'}


def safe_text(value):
    return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ').replace('<', '&lt;').replace('>', '&gt;')


def table(rows):
    lines = ['| Symbol | Close | Breakout pivot | Relative volume | Excess vs SPY | Distance from pivot |',
             '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {safe_text(r['symbol'])} | ${r['close']:.2f} | ${r['pivot']:.2f} | {r['volume_ratio']:.2f}x | {r['rs_excess']:.1%} | {r['pivot_extension']:.1%} |")
    return lines


def research_markdown(research):
    lines = []
    for symbol, item in research.items():
        lines += [f'### Research: {safe_text(symbol)}', '', f"Review status: {safe_text(item.get('status'))}", '', 'Sourced facts:', '']
        for fact in item.get('facts', []):
            lines.append(f"- {safe_text(fact['text'])} — Source: {safe_text(fact['source'])}; checked: {safe_text(fact.get('checked_at', ''))}")
            if fact.get('linked_primary_source_retrieved') is False:
                lines.append(f"  Provider record retrieved from {safe_text(fact.get('data_retrieved_from', 'unavailable'))}; linked primary page was not independently retrieved.")
        lines += ['', 'Hypotheses to investigate (not established facts or proven causes of the breakout):', '']
        lines += [f'- {safe_text(x)}' for x in item.get('hypotheses', [])]
        lines += ['', 'Missing information / further verification required:', '']
        lines += [f'- {safe_text(x)}' for x in item.get('missing', [])]
        lines += ['']
    return lines


def daily_markdown(report):
    coverage = report.get('coverage', {})
    rules = report.get('rules', {})
    liquidity_days = rules.get('liquidity_days', 50)
    near_distance = rules.get('near_pivot_distance', .03)
    lines = ['# Stock research — daily screen', '',
             f"**Status:** {STATUS_LABEL.get(report['status'], report['status'])}",
             f"**Data date:** {report['data_date']} · Generated at {report['run_at_utc']}",
             '**Source:** Massive · Prices and share volume are adjusted together for splits through the data date', '',
             '## Coverage and quality', '',
             f"- Provider listings: {coverage.get('provider_listings', 0):,}; selected common shares / ADRs: {coverage.get('selected_equities', 0):,}.",
             f"- Evaluated: {coverage.get('evaluated', 0):,}; valid histories: {coverage.get('valid_histories', 0):,}; insufficient history: {coverage.get('insufficient_history', 0):,}; data errors: {coverage.get('data_errors', 0):,}.",
             f"- Window: {coverage.get('first_session', 'unavailable')} through {report['data_date']}; cached sessions: {coverage.get('cached_sessions', 0)} / {coverage.get('required_sessions', 0)}.",
             f"- SPY and IWM benchmark observations: {safe_text(report.get('benchmarks', {}))}",
             '- No sector or market-cap filter. Coverage is limited to the documented US exchanges; OTC is excluded.',
             '- Companies delisted before the listing date are not covered; this is not a historical strategy backtest.', '']
    for error in report.get('errors', []):
        lines.append(f'- Error: {safe_text(error)}')
    if report['status'].startswith('blocked'):
        lines += ['', '**Opportunity availability cannot be inferred. A data failure is not a zero-candidate result.**', '']
    else:
        lines += ['## Candidates passing all rules', '']
        if report.get('candidates'):
            lines += table(report['candidates'])
        else:
            lines.append('No candidates passed every rule among the verified histories evaluated. The list is never filled to an arbitrary count.')
        lines += ['', '## Near-breakout watchlist', '',
                  f'A separate watchlist within {near_distance:.0%} below the pivot. Breakout and volume confirmation may still be missing.', '']
        lines += table(report.get('near_breakouts', [])) if report.get('near_breakouts') else ['No securities meet the current watchlist rules.']
    lines += ['', '## Filter reasons', '']
    for name, count in sorted(report.get('filter_counts', {}).items(), key=lambda x: (-x[1], x[0])):
        lines.append(f'- {FILTER_LABEL.get(name, name)}: {count:,}. A stock can fail multiple rules.')
    lines += ['', '## Liquidity and smaller companies', '',
              f'Liquidity averages use the prior {liquidity_days} sessions, excluding the current session. With the default $10 million threshold, a $5 stock trading 500,000 shares daily generates only approximately $2.5 million and fails the dollar-volume test. At that price, approximately 2 million shares per day are needed. Many smaller companies fail this requirement even without a market-cap floor.', '']
    for item in report.get('liquidity_examples', []):
        cap = item.get('market_cap')
        size = f"Market cap ${cap:,.0f} ({item.get('cap_class')})" if cap is not None else 'Market cap unverified; no claim that this is a small company'
        lines.append(f"- {safe_text(item['symbol'])} ({safe_text(item.get('name', ''))}): {item['avg_volume_50']:,.0f} shares, ${item['avg_dollar_volume_50']:,.0f} daily; {size}. Liquidity failures: {', '.join(FILTER_LABEL.get(k,k) for k in item['liquidity_failures'])}.")
    lines += ['', '## Research on leading candidates', '']
    if report.get('research_run'):
        lines += [f"Company research: {safe_text(report['research_run']['status'])}; requested: {safe_text(report['research_run']['requested'])}.", '']
    lines += research_markdown(report.get('research', {})) or ['No company research was produced in this run; a catalyst must not be inferred without a source.']
    lines += ['', '## Limitations', '']
    lines += [f'- {safe_text(w)}' for w in report.get('warnings', [])]
    lines += ['- Personal research signals only. No broker connection or trade execution.',
              '- Raw data and reports remain outside the repository. Review usage terms before redistribution, including derived reports.', '']
    return '\n'.join(lines)


def write_daily(directory, report, results):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(directory / 'report.json', report)
    atomic_json(directory / 'all_results.json.gz', results)
    (directory / 'report.md').write_text(daily_markdown(report), encoding='utf-8')


def weekly_markdown(report):
    lines = ['# Stock research — weekly summary', '', f"**Data date:** {report.get('data_date', 'unavailable')}",
             f"**Status:** {safe_text(report['status'])}", '',
             f"Daily reports in this week: {report['daily_run_count']}; prior signals monitored: {len(report['signals'])}.",
             'There is no simulated portfolio or assumed entry/exit price. Observed price changes are signal observations, excluding dividends, fees and execution.', '',
             '## Signal monitoring', '', '| Symbol | Signal date | Status | Observed price change | Maximum close drawdown | Closes below pivot |',
             '|---|---|---|---:|---:|---:|']
    for s in report['signals']:
        change = f"{s['price_change']:.1%}" if s.get('price_change') is not None else 'unavailable'
        drawdown = f"{s['close_drawdown']:.1%}" if s.get('close_drawdown') is not None else 'unavailable'
        lines.append(f"| {safe_text(s['symbol'])} | {s['signal_date']} | {safe_text(s['monitor_status'])} | {change} | {drawdown} | {s.get('closes_below_pivot', 'unavailable')} |")
    if not report['signals']:
        lines += ['', 'No prior verified signals are available in the cache. Historical performance must not be invented.']
    lines += ['', '## Daily outcomes and errors', '']
    for d in report['daily_runs']:
        lines.append(f"- {d['data_date']}: {safe_text(d['status'])}; {d['candidate_count']} candidates; {d.get('data_errors', 0)} data errors.")
    lines += [f'- {safe_text(e)}' for e in report.get('errors', [])]
    lines += ['', 'A failed signal means a close below the original split-adjusted breakout pivot. This is a monitoring definition, not a trading execution rule.', '']
    return '\n'.join(lines)
