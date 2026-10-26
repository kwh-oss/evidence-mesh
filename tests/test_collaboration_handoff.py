import json
import unittest
from types import SimpleNamespace
from acps_sdk.aip import TextDataItem
from evidence_mesh.collaboration_input import command_text
from evidence_mesh.partner_input import partner_request, partner_product
from evidence_mesh.processors import find_contradiction
from evidence_mesh.contracts import MISSING_SOURCE_EXCERPT


class HandoffTests(unittest.TestCase):
    def test_upstream_report_is_material_not_authenticated_source(self):
        req = partner_request(json.dumps({'claim': '全部人免费', 'upstream_results': [
            {'title': '上游报告', 'text': '只有登记会员免费。', 'url': 'https://example.org/a'}]}), default_claim_id='t')
        product = json.loads(partner_product('contradiction-check', find_contradiction, req))
        self.assertTrue(product['input_assessment']['inspection_performed'])
        self.assertEqual(product['collaboration']['material_origin'], 'caller-upstream-unverified')
        self.assertTrue(product['collaboration']['standalone_callable'])
        self.assertFalse(product['collaboration']['requires_our_leader'])
        self.assertFalse(product['collaboration']['source_authenticity_verified'])

    def test_links_and_status_are_not_evidence(self):
        for item in ({'url': 'https://example.org', 'title': 'title'}, {'status': 'completed', 'task': '检查前序结果'}):
            req = partner_request(json.dumps({'claim': '全部免费', 'upstream_results': [item]}), default_claim_id='t')
            self.assertEqual(req.source_excerpt, MISSING_SOURCE_EXCERPT)

    def test_explicit_excerpt_wins_over_report(self):
        req = partner_request(json.dumps({'claim': 'x', 'source_excerpt': '真实传入的材料',
            'upstream_results': [{'text': '另外报告'}]}), default_claim_id='t')
        self.assertEqual(req.source_excerpt, '真实传入的材料')

    def test_nested_handoff(self):
        req = partner_request(json.dumps({'input': {'claim': '全部免费', 'previous_results': [
            {'retrieval': {'sources': [{'source_id': 'a', 'text': '登记会员免费'}]}}]}}), default_claim_id='t')
        self.assertIn('登记会员免费', req.source_excerpt)

    def test_multiple_items_preserved(self):
        cmd = SimpleNamespace(dataItems=[TextDataItem(text='全部人免费'), TextDataItem(text=json.dumps(
            {'sources': [{'title': '规则', 'text': '登记会员免费'}]}))])
        req = partner_request(command_text(cmd), default_claim_id='t')
        self.assertEqual(req.claim_text, '全部人免费')
        self.assertIn('登记会员免费', req.source_excerpt)

    def test_extra_instructions_not_inferred_as_material(self):
        cmd = SimpleNamespace(dataItems=[TextDataItem(text='全部人免费'), TextDataItem(text='请根据前序结果核验')])
        req = partner_request(command_text(cmd), default_claim_id='t')
        self.assertEqual(req.source_excerpt, MISSING_SOURCE_EXCERPT)

    def test_multiple_items_total_limit(self):
        with self.assertRaises(ValueError):
            command_text(SimpleNamespace(dataItems=[TextDataItem(text='x'*40000), TextDataItem(text='y'*40000)]))
