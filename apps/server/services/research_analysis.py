"""Prepare bounded offline measurements for authorized research conversations."""
import math

from stock_scanner.calendar import calendar, expected_session
from stock_scanner.market import assess
from stock_scanner.rules import Rules

from ..errors import ServiceError
from .market import matrix_for
from .research_tools import analysis_catalog, catalog


def prepare(packet, storage, settings):
    packet['research_tools_version'] = 1
    packet['market_freshness'] = []
    price_charts = []
    slots = 4
    for report in packet['reports']:
        if report['mode'] not in {'live', 'historical_snapshot'}:
            continue
        end, data = report['data_date'], report['data']
        latest = min(packet['end_date'], expected_session(settlement_minutes=settings.settlement_minutes))
        latest = calendar().date_to_session(latest, direction='previous').date().isoformat()
        packet['market_freshness'].append({'source_id': report['id'], 'market_data_through': end,
                                           'latest_completed_session_at_context': latest,
                                           'older_than_latest_completed_session': end < latest,
                                           'note': 'SEC sync dates and analysis dates do not refresh market prices.'})
        selected = {}
        for group in ('candidates', 'near_breakouts'):
            for row in data.get(group, []):
                selected.setdefault(row['symbol'], row)
        selected = dict(list(selected.items())[:slots])
        slots -= len(selected)
        if not selected:
            continue
        symbols = list(dict.fromkeys([*selected, 'SPY']))
        try:
            rules = Rules(**data.get('rules', {}))
            with storage.reader():
                sessions, matrix, errors, *_ = matrix_for(storage, end, symbols)
            benchmark = matrix[symbols.index('SPY')]
            for symbol, row in selected.items():
                bars = matrix[symbols.index(symbol)]
                measured = assess(symbol, bars, benchmark, sessions, rules, errors.get(symbol))
                if not measured['data_valid']:
                    packet.setdefault('tool_gaps', []).append({'symbol': symbol, 'code': measured['reason']})
                    continue
                if any(k in row and not math.isclose(row[k], measured[k], rel_tol=1e-6, abs_tol=1e-8) for k in ('close', 'pivot')):
                    packet.setdefault('tool_gaps', []).append({'symbol': symbol, 'code': 'cached_basis_mismatch'})
                    continue
                row.update(analytics=measured['analytics'], filter_evidence=measured['filter_evidence'])
                points = [{'label': day, 'value': float(values[3])} for day, values in zip(sessions[-60:], bars[-60:])]
                price_charts.append({'id': report['id']+':price:'+symbol, 'source_id': report['id'],
                                     'title': symbol+' · cached daily close', 'kind': 'line', 'unit': 'USD', 'points': points,
                                     'note': f'Split-adjusted cached closes through {end}. Excludes dividends; not trading returns.'})
        except ServiceError as error:
            packet.setdefault('tool_gaps', []).append({'source_id': report['id'], 'code': error.code})
        except (ValueError, TypeError):
            packet.setdefault('tool_gaps', []).append({'source_id': report['id'], 'code': 'invalid_saved_rules_or_measurements'})
    packet['research_analyses'] = analysis_catalog(packet)
    packet['chart_datasets'] = price_charts+catalog(packet)
    return packet
