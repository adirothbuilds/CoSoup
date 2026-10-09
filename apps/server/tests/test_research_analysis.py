import contextlib
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from stock_scanner.calendar import sessions_ending
from apps.server.config import Settings
from apps.server.services.research_analysis import prepare
from apps.server.services.research_tools import analysis_catalog, catalog, screen
from apps.server.persistence.models import Report
from apps.server.services.agent_context import add_screening_context, context_packet, mentioned_symbols
from test_server import ServerCase


class ResearchAnalysisTests(unittest.TestCase):
    def test_financial_acronyms_do_not_select_unrequested_tickers(self):
        self.assertEqual(mentioned_symbols('Compare AVT and ARW using ATR, EPS, FCF and SEC facts'),['AVT','ARW'])
        self.assertEqual(mentioned_symbols('Compare $ATR and ticker SEC using ATR and SEC facts'),['ATR','SEC'])

    def test_numeric_filters_preserve_eligibility_and_exclude_unknowns(self):
        analysis={'kind':'screening','source_id':'report','data':{'data_date':'2026-10-02','note':'Bounded list', 'rows':[
            {'symbol':'ABC','eligible':False,'analytics':{'realized_volatility20_pct':30,'pivot_distance_atr':-1,
             'volume_confirmed_days5':2,'relative_strength_windows':{'21':{'excess_pct':5}}}},
            {'symbol':'UNKNOWN','eligible':True}]}}
        result=screen(analysis,{'min_rs21':0,'max_volatility':40,'max_abs_pivot_atr':2,'min_confirmed_days':2})
        self.assertEqual(result['matched'],1);self.assertEqual(result['missing_required_measurements'],1)
        self.assertFalse(result['rows'][0]['eligible'])
        self.assertEqual(screen(analysis,{'max_abs_pivot_atr':.5})['matched'],0)
        for filters in ({'max_volatility':float('nan')},{'unknown':1},{'min_confirmed_days':6}):
            with self.assertRaises(ValueError):screen(analysis,filters)

    def test_chart_percentages_use_canonical_scanner_fields(self):
        packet={'reports':[{'id':'source','mode':'live','data_date':'2026-10-02','data':{'candidates':[
            {'symbol':'ABC','volume_ratio':2,'pivot_extension':.02,'rs_excess':.1}]}}]}
        datasets=catalog(packet)
        self.assertEqual(next(d for d in datasets if d['id']=='source:pivot_extension')['points'][0]['value'],2)
        self.assertEqual(next(d for d in datasets if d['id']=='source:rs_excess')['points'][0]['value'],10)

    def test_legacy_measurements_batch_cache_reads_and_disclose_stale_prices(self):
        symbols=['ABC','DEF','SPY']
        sessions=sessions_ending('2026-10-02')
        data=np.tile([100.,101.,99.,100.,1000000.],(3,260,1))
        packet={'end_date':'2026-10-08','reports':[{'id':'report','mode':'live','data_date':'2026-10-02',
            'data':{'candidates':[{'symbol':'ABC','close':100,'pivot':101},{'symbol':'DEF','close':100,'pivot':101}]}}]}
        class Storage:
            def reader(self):return contextlib.nullcontext()
        with patch('apps.server.services.research_analysis.matrix_for',return_value=(sessions,data,{},[],None,None)) as cache:
            prepare(packet,Storage(),Settings())
        self.assertEqual(cache.call_count,1);self.assertEqual(cache.call_args.args[-1],symbols)
        self.assertTrue(packet['market_freshness'][0]['older_than_latest_completed_session'])
        self.assertEqual(len([d for d in packet['chart_datasets'] if ':price:' in d['id']]),2)
        self.assertEqual(packet['reports'][0]['data']['candidates'][0]['analytics']['atr14'],2)
        self.assertFalse(any(a['kind']=='breadth' for a in packet['research_analyses']))

    def test_watchlist_charts_remain_available_without_eligible_candidates(self):
        packet={'reports':[{'id':'source','mode':'live','data_date':'2026-10-07','data':{'candidates':[],
            'near_breakouts':[{'symbol':'WATCH','eligible':False,'analytics':{'realized_volatility20_pct':35}}]}}]}
        datasets=catalog(packet)
        chart=next(d for d in datasets if d['id']=='source:near_breakouts:realized_volatility20_pct')
        self.assertEqual(chart['points'],[{'label':'WATCH','value':35}])
        self.assertIn('not eligible candidates',chart['note'])

    def test_cache_mismatch_or_missing_history_cannot_supply_measurements(self):
        sessions=sessions_ending('2026-10-02');data=np.tile([100.,101.,99.,100.,1000000.],(2,260,1))
        class Storage:
            def reader(self):return contextlib.nullcontext()
        for price,missing in [(999,False),(100,True)]:
            packet={'end_date':'2026-10-08','reports':[{'id':'report','mode':'live','data_date':'2026-10-02',
                'data':{'candidates':[{'symbol':'ABC','close':price,'pivot':101}]}}]}
            values=data.copy()
            if missing:values[0,-1]=np.nan
            with patch('apps.server.services.research_analysis.matrix_for',return_value=(sessions,values,{},[],None,None)):
                prepare(packet,Storage(),Settings())
            self.assertTrue(packet['tool_gaps']);self.assertNotIn('analytics',packet['reports'][0]['data']['candidates'][0])
            self.assertEqual(packet['chart_datasets'],[])

    def test_standalone_tools_require_approved_ids_and_return_json(self):
        path=Path(__file__).resolve().parents[1]/'services/research_tools.py'
        with tempfile.TemporaryDirectory() as directory:
            packet={'chart_datasets':[],'research_analyses':[{'id':'approved:screening','source_id':'approved',
                    'kind':'screening','title':'Fixture','data':{'data_date':'2026-10-02','rows':[],'note':'Bounded'}}]}
            Path(directory,'inputs.json').write_text(json.dumps(packet))
            result=subprocess.run([sys.executable,str(path),'screen','approved:screening','--max-volatility','40'],cwd=directory,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['matched'],0)
            bad=subprocess.run([sys.executable,str(path),'inspect','../../private'],cwd=directory,capture_output=True,text=True)
            self.assertNotEqual(bad.returncode,0);self.assertNotIn('private',bad.stderr)


