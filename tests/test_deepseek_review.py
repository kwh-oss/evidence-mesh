import json
from pathlib import Path
import tempfile
import unittest

import httpx

from evidence_mesh.deepseek_review import DeepSeekReviewer
from evidence_mesh.semantic_review import validate_review, run_semantic_review, render_review


def example():
    return {'schema_version': '1.0', 'claims': [{'claim_span': '所有门店开放',
        'kind': 'fact', 'status': 'overstated',
        'quotes': [{'start': 0, 'end': 6, 'text': '部分门店开放'}],
        'explanation': '帖子将部分门店扩大为所有门店。'}]}


class ReviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_exhausted_budget_is_reported_without_second_provider_request(self):
        calls = 0
        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(503)
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory)/'key'
            key.write_text('test-only-key')
            budget = Path(directory)/'quota.sqlite3'
            for index in range(2):
                client = DeepSeekReviewer(model='test', key_file=key, max_calls=1,
                    budget_file=budget, transport=httpx.MockTransport(handler))
                result = await run_semantic_review('消息','材料',client)
                self.assertEqual(result['failure_code'], 'model-provider-failed' if index == 0 else 'model-budget-exhausted')
                self.assertNotIn('test-only-key', json.dumps(result))
            self.assertEqual(calls, 1)

    async def test_timeout_and_budget_unavailable_have_safe_separate_codes(self):
        from evidence_mesh.model_budget import BudgetUnavailable
        for error, code in [(TimeoutError('private-url'), 'model-timeout'),
                            (BudgetUnavailable('private-path'), 'model-budget-unavailable')]:
            class Broken:
                async def review(self, *args):
                    raise error
            result = await run_semantic_review('消息','材料',Broken())
            self.assertEqual(result['failure_code'], code)
            self.assertNotIn('private-', json.dumps(result))

    async def test_failed_provider_attempt_persists_across_new_clients(self):
        calls = 0
        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(503)
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / 'test.key'
            key.write_text('test-only-not-a-real-key', encoding='utf-8')
            budget = Path(directory) / 'quota.sqlite3'
            for _ in range(2):
                client = DeepSeekReviewer(model='test-model', key_file=key, max_calls=1,
                    budget_file=budget, transport=httpx.MockTransport(handler))
                with self.assertRaises(ValueError):
                    await client.review('system', 'data')
            self.assertEqual(calls, 1)

    async def test_mock_transport_budget_and_request_shape(self):
        count = 0
        def handler(request):
            nonlocal count
            count += 1
            self.assertEqual(str(request.url), 'https://api.deepseek.com/chat/completions')
            body = json.loads(request.content)
            self.assertEqual(body['response_format'], {'type': 'json_object'})
            self.assertFalse(body['stream'])
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
                'message': {'content': json.dumps(example())}}]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.key'
            path.write_text('test-only-not-a-real-key', encoding='utf-8')
            client = DeepSeekReviewer(model='test-model', key_file=path, max_calls=1,
                                      transport=httpx.MockTransport(handler))
            result = await run_semantic_review('所有门店开放', '部分门店开放', client)
            self.assertEqual(result['status'], 'model-suggestion')
            self.assertIn('部分门店开放', render_review(result))
            self.assertNotIn('不代表模型推理一定正确', render_review(result))
            self.assertEqual((await run_semantic_review('所有门店开放', '部分门店开放', client))['status'], 'failed-or-invalid')
            self.assertEqual(count, 1)
            self.assertEqual(len(client.attempts), 1)
            self.assertEqual(client.attempts[0]['http_status'], 200)
            self.assertNotIn('test-only-not-a-real-key', json.dumps(client.attempts))

    async def test_no_material_or_disabled_never_calls(self):
        class Forbidden:
            async def review(self, *args):
                raise AssertionError('must not call')
        self.assertEqual((await run_semantic_review('帖子', '', Forbidden()))['status'], 'not-inspected')
        self.assertEqual((await run_semantic_review('帖子', '材料', None))['status'], 'disabled')

    def test_fabricated_and_wrong_offset_quotes_rejected(self):
        for quote in ({'start': 0, 'end': 6, 'text': '所有门店开放'},
                      {'start': 1, 'end': 7, 'text': '部分门店开放'}):
            data = example()
            data['claims'][0]['quotes'] = [quote]
            with self.assertRaises(ValueError):
                validate_review(data, '所有门店开放', '部分门店开放')

    def test_missing_quote_and_invented_claim_rejected(self):
        for field, value in [('quotes', []), ('claim_span', '所有门店关门')]:
            data = example()
            data['claims'][0][field] = value
            with self.assertRaises(ValueError):
                validate_review(data, '所有门店开放', '部分门店开放')

    def test_partial_coverage_disclosed(self):
        result = validate_review(example(), '所有门店开放，所有商品免费', '部分门店开放')
        self.assertFalse(result['coverage_complete'])
        self.assertIn('未覆盖', render_review(result))

    async def test_provider_error_does_not_leak(self):
        class Broken:
            async def review(self, *args):
                raise RuntimeError('PRIVATE_KEY=secret')
        result = await run_semantic_review('帖子', '材料', Broken())
        self.assertNotIn('secret', json.dumps(result))
        self.assertEqual(result['status'], 'failed-or-invalid')
        self.assertEqual(result['failure_stage'], 'provider')

    async def test_invalid_output_distinguished_from_provider_failure(self):
        class Invalid:
            async def review(self, *args):
                return {'secret': 'must-not-be-exposed'}
        result = await run_semantic_review('帖子', '材料', Invalid())
        self.assertEqual(result['failure_stage'], 'output-validation')
        self.assertNotIn('must-not-be-exposed', json.dumps(result))

    def test_large_budget_requires_explicit_evaluation_mode(self):
        with self.assertRaises(ValueError):
            DeepSeekReviewer(model='test-model', key_file='not-read.key', max_calls=24)
