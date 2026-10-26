"""Quote/contract regressions; actual reasoning is measured by the live case suite."""
import unittest

from evidence_mesh.semantic_review import validate_review
from evidence_mesh.semantic_conflict import validate_conflict
from test_spread_semantic_workflow import review_v11
from test_semantic_conflict_partner import row


class QuantityContractTests(unittest.TestCase):
    def test_subset_bound_support_keeps_actual_quote(self):
        claim = '2020年全球同类产品销量至少60万件'
        material = '2020年中国该类产品实际销量60万件。'
        value = review_v11()
        value['claims'][0].update(claim_span=claim, status='supported',
            quotes=[{'text': material}], suggested_wording=None,
            explanation='结论：支持至少60万件。\n依据：中国属于全球，全球销量不小于中国销量。\n边界：未确定全球精确总量。')
        result = validate_review(value, claim, material)
        self.assertEqual(result['claims'][0]['quotes'][0]['text'], material)
        # The computed conclusion must not be substituted for source text.
        value['claims'][0]['quotes'] = [{'text': '全球实际销量60万件。'}]
        with self.assertRaises(ValueError):
            validate_review(value, claim, material)

    def test_subset_lower_bound_can_refute_smaller_global_total(self):
        claim = '2020年全球该类产品总销量仅10万件。'
        material = '2020年中国该类产品实际销量60万件。'
        value = row(claim, material)
        value['findings'][0].update(basis='mutually-exclusive-outcome',
            explanation='中国属于全球，全球销量至少60万件，与全球总量仅10万件互斥。')
        result = validate_conflict(value, claim, material)
        self.assertEqual(result['findings'][0]['relation'], 'clear-conflict')

    def test_unknown_time_still_blocks_definite_conflict(self):
        claim, material = '今年全球总销量仅10万件。', '中国过去曾有一年销量60万件。'
        value = row(claim, material, time='unknown')
        value['findings'][0]['basis'] = 'mutually-exclusive-outcome'
        with self.assertRaisesRegex(ValueError, 'unaligned-conflict'):
            validate_conflict(value, claim, material)
