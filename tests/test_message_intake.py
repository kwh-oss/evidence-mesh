import json
import unittest
from unittest.mock import AsyncMock, patch
from evidence_mesh.message_intake import assess_message
from evidence_mesh.source_partner import source_product
from evidence_mesh.contracts import request_from_caller_text, request_json
from evidence_mesh.leader import PartnerTarget, audit_claim


class IntakeTests(unittest.TestCase):
    def test_bare_truth_question_requires_a_referent(self):
        for text in ('这是真的吗？','是真的吗','这个靠谱吗？','请问这条消息是否属实？','帮我看看这个视频真的假的'):
            with self.subTest(text=text):
                value=assess_message(text)
                self.assertTrue(value['clarification_required'])
                self.assertIn('missing-claim-or-referent',value['ambiguity_reasons'])
                self.assertIn('具体说法',value['questions'][0])

    def test_specific_claim_or_explicit_link_is_not_bare_reference(self):
        for text in ('零蔗糖就是无糖吗？','Transformer最早出自哪篇论文？','北京课间十五分钟是真的吗？',
                     '什么是“这是真的吗”栏目？','这是真的吗？原文：https://example.com/post'):
            self.assertFalse(assess_message(text)['clarification_required'])
        self.assertFalse(assess_message('这是真的吗？',provided_link=True)['clarification_required'])

    def test_introductory_pronoun(self):
        for text in ('我刷到他被捕是真的吗', '据说她涉嫌诈骗', '听说他出轨了'):
            with self.subTest(text=text):
                self.assertTrue(assess_message(text)['clarification_required'])

    def test_embedded_vague_person(self):
        self.assertTrue(assess_message('我看到消息称，某博主涉嫌诈骗，是真的吗？')['clarification_required'])

    def test_nickname_relationship_allegation_needs_account(self):
        result = assess_message('最近刷到百万博主叮当猫被女友带了绿帽子，这消息真的吗？')
        self.assertTrue(result['clarification_required'])
        self.assertIn('role-or-nickname-not-unique-account', result['ambiguity_reasons'])

    def test_link_permits_search_but_does_not_authenticate_identity(self):
        result = assess_message('博主叮当猫出轨是真的吗？原帖 https://example.com/post/1')
        self.assertFalse(result['clarification_required'])
        self.assertFalse(result['entity_identity_resolved'])
        self.assertFalse(result['claim_verified'])

    def test_other_is_not_pronoun(self):
        self.assertFalse(assess_message('北京其他被调整的学校有哪些')['clarification_required'])

    def test_more_relative_dates_remain_unresolved(self):
        result = assess_message('去年传过的消息，今年近日又出现了')
        self.assertTrue(result['relative_time_unresolved'])
        self.assertEqual(set(result['relative_time_expressions']), {'去年', '今年', '近日'})

    def test_vague_subject_requires_clarification(self):
        self.assertTrue(assess_message('某博主被捕是真的吗')['clarification_required'])

    def test_specific_public_policy_not_blocked(self):
        self.assertFalse(assess_message('北京课间十五分钟是真的吗')['clarification_required'])

    def test_relative_time_is_not_event_date(self):
        result = assess_message('最近叮当猫出轨是真的吗')
        self.assertTrue(result['relative_time_unresolved'])
        self.assertTrue(result['sensitive_allegation'])
        self.assertFalse(result['entity_identity_resolved'])
        self.assertFalse(result['claim_verified'])


class IntakeFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_bare_question_skips_search_and_downstream_analysis(self):
        request=request_from_caller_text('这是真的吗？',default_claim_id='bare-reference')
        collector=AsyncMock()
        product=json.loads(await source_product(request,collector))
        collector.collect.assert_not_awaited()
        targets=[PartnerTarget(n,'http://unused.test/rpc') for n in
                 ('source-verifier','evidence-grader','contradiction-scout')]
        call=AsyncMock(return_value={'task_id':'source-only','state':'completed','product':product})
        reviewer=AsyncMock()
        with patch('evidence_mesh.leader._call_partner',call):
            value=await audit_claim(request_json(request),targets,semantic_reviewer=reviewer)
        self.assertEqual(call.await_count,1)
        reviewer.review.assert_not_awaited()
        self.assertEqual(value['decision_scope'],'clarification-only')
        self.assertIn('具体说法',value['answer'])

    async def test_clarification_without_configured_search(self):
        request = request_from_caller_text('我刷到他被捕是真的吗', default_claim_id='offline')
        with patch('evidence_mesh.source_partner.configured_collector', side_effect=RuntimeError('must not configure search')) as configured:
            result = json.loads(await source_product(request))
        configured.assert_not_called()
        self.assertEqual(result['retrieval']['status'], 'needs-clarification')

    async def test_supplied_material_retains_old_flow(self):
        request = request_from_caller_text('主张：某博主涉嫌诈骗；原文：这条材料没有确认该指控。', default_claim_id='offline')
        collector = AsyncMock()
        result = json.loads(await source_product(request, collector))
        collector.collect.assert_not_awaited()
        self.assertNotIn('retrieval', result)

    async def test_no_network_request_keeps_opt_out(self):
        from dataclasses import replace
        request = replace(request_from_caller_text('我刷到他被捕是真的吗', default_claim_id='offline'), constraints=('不联网',))
        collector = AsyncMock()
        result = json.loads(await source_product(request, collector))
        collector.collect.assert_not_awaited()
        self.assertEqual(result['retrieval']['status'], 'not-requested')

    async def test_sensitive_nickname_does_not_query_before_account_clarification(self):
        collector = AsyncMock()
        request = request_from_caller_text('最近刷到百万博主叮当猫被女友带了绿帽子，这消息真的吗？', default_claim_id='offline')
        result = json.loads(await source_product(request, collector))
        collector.collect.assert_not_awaited()
        self.assertEqual(result['retrieval']['status'], 'needs-clarification')

    async def test_leader_does_not_grade_or_call_model_before_clarification(self):
        request = request_from_caller_text('那个人出轨是真的吗', default_claim_id='offline')
        product = json.loads(await source_product(request, AsyncMock()))
        targets = [PartnerTarget(name, 'http://unused.test/rpc') for name in
                   ('source-verifier', 'evidence-grader', 'contradiction-scout')]
        call = AsyncMock(return_value={'task_id': 'offline-source-task',
                                     'state': 'completed', 'product': product})
        reviewer = AsyncMock()
        with patch('evidence_mesh.leader._call_partner', call):
            result = await audit_claim(request_json(request), targets, semantic_reviewer=reviewer)
        self.assertEqual(call.await_count, 1)
        self.assertEqual(call.await_args.args[0].name, 'source-verifier')
        reviewer.review.assert_not_awaited()
        self.assertTrue(result['clarification_required'])
        self.assertEqual(result['decision_scope'], 'clarification-only')
        self.assertEqual(set(result['task_ids']), {'source-verifier'})
        self.assertIn('尚未检索或核验', result['answer'])

    async def test_clarification_does_not_send_query(self):
        collector = AsyncMock()
        request = request_from_caller_text('那个人出轨是真的吗', default_claim_id='offline')
        result = json.loads(await source_product(request, collector))
        collector.collect.assert_not_awaited()
        self.assertEqual(result['retrieval']['status'], 'needs-clarification')


if __name__ == '__main__':
    unittest.main()
