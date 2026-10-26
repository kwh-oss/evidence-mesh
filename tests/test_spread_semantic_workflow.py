"""Contract and local workflow tests, not model quality measurements."""
import copy
import json
import unittest

from evidence_mesh.semantic_review import validate_review, render_review, run_semantic_review
from evidence_mesh.leader import audit_claim, PartnerTarget
from test_evidence_leader import local_targets, request_json
from test_partner_friendly_input import CASES


def review_v11():
    return {'schema_version': '1.1', 'claims': [{
        'claim_span': '所有门店开放', 'kind': 'fact', 'status': 'overstated',
        'quotes': [{'text': '部分门店开放。'}],
        'explanation': '材料只说部分，不能推出所有门店开放。',
        'mechanisms': ['scope'], 'suggested_wording': '部分门店开放。'}]}


class SemanticContractTests(unittest.TestCase):
    def test_all_mechanism_inputs_preserved_by_parser(self):
        from pathlib import Path
        from evidence_mesh.contracts import request_from_caller_text, MISSING_SOURCE_EXCERPT
        suite = json.loads(Path('benchmarks/spread-mechanisms-2026-10-06.json').read_text(encoding='utf-8'))
        for case in suite['cases']:
            with self.subTest(case=case['id']):
                text = ('原始材料：' + case['material'] + '\n' if case['material'] else '') + '待核验帖子：' + case['post']
                request = request_from_caller_text(text, default_claim_id=case['id'])
                self.assertEqual(request.claim_text, case['post'])
                self.assertEqual(request.source_excerpt, case['material'] or MISSING_SOURCE_EXCERPT)

    def test_server_anchors_exact_quote_and_readable_rewrite(self):
        result = validate_review(review_v11(), '所有门店开放', '公告：部分门店开放。')
        self.assertEqual(result['claims'][0]['quotes'][0]['start'], 3)
        self.assertTrue(result['coverage_complete'])
        answer = render_review(result)
        self.assertIn('保守转述建议', answer)
        self.assertIn('所提供材料中的引文：部分门店开放。', answer)
        self.assertIn('模型生成', answer)
        self.assertEqual(result['claims'][0]['quotes'][0]['text'], '部分门店开放。')
        self.assertNotIn('字符', answer)

    def test_ambiguous_or_fabricated_quote_fails_closed(self):
        for material in ('部分门店开放。部分门店开放。', '全部门店关闭。'):
            with self.subTest(material=material), self.assertRaises(ValueError):
                validate_review(review_v11(), '所有门店开放', material)

    def test_invalid_mechanism_or_unsupported_rewrite_rejected(self):
        for change in ({'mechanisms': ['invented']}, {'mechanisms': ['scope', 'scope']},
                       {'status': 'unsupported'}, {'suggested_wording': 123}):
            value = review_v11()
            value['claims'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_review(value, '所有门店开放', '部分门店开放。')

    def test_unreviewed_span_visible(self):
        result = validate_review(review_v11(), '所有门店开放，明年一定免费', '部分门店开放。')
        self.assertFalse(result['coverage_complete'])
        self.assertIn('明年一定免费', render_review(result))

    def test_opinion_without_rewrite_or_quote_allowed(self):
        value = review_v11()
        value['claims'][0].update(claim_span='我觉得很糟糕', kind='opinion', status='opinion',
                                 quotes=[], mechanisms=[], suggested_wording=None)
        result = validate_review(value, '我觉得很糟糕', '部分门店开放。')
        self.assertIn('主观评价', render_review(result))


class MockReviewer:
    def __init__(self):
        self.calls = 0

    async def review(self, system, data):
        self.calls += 1
        assert 'source-independence' in system
        assert json.loads(data)['post'] == '所有门店开放'
        return copy.deepcopy(review_v11())


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_leader_keeps_real_partner_products_and_model_separate(self):
        reviewer = MockReviewer()
        result = await audit_claim(request_json('所有门店开放', '部分门店开放。'),
                                   local_targets(), semantic_reviewer=reviewer)
        self.assertEqual(reviewer.calls, 1)
        self.assertEqual(len(result['task_ids']), 3)
        self.assertEqual(result['semantic_review']['status'], 'model-suggestion')
        self.assertIn('材料只说部分', result['answer'])
        self.assertTrue(all('answer' in p for p in result['partner_products'].values()))
        self.assertFalse(result['semantic_review']['source_authenticity_verified'])

    async def test_partner_failure_prevents_model_claiming_success(self):
        targets = local_targets()
        import httpx
        targets[0] = PartnerTarget('source-verifier', 'http://failed.test/rpc',
                                   httpx.MockTransport(lambda req: httpx.Response(500)))
        reviewer = MockReviewer()
        result = await audit_claim(request_json('所有门店开放', '部分门店开放。'),
                                   targets, semantic_reviewer=reviewer)
        self.assertEqual(reviewer.calls, 0)
        self.assertEqual(result['decision'], 'incomplete')
        self.assertIn('未完成', result['answer'])

    async def test_missing_material_never_calls_model(self):
        reviewer = MockReviewer()
        result = await run_semantic_review('所有门店开放', '', reviewer)
        self.assertEqual(result['status'], 'not-inspected')
        self.assertEqual(reviewer.calls, 0)


class ReadablePartnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_aip_candidate_message_is_chinese_and_product_retained(self):
        import uuid
        import httpx
        from acps_sdk.aip.aip_rpc_client import AipRpcClient
        for app, kind, _ in CASES:
            client = AipRpcClient('http://local.test/rpc', 'local',
                transport=httpx.ASGITransport(app=app), identity_binding_enabled=False)
            try:
                started = await client.start_task('session-' + str(uuid.uuid4()),
                    '原始材料：部分门店开放。\n待核验帖子：所有门店开放',
                    task_id='task-' + str(uuid.uuid4()))
                self.assertNotIn('Structured product', started.status.dataItems[0].text)
                self.assertTrue(any('\u4e00' <= c <= '\u9fff' for c in started.status.dataItems[0].text))
                self.assertTrue(started.products)
            finally:
                await client.close()