class ScreeningContextTests(ServerCase):
    def seed(self, owner='owner', mismatch=False):
        directory=self.storage.path(f'reports/diagnostics-{owner}-{int(mismatch)}');directory.mkdir(parents=True)
        body=directory/'report.json';body.write_text(json.dumps({'candidates':[], 'near_breakouts':[]}))
        detailed=directory/'all_results.json.gz'
        with gzip.open(detailed,'wt') as out:
            json.dump([{'symbol':'AVT','data_date':'2026-10-07','eligible':False,'data_valid':True,
                        'failed_filters':['breakout'],'filter_evidence':{'breakout':{'actual':100,'threshold':101}}},
                       {'symbol':'ARW','data_date':'2026-10-09','eligible':True}],out)
        with self.database.session() as db:
            original=self.storage.register(db,'owner',body,'reports')
            detail=self.storage.register(db,owner,detailed,'reports',{'session':'2026-10-06' if mismatch else '2026-10-07'})
            r=Report(owner_id='owner',job_id=f'diagnostics-{owner}-{int(mismatch)}',data_date='2026-10-07',mode='live',quality='partial_coverage',
                     artifact_id=original.id,markdown_id=original.id,summary={'details_artifact_id':detail.id})
            db.add(r);db.flush();return r.id

    def packet(self, identity):
        with self.database.session() as db:
            return context_packet(db,self.storage,self.settings,'owner',{'task_type':'research_chat',
                'end_date':'2026-10-08','report_ids':[identity],'prompt':'Why did AVT and ARW disappear?'})

    def test_selected_symbols_get_exact_saved_failures_without_future_rows(self):
        packet=self.packet(self.seed())
        rows=packet['reports'][0]['data']['screening_context']
        self.assertEqual([r['symbol'] for r in rows],['AVT'])
        self.assertEqual(rows[0]['failed_filters'],['breakout'])
        self.assertFalse(rows[0]['eligible'])

    def test_detailed_artifact_must_belong_to_owner_and_match_report_session(self):
        for owner,mismatch in [('other',False),('owner',True)]:
            with self.subTest(owner=owner,mismatch=mismatch):
                packet=self.packet(self.seed(owner,mismatch))
                self.assertNotIn('screening_context',packet['reports'][0]['data'])
                self.assertTrue(packet['tool_gaps'])

    def test_compressed_diagnostics_have_a_decompressed_budget(self):
        identity=self.seed()
        packet={'reports':[{'id':identity,'data':{'candidates':[]}}]}
        settings=self.settings.model_copy(update={'limits':self.settings.limits.model_copy(update={'agent_reservation_bytes':128})})
        with self.database.session() as db:
            row=db.get(Report,identity)
            add_screening_context(db,self.storage,settings,'owner',[row],packet,'AVT')
        self.assertEqual(packet['tool_gaps'][0]['code'],'diagnostics_limit')
        self.assertNotIn('screening_context',packet['reports'][0]['data'])
