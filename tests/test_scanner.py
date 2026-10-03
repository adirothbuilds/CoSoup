import io
import json
import tempfile
import unittest
import urllib.error
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from stock_scanner.calendar import expected_session, next_run, sessions_ending
from stock_scanner.cli import scheduled
from stock_scanner.delivery import DeliveryError, prepare
from stock_scanner.market import assess, classify_universe, load_market, quality, split_events
from stock_scanner.provider import Client, ProviderError, ScopedRedirects, ensure_grouped
from stock_scanner.reporting import daily_markdown
from stock_scanner.research import Researcher, filing_source
from stock_scanner.rules import Rules
from stock_scanner.signals import observations, previous_signals, record_signals, weekly
from stock_scanner.storage import atomic_json, read_json, state_directory
from stock_scanner.workflow import daily


def fixtures():
    sessions = sessions_ending('2026-10-02', 260)
    c = np.linspace(50, 90, len(sessions)); c[-1] = 92
    stock = np.column_stack((c-.2, c+.2, c-.5, c, np.full(260, 1_000_000.)))
    stock[-1, 4] = 2_000_000
    bc = np.linspace(100, 110, len(sessions))
    benchmark = np.column_stack((bc, bc+1, bc-1, bc, np.full(260, 10_000_000.)))
    return sessions, stock, benchmark


class CalendarTests(unittest.TestCase):
    def test_regular_close_buffer(self):
        self.assertEqual(expected_session('2026-10-02T20:29:00Z'), '2026-10-01')
        self.assertEqual(expected_session('2026-10-02T20:30:00Z'), '2026-10-02')

    def test_weekend_holiday_and_good_friday(self):
        self.assertEqual(expected_session('2026-10-04T21:00:00Z'), '2026-10-02')
        self.assertEqual(expected_session('2026-07-03T21:00:00Z'), '2026-07-02')
        self.assertEqual(expected_session('2026-04-03T21:00:00Z'), '2026-04-02')

    def test_early_close(self):
        self.assertEqual(expected_session('2026-11-27T18:29:00Z'), '2026-11-25')
        self.assertEqual(expected_session('2026-11-27T18:30:00Z'), '2026-11-27')

    def test_dst_and_next_due(self):
        self.assertEqual(next_run('2026-11-02T20:00:00Z')['run_at_utc'], '2026-11-02T21:30:00+00:00')
        self.assertEqual(next_run('2026-11-27T17:00:00Z')['run_at_utc'], '2026-11-27T18:30:00+00:00')

    def test_exact_260_sessions_and_timezone_required(self):
        self.assertEqual(len(sessions_ending('2026-10-02', 260)), 260)
        self.assertEqual(sessions_ending('2026-10-02', 260)[0], '2025-09-22')
        with self.assertRaises(ValueError): expected_session('2026-10-02T21:00:00')


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.sessions, self.stock, self.benchmark = fixtures()

    def result(self, **kwargs):
        return assess('TEST', self.stock, self.benchmark, self.sessions, Rules(), **kwargs)

    def test_pass_and_no_current_day_in_pivot_or_average(self):
        self.stock[-1, 1] = 999
        result = self.result()
        self.assertTrue(result['eligible'])
        self.assertEqual(result['volume_ratio'], 2)
        self.assertAlmostEqual(result['pivot'], self.stock[-2, 1])
        self.assertAlmostEqual(result['avg_volume_50'], 1_000_000)

    def test_price_volume_and_dollar_filters_separate(self):
        self.stock[:, :4] *= .1
        result = self.result()
        self.assertLess(result['avg_dollar_volume_50'], 10_000_000)
        self.assertIn('average_dollar_volume', result['failed_filters'])
        self.assertNotIn('average_share_volume', result['failed_filters'])
        self.stock[:, 4] = 100
        self.assertIn('average_share_volume', self.result()['failed_filters'])

    def test_extension_rejects(self):
        self.stock[-1, 3] = 110; self.stock[-1, 1] = 111
        result = self.result()
        self.assertFalse(result['eligible'])
        self.assertIn('pivot_extension', result['failed_filters'])

    def test_near_breakout_is_not_candidate(self):
        self.stock[-1, :4] = [89, 90, 88, 89.8]
        self.stock[-1, 4] = 1_000_000
        result = self.result()
        self.assertFalse(result['eligible'])
        self.assertTrue(result['near_breakout'])
        self.assertIn('breakout', result['failed_filters'])
        self.assertIn('volume_confirmation', result['failed_filters'])

    def test_benchmark_alignment_and_strength(self):
        self.benchmark[-1, :4] = [200, 201, 199, 200]
        self.assertIn('relative_strength', self.result()['failed_filters'])
        self.benchmark[-10] = np.nan
        self.assertEqual(self.result()['reason'], 'invalid_benchmark')

    def test_invalid_ohlc_nan_infinity_and_negative_volume(self):
        original = self.stock.copy()
        for column, value in [(1, 1), (4, -1), (3, np.nan), (3, np.inf), (3, 0)]:
            self.stock = original.copy(); self.stock[-1, column] = value
            self.assertFalse(self.result()['data_valid'])

    def test_missing_short_stale_and_internal_gap(self):
        original = self.stock.copy()
        self.stock[:] = np.nan
        self.assertEqual(self.result()['reason'], 'missing_data')
        self.stock = original.copy(); self.stock[:-100] = np.nan
        self.assertEqual(self.result()['reason'], 'insufficient_history')
        self.stock = original.copy(); self.stock[-1] = np.nan
        self.assertEqual(self.result()['reason'], 'stale_data')
        self.assertEqual(self.result()['last_bar_date'],self.sessions[-2])
        self.stock = original.copy(); self.stock[-10] = np.nan
        self.assertEqual(self.result()['reason'], 'missing_sessions')

    def test_minimum_history_can_exclude_prelisting_days(self):
        self.stock[:40] = np.nan
        self.assertTrue(self.result()['eligible'])

    def test_rules_validation(self):
        for kwargs in [{'min_history': 100}, {'rs_days': 500}, {'liquidity_days': 0}, {'min_price': float('nan')}, {'research_limit': 50}, {'rs_days': 3.5}]:
            with self.assertRaises(ValueError): Rules(**kwargs)


