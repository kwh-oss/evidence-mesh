import copy
import unittest
from evidence_mesh.semantic_review import validate_partial_review, render_review
from test_spread_semantic_workflow import review_v11


class DiagnosticsCompoundTests(unittest.TestCase):
    def test_opinion_with_fact_status_rejected_with_specific_safe_reason(self):
        value=review_v11()
        value['claims'][0].update(kind='opinion',status='unsupported',suggested_wording=None)
        result=validate_partial_review(value,'所有门店开放','部分门店开放。')
        self.assertEqual(result['claims'],[])
        self.assertEqual(result['rejected_claims'][0]['reason_code'],'classification-pair')
        self.assertFalse(result['coverage_complete'])

    def test_missing_quote_metadata_without_leak(self):
        value = review_v11()
        value['claims'][0]['quotes'] = [{'text': 'DO-NOT-EXPOSE'}]
        result = validate_partial_review(value, '所有门店开放', '部分门店开放。')
        diagnostics = result['rejected_claims'][0]['quote_diagnostics']
        self.assertEqual(diagnostics[0]['category'], 'absent')
        self.assertEqual(diagnostics[0]['exact_match_count'], 0)
        self.assertNotIn('DO-NOT-EXPOSE', str(result))

    def test_ambiguous_quote_not_arbitrarily_anchored(self):
        result = validate_partial_review(review_v11(), '所有门店开放', '部分门店开放。部分门店开放。')
        self.assertEqual(result['rejected_claims'][0]['quote_diagnostics'][0]['category'], 'ambiguous')
        self.assertEqual(result['rejected_claims'][0]['quote_diagnostics'][0]['exact_match_count'], 2)
        self.assertFalse(result['coverage_complete'])

    def test_compound_whole_row_rejected_but_exact_subspans_accepted(self):
        claim = '北京出台安排，所以全国所有学校必须执行'
        value = review_v11()
        row = value['claims'][0]
        row['claim_span'] = claim
        result = validate_partial_review(value, claim, '部分门店开放。')
        self.assertEqual(result['rejected_claims'][0]['reason_code'], 'compound-boundary')
        premise, conclusion = copy.deepcopy(row), copy.deepcopy(row)
        premise.update(claim_span='北京出台安排', status='supported', quotes=[{'text':'北京出台安排。'}])
        conclusion.update(claim_span='所以全国所有学校必须执行', quotes=[{'text':'只适用于北京。'}])
        value['claims'] = [premise, conclusion]
        result = validate_partial_review(value, claim, '北京出台安排。只适用于北京。')
        self.assertTrue(result['coverage_complete'])
        self.assertEqual([r['status'] for r in result['claims']], ['supported','overstated'])

    def test_opinion_quote_not_displayed_as_evidence(self):
        value = review_v11()
        value['claims'][0].update(claim_span='我觉得值得', kind='opinion', status='opinion', suggested_wording=None)
        result = validate_partial_review(value, '我觉得值得', '部分门店开放。')
        self.assertEqual(len(result['claims'][0]['quotes']), 1)
        self.assertNotIn('所提供材料中的引文', render_review(result))
        self.assertIn('评价所涉事实的材料引文', render_review(result))
        quote = result['claims'][0]['quotes'][0]
        self.assertEqual('部分门店开放。'[quote['start']:quote['end']], quote['text'])
        self.assertNotIn('本次没有提供可展示的原文引文', render_review(result))
