# Prospective paper portfolio: proposed implementation

Status: design proposal. No experiment, recurring agent decision or simulated transaction has been activated. This is personal research software; the feature has no broker connection or real order execution.

## Purpose

Observe how an account-authenticated analyst manages a hypothetical portfolio using CoSoup's dated research over several future months. This tests the combination of supplied information, deterministic tools, agent decisions and portfolio constraints. It does not establish that a strategy will produce similar real trading returns.

Prospective observation is independent of a historical backtest. Existing 260-session data supports current screening; five years of prices is not necessary to begin a future observation period. Historical strategy evaluation would need a separate, dated-universe and information-availability design.

## Daily flow

1. The existing scheduler acquires provider-ready daily data and completes deterministic research. A missing or blocked report becomes an experiment gap; stale data never silently substitutes for a completed update.
2. A separate experiment task prepares approved dated reports, offline analytics, the hypothetical ledger and the experiment policy. The task records the actual observation cutoff, supplied artifact hashes and session coverage. Decisions can use only information supplied by that cutoff.
3. The native analyst proposes target holdings or an explicit no-change decision, with evidence references and an explanation. It may use the existing chart and screening tools. The analyst cannot choose arbitrary accounting values or directly modify the ledger.
4. A deterministic validator checks symbols, cash, position limits, price availability and the proposed changes. Accepted proposals enter a pending hypothetical execution list. Invalid or unsupported proposals remain visible without a fill.
5. A separate calculation resolves eligible pending proposals when future price data becomes available, applies supported splits, and records immutable hypothetical fills and daily valuations. This calculation needs no model invocation.

Each job is keyed by experiment, session and stage. Lease recovery, duplicate schedules and conversation replay cannot create duplicate decisions or fills. Preserve a raw decision and every rejection; do not retrospectively rewrite the result.

## Timing and hypothetical prices

The initial price convention should be deliberately simple: a decision made on a New York calendar date can first execute at the daily open of a trading session on a strictly later date. This adds a conservative delay but prevents a daily bar's opening price from preceding the decision. Never fill at the closing price that informed the decision. Display the target session and pending status immediately; resolve its open only after its daily data is acquired.

A provider's daily open is a daily-bar convention and is not certified as the official 09:30 core-session auction price. Supporting an earlier next-opening convention would require an explicit session-specific price source and proof that its timestamp follows the completed decision.

Use raw same-session prices for hypothetical cash/share accounting. Apply known splits to shares before valuation; do not apply a split adjustment twice. Missing bars, unsupported corporate actions, delisting evidence or invalid prices suspend the affected calculation and reduce disclosed coverage. No stale-price fabricated fill or assumed zero-value liquidation is allowed.

Initially publish price-only results with dividend treatment explicitly excluded for both portfolio and benchmark. A later dividend-aware variant needs matching dated corporate-action data and consistent benchmark accounting.

## Experiment policy and measurement

Proposed starter settings, subject to owner selection: USD 100,000 hypothetical cash, long-only positions, no borrowing, and explicit maximum position/count limits. Cash is an allowed outcome; the agent is not required to buy or replace a fixed number of positions. Store the policy and model/profile version with every decision. Changing the policy or analyst should create a new comparison series rather than overwrite an existing experiment.

Calculate daily hypothetical equity, cash, exposure, drawdown, turnover, and percentage change from starting equity. Show a parallel buy-and-hold SPY series starting at the same eligible hypothetical execution session, with the same price basis and cash conventions. Include a deterministic scanner-policy baseline with separately specified selection/sizing rules to distinguish an agent contribution from general market exposure.

The requested zero-fee view can be the primary display. Include a clearly labeled configurable cost/slippage sensitivity view, recalculated from the same immutable fills. Neither view claims real spread, liquidity, execution or tax modeling. A few months can reveal implementation problems and decision behavior; performance interpretation must disclose the short observation window and incomplete coverage.

## Integration and user experience

Add an experiment record, immutable decisions, pending proposals, hypothetical fills and valuation snapshots in private storage. Keep this ledger separate from the owner's personal portfolio and imports. The agent receives public research and the experiment ledger; sharing a personal portfolio continues to require its existing permission.

Reuse the existing provider-neutral analyst adapter, native explicitly resumed conversation, trusted local tools and strict structured-output validation. Add tools to inspect an experiment, explain a decision, compare its series and prepare approved charts. Codex uses the existing dedicated account login. A future Claude adapter must preserve the same tool, ledger and timing contracts and use its supported account-authenticated runtime.

The daily deterministic scan remains independent of model availability. A successful scan enqueues an eligible experiment decision through a durable dependency, rather than relying on two clocks firing in the correct order. A model failure or expired login leaves an explicit skipped decision and continues deterministic valuation. Do not automatically repeat a provider or analyst failure. Recurring analyst usage is enabled explicitly with the experiment.

Keep the main interface conversational: an experiment summary/chart appears when requested, and the user can ask about performance, holdings, gaps or a particular decision. Detailed decision/fill history is expandable. Charts are rendered from host-calculated approved datasets, not invented model points.

## Implementation sequence

1. Build private experiment persistence, immutable hypothetical accounting and meaningful timing/idempotency fixtures.
2. Add a strict analyst decision contract, constraints, native session isolation and owner-reviewed experiment configuration.
3. Connect report-completion dependencies to the existing durable scheduler, and expose performance/explanation tools in chat.
4. Start a selected experiment only after its policy, baseline, hypothetical fill convention and recurring account usage are set; verify the first complete decision-to-valuation cycle.
