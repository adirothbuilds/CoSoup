import io
import json
import tempfile
import unittest
from pathlib import Path

from stock_scanner.primary import sec_company_facts, sec_metrics
from stock_scanner.storage import atomic_json


class PrimaryTests(unittest.TestCase):
    def test_no_massive_authorization_is_sent_to_sec(self):
        with tempfile.TemporaryDirectory() as d:
            requests=[]
            def opener(request,timeout):
                requests.append(request)
                return io.BytesIO(b'{"cik":7536,"facts":{}}')
            result=sec_company_facts(Path(d),'0000007536','2026-10-02',opener=opener)
            self.assertFalse(result.get('error'));self.assertFalse(requests[0].has_header('Authorization'))
            again=sec_company_facts(Path(d),'0000007536','2026-10-02',opener=opener)
            self.assertEqual(len(requests),1)

    def test_known_network_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);atomic_json(state/'raw'/'research'/'2026-10-02'/'_blocked_sec.json',{'message':'blocked'})
            def opener(*args,**kwargs):raise AssertionError('Must not call network')
            result=sec_company_facts(state,'7536','2026-10-02',opener=opener)
            self.assertEqual(result['error']['message'],'blocked')

    def test_future_filings_and_invalid_values_cannot_be_quoted(self):
        rows=[{'val':100,'form':'10-Q','end':'2026-06-30','filed':'2026-08-01'},
              {'val':200,'form':'10-Q','end':'2026-09-30','filed':'2026-11-01'},
              {'val':float('nan'),'form':'10-Q','end':'2026-09-30','filed':'2026-10-01'}]
        data={'data':{'facts':{'us-gaap':{'LongTermDebtNoncurrent':{'units':{'USD':rows}}}}}}
        result=sec_metrics(data,'2026-10-02')
        self.assertEqual(len(result),1);self.assertEqual(result[0]['value'],100)

    def test_wrong_issuer_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            result=sec_company_facts(Path(d),'7536','2026-10-02',opener=lambda request,timeout:io.BytesIO(b'{"cik":8858}'))
            self.assertIn('does not match',result['error']['message'])
