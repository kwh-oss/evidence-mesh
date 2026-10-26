import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

class WebTestBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        token = Path(cls.temp.name) / 'token.txt'
        token.write_text('a' * 40)
        cls.env = patch.dict(os.environ, {
            'WEB_TEST_TOKEN_FILE': str(token), 'WEB_TEST_LEADER_AIC': 'leader-aic',
            'WEB_TEST_CALLER_AIC': 'caller-aic', 'WEB_TEST_LEADER_URL': 'https://example.test/rpc',
            'WEB_TEST_PARTNERS': '{}', 'WEB_TEST_RECOVERY_DB':str(Path(cls.temp.name)/'recovery.sqlite3')})
        cls.env.start()
        with patch('evidence_mesh.runtime_config.build_client_ssl_context', return_value=None):
            cls.module = importlib.import_module('evidence_mesh.web_test_app')
        cls.client = TestClient(cls.module.app)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.temp.cleanup()

    def test_no_token_no_call(self):
        with patch.object(self.module, 'AipRpcClient') as client:
            self.assertEqual(self.client.post('/audit', json={}).status_code, 401)
            client.assert_not_called()

    def test_parallel_external_trace_keeps_both_peers(self):
        peers = [{'task_id': 'peer-task-' + str(i), 'partner_aic': 'peer-' + str(i),
                  'partner_name': '伙伴' + str(i), 'status': state}
                 for i, state in enumerate(('grounded-suggestions', 'pending'))]
        traces = self.module.partner_trace({'external_collaboration': {'reviews': peers}})
        external = [t for t in traces if t.get('external')]
        self.assertEqual(len(external), 2)
        self.assertEqual([p['status'] for p in external], ['grounded-suggestions', 'pending'])

    def test_wrong_origin(self):
        response = self.client.post('/audit', headers={'x-test-token': 'a'*40,
            'origin': 'https://evil.test'}, json={})
        self.assertEqual(response.status_code, 403)

    def test_bounded_input(self):
        response = self.client.post('/audit', headers={'x-test-token': 'a'*40}, content=b'x'*65537)
        self.assertEqual(response.status_code, 413)

    def test_invalid_input(self):
        response = self.client.post('/audit', headers={'x-test-token': 'a'*40}, content='not json')
        self.assertEqual(response.status_code, 422)

    def test_bridge_reads_metadata_and_legacy_passports(self):
        from acps_sdk.aip import Product, TextDataItem, TaskResult, TaskStatus, TaskState
        from evidence_mesh.product_presentation import readable_product_item
        passport = {'product_type': 'evidence-passport', 'answer': '结论：规则有例外。',
                    'task_ids': {'source-verifier': 'fixture-source-task'}}
        for item in (readable_product_item(passport), TextDataItem(text=json.dumps(passport))):
            result = TaskResult(id='fixture', sentAt='2026-10-20T00:00:00Z', senderRole='partner',
                senderId='leader-aic', taskId='fixture', status=TaskStatus(state=TaskState.Completed,
                stateChangedAt='2026-10-20T00:00:00Z'), products=[Product(id='p', dataItems=[item])])
            class Client:
                async def start_task(self, *args, **kwargs): return result
                async def close(self): pass
            with patch.object(self.module, 'AipRpcClient', return_value=Client()):
                response = self.client.post('/audit', headers={'x-test-token': 'a'*40},
                    json={'task_text': '规则是否有例外？'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['passport'], passport)

    def test_static_has_no_secret(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('a'*40, response.text)
        self.assertNotIn('PRIVATE KEY', response.text)
        self.assertIn('完整原始结果', response.text)
        self.assertEqual(self.client.get('/docs').status_code, 404)

    def test_batch_trace_preserves_each_actual_task(self):
        passport = {'claim_results': [
            {'claim_id': 'first', 'task_ids': {'source-verifier': 'actual-1'}},
            {'claim_id': 'second', 'task_ids': {'source-verifier': 'actual-2'}}]}
        with patch.object(self.module, 'PARTNERS', {'source-verifier': {'aic': 'registered-aic'}}):
            trace = self.module.partner_trace(passport)
        self.assertEqual([row['task_id'] for row in trace], ['actual-1', 'actual-2'])
        self.assertEqual([row['claim_id'] for row in trace], ['first', 'second'])

    def test_answer_is_primary_and_technical_details_collapsed(self):
        page = self.client.get('/').text
        self.assertLess(page.index('核验结果'), page.index('执行过程与任务身份'))
        self.assertIn('完整原始结果（技术详情）', page)
        self.assertNotIn('<details open', page)
        self.assertIn("el('answer').textContent", page)

    def test_message_entry_allows_missing_material(self):
        from evidence_mesh.contracts import request_from_caller_text, MISSING_SOURCE_EXCERPT
        message = '北京2024年课间安排是否适用于全国学校？'
        source = {'source_id': '', 'title': '', 'locator': ''}
        forwarded = self.module.caller_text({'task_text': message, 'source': source})
        parsed = request_from_caller_text(forwarded, default_claim_id='offline-message')
        self.assertEqual(parsed.claim_text, message)
        self.assertEqual(parsed.source_excerpt, MISSING_SOURCE_EXCERPT)
        page = self.client.get('/').text
        self.assertNotRegex(page, r'id="excerpt"[^>]*required')
        self.assertIn('不保证自动打开该链接', page)
        self.assertNotIn('localStorage', page)

    def test_full_task_preserves_exact_input_for_new_leader_parser(self):
        original = '政策原文：仓库验收后处理。 待核验客服回答：寄出后到账。'
        self.assertEqual(self.module.caller_text({'task_text': original}), original)
        for bad in ('', [], {}):
            with self.assertRaises(ValueError):
                self.module.caller_text({'task_text': bad})

    def test_full_task_preserves_material_and_explicit_source_date(self):
        from evidence_mesh.contracts import request_from_caller_text
        original = '原始材料：部门从未发布该通知。\n待核验帖子：2026年今天收到的通知不是部门发的。'
        source = {'source_id':'https://example.test/notice','title':'历史声明','locator':'2020-09-01'}
        text = self.module.caller_text({'task_text':original,'source':source,'claim_id':'test-id'})
        parsed = request_from_caller_text(text)
        self.assertEqual(parsed.claim_text,'2026年今天收到的通知不是部门发的。')
        self.assertEqual(parsed.source_excerpt,'部门从未发布该通知。')
        self.assertEqual(parsed.source.locator,'2020-09-01')
        self.assertEqual(parsed.claim_id,'test-id')
        self.assertEqual(self.module.caller_text({'task_text':original,'source':{}}),original)

    def test_invalid_source_metadata_rejected(self):
        for source in ([], {'locator':123}, {'title':{'private':'invalid'}}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.module.caller_text({'task_text':'原始材料：部分设备支持。\n待核验帖子：所有设备支持。','source':source})

    def result(self, state):
        from acps_sdk.aip import Product,TextDataItem,TaskResult,TaskStatus
        return TaskResult(id='fixture',sentAt='2026-10-21T00:00:00Z',senderRole='partner',
            senderId='leader-aic',taskId='fixture',status=TaskStatus(state=state,stateChangedAt='2026-10-21T00:00:00Z'),
            products=[Product(id='p',dataItems=[TextDataItem(text=json.dumps(
                {'product_type':'evidence-passport','answer':'不能直接等同。'}))])])

    def test_timeout_recovers_same_task_without_another_start(self):
        import httpx
        from acps_sdk.aip import TaskState
        outer=self;calls=[]
        class Client:
            async def start_task(self,sid,text,task_id):
                calls.append(('start',task_id,sid));raise httpx.ReadTimeout('fixture')
            async def get_task(self,task_id,sid):
                calls.append(('get',task_id,sid));return outer.result(TaskState.Completed)
            async def close(self):pass
        with patch.object(self.module,'AipRpcClient',return_value=Client()):
            response=self.client.post('/audit',headers={'x-test-token':'a'*40},json={'task_text':'零蔗糖就是无糖吗？'})
        value=response.json()
        self.assertEqual(value['state'],'completed');self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][1:],calls[1][1:])

    def test_pending_response_preserves_identity_and_completion_is_never_resent(self):
        import httpx
        from acps_sdk.aip import TaskState
        outer=self;counts={'start':0,'get':0,'complete':0}
        class Client:
            async def start_task(self,*a,**kw):counts['start']+=1;raise httpx.ReadTimeout('fixture')
            async def get_task(self,*a):
                counts['get']+=1
                state=TaskState.Working if counts['get']==1 else TaskState.AwaitingCompletion if counts['get']<=3 else TaskState.Completed
                return outer.result(state)
            async def complete_task(self,*a):counts['complete']+=1;raise httpx.ReadTimeout('unknown completion')
            async def close(self):pass
        with patch.object(self.module,'AipRpcClient',return_value=Client()):
            value=self.client.post('/audit',headers={'x-test-token':'a'*40},json={'task_text':'只有短问题'}).json()
            self.assertEqual(value['state'],'pending');self.assertTrue(value['leader_task_id'])
            url=value['recovery_url']
            for _ in range(2):self.assertEqual(self.client.post(url,headers={'x-test-token':'a'*40}).json()['state'],'pending')
            self.assertEqual(self.client.post(url,headers={'x-test-token':'a'*40}).json()['state'],'completed')
            self.client.post(url,headers={'x-test-token':'a'*40})
        self.assertEqual(counts,{'start':1,'get':4,'complete':1})

    def test_recovery_requires_original_authorization_and_known_task(self):
        with patch.object(self.module,'AipRpcClient') as factory:
            self.assertEqual(self.client.post('/audit/unknown/resume').status_code,401)
            self.assertEqual(self.client.post('/audit/unknown/resume',headers={'x-test-token':'a'*40,'origin':'https://evil.test'}).status_code,403)
            self.assertEqual(self.client.post('/audit/unknown/resume',headers={'x-test-token':'a'*40}).status_code,404)
            factory.assert_not_called()

    def test_httpx_hook_overrides_sdk_30_seconds_without_replacing_transport(self):
        import asyncio,httpx
        from acps_sdk.aip.aip_rpc_client import AipRpcClient
        observed=[]
        async def handler(request):
            observed.append(request.extensions['timeout']['read'])
            if observed[-1]<35:raise httpx.ReadTimeout('32 second task would time out')
            return httpx.Response(200,json={'fixture':True})
        async def run():
            client=AipRpcClient('https://example.test/rpc','caller-aic',expected_partner_aic='leader-aic',transport=httpx.MockTransport(handler))
            with patch.object(self.module,'AipRpcClient',return_value=client):
                self.assertIs(self.module.make_aip_client(),client)
                response=await client.http_client.post('https://example.test/rpc',json={},timeout=30)
                self.assertEqual(response.status_code,200)
                self.assertTrue(client._identity_binding_enabled)
            await client.close()
        asyncio.run(run());self.assertEqual(observed,[75])

    def test_recovery_store_survives_reopen(self):
        from evidence_mesh.web_task_recovery import WebTaskRecovery
        store=WebTaskRecovery(Path(self.temp.name)/'durable.sqlite3')
        store.register('original','session',False)
        self.assertTrue(store.claim_completion('original'))
        reopened=WebTaskRecovery(store.path)
        self.assertEqual(reopened.read('original')['session'],'session')
        self.assertFalse(reopened.claim_completion('original'))

if __name__ == '__main__':
    unittest.main()


    def test_completed_root_with_pending_children_is_recoverable_not_frozen_in_cache(self):
        from acps_sdk.aip import TaskState,TextDataItem
        outer=self;calls=[]
        pending={'product_type':'evidence-passport','decision_scope':'external-consultation',
            'consultation_status':'pending','answer':'外部尚在运行',
            'external_collaboration':{'reviews':[{'aip_state':'working'}]}}
        done={**pending,'consultation_status':'completed','answer':'外部最终答复',
            'external_collaboration':{'reviews':[{'aip_state':'completed'}]}}
        def result(body):
            value=outer.result(TaskState.Completed)
            value.products[0].dataItems=[TextDataItem(text=json.dumps(body))]
            return value
        class Client:
            async def start_task(self,*a,**k):calls.append('start');return result(pending)
            async def get_task(self,*a):calls.append('get');return result(done)
            async def close(self):pass
        with patch.object(self.module,'AipRpcClient',return_value=Client()):
            first=self.client.post('/audit',headers={'x-test-token':'a'*40},json={'task_text':'查询民法典第五百零九条原文。'}).json()
            self.assertEqual(first['state'],'pending');self.assertTrue(first['recoverable'])
            entry=self.module.recovery.read(first['leader_task_id'])
            self.assertIsNone(entry['result'])
            # Old releases may have cached such a pending passport as complete.
            self.module.recovery.finish(entry['task'],{**first,'state':'completed'})
            final=self.client.post(first['recovery_url'],headers={'x-test-token':'a'*40}).json()
            self.assertEqual(final['state'],'completed')
            self.assertEqual(final['passport']['answer'],'外部最终答复')
            cached=self.client.post(first['recovery_url'],headers={'x-test-token':'a'*40}).json()
            self.assertEqual(cached['passport']['answer'],'外部最终答复')
        self.assertEqual(calls,['start','get'])
