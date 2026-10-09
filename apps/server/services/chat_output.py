"""Validate untrusted analyst proposals without writing the portfolio ledger."""
from ..errors import ServiceError

FIELDS={'type','symbol','quantity','price','amount','at','fees','currency','source_text'}
TYPES={'buy','sell','opening','deposit','withdrawal','dividend','fee','split'}

def proposals(value, imports):
    if not isinstance(value,list) or len(value)>4:
        raise ServiceError('invalid_portfolio_proposal','Too many proposed document reviews')
    allowed={i['id'] for i in imports if i['status']=='awaiting_review'}; seen=set()
    for p in value:
        if not isinstance(p,dict) or set(p)!={'import_id','rows','warnings'} or p['import_id'] not in allowed or p['import_id'] in seen:
            raise ServiceError('invalid_portfolio_proposal','Proposal must reference an authorized unconfirmed document')
        seen.add(p['import_id'])
        if not isinstance(p['rows'],list) or len(p['rows'])>100 or not isinstance(p['warnings'],list) or len(p['warnings'])>20 or not all(isinstance(w,str) and len(w)<=2000 for w in p['warnings']):
            raise ServiceError('invalid_portfolio_proposal','Proposal exceeds the review bounds')
        for r in p['rows']:
            if not isinstance(r,dict) or set(r)!=FIELDS or r['type'] not in TYPES or not all(v is None or isinstance(v,str) and len(v)<=2000 for v in r.values()):
                raise ServiceError('invalid_portfolio_proposal','Proposal fields are invalid')
    return value
