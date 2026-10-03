from collections import defaultdict, deque
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..errors import ServiceError
from ..persistence.models import Artifact, Portfolio, Transaction
from .jobs import owned, utc

ZERO = Decimal("0")


def transaction(db, owner, portfolio_id, values, provenance=None, correction_of=None):
    portfolio = owned(db, Portfolio, portfolio_id, owner, lock=True)
    if values["currency"] != portfolio.currency:
        raise ServiceError("currency_not_supported", "Mixed-currency accounting requires a sourced FX adapter", 422)
    data = values.copy()
    data["at"] = datetime.fromisoformat(data["at"]) if isinstance(data["at"], str) else data["at"]
    for key in ["quantity", "price", "amount", "fees"]:
        if data.get(key) is not None:
            data[key] = Decimal(str(data[key]))
    row = Transaction(owner_id=owner, portfolio_id=portfolio_id, provenance=provenance or {}, correction_of=correction_of, **data)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        raise ServiceError("duplicate_transaction", "External transaction reference already exists") from None
    # Validate the entire effective history: inserting an older sale cannot silently
    # invalidate a later position, and unknown opening basis is never fabricated.
    ledger(db, owner, portfolio_id)
    return row


def ledger(db, owner, portfolio_id, as_of=None):
    portfolio = owned(db, Portfolio, portfolio_id, owner)
    q = select(Transaction).where(Transaction.owner_id == owner, Transaction.portfolio_id == portfolio_id,
                                  Transaction.superseded.is_(False)).order_by(Transaction.at, Transaction.created_at, Transaction.id)
    if as_of:
        q = q.where(Transaction.at <= as_of)
    rows = list(db.scalars(q))
    lots = defaultdict(deque)
    cash, realized, incomplete = ZERO, ZERO, False
    for r in rows:
        qty, price, amount, fees = r.quantity, r.price, r.amount, r.fees or ZERO
        if r.type in {"buy", "opening"}:
            basis = (qty*price+fees) if price is not None else None
            lots[r.symbol].append([qty, basis])
            if r.type == "buy":
                cash -= qty*price+fees
        elif r.type == "sell":
            remaining, removed, unknown = qty, ZERO, False
            while remaining > ZERO:
                if not lots[r.symbol]:
                    raise ServiceError("negative_position", "Sale exceeds available holdings; short positions are unsupported", 422)
                lot_qty, basis = lots[r.symbol][0]
                take = min(remaining, lot_qty)
                if basis is None:
                    unknown = True
                    next_basis = None
                else:
                    removed += basis*take/lot_qty
                    next_basis = basis*(lot_qty-take)/lot_qty
                remaining -= take
                if take == lot_qty:
                    lots[r.symbol].popleft()
                else:
                    lots[r.symbol][0] = [lot_qty-take, next_basis]
            proceeds = qty*price-fees
            cash += proceeds
            if unknown:
                incomplete = True
            else:
                realized += proceeds-removed
        elif r.type == "split":
            factor = qty
            for lot in lots[r.symbol]:
                lot[0] *= factor
        elif r.type in {"deposit", "dividend"}:
            cash += amount-fees
        elif r.type in {"withdrawal", "fee"}:
            cash -= amount+fees
    positions = []
    for symbol, entries in sorted(lots.items()):
        if not entries:
            continue
        quantity = sum((x[0] for x in entries), ZERO)
        known = all(x[1] is not None for x in entries)
        positions.append({"symbol": symbol, "quantity": str(quantity),
                          "cost_basis": str(sum((x[1] for x in entries), ZERO)) if known else None,
                          "basis_known": known})
    return {"portfolio_id": portfolio_id, "currency": portfolio.currency, "cash": str(cash),
            "cash_note": "Reconstructed from supplied ledger only; missing opening cash can make this incomplete",
            "realized_pnl": None if incomplete else str(realized), "realized_pnl_complete": not incomplete,
            "positions": positions, "accounting": "FIFO; no tax reporting or simulated scanner returns"}


