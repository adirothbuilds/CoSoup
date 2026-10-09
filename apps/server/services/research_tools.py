"""Provider-neutral offline research tools over explicitly authorized evidence."""
import json
import math


def analysis_catalog(packet):
    from stock_scanner.financial_analytics import financial_analysis, institutional_analysis, institutional_overlap
    analyses = []
    def add(source, key, kind, title, data):
        analyses.append({'id': source+':'+key, 'source_id': source, 'kind': kind, 'title': title, 'data': data})
    for report in packet['reports']:
        source, data = report['id'], report['data']
        if report['mode'] in {'live', 'historical_snapshot'}:
            rows = {}
            for group in ('candidates', 'near_breakouts', 'screening_review', 'screening_context'):
                for row in data.get(group, []):
                    rows.setdefault(row['symbol'], row)
            add(source, 'screening', 'screening', 'Explain and filter dated screening observations',
                {'data_date': report['data_date'], 'quality': report.get('quality'), 'coverage': {k:v for k,v in data.get('coverage', {}).items() if k!='daily_bars'},
                 'rows': list(rows.values()), 'rules': data.get('rules', {}),
                 'note': 'Bounded candidate, near-breakout, filter-review and selected-symbol context lists only; not the entire evaluated universe. Context may include failed or invalid histories. Extra filters never change the original eligibility. Missing measurements cannot pass a requested numeric filter.'})
            if data.get('market_breadth'):
                add(source, 'breadth', 'breadth', 'Breadth among verified market histories', data['market_breadth'])
        elif report['mode'] == 'sec_research':
            for company in data.get('companies', []):
                add(source, 'financial:'+company['symbol'], 'financial', company['symbol']+' · financial quality',
                    financial_analysis(company, report['data_date']))
            managers = [institutional_analysis(m) for m in data.get('managers', [])]
            for manager in managers:
                add(source, 'holdings:'+manager['cik'], 'holdings', manager['name']+' · reported concentration', manager)
            if managers:
                add(source, 'overlap', 'overlap', 'Common reported institutional positions', institutional_overlap(managers))
    return analyses