class MarketTests(unittest.TestCase):
    def test_classification_all_common_types_and_exclusions(self):
        rows = [{'ticker': str(i), 'type': type_, 'primary_exchange': 'XNAS', 'active': True, 'market': 'stocks', 'locale': 'us'} for i, type_ in enumerate(['CS','ADRC','OS','NYRS','ETF','PFD','WARRANT','UNIT','FUND'])]
        selected, excluded = classify_universe({'results':rows})
        self.assertEqual(len(selected), 4); self.assertEqual(sum(excluded.values()), 5)
        rows[0]['primary_exchange'] = None
        selected, excluded = classify_universe({'results': rows})
        self.assertEqual(excluded['outside_supported_us_exchanges'], 1)

    def test_duplicate_listing_is_failure(self):
        row = {'ticker':'T','type':'CS','primary_exchange':'XNYS','active':True,'market':'stocks','locale':'us'}
        with self.assertRaises(ValueError): classify_universe({'results':[row,row]})

    def test_provider_common_type_cannot_override_fund_or_unit_name(self):
        rows = [{'ticker':str(i),'name':name,'type':'CS','primary_exchange':'XNYS','active':True,'market':'stocks','locale':'us'}
                for i,name in enumerate(['Actual Company Common Stock','Closed-End Income Fund','Partnership Common Units','Company Preferred Shares','Real Estate Investment Trust Common Stock','Infrastructure, LP','Resource Partners L.P.','Realty Associates Limited Partnership'])]
        selected, excluded = classify_universe({'results':rows})
        self.assertEqual([r['name'] for r in selected], ['Actual Company Common Stock','Real Estate Investment Trust Common Stock'])
        self.assertEqual(excluded['ineligible_security_name_despite_common_type'],6)

    def test_forward_and_reverse_split_preserve_dollar_volume(self):
        sessions = ['2026-09-30','2026-10-01','2026-10-02']
        from datetime import datetime
        from zoneinfo import ZoneInfo
        with tempfile.TemporaryDirectory() as d:
            state = Path(d)
            for day in sessions:
                before = day < '2026-10-01'
                rows = [{'T':'F','o':100 if before else 50,'h':100 if before else 50,'l':100 if before else 50,'c':100 if before else 50,'v':1000 if before else 2000},
                        {'T':'R','o':1 if before else 10,'h':1 if before else 10,'l':1 if before else 10,'c':1 if before else 10,'v':1000 if before else 100}]
                for row in rows: row['t'] = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('America/New_York')).timestamp()*1000
                atomic_json(state/'raw'/'grouped'/(day+'.json.gz'),{'session':day,'adjusted':False,'data':{'adjusted':False,'results':rows}})
            split = {'results':[{'ticker':'F','execution_date':'2026-10-01','split_from':1,'split_to':2},
                                {'ticker':'R','execution_date':'2026-10-01','split_from':10,'split_to':1}]}
            matrix, errors, _, _ = load_market(state,sessions,['F','R'],split)
            self.assertFalse(errors)
            np.testing.assert_allclose(matrix[0,:,3],50); np.testing.assert_allclose(matrix[0,:,4],2000)
            np.testing.assert_allclose(matrix[1,:,3],10); np.testing.assert_allclose(matrix[1,:,4],100)
            self.assertEqual(matrix[0,0,3]*matrix[0,0,4],100*1000)

    def test_invalid_and_ambiguous_split_rejected(self):
        _, errors = split_events({'results':[{'ticker':'T','execution_date':'2026-10-01','split_from':0,'split_to':1}]})
        self.assertEqual(errors['T'],'invalid_split_event')
        _, errors = split_events({'results':[{'ticker':'T','execution_date':'2026-10-01','split_from':1,'split_to':2}, {'ticker':'T','execution_date':'2026-10-01','split_from':1,'split_to':3}]})
        self.assertEqual(errors['T'],'ambiguous_split_events')


