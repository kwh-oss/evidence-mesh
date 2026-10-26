import json
import unittest
from acps_sdk.aip import Product, TextDataItem, TaskResult, StructuredDataItem
from evidence_mesh.product_presentation import readable_product_item, read_product
from evidence_mesh.contracts import request_from_caller_text
from evidence_mesh.partner_input import partner_product
from evidence_mesh.processors import grade_evidence


class ProductPresentationTests(unittest.TestCase):
    def test_wire_roundtrip_preserves_machine_fields_without_json_text(self):
        value = {'product_type': 'contradiction-check', 'answer': '结论：有明确冲突。',
                 'semantic_conflict': {'status': 'model-suggestion'},
                 'collaboration': {'standalone_callable': True}}
        product = Product(id='test', dataItems=[readable_product_item(value)])
        decoded = Product.model_validate_json(product.model_dump_json())
        self.assertEqual(decoded.dataItems[0].text, value['answer'])
        self.assertEqual(read_product([decoded]), value)

    def test_legacy_json_and_standard_structured_items_still_readable(self):
        value = {'product_type': 'evidence-finding', 'payload': {'level': 'conditional'}}
        for item in (TextDataItem(text=json.dumps(value)), StructuredDataItem(data=value)):
            self.assertEqual(read_product([Product(id='test', dataItems=[
                TextDataItem(text='面向用户的摘要'), item])]), value)
        with self.assertRaises(ValueError):
            read_product([Product(id='test', dataItems=[TextDataItem(text='只有摘要')])])

    def test_grader_abstention_describes_its_own_scope(self):
        request = request_from_caller_text(json.dumps({'claim_text': '所有人免费入场',
            'source_excerpt': '仅学生免费入场'}), default_claim_id='test')
        product = json.loads(partner_product('evidence-finding', grade_evidence, request))
        self.assertIn('初筛未得出结论', product['answer'])
        self.assertIn('仍需语义分析', product['answer'])
        self.assertTrue(product['input_assessment']['inspection_performed'])
        self.assertFalse(product['input_assessment']['claim_verified'])


class SemanticPresentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_leader_reads_completed_wire_metadata(self):
        from unittest.mock import patch
        from acps_sdk.aip import TaskState, TaskStatus
        from evidence_mesh.leader import PartnerTarget, _call_partner
        value = {'product_type':'evidence-finding','answer':'初筛未得出结论', 'input_assessment':{'evidence_provided':True}}
        def result(state):
            return TaskResult.model_validate_json(TaskResult(id='reply',sentAt='2026-10-19T00:00:00Z',senderRole='partner',senderId='test-partner',taskId='task',status=TaskStatus(state=state,stateChangedAt='2026-10-19T00:00:00Z'),products=[Product(id='result',dataItems=[readable_product_item(value)])]).model_dump_json())
        class Client:
            closed=False
            async def start_task(self,*args,**kwargs): return result(TaskState.AwaitingCompletion)
            async def complete_task(self,*args): return result(TaskState.Completed)
            async def close(self): self.closed=True
        client=Client()
        with patch('evidence_mesh.leader.AipRpcClient',return_value=client):
            reply=await _call_partner(PartnerTarget('grader','http://test/rpc'),'test')
        self.assertEqual(reply['product'],value)
        self.assertEqual(reply['state'],'completed')
        self.assertTrue(client.closed)

    async def test_readable_rpc_product_survives_start_complete(self):
        import httpx, uuid
        from unittest.mock import patch
        from acps_sdk.aip.aip_rpc_client import AipRpcClient
        from evidence_mesh.aip_partner import build_partner_app
        with patch.dict('os.environ',{'AIP_IDENTITY_BINDING_ENABLED':'false','AMP_ENABLED':'false','GROUP_ENABLED':'false'}):
            app=build_partner_app(service_name='evidence-grader',product_type='evidence-finding',processor=grade_evidence)
        client=AipRpcClient('http://test/rpc','test-leader',transport=httpx.ASGITransport(app=app),identity_binding_enabled=False)
        try:
            session=str(uuid.uuid4())
            started=await client.start_task(session,json.dumps({'claim_text':'所有人免费入场','source_excerpt':'仅学生免费入场'}))
            completed=await client.complete_task(started.taskId,session)
            value=read_product(completed.products)
            self.assertEqual(value['product_type'],'evidence-finding')
            self.assertEqual(completed.products[0].dataItems[0].text,value['answer'])
            self.assertFalse(completed.products[0].dataItems[0].text.startswith('{'))
        finally: await client.close()

    async def test_conclusion_first_preserves_exact_quotes_and_boundary(self):
        from evidence_mesh.semantic_conflict import semantic_conflict_product
        from test_semantic_conflict_partner import row, Reviewer
        claim, material = '所有人免费入场', '仅学生免费入场'
        result = row(claim, material)
        result['findings'][0]['explanation'] = 'claim包含非学生免费，而material只允许学生免费，两者冲突。'
        req = request_from_caller_text(json.dumps({'claim_text': claim, 'source_excerpt': material}), default_claim_id='test')
        product = json.loads(await semantic_conflict_product(req, Reviewer(result)))
        answer = product['answer']
        self.assertTrue(answer.startswith('结论：有明确冲突。'))
        self.assertIn('所有人免费入场', answer)
        self.assertIn('仅学生免费入场', answer)
        self.assertNotIn('claim', answer)
        self.assertNotIn('material', answer)
        self.assertIn('结论：', answer)
        self.assertEqual(product['semantic_conflict']['findings'][0]['relation'], 'clear-conflict')
