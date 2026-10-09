import unittest

import numpy as np

from stock_scanner.analytics import breadth, technical
from stock_scanner.financial_analytics import financial_analysis, institutional_analysis, institutional_overlap


def fact(label, value, start='2026-04-01', end='2026-06-30', filed='2026-08-01', unit='USD'):
    return {'label': label, 'value': value, 'period_start': start, 'period_end': end,
            'filing_date': filed, 'unit': unit, 'source': 'https://www.sec.gov/fixture/'+filed}


class TechnicalAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.bars = np.tile([100., 101., 99., 100., 1_000_000.], (260, 1))

    def test_true_range_captures_gap_and_base_excludes_breakout_session(self):
        self.bars[-1] = [110, 111, 109, 110, 2_000_000]
        result = technical(self.bars, self.bars, 101)
        self.assertAlmostEqual(result['atr14'], 37/14)
        self.assertAlmostEqual(result['pivot_distance_atr'], 9/(37/14))
        self.assertEqual(result['prior_range_contraction_ratio'], 1)
        self.assertEqual(result['volume_confirmed_days5'], 1)
        self.assertEqual(result['relative_strength_windows']['21']['excess_pct'], 0)

    def test_constant_prices_zero_volatility_and_zero_range_not_infinity(self):
        result = technical(self.bars, self.bars, 101)
        self.assertEqual(result['realized_volatility20_pct'], 0)
        self.assertEqual(result['max_close_drawdown63_pct'], 0)
        self.bars[:, :4] = 100
        result = technical(self.bars, self.bars, 100)
        self.assertIsNone(result['pivot_distance_atr'])
        self.assertIsNone(result['prior_range_contraction_ratio'])

    def test_breadth_excludes_unknown_histories_and_keeps_denominator(self):
        result = breadth([{'data_valid': True, 'close': 10, 'sma50': 9, 'sma200': 11, 'pivot': 9, 'rs_excess': .1},
                          {'data_valid': False}], '2026-10-02')
        self.assertEqual(result['valid_histories'], 1)
        self.assertEqual(result['excluded_histories'], 1)
        self.assertEqual(result['measures']['above_sma50']['pct'], 100)
        self.assertIsNone(breadth([], '2026-10-02')['measures']['above_sma50']['pct'])


class FinancialAnalyticsTests(unittest.TestCase):
    def analyze(self, rows):
        return financial_analysis({'symbol': 'ABC', 'metrics': rows}, '2026-10-08')

    def test_aligned_ratios_and_growth_use_actual_operands(self):
        rows = [fact('Revenue', 100), fact('Operating income', 20), fact('Net income', 10),
                fact('Operating cash flow', 12), fact('Capital expenditure', 3),
                fact('Revenue', 80, '2025-04-01', '2025-06-30', '2025-08-01')]
        result = self.analyze(rows)
        derived = {r['label']: r for r in result['series']}
        self.assertEqual(derived['Operating margin']['value'], 20)
        self.assertEqual(derived['Cash conversion']['value'], 1.2)
        self.assertEqual(derived['Free cash flow']['value'], 9)
        self.assertEqual(derived['Revenue YoY change']['value'], 25)
        self.assertEqual(len(derived['Free cash flow']['inputs']), 2)
        self.assertEqual(derived['Operating margin']['filing_date'], '2026-08-01')

    def test_ytd_units_future_filings_and_negative_base_never_fill_gaps(self):
        rows = [fact('Revenue', 100), fact('Operating income', 20, '2026-01-01'),
                fact('Operating cash flow', 12), fact('Capital expenditure', 3, unit='EUR'),
                fact('Net income', 10, filed='2026-10-09'),
                fact('Revenue', -80, '2025-04-01', '2025-06-30', '2025-08-01')]
        result = self.analyze(rows)
        self.assertFalse(any(r['label'] in {'Operating margin', 'Net margin', 'Free cash flow', 'Cash conversion', 'Revenue YoY change'} for r in result['series']))
        self.assertTrue(any('Free cash flow' in g for g in result['gaps']))

    def test_restatement_deduplication_and_conflicts_do_not_double_count(self):
        rows = [fact('Revenue', 80, filed='2026-07-01'), fact('Revenue', 100), fact('Operating income', 20)]
        derived = self.analyze(rows)['series']
        self.assertEqual(next(r for r in derived if r['label']=='Operating margin')['value'], 20)
        rows.append(fact('Revenue', 101))
        result = self.analyze(rows)
        self.assertFalse(any(r['label']=='Operating margin' for r in result['series']))
        self.assertTrue(any('Conflicting' in gap for gap in result['gaps']))

    def test_different_quarter_durations_and_zero_denominators_omitted(self):
        rows = [fact('Revenue', 0), fact('Net income', 10), fact('Operating income', 20),
                fact('Revenue', 50, '2025-01-01', '2025-06-30', '2025-08-01')]
        self.assertFalse(any(r['label'] in {'Operating margin','Net margin','Revenue YoY change'} for r in self.analyze(rows)['series']))


def manager(cik='1', period='2026-06-30', security_class='COM'):
    rows=[{'issuer': 'Issuer '+str(i), 'cusip': str(i), 'class': security_class, 'put_call': '',
           'amount_type': 'SH', 'shares': 10, 'value_usd': 100} for i in range(8)]
    rows.append({**rows[0], 'put_call': 'PUT', 'value_usd': 10000})
    return {'name': 'Manager '+cik, 'cik': cik, 'snapshots': [{'period_end': period, 'filing_date': '2026-08-01',
            'source': 'https://www.sec.gov/fixture', 'holdings': rows}], 'changes': [], 'gaps': []}


class InstitutionalAnalyticsTests(unittest.TestCase):
    def test_concentration_uses_full_equity_subset_and_excludes_options(self):
        snapshot=institutional_analysis(manager())['snapshots'][0]
        self.assertEqual(snapshot['reported_equity_value_usd'], 800)
        self.assertEqual(snapshot['top5_weight_pct'], 62.5)
        self.assertEqual(snapshot['excluded_positions'], 1)

    def test_overlap_requires_same_quarter_and_exact_security_class(self):
        first=institutional_analysis(manager())
        second=institutional_analysis(manager('2'))
        self.assertEqual(len(institutional_overlap([first,second])['positions']), 8)
        other_class=institutional_analysis(manager('2', security_class='CLASS B'))
        self.assertEqual(institutional_overlap([first,other_class])['positions'], [])
        other_quarter=institutional_analysis(manager('2', period='2026-03-31'))
        self.assertTrue(institutional_overlap([first,other_quarter])['gaps'])