class FakeClock:
    def __init__(self): self.now = 1_000_000.0
    def time(self): return self.now
    def sleep(self, seconds): self.now += seconds


class ProviderTests(unittest.TestCase):
    def test_connection_blocker_keeps_exact_reason_without_secret(self):
        with tempfile.TemporaryDirectory() as d:
            def opener(request,timeout):raise urllib.error.URLError('Tunnel connection failed: 403 Forbidden private-value')
            with self.assertRaises(ProviderError) as ctx:Client(Path(d),'private-value',opener).get('/test')
            self.assertIn('Tunnel connection failed: 403 Forbidden',str(ctx.exception));self.assertNotIn('private-value',str(ctx.exception))
    def test_reflected_credential_cannot_enter_cache_payload(self):
        with tempfile.TemporaryDirectory() as d:
            client=Client(Path(d),'private-value',lambda request,timeout:io.BytesIO(b'{"results":[{"apiKey":"private-value","url":"https://api.massive.com/a?apiKey=private-value"}]}'))
            data=client.get('/test')
            self.assertNotIn('private-value',json.dumps(data));self.assertNotIn('apiKey',data['results'][0])
    def test_redirect_cannot_forward_authorization_outside_provider(self):
        from urllib.request import Request
        req = Request('https://api.massive.com/test',headers={'Authorization':'Bearer fake'})
        for url in ['https://other.example/a','http://api.massive.com/a']:
            with self.assertRaises(ProviderError): ScopedRedirects().redirect_request(req,None,302,'Found',{},url)

    def test_persistent_rate_limit_across_clients(self):
        with tempfile.TemporaryDirectory() as d:
            state, clock, calls = Path(d), FakeClock(), []
            def opener(request, timeout):
                calls.append(clock.now)
                self.assertNotIn('secret', request.full_url)
                return io.BytesIO(b'{"status":"OK","results":[]}')
            for i in range(11):
                client = Client(state,'secret',opener,clock.time,clock.sleep)
                client.get('/v3/reference/tickers')
            for stamp in calls:
                self.assertLessEqual(sum(stamp-60 < other <= stamp for other in calls),5)
            self.assertTrue(all(b-a >= 13 for a,b in zip(calls,calls[1:])))

    def test_http_failure_is_exact_redacted_and_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []
            def opener(request, timeout):
                calls.append(1)
                raise urllib.error.HTTPError(request.full_url,403,'Forbidden',{},io.BytesIO(b'{"status":"ERROR","error":"secret rejected"}'))
            with self.assertRaises(ProviderError) as ctx: Client(Path(d),'secret',opener).get('/test')
            self.assertEqual(ctx.exception.status,403); self.assertNotIn('secret',str(ctx.exception)); self.assertEqual(len(calls),1)

    def test_cooldown_stops_next_process(self):
        with tempfile.TemporaryDirectory() as d:
            clock = FakeClock(); calls=[]
            def opener(request, timeout):
                calls.append(1)
                raise urllib.error.HTTPError(request.full_url,429,'Too Many Requests',{'Retry-After':'120'},io.BytesIO(b'{}'))
            for _ in range(2):
                with self.assertRaises(ProviderError): Client(Path(d),'secret',opener,clock.time,clock.sleep).get('/test')
            self.assertEqual(len(calls),1)

    def test_never_forward_key_to_pagination_other_host(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def opener(request, timeout):
                calls.append(1); return io.BytesIO(b'{"results":[],"next_url":"https://evil.example/a"}')
            with self.assertRaises(ProviderError): Client(Path(d),'secret',opener).pages('/test')
            self.assertEqual(len(calls),1)

    def test_resume_fetches_only_missing_and_replaces_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as d:
            class FakeClient:
                state = Path(d)
                calls = []
                def get(self, path, params):
                    self.calls.append(path)
                    return {'adjusted':False,'results':[{'T':'T'}]}
            client=FakeClient()
            ensure_grouped(client,['2026-10-01'],progress=lambda *a,**k:None)
            ensure_grouped(client,['2026-10-01','2026-10-02'],progress=lambda *a,**k:None)
            self.assertEqual(len(client.calls),2)
            (client.state/'raw'/'grouped'/'2026-10-02.json.gz').write_bytes(b'corrupt')
            ensure_grouped(client,['2026-10-02'],progress=lambda *a,**k:None)
            self.assertEqual(len(client.calls),3)


class WorkflowTests(unittest.TestCase):
    def test_blocked_provider_is_reported_not_zero_opportunities(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('stock_scanner.workflow.universe',side_effect=ProviderError(403,'/v3/reference/tickers','Not entitled')), patch.dict('os.environ',{'MASSIVE_API_KEY':'fake'}):
                directory, report=daily(Path(d),Rules(),now='2026-10-02T21:00:00Z')
            self.assertEqual(report['status'],'blocked_provider'); self.assertFalse(report['candidates'])
            self.assertIn('A data failure is not', (directory/'report.md').read_text())
            self.assertEqual(read_json(directory/'report.json')['errors'][0]['http_status'],403)

    def test_benchmark_failure_prevents_evaluation(self):
        sessions,stock,bench=fixtures()
        listing={'as_of':sessions[-1],'retrieved_at':'test','results':[{'ticker':'T','type':'CS','primary_exchange':'XNAS','active':True,'market':'stocks','locale':'us'}]}
        matrix=np.array([bench.copy(),bench.copy(),stock]) # IWM, SPY, T
        matrix[0,-1]=np.nan
        with tempfile.TemporaryDirectory() as d, patch('stock_scanner.workflow.read_json',side_effect=[listing,{'first':sessions[0],'last':sessions[-1],'results':[]}]), patch('stock_scanner.workflow.load_market',return_value=(matrix,{},[],defaultdict(list))):
            _,report=daily(Path(d),Rules(),now='2026-10-02T21:00:00Z',offline=True)
            self.assertEqual(report['status'],'blocked_benchmarks'); self.assertEqual(report['candidates'],[])

    def test_full_evaluation_does_not_force_number_and_insufficient_history_is_visible(self):
        sessions,stock,bench=fixtures()
        rows=[{'ticker':t,'type':'CS','primary_exchange':'XNAS','active':True,'market':'stocks','locale':'us'} for t in ['T','IPO']]
        ipo=stock.copy();ipo[:-50]=np.nan
        matrix=np.array([ipo,bench,bench,stock]) # IPO, IWM, SPY, T
        with tempfile.TemporaryDirectory() as d, patch('stock_scanner.workflow.read_json',side_effect=[{'as_of':sessions[-1],'retrieved_at':'test','results':rows},{'first':sessions[0],'last':sessions[-1],'results':[]}]), patch('stock_scanner.workflow.load_market',return_value=(matrix,{},[],defaultdict(list))):
            _,report=daily(Path(d),Rules(),now='2026-10-02T21:00:00Z',offline=True)
            self.assertEqual(report['status'],'complete');self.assertEqual(len(report['candidates']),1)
            self.assertEqual(report['coverage']['insufficient_history'],1)
            self.assertEqual(len(previous_signals(Path(d))),1)

    def test_weekly_without_daily_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            _, report=weekly(Path(d),'2026-10-02T21:00:00Z')
            self.assertEqual(report['status'],'blocked_missing_current_daily')
            self.assertTrue(report['missing_daily_sessions'])


class ObservationTests(unittest.TestCase):
    def test_revised_signal_price_is_not_silently_used_for_performance(self):
        bars=np.array([[10.03,10.03,10.03,10.03,1],[11,11,11,11,1]])
        signal={'symbol':'T','signal_date':'2026-10-01','rules_id':'r','original':{'close':10,'pivot':9}}
        result=observations([signal],np.array([bars]),['T'],['2026-10-01','2026-10-02'],defaultdict(list),{})[0]
        self.assertEqual(result['monitor_status'],'unavailable');self.assertIsNone(result['price_change'])
        self.assertEqual(result['error'],'signal_price_revised_or_corporate_action_mismatch')
    def test_prior_failure_recovery_and_drawdown_are_price_observations(self):
        bars=np.array([[10,11,9,10,1],[8,9,7,8,1],[11,12,10,11,1]],dtype=float)
        signal={'symbol':'T','signal_date':'2026-09-30','rules_id':'r','original':{'close':10,'pivot':9}}
        result=observations([signal],np.array([bars]),['T'],['2026-09-30','2026-10-01','2026-10-02'],defaultdict(list),{})[0]
        self.assertEqual(result['monitor_status'],'recovered_after_failure');self.assertEqual(result['closes_below_pivot'],1)
        self.assertAlmostEqual(result['price_change'],.1);self.assertAlmostEqual(result['close_drawdown'],-.2)
        self.assertNotIn('trading_return',result)

    def test_split_after_signal_rebases_original_pivot(self):
        bars=np.array([[5,5,5,5,2],[5.5,5.5,5.5,5.5,2]],dtype=float)
        signal={'symbol':'T','signal_date':'2026-10-01','rules_id':'r','original':{'close':10,'pivot':9}}
        result=observations([signal],np.array([bars]),['T'],['2026-10-01','2026-10-02'],defaultdict(list,{'T':[('2026-10-02',2)]}),{})[0]
        self.assertAlmostEqual(result['price_change'],.1);self.assertAlmostEqual(result['original_pivot_on_current_basis'],4.5)

    def test_registry_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            report={'rules':{'a':1},'data_date':'2026-10-02','run_at_utc':'test','candidates':[{'symbol':'T','close':10,'pivot':9}]}
            record_signals(Path(d),report);record_signals(Path(d),report)
            self.assertEqual(len(previous_signals(Path(d))),1)


class MailAndResearchTests(unittest.TestCase):
    def test_filing_citation_points_to_public_sec_index(self):
        result=filing_source('https://api.polygon.io/v1/reference/sec/filings/0000320193-26-000020','fallback','0000320193')
        self.assertEqual(result,'https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/0000320193-26-000020-index.html')

    def test_filing_agent_prefix_does_not_replace_issuer_cik(self):
        result=filing_source('https://api.polygon.io/v1/reference/sec/filings/0001104659-26-091983','fallback','0000007536')
        self.assertIn('/data/7536/',result);self.assertNotIn('/data/1104659/',result)
    def test_mail_draft_private_and_never_sent_by_default(self):
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ',{'SCANNER_REPORT_TO':'recipient@example.invalid','SMTP_FROM':'sender@example.invalid'},clear=True), patch('stock_scanner.delivery.smtplib.SMTP_SSL') as smtp:
            state=Path(d);report=state/'runs'/'report.md';report.parent.mkdir();report.write_text('Report')
            atomic_json(report.with_name('report.json'),{'data_date':'2026-10-02','status':'complete'})
            result=prepare(report,state)
            self.assertEqual(result['status'],'draft');smtp.assert_not_called()
            self.assertEqual(Path(result['message_path']).stat().st_mode&0o777,0o600)
            with self.assertRaises(DeliveryError): prepare(report,state,True)

    def test_mail_missing_configuration_reports_names_not_values(self):
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ',{},clear=True):
            state=Path(d);report=state/'report.md';report.write_text('x')
            atomic_json(report.with_name('report.json'),{'data_date':'2026-10-02','status':'complete'})
            with self.assertRaisesRegex(DeliveryError,'SCANNER_REPORT_TO'): prepare(report,state)

    def test_research_missing_finances_does_not_claim_zero_debt_or_date(self):
        with tempfile.TemporaryDirectory() as d:
            class FakeClient:
                state=Path(d)
                calls=[]
                def get(self,path,params=None):
                    self.calls.append(path)
                    if path.endswith('balance-sheets'): raise ProviderError(403,path,'Not entitled')
                    return {'results':{} if '/tickers/' in path else []}
            client=FakeClient();r=Researcher(client,'2026-10-02')
            a=r.candidate({'symbol':'T'});b=r.candidate({'symbol':'U'})
            self.assertEqual(sum(x.endswith('balance-sheets') for x in client.calls),1)
            self.assertFalse(any(x.startswith('/vX') for x in client.calls))
            self.assertIn('Next earnings date is not verified',' '.join(a['missing']))
            self.assertFalse(any('debt' in x['text'] for x in a['facts']))

    def test_state_cannot_be_inside_public_checkout(self):
        from stock_scanner.storage import ROOT
        with self.assertRaises(ValueError): state_directory(ROOT/'raw')

    def test_state_does_not_reuse_public_directory(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'public';path.mkdir();path.chmod(0o755)
            with self.assertRaisesRegex(ValueError,'group/other'): state_directory(path)
            self.assertEqual(path.stat().st_mode&0o777,0o755)

    def test_scheduled_before_close_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as d, patch('stock_scanner.cli.utc_now',return_value=__import__('datetime').datetime.fromisoformat('2026-10-02T18:00:00+00:00')),patch('stock_scanner.cli.daily') as run:
            result=scheduled(Path(d),Rules());self.assertEqual(result['status'],'not_due');run.assert_not_called()

    def test_scheduled_last_session_before_holiday_runs_weekly_once(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as d, patch('stock_scanner.cli.utc_now',return_value=datetime.fromisoformat('2026-04-02T21:00:00+00:00')):
            state=Path(d)
            with patch('stock_scanner.cli.daily',return_value=(state/'daily',{'status':'complete'})) as day, patch('stock_scanner.cli.weekly',return_value=(state/'weekly',{'status':'partial_week'})) as week:
                first=scheduled(state,Rules());second=scheduled(state,Rules())
                self.assertEqual(first['status'],'processed');self.assertIsNotNone(first['weekly'])
                self.assertEqual(day.call_count,1);self.assertEqual(week.call_count,1)

    def test_failed_scheduled_mail_is_not_retried_by_timer(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as d, patch('stock_scanner.cli.utc_now',return_value=datetime.fromisoformat('2026-10-01T21:00:00+00:00')):
            state=Path(d)
            with patch('stock_scanner.cli.daily',return_value=(state/'daily',{'status':'complete'})),patch('stock_scanner.cli.prepare',side_effect=DeliveryError('failed')) as deliver:
                with self.assertRaises(DeliveryError):scheduled(state,Rules(),send=True)
                with self.assertRaises(DeliveryError):scheduled(state,Rules(),send=True)
                self.assertEqual(deliver.call_count,1)


if __name__ == '__main__':
    unittest.main()