def analyze(context):
    from stock_scanner.calendar import expected_session
    from stock_scanner.storage import read_json
    from .reports import publish, published
    existing = published(context, "portfolio")
    if existing:
        return existing
    end = context.job.payload.get("data_date") or expected_session(settlement_minutes=context.settings.settlement_minutes)
    latest = expected_session(settlement_minutes=context.settings.settlement_minutes)
    if end > latest:
        raise ServiceError("invalid_date", "Portfolio valuation cannot use a future session", 422)
    from stock_scanner.calendar import calendar
    import pandas as pd
    if not calendar().is_session(end):
        raise ServiceError("invalid_date", "Valuation date must be a completed trading session", 422)
    cutoff = calendar().session_close(pd.Timestamp(end)).to_pydatetime()
    with context.database.session() as db:
        result = ledger(db, context.job.owner_id, context.job.payload["portfolio_id"], cutoff)
        transactions = list(db.scalars(select(Transaction).where(Transaction.owner_id == context.job.owner_id,
                Transaction.portfolio_id == context.job.payload["portfolio_id"], Transaction.superseded.is_(False), Transaction.at <= cutoff)))
    path = context.storage.path(f"market/raw/grouped/{end}.json.gz")
    if not path.is_file():
        raise ServiceError("restore_required", "Market-date prices are unavailable; ingest or restore before resuming")
    snapshot = read_json(path)
    if snapshot.get("session") != end or snapshot.get("adjusted") is not False or snapshot.get("data", {}).get("adjusted") is not False:
        raise ServiceError("invalid_market_basis", "Portfolio prices require unadjusted bars for the requested session")
    rows, duplicate = {}, set()
    for r in snapshot["data"]["results"]:
        if r.get("T") in rows:
            duplicate.add(r["T"])
        rows[r.get("T")] = r
    # Detect known splits absent from the supplied journal. Cached corporate-action
    # history can be incomplete; it is evidence, not a broker reconciliation.
    from zoneinfo import ZoneInfo
    zone = ZoneInfo("America/New_York")
    actions, seen = [], set()
    for file in context.storage.path("market/raw/splits").glob("*.json.gz"):
        for action in read_json(file).get("results", []):
            identity = (action.get("ticker"), action.get("execution_date"))
            if identity not in seen:
                seen.add(identity)
                actions.append(action)
    action_gaps = []
    for action in actions:
        symbol, day = action.get("ticker"), action.get("execution_date")
        if not day or day > end:
            continue
        held_before = any(r.symbol == symbol and r.type in {"buy", "opening"} and utc(r.at).astimezone(zone).date().isoformat() < day for r in transactions)
        recorded = [r for r in transactions if r.symbol == symbol and r.type == "split" and utc(r.at).astimezone(zone).date().isoformat() == day]
        try:
            ratio = Decimal(str(action["split_to"]))/Decimal(str(action["split_from"]))
            matches = len(recorded) == 1 and recorded[0].quantity == ratio
        except (KeyError, ArithmeticError):
            matches = False
        if held_before and not matches:
            action_gaps.append({"symbol": symbol, "date": day, "code": "split_requires_reconciliation"})
    missing, total = [], ZERO
    for position in result["positions"]:
        bar = rows.get(position["symbol"])
        import numpy as np
        from stock_scanner.market import quality
        try:
            values = [bar[k] for k in ["o", "h", "l", "c", "v"]]
            valid = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
            valid = valid and not quality(np.array([values]), [end], 1)
            valid = valid and datetime.fromtimestamp(bar["t"]/1000, zone).date().isoformat() == end
        except (KeyError, TypeError, ValueError, OSError, OverflowError):
            valid = False
        if not valid or position["symbol"] in duplicate or any(g["symbol"] == position["symbol"] for g in action_gaps):
            missing.append(position["symbol"])
            position.update(market_value=None, unrealized_pnl=None)
            continue
        price = Decimal(str(bar["c"]))
        value = Decimal(position["quantity"])*price
        total += value
        basis = position["cost_basis"]
        position.update(price=str(price), price_date=end, market_value=str(value),
                        unrealized_pnl=str(value-Decimal(basis)) if basis is not None else None)
    result.update(status="partial_coverage" if missing else "complete", data_date=end, valuation_cutoff=cutoff.isoformat(),
                  missing_or_unreconciled_positions=missing, corporate_action_gaps=action_gaps, known_equity_value=str(total),
                  reconciliation_note="Holdings, cash and FIFO depend on a complete supplied journal; cached split checks are not a broker reconciliation or complete corporate-action history",
                  note="Actual ledger and unadjusted same-date closing prices; no order execution, fees inferred or invented basis")
    for position in result["positions"]:
        position["known_equity_weight"] = str(Decimal(position["market_value"])/total) if position["market_value"] is not None and total else None
    md = f"# Portfolio analysis: {end}\n\nQuality: {result['status']}. Currency: {result['currency']}.\n\nFIFO calculations use supplied transactions only; missing basis remains unknown.\n\n"
    for p in result["positions"]:
        md += f"- {p['symbol']}: {p['quantity']} shares; value {p['market_value']}; basis {p['cost_basis']}.\n"
    return publish(context, end, "portfolio", result, md)
