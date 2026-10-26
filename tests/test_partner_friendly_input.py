from evidence_mesh.product_presentation import read_product
import json
import unittest
import uuid

import httpx
from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient
from evidence_mesh.partner_input import partner_request, partner_product
from evidence_mesh.contracts import MISSING_SOURCE_EXCERPT, product_json
from evidence_mesh.processors import verify_source, grade_evidence, find_contradiction
from evidence_mesh.source_partner import app as source_app
from evidence_mesh.grader_partner import app as grader_app
from evidence_mesh.contradiction_partner import app as scout_app

CASES = [(source_app, 'source-check', verify_source),
         (grader_app, 'evidence-finding', grade_evidence),
         (scout_app, 'contradiction-check', find_contradiction)]


class PartnerInputTests(unittest.TestCase):
    def test_aliases_and_task_id(self):
        req = partner_request('{"answer":"所有用户可无条件退款","context":"未使用订单可申请退款"}', default_claim_id='task-1')
        self.assertEqual(req.claim_id, 'task-1')
        self.assertEqual(req.source_excerpt, '未使用订单可申请退款')
        self.assertEqual(req.source.source_id, '')

    def test_labeled_text_preserves_supplied_evidence(self):
        req = partner_request('主张：退款期限为七天；依据：退款期限为三天', default_claim_id='t')
        self.assertEqual(req.claim_text, '退款期限为七天')
        self.assertEqual(req.source_excerpt, '退款期限为三天')

    def test_nested_aliases(self):
        req = partner_request('{"payload":{"draft":"主张","context":"依据"}}', default_claim_id='t')
        self.assertEqual(req.claim_text, '主张')

    def test_malformed_or_unsupported_json_rejected(self):
        for text in ('{broken', '[]', 'null', '{"source":"oops","claim":"x"}',
                     '{"payload":{"source":[],"claim":"x"}}',
                     '{"schema_version":"2.0","answer":"x"}', ' ', 'x'*65537):
            with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                partner_request(text, default_claim_id='t')

    def test_legacy_payload_unchanged(self):
        raw = {'schema_version':'1.0', 'claim_id':'legacy', 'claim_text':'退款期限为七天',
               'source_excerpt':'服务说明：退款期限为七天。',
               'source':{'source_id':'provided:terms', 'title':'服务说明', 'locator':'第2段'}}
        req = partner_request(json.dumps(raw), default_claim_id='fallback')
        for _, kind, processor in CASES:
            new = json.loads(partner_product(kind, processor, req))
            self.assertEqual(new['payload'], json.loads(product_json(kind, processor(req)))['payload'])
            self.assertTrue(new['input_assessment']['evidence_provided'])

    def test_missing_material_never_supports_even_marker_claim(self):
        req = partner_request(MISSING_SOURCE_EXCERPT, default_claim_id='t')
        outputs = {kind:json.loads(partner_product(kind, processor, req)) for _, kind, processor in CASES}
        self.assertEqual(outputs['source-check']['payload']['status'], 'incomplete')
        grade = outputs['evidence-finding']
        self.assertEqual(grade['payload']['level'], 'unsupported')
        self.assertEqual(grade['payload']['confidence'], 0)
        self.assertFalse(grade['input_assessment']['inspection_performed'])
        scout = outputs['contradiction-check']
        self.assertFalse(scout['input_assessment']['inspection_performed'])
        self.assertIn('not-inspected', scout['payload']['indicators'][0])
        for output in outputs.values():
            self.assertIn('source_excerpt', output['input_assessment']['missing_fields'])
            self.assertFalse(output['input_assessment']['claim_verified'])


class FriendlyAipTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, app, text):
        client = AipRpcClient('http://offline.test/rpc', 'local-test',
            transport=httpx.ASGITransport(app=app), identity_binding_enabled=False)
        tid, sid = 'task-'+str(uuid.uuid4()), 'session-'+str(uuid.uuid4())
        try:
            started = await client.start_task(sid, text, task_id=tid)
            if started.status.state == TaskState.Failed:
                return started, None, tid
            self.assertEqual(started.status.state, TaskState.AwaitingCompletion)
            completed = await client.complete_task(tid, sid)
            self.assertEqual(completed.status.state, TaskState.Completed)
            output = read_product(completed.products)
            return completed, output, tid
        finally:
            await client.close()

    async def test_all_three_compact_and_labeled_inputs(self):
        for app, kind, _ in CASES:
            for text in ('{"claim":"退款期限为七天","evidence":"退款期限为三天"}',
                         '主张：退款期限为七天；依据：退款期限为三天'):
                with self.subTest(kind=kind, text=text):
                    _, output, tid = await self.invoke(app, text)
                    self.assertEqual(output['payload']['claim_id'], tid)
                    self.assertEqual(output['product_type'], kind)
                    self.assertTrue(output['input_assessment']['evidence_provided'])

    async def test_all_three_missing_material_is_explicit(self):
        for app, kind, _ in CASES:
            with self.subTest(kind=kind):
                _, output, _ = await self.invoke(app, '服务支持退款')
                self.assertFalse(output['input_assessment']['evidence_provided'])
                self.assertIn('source_excerpt', output['input_assessment']['missing_fields'])

    async def test_invalid_source_fails_as_request_not_server_error(self):
        for app, _, _ in CASES:
            result, _, _ = await self.invoke(app, '{"claim":"x","source":"invalid"}')
            self.assertEqual(result.status.state, TaskState.Failed)


if __name__ == '__main__':
    unittest.main()
