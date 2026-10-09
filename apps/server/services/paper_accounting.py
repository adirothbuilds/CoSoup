"""Deterministic hypothetical accounting; no broker or external side effects."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import re

from ..errors import ServiceError


def number(value):
    try:
        result = Decimal(str(value))
        if isinstance(value, bool) or not result.is_finite():
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ServiceError('invalid_paper_number', 'Hypothetical accounting requires finite numeric values', 422) from None


def book(cash):
    return {'cash':str(number(cash)), 'positions':{}, 'turnover_notional':'0', 'fills':[], 'applied_splits':[]}


def targets(rows, policy, allowed):
    if not isinstance(rows, list) or len(rows)>policy['max_positions']:
        raise ServiceError('paper_position_limit', 'Proposed holdings exceed the experiment limit', 422)
    output={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'symbol','weight','reason'}:
            raise ServiceError('invalid_paper_target', 'Targets require symbol, weight and reason', 422)
        symbol=row['symbol']
        if not isinstance(symbol,str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,29}',symbol) or symbol not in allowed or symbol in output:
            raise ServiceError('paper_unapproved_symbol', 'Target must be a unique approved symbol', 422)
        weight=number(row['weight'])
        if weight<=0 or weight>number(policy['max_position_weight']) or not isinstance(row['reason'],str) or len(row['reason'])>2000:
            raise ServiceError('paper_weight_limit', 'Target exceeds a position constraint or has an invalid explanation', 422)
        output[symbol]=str(weight)
    if sum((number(w) for w in output.values()),Decimal(0))>1:
        raise ServiceError('paper_cash_limit', 'Target exposure cannot exceed available hypothetical equity', 422)
    return output


def valuation(ledger, prices):
    missing=sorted(symbol for symbol in ledger['positions'] if symbol not in prices or number(prices[symbol])<=0)
    if missing:
        return {'equity':None,'cash':ledger['cash'],'missing_symbols':missing,'quality':'partial_coverage'}
    equity=number(ledger['cash'])+sum((number(q)*number(prices[s]) for s,q in ledger['positions'].items()),Decimal(0))
    return {'equity':str(equity),'cash':ledger['cash'],'missing_symbols':[],'quality':'complete'}


def apply_splits(ledger, events, session):
    for event in events:
        if event['execution_date']!=session:
            continue
        key=':'.join(str(event[k]) for k in ['ticker','execution_date','split_from','split_to'])
        if key in ledger['applied_splits']:
            continue
        a,b=number(event['split_from']),number(event['split_to'])
        if a<=0 or b<=0:
            raise ServiceError('paper_split_invalid','Split factors must be positive')
        ratio=b/a
        symbol=event['ticker']
        if symbol in ledger['positions']:
            ledger['positions'][symbol]=str(number(ledger['positions'][symbol])*ratio)
        ledger['applied_splits'].append(key)


def rebalance(ledger, weights, prices, session, decision_id):
    if any(fill['decision_id']==decision_id for fill in ledger['fills']):
        return []
    required=set(weights)|set(ledger['positions'])
    if any(s not in prices or number(prices[s])<=0 for s in required):
        raise ServiceError('paper_execution_prices_missing','Missing original target-session prices; no hypothetical fill')
    equity=number(valuation(ledger,prices)['equity'])
    desired={s:(equity*number(w)/number(prices[s])).quantize(Decimal('0.00000001'),rounding=ROUND_DOWN) for s,w in weights.items()}
    differences={s:desired.get(s,Decimal(0))-number(ledger['positions'].get(s,0)) for s in required}
    cash=number(ledger['cash']);fills=[]
    # Compute atomically: all sells precede buys and no partial mutation on failure.
    for symbol,quantity in sorted(differences.items(),key=lambda row:(row[1]>0,row[0])):
        if not quantity:
            continue
        amount=quantity*number(prices[symbol]);cash-=amount
        if cash<0:
            raise ServiceError('paper_cash_limit','Hypothetical execution cannot borrow cash')
        fills.append({'decision_id':decision_id,'session':session,'symbol':symbol,
                      'side':'buy' if quantity>0 else 'sell','quantity':str(abs(quantity)),
                      'price':str(number(prices[symbol])),'notional':str(abs(amount)),'fees':'0'})
    ledger['cash']=str(cash)
    ledger['positions']={s:str(q) for s,q in desired.items() if q>0}
    ledger['turnover_notional']=str(number(ledger['turnover_notional'])+sum((number(f['notional']) for f in fills),Decimal(0)))
    ledger['fills'].extend(fills)
    return fills