def catalog(packet):
    datasets = []
    def add(source, key, title, points, unit='', kind='bar', note=''):
        points = [{'label':str(p['label'])[:80], 'value':float(p['value'])} for p in points
                  if isinstance(p.get('value'), (int,float)) and not isinstance(p['value'],bool) and math.isfinite(p['value'])][:260]
        if points:
            datasets.append({'id':f'{source}:{key}', 'source_id':source, 'title':title, 'kind':kind,
                             'unit':unit, 'points':points, 'note':note})
    for r in packet['reports']:
        data=r['data']; source=r['id']
        if r['mode'] in {'live','historical_snapshot'}:
            for field,label,unit in [('volume_ratio','Screening volume ratio','×'),('pivot_extension','Distance above breakout pivot','%'),('rs_excess','Excess price change versus SPY','%')]:
                add(source,field,label,[{'label':c['symbol'],'value':c[field]*(100 if unit=='%' else 1)} for c in data.get('candidates',[]) if isinstance(c.get(field),(int,float))][:20],unit,note=f"Scan data: {r['data_date']}. Screening observations, not returns.")
            for field,label,unit in [('atr14_pct','ATR / close','%'),('realized_volatility20_pct','Annualized recent price volatility','%'),('pivot_distance_atr','Distance from pivot in ATR units','ATR'),('volume_confirmed_days5','Volume-confirmed sessions out of five','sessions')]:
                add(source,field,label,[{'label':c['symbol'],'value':c.get('analytics',{}).get(field)} for c in data.get('candidates',[])][:20],unit,
                    note=f"Computed from verified cached daily bars through {r['data_date']}; descriptive measurements, not forecasts.")
                for group,scope in [('near_breakouts','Near-breakout watchlist'),('screening_review','Filter review'),('screening_context','Selected symbol context')]:
                    rows=data.get(group,[])[:12]
                    add(source,group+':'+field,scope+' · '+label,
                        [{'label':c['symbol'],'value':c.get('analytics',{}).get(field)} for c in rows],unit,
                        note=f"First {len(rows)} supplied {scope.lower()} observations through {r['data_date']}; these are not eligible candidates. Unknown measurements omitted; not the full evaluated universe.")
            if data.get('market_breadth'):
                breadth=data['market_breadth']
                add(source,'breadth','Breadth among verified histories',[{'label':k.replace('_',' '),'value':v['pct']} for k,v in breadth['measures'].items()], '%',note=breadth['note'])
        if r['mode']=='sec_research':
            for company in data.get('companies',[]):
                for label in dict.fromkeys(m['label'] for m in company.get('metrics',[])):
                    rows=[m for m in company['metrics'] if m['label']==label]
                    first=rows[0]
                    def days(m):
                        from datetime import date
                        return (date.fromisoformat(m['period_end'])-date.fromisoformat(m['period_start'])).days if m.get('period_start') else 0
                    comparable=[m for m in rows if m['unit']==first['unit'] and abs(days(m)-days(first))<=7]
                    add(source,company['symbol']+':'+label,company['symbol']+' · '+label,
                        [{'label':m['period_end'],'value':m['value']} for m in sorted(comparable,key=lambda m:m['period_end'])],first['unit'],'line',
                        'Reported periods of comparable duration only; retain filing dates in the explanation.')
            for manager in data.get('managers',[]):
                snapshot=next(iter(manager.get('snapshots',[])),None)
                if snapshot:
                    add(source,'13f:'+manager['cik'],manager['name']+' · reported 13F holdings',
                        [{'label':h['issuer']+(' · '+h['put_call'] if h.get('put_call') else ''),'value':h['value_usd']} for h in snapshot['holdings'][:12]],'USD',
                        note=f"Quarter end {snapshot['period_end']}; filed {snapshot['filing_date']}. Not total assets or live trades.")
    for analysis in packet.get('research_analyses', []):
        data, source = analysis['data'], analysis['source_id']
        if analysis['kind']=='financial':
            groups={}
            from datetime import date
            for row in data['series']:
                duration=(date.fromisoformat(row['period_end'])-date.fromisoformat(row['period_start'])).days if row.get('period_start') else 0
                band='instant' if not row.get('period_start') else 'quarter' if 70<=duration<=110 else 'six-month YTD' if 145<=duration<=205 else 'nine-month YTD' if 235<=duration<=300 else 'annual' if 330<=duration<=380 else None
                if band:
                    groups.setdefault((row['label'],row['unit'],band),[]).append(row)
            for (label,unit,band),rows in groups.items():
                add(source,'derived:'+data['symbol']+':'+label+':'+band,data['symbol']+' · '+label+' · '+band,
                    [{'label':v['period_end'],'value':v['value']} for v in sorted(rows,key=lambda r:r['period_end'])],unit,'line',
                    note='Derived from matching reported periods. '+data['method'])
        elif analysis['kind']=='holdings' and data['snapshots']:
            snapshot=data['snapshots'][0]
            add(source,'weights:'+data['cik'],data['name']+' · reported equity weights',
                [{'label':h['issuer'],'value':h['weight_pct']} for h in snapshot['positions'][:12]],'%',note=f"Quarter end {snapshot['period_end']}; filed {snapshot['filing_date']}. "+data['note'])
    if packet.get('portfolio'):
        p=packet['portfolio']
        add(p['portfolio_id'],'basis','Recorded cost basis',[{'label':r['symbol'],'value':float(r['cost_basis'])} for r in p['positions'] if r.get('basis_known')],
            'USD',note='Known supplied cost basis only; not current market value. Unknown basis is excluded.')
    return datasets[:160]


