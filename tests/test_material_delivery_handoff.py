import json
import unittest
from unittest.mock import patch
from evidence_mesh.contracts import request_from_caller_text, request_from_json, request_json, MISSING_SOURCE_EXCERPT
from evidence_mesh.leader import audit_claim, PartnerTarget
from evidence_mesh.partner_input import partner_product
from evidence_mesh.processors import verify_source, grade_evidence, find_contradiction


class MaterialDeliveryHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def run_handoff(self, assessment):
        request = request_from_caller_text('博物馆每天都开放吗？', default_claim_id='fixture')
        text = '博物馆是不是每天都开放？\n' * 8
        source = json.loads(partner_product('source-check', verify_source, request))
        source['retrieval'] = {'status': 'retrieved', 'sources': [{'source_id': 'p',
            'url': 'https://example.com/rules', 'text': text, 'title': '开放问题'}]}
        if assessment is not None:
            source['output_assessment'] = assessment
        observed = {}
        async def partner(target, raw, amp=None):
            req = request_from_json(raw)
            observed[target.name] = req.source_excerpt
            if target.name == 'source-verifier':
                value = source
            else:
                kind, processor = ('evidence-finding', grade_evidence) if target.name == 'evidence-grader' else ('contradiction-check', find_contradiction)
                value = json.loads(partner_product(kind, processor, req))
            return {'state': 'completed', 'task_id': 'fixture-'+target.name, 'product': value}
        targets = [PartnerTarget(name, 'http://fixture/rpc') for name in ('source-verifier', 'evidence-grader', 'contradiction-scout')]
        with patch('evidence_mesh.leader._call_partner', side_effect=partner):
            await audit_claim(request_json(request), targets)
        return observed

    async def test_title_only_delivery_is_not_sent_as_evidence_for_comparison(self):
        observed = await self.run_handoff({'material_available': False})
        self.assertEqual(observed['evidence-grader'], MISSING_SOURCE_EXCERPT)
        self.assertEqual(observed['contradiction-scout'], MISSING_SOURCE_EXCERPT)

    async def test_legacy_source_products_keep_the_previous_reading_contract(self):
        observed = await self.run_handoff(None)
        self.assertNotEqual(observed['evidence-grader'], MISSING_SOURCE_EXCERPT)
        self.assertNotEqual(observed['contradiction-scout'], MISSING_SOURCE_EXCERPT)
