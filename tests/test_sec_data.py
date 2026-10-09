import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from stock_scanner.sec_data import SecClient, company, filing_rows, financial_series, manager, parse_holdings
from stock_scanner.storage import read_json

XML = '<informationTable xmlns="urn:sec"><infoTable><nameOfIssuer>Example</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>123456789</cusip><value>1200</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable></informationTable>'


class SecDataTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'SEC_USER_AGENT': 'CoSoup tests contact@example.test'})
        env.start(); self.addCleanup(env.stop)

    def test_public_requests_are_cached_and_have_no_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            requests=[]
            def opener(r,timeout): requests.append(r);return io.BytesIO(b'{"ok":true}')
            client=SecClient(Path(tmp),'2026-10-08',opener)
            one=client.get('https://data.sec.gov/submissions/CIK0000000001.json')
            self.assertEqual(one,client.get(one['source']))
            self.assertEqual(len(requests),1)
            self.assertFalse(requests[0].has_header('Authorization'))
            self.assertEqual(requests[0].get_header('User-agent'), 'CoSoup tests contact@example.test')
            self.assertEqual(len(read_json(Path(tmp)/'rate-limit.json')['requests']),1)

    def test_private_contact_file_overrides_ambient_identity_in_both_clients(self):
        from stock_scanner.primary import sec_company_facts
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); contact=root/'contact'; contact.write_text('CoSoup private contact@example.test')
            seen=[]
            def opener(request, timeout):
                seen.append(request.get_header('User-agent')); return io.BytesIO(b'{"cik":1,"facts":{}}')
            with patch.dict(os.environ, {'SEC_USER_AGENT_FILE':str(contact),'SEC_USER_AGENT':'CoSoup ambient other@example.test'}):
                self.assertIsNotNone(SecClient(root/'new','2026-10-08',opener).get('https://data.sec.gov/submissions/CIK0000000001.json'))
                state=root/'old'; state.mkdir()
                self.assertNotIn('error',sec_company_facts(state,1,'2026-10-08',opener=opener))
            self.assertEqual(seen,['CoSoup private contact@example.test']*2)

    def test_invalid_contact_stops_before_network_and_does_not_echo_identity(self):
        from stock_scanner.primary import validate_sec_user_agent
        for value in ['', 'CoSoup https://example.test', 'CoSoup noreply@example.test', 'CoSoup contact@example.test\r\nX: injected', 'CoSoup contact@example.test'+'x'*513]:
            with self.subTest(length=len(value)), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):validate_sec_user_agent(value)
                with patch.dict(os.environ,{'SEC_USER_AGENT':value}):
                    client=SecClient(Path(tmp),'2026-10-08',lambda *a,**kw:self.fail('Invalid contact must not send a request'))
                    self.assertIsNone(client.get('https://www.sec.gov/files/company_tickers.json'))
                    self.assertEqual(client.requests,0)
                    self.assertTrue(client.stopped)
                    self.assertFalse((Path(tmp)/'rate-limit.json').exists())
                    self.assertNotIn('contact@example.test',json.dumps(client.errors))

    def test_missing_private_contact_file_does_not_fall_back_to_ambient_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ,{'SEC_USER_AGENT_FILE':str(Path(tmp)/'absent')}):
                c=SecClient(Path(tmp),'2026-10-08',lambda *a,**kw:self.fail('No request without private identity'))
                self.assertIsNone(c.get('https://www.sec.gov/files/company_tickers.json'))
                self.assertEqual(c.requests,0)
                self.assertIn('unavailable',c.errors[0]['message'])

    def test_access_failure_stops_all_further_network_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def opener(r,timeout):calls.append(r);raise urllib.error.HTTPError(r.full_url,403,'private intermediary text',{},None)
            c=SecClient(Path(tmp),'2026-10-08',opener)
            self.assertIsNone(c.get('https://www.sec.gov/files/company_tickers.json'))
            self.assertIsNone(c.get('https://data.sec.gov/submissions/CIK0000000001.json'))
            self.assertEqual(len(calls),1);self.assertEqual(c.errors[0]['http_status'],403)
            self.assertNotIn('private intermediary',json.dumps(c.errors))

    def test_cooldown_prevents_a_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            from stock_scanner.storage import atomic_json
            atomic_json(Path(tmp)/'rate-limit.json',{'cooldown_until':100})
            c=SecClient(Path(tmp),'2026-10-08',lambda *a,**kw:self.fail('No request during cooldown'))
            with patch('stock_scanner.sec_data.time.time',return_value=1):
                self.assertIsNone(c.get('https://www.sec.gov/files/company_tickers.json'))
            self.assertIn('cooldown',c.errors[0]['message'])

    def test_foreign_hosts_userinfo_and_queries_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=SecClient(Path(tmp),'2026-10-08')
            for url in ['https://api.massive.com/x','http://www.sec.gov/x','https://u:p@www.sec.gov/x','https://www.sec.gov/x?token=synthetic']:
                with self.assertRaises(ValueError):c.get(url)

    def test_periods_units_restatements_and_cutoff_are_preserved(self):
        facts={'cik':1,'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[
            {'val':10,'start':'2026-01-01','end':'2026-06-30','filed':'2026-08-01','form':'10-Q','accn':'0000000001-26-000001'},
            {'val':5,'start':'2026-04-01','end':'2026-06-30','filed':'2026-08-01','form':'10-Q','accn':'0000000001-26-000001'},
            {'val':6,'start':'2026-04-01','end':'2026-06-30','filed':'2026-09-01','form':'10-Q','accn':'0000000001-26-000002'},
            {'val':100,'end':'2026-09-30','filed':'2026-11-01','form':'10-Q','accn':'0000000001-26-000003'},
            {'val':float('nan'),'end':'2026-09-30','filed':'2026-10-01','form':'10-Q','accn':'0000000001-26-000004'}]}}}}}
        rows=financial_series(facts,1,'2026-10-08')
        self.assertEqual(sorted(r['value'] for r in rows),[6,10]);self.assertEqual(rows[0]['unit'],'USD')
        self.assertEqual({r['period_start'] for r in rows},{'2026-01-01','2026-04-01'})

    def test_filing_discovery_rejects_future_and_unsafe_document_paths(self):
        data={'filings':{'recent':{'form':['10-K','10-Q','4'],'accessionNumber':['0000000001-26-000001']*3,
              'filingDate':['2026-01-01','2026-11-01','2026-01-02'],'primaryDocument':['report.htm','future.htm','../secret']}}}
        rows=filing_rows(data,1,'2026-10-08');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['form'],'10-K')

    def test_annual_and_quarterly_documents_are_selected_before_link_list_truncation(self):
        recent={'form':['4']*45+['10-Q','10-K'],
                'accessionNumber':[f'0000000001-26-{i:06d}' for i in range(47)],
                'filingDate':['2026-10-07']*45+['2026-08-01','2026-02-01'],
                'reportDate':['']*45+['2026-06-30','2025-12-31'],
                'primaryDocument':['insider.xml']*45+['quarterly.htm','annual.htm']}
        class Client:
            as_of='2026-10-08'
            def get(self,url,kind='json'):
                if 'submissions' in url:return {'data':{'cik':1,'filings':{'recent':recent}}}
                if 'companyfacts' in url:return {'data':{'cik':1,'facts':{}}}
                return {'data':'<p>Synthetic filing excerpt.</p>','checked_at':'2026-10-08'}
        result=company(Client(),'ABC',1)
        self.assertEqual(len(result['filings']),40)
        self.assertEqual({d['form'] for d in result['documents']},{'10-K','10-Q'})
        self.assertFalse(any('No recent' in gap for gap in result['gaps']))

    def test_xml_holdings_preserve_option_classes_and_value_units(self):
        rows=parse_holdings(XML,'2026-06-30','2026-08-01');self.assertEqual(rows[0]['value_usd'],1200)
        self.assertEqual(parse_holdings(XML,'2022-12-31','2023-02-14')[0]['value_usd'],1200)
        self.assertEqual(parse_holdings(XML,'2022-06-30','2022-08-01')[0]['value_usd'],1_200_000)
        with self.assertRaises(ValueError):parse_holdings('<!DOCTYPE x>'+XML,'2026-06-30')
        with self.assertRaises(ValueError):parse_holdings(XML.replace('<value>1200','<value>NaN'),'2026-06-30')

    def test_amended_holdings_are_not_silently_compared(self):
        class Client:
            as_of='2026-10-08'
            def get(self,url):
                return {'data':{'cik':1,'name':'Manager','filings':{'recent':{'form':['13F-HR/A','13F-HR'],
                        'accessionNumber':['0000000001-26-000002','0000000001-26-000001'],
                        'filingDate':['2026-08-10','2026-08-01'],'reportDate':['2026-06-30']*2,
                        'primaryDocument':['amend.xml','base.xml']}}}}
        result=manager(Client(),1);self.assertFalse(result['snapshots']);self.assertFalse(result['changes'])
        self.assertTrue(any('amended' in g for g in result['gaps']))

    def test_edgar_xsl_primary_documents_are_discovered_without_allowing_traversal(self):
        data={'filings':{'recent':{'form':['13F-HR'],'accessionNumber':['0000000001-26-000001'],
              'filingDate':['2026-08-01'],'reportDate':['2026-06-30'],'primaryDocument':['xslForm13F_X02/primary_doc.xml']}}}
        rows=filing_rows(data,1,'2026-10-08',{'13F-HR'})
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['source'].endswith('/xslForm13F_X02/primary_doc.xml'))

    def test_snapshot_changes_keep_options_separate(self):
        class Client:
            as_of='2026-10-08'
            def get(self,url,kind='json'):
                if 'submissions' in url:
                    return {'data':{'cik':1,'name':'Manager','filings':{'recent':{'form':['13F-HR']*2,
                            'accessionNumber':['0000000001-26-000002','0000000001-26-000001'],
                            'filingDate':['2026-08-01','2026-05-01'],'reportDate':['2026-06-30','2026-03-31'],
                            'primaryDocument':['primary.xml']*2}}}}
                if url.endswith('index.json'):return {'data':{'directory':{'item':[{'name':'primary.xml'},{'name':'table.xml'}]}}}
                return {'checked_at':'2026-10-08','data':XML if '-000002' in url else XML.replace('>10<','>8<')}
        # Accession directory names omit hyphens.
        client=Client();old_get=client.get
        def get(url,kind='json'):
            if url.endswith('table.xml'):return {'checked_at':'2026-10-08','data':XML if '26000002' in url else XML.replace('>10<','>8<')}
            return old_get(url,kind)
        client.get=get
        result=manager(client,1);self.assertEqual(result['changes'][0]['share_delta'],2)


if __name__=='__main__':unittest.main()