def screen(analysis, filters, limit=20):
    """Filter an approved bounded observation set without changing saved signals."""
    if analysis['kind'] != 'screening':
        raise ValueError('Choose an approved screening analysis')
    valid={'min_rs21','max_volatility','max_abs_pivot_atr','min_confirmed_days'}
    if set(filters)-valid or not 1<=limit<=50:
        raise ValueError('Unknown filter or invalid result limit')
    for key,value in filters.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Filters require finite numeric thresholds')
        if key!='min_rs21' and value<0 or key=='min_confirmed_days' and (value>5 or int(value)!=value):
            raise ValueError('Filter threshold is outside its supported range')
    matched, unavailable= [], 0
    for row in analysis['data']['rows']:
        metrics=row.get('analytics', {})
        values={'min_rs21':metrics.get('relative_strength_windows',{}).get('21',{}).get('excess_pct'),
                'max_volatility':metrics.get('realized_volatility20_pct'),
                'max_abs_pivot_atr':metrics.get('pivot_distance_atr'),
                'min_confirmed_days':metrics.get('volume_confirmed_days5')}
        if any(values[k] is None for k in filters):
            unavailable+=1; continue
        if all(values[k]>=v if k.startswith('min_') else abs(values[k])<=v for k,v in filters.items()):
            matched.append(row)
    return {'source_id':analysis['source_id'],'data_date':analysis['data']['data_date'],
            'filters':filters,'observations':len(analysis['data']['rows']), 'matched':len(matched),
            'missing_required_measurements':unavailable,'returned':min(limit,len(matched)),
            'rows':matched[:limit], 'note':analysis['data']['note']}


def render(requests, datasets):
    from ..errors import ServiceError
    if not isinstance(requests,list) or len(requests)>4:
        raise ServiceError('invalid_chart_tool','At most four chart tool calls are allowed')
    lookup={d['id']:d for d in datasets}; result=[]
    for call in requests:
        if not isinstance(call,dict) or set(call)!={'dataset_id','title'} or call['dataset_id'] not in lookup or not isinstance(call['title'],str) or len(call['title'])>160:
            raise ServiceError('invalid_chart_tool','Chart tool must reference an authorized dataset')
        result.append({**lookup[call['dataset_id']], 'title':call['title'] or lookup[call['dataset_id']]['title']})
    return result


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description='Inspect, compare, filter and chart authorized local evidence without network access')
    parser.add_argument('action',choices=['list','chart','analyses','inspect','screen']);parser.add_argument('dataset_id',nargs='?')
    parser.add_argument('--min-rs21',type=float);parser.add_argument('--max-volatility',type=float)
    parser.add_argument('--max-abs-pivot-atr',type=float);parser.add_argument('--min-confirmed-days',type=int)
    parser.add_argument('--limit',type=int,default=20)
    args=parser.parse_args();packet=json.loads(Path('inputs.json').read_text());datasets=packet.get('chart_datasets',[])
    if args.action!='screen' and (args.limit!=20 or any(getattr(args,k) is not None for k in ('min_rs21','max_volatility','max_abs_pivot_atr','min_confirmed_days'))):
        parser.error('Numeric filters apply only to screen')
    if args.action=='list':
        value=[{k:d[k] for k in ['id','title','unit','note']} for d in datasets]
    elif args.action=='chart':
        value=next((d for d in datasets if d['id']==args.dataset_id),None)
        if value is None:parser.error('Dataset is outside the approved context')
    elif args.action=='analyses':
        value=[{k:d[k] for k in ['id','source_id','kind','title']} for d in packet.get('research_analyses',[])]
    else:
        value=next((d for d in packet.get('research_analyses',[]) if d['id']==args.dataset_id),None)
        if value is None:parser.error('Analysis is outside the approved context')
        if args.action=='screen':
            filters={k:getattr(args,k) for k in ('min_rs21','max_volatility','max_abs_pivot_atr','min_confirmed_days') if getattr(args,k) is not None}
            try:value=screen(value,filters,args.limit)
            except ValueError as error:parser.error(str(error))
    print(json.dumps(value,allow_nan=False))

if __name__=='__main__':main()
