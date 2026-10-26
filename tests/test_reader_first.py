import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from acps_sdk.aip import TextDataItem, Product, TaskResult, TaskStatus, TaskState
from evidence_mesh.collaboration_input import command_text, retrieval_request
from evidence_mesh.partner_input import partner_request
from evidence_mesh.contracts import MISSING_SOURCE_EXCERPT
from evidence_mesh.result_presentation import leader_answer, present_passport
from evidence_mesh.product_presentation import readable_product_item, read_product


def handoff(text):
    return partner_request(command_text(SimpleNamespace(dataItems=[TextDataItem(text=text)])), default_claim_id='fixture')


def passport():
    return {'product_type': 'evidence-passport', 'decision': 'conflicting',
        'checked_claim': '活动对所有人免费吗？',
        'semantic_review': {'status': 'model-suggestion', 'coverage_complete': True, 'claims': [{
            'claim_span': '活动对所有人免费吗？', 'kind': 'fact', 'status': 'contradicted',
            'explanation': '结论：不是，免费仅限登记会员。\n依据：规则排除了非会员。\n边界：仅适用于这次活动。',
            'quotes': [{'text': '仅登记会员免费，其他人需购票。', 'source_id': 'p1'}]}]},
        'public_retrieval': {'sources': [{'source_id': 'p1', 'title': '活动规则',
            'url': 'https://example.com/rules', 'text': '仅登记会员免费，其他人需购票。'}]},
        'answer': '旧的执行信息和规则输出', 'task_ids': {'source-verifier': 'private-debug-id'}}


class ReaderFirstTests(unittest.TestCase):
    def test_ingress_makes_quoted_comparison_explicit_before_legacy_contract_parser(self):
        question = '广告写着“终身免费”，条款却写“仅首年免费”，这两句话矛盾吗？'
        for suffix in ('', '\nDAG 指定的上游产物摘要：叮当已开始执行。'):
            raw = command_text(SimpleNamespace(dataItems=[TextDataItem(text=question + suffix)]))
            parsed = json.loads(raw)
            self.assertEqual(parsed['claim_text'], '终身免费')
            self.assertEqual(parsed['source_excerpt'], '仅首年免费')
            self.assertEqual(parsed['task_type'], 'cross_text_conflict')
            self.assertEqual(parsed['source']['source_id'], 'caller:quoted-comparison')

    def test_review_assignment_retains_upstream_text_without_certifying_it(self):
        report = ('结论：有明确冲突。\n待核对说法：终身免费\n'
                  '对照材料：仅首年免费\n以上为所提供文字的语义比较。')
        req = handoff('在语义判断之外，补充宣传承诺与条款一致性的证据审查环节，说明结论边界。'
                      '\nDAG 指定的上游产物摘要：' + report)
        retained, context = retrieval_request(req)
        self.assertEqual(retained.source_excerpt, req.source_excerpt)
        self.assertIn('仅首年免费', retained.source_excerpt)
        self.assertTrue(context['used_as_supplied_material'])
        self.assertFalse(context['used_as_primary_evidence'])
        self.assertEqual(retained.source.source_id, 'caller:upstream-report')

    def test_review_request_does_not_disable_explicit_original_source_acquisition(self):
        req = handoff('审查现有材料，并联网核实出处。\nDAG 指定的上游产物摘要：见 https://example.com/rules。')
        retained, context = retrieval_request(req)
        self.assertEqual(retained.source_excerpt, MISSING_SOURCE_EXCERPT)
        self.assertEqual(context['seed_url'], 'https://example.com/rules')

    def test_long_flattened_report_is_material_not_many_claims(self):
        question = '我想知道，活动是不是每周一都关闭？'
        report = '\n'.join('| 项目%d | 仅登记会员免费，其他人需购票。 |' % i for i in range(25))
        req = handoff(question + '\n\nDAG 指定的上游产物摘要：\n' + report)
        self.assertEqual(req.claim_text, question)
        self.assertIn(report, req.source_excerpt)
        self.assertEqual(req.source.source_id, 'caller:upstream-report')

    def test_scheduler_status_is_not_evidence_and_quoted_marker_not_cut(self):
        req = handoff('活动对所有人免费吗？ DAG 指定的上游产物摘要：叮当已完成协作规划并开始按 DAG 派发。')
        self.assertEqual(req.claim_text, '活动对所有人免费吗？')
        self.assertEqual(req.source_excerpt, MISSING_SOURCE_EXCERPT)
        text = '帮我解释“术语 DAG 指定的上游产物摘要：例子”'
        self.assertEqual(handoff(text).claim_text, text)

    def test_explicit_evidence_wins_and_single_item_size_limit(self):
        text = json.dumps({'claim_text': '全部免费', 'source_excerpt': '仅学生免费'})
        req = handoff(text + '\nDAG 指定的上游产物摘要：另外报告声称全部免费。')
        self.assertEqual(req.source_excerpt, '仅学生免费')
        self.assertIsNone(retrieval_request(req)[1])
        with self.assertRaises(ValueError):
            handoff('x' * 65537)

    def test_upstream_link_is_fetch_lead_not_primary_evidence(self):
        req = handoff('活动免费吗？\nDAG 指定的上游产物摘要：报告称免费，见 https://example.com/rules。')
        request, context = retrieval_request(req)
        self.assertEqual(request.source_excerpt, MISSING_SOURCE_EXCERPT)
        self.assertEqual(request.source.locator, 'https://example.com/rules')
        self.assertFalse(context['used_as_primary_evidence'])
        for url in ('https://127.0.0.1/private', 'https://169.254.169.254/metadata'):
            req = handoff('活动免费吗？\nDAG 指定的上游产物摘要：见 ' + url)
            self.assertEqual(retrieval_request(req)[0].source.locator, '')

    def test_reader_gets_direct_answer_links_and_no_debug(self):
        result = present_passport(passport())
        answer = result['answer']
        self.assertTrue(answer.startswith('结论：不是，免费仅限登记会员。'))
        self.assertIn('https://example.com/rules', answer)
        self.assertIn('仅登记会员免费，其他人需购票。', answer)
        self.assertNotIn('旧的执行信息', answer)
        self.assertNotIn('private-debug-id', answer)
        self.assertNotIn('task_ids', answer)
        wire = Product.model_validate_json(Product(id='p', dataItems=[readable_product_item(result)]).model_dump_json())
        machine = read_product([wire])
        self.assertEqual(machine['task_ids'], result['task_ids'])
        self.assertEqual(machine['technical_answer'], '旧的执行信息和规则输出')

    def test_failure_is_not_packaged_as_success_partial_and_sensitive_preserved(self):
        value = passport()
        value['semantic_review'] = {'status': 'input-limit', 'reason': '结构拆分超过范围。'}
        answer = leader_answer(value)
        self.assertIn('未得出核验结论', answer)
        self.assertIn('结构拆分超过范围', answer)
        self.assertNotIn('不是，免费', answer)
        value = passport()
        value['semantic_review']['coverage_complete'] = False
        value['semantic_review']['unreviewed_spans'] = ['后半段']
        self.assertIn('尚未核验：后半段', leader_answer(value))
        value['message_assessment'] = {'status': 'unverified-sensitive', 'interpretation': {'summary': '不能可靠确认该指控。'}}
        self.assertEqual(leader_answer(value), '不能可靠确认该指控。')

    def test_untrusted_report_quotes_and_markdown_not_authenticated(self):
        value = passport()
        value.pop('public_retrieval')
        value['partner_products'] = {'grader': {'collaboration': {'material_origin': 'caller-upstream-unverified'}}}
        value['semantic_review']['claims'][0]['quotes'][0]['text'] = '![图](https://bad.example/image) <script>'
        text = leader_answer(value)
        self.assertIn('上游报告', text)
        self.assertNotIn('![图]', text)
        self.assertNotIn('<script>', text)

    def test_unreviewed_rewrite_is_retained_for_audit_not_displayed(self):
        value = passport()
        value['semantic_review']['claims'][0]['suggested_wording'] = '所有人免费，包括收费人群。'
        result = present_passport(value)
        self.assertNotIn('所有人免费，包括收费人群', result['answer'])
        self.assertEqual(result['semantic_review']['claims'][0]['suggested_wording'], '所有人免费，包括收费人群。')
        self.assertIn('不是，免费仅限登记会员', result['answer'])

    def test_inline_conclusion_evidence_and_boundary_are_separate(self):
        value = passport()
        value['semantic_review']['claims'][0]['explanation'] = '结论：并非全部免费。依据：仅会员免费。边界：限本次活动。'
        answer = leader_answer(value)
        self.assertTrue(answer.startswith('结论：并非全部免费。\n\n依据：仅会员免费。'))
        self.assertIn('适用条件：限本次活动。', answer)


class ReaderFirstAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_leader_plain_quoted_comparison_is_material_not_search_query(self):
        import httpx, uuid
        from acps_sdk.aip.aip_rpc_client import AipRpcClient
        from evidence_mesh.leader_app import app
        client = AipRpcClient('http://test/rpc', 'fixture-caller', transport=httpx.ASGITransport(app=app), identity_binding_enabled=False)
        try:
            task = 'quoted-' + str(uuid.uuid4())
            text = '广告写着“终身免费”，条款却写“仅首年免费”，这两句话矛盾吗？'
            with patch('evidence_mesh.leader_app.audit_claim', new_callable=AsyncMock, return_value=passport()) as audit:
                await client.start_task(task, text, task_id=task)
                req = json.loads(audit.await_args.args[0])
                self.assertEqual(req['claim_text'], '终身免费')
                self.assertEqual(req['source_excerpt'], '仅首年免费')
                self.assertEqual(req['task_type'], 'cross_text_conflict')
                await client.complete_task(task, task)
        finally:
            await client.close()

    async def test_leader_review_assignment_passes_report_to_audit(self):
        import httpx, uuid
        from acps_sdk.aip.aip_rpc_client import AipRpcClient
        from evidence_mesh.leader_app import app
        client = AipRpcClient('http://test/rpc', 'fixture-caller', transport=httpx.ASGITransport(app=app), identity_binding_enabled=False)
        try:
            task = 'review-' + str(uuid.uuid4())
            text = ('补充宣传承诺与条款一致性的证据审查，说明结论边界。'
                    '\nDAG 指定的上游产物摘要：'
                    '待核对说法：终身免费\n对照材料：仅首年免费\n两句期限不同。')
            with patch('evidence_mesh.leader_app.audit_claim', new_callable=AsyncMock, return_value=passport()) as audit:
                started = await client.start_task(task, text, task_id=task)
                req = json.loads(audit.await_args.args[0])
                self.assertIn('仅首年免费', req['source_excerpt'])
                self.assertNotEqual(req['source_excerpt'], MISSING_SOURCE_EXCERPT)
                self.assertEqual(started.status.state, TaskState.AwaitingCompletion)
                final = await client.complete_task(task, task)
                value = read_product(final.products)
                self.assertTrue(value['upstream_handoff']['used_as_supplied_material'])
                self.assertFalse(value['upstream_handoff']['used_as_primary_evidence'])
        finally:
            await client.close()

    async def test_real_leader_protocol_parser_readable_wire_and_completion(self):
        import httpx, uuid
        from acps_sdk.aip.aip_rpc_client import AipRpcClient
        from evidence_mesh.leader_app import app
        client = AipRpcClient('http://test/rpc', 'fixture-caller', transport=httpx.ASGITransport(app=app), identity_binding_enabled=False)
        try:
            question = '活动对所有人免费吗？'
            task = 'reader-' + str(uuid.uuid4())
            with patch('evidence_mesh.leader_app.audit_claim', new_callable=AsyncMock, return_value=passport()) as audit:
                started = await client.start_task(task, question + '\nDAG 指定的上游产物摘要：' + '\n'.join('其他报道段落%d' % i for i in range(25)), task_id=task)
                req = json.loads(audit.await_args.args[0])
                self.assertEqual(req['claim_text'], question)
                self.assertEqual(req['source_excerpt'], MISSING_SOURCE_EXCERPT)
                self.assertEqual(started.status.state, TaskState.AwaitingCompletion)
                final = await client.complete_task(task, task)
                value = read_product(final.products)
                self.assertTrue(value['answer'].startswith('结论：不是'))
                self.assertFalse(value['upstream_handoff']['used_as_primary_evidence'])
                self.assertEqual(len(final.products), 1)
                self.assertEqual(final.products[0].dataItems[0].text, value['answer'])
        finally:
            await client.close()

    async def test_upstream_source_fetches_original_question_and_report_link(self):
        from evidence_mesh.source_partner import source_product
        collector = AsyncMock()
        collector.collect.return_value = {'status': 'retrieved', 'sources': [{'source_id': 'p',
            'title': '规则', 'url': 'https://example.com/rules', 'text': '仅登记会员免费，其他人需购票。'}]}
        req = handoff('活动免费吗？\nDAG 指定的上游产物摘要：报告称免费 https://example.com/rules。')
        result = json.loads(await source_product(req, collector))
        collector.collect.assert_awaited_once_with('活动免费吗？', seed_urls=('https://example.com/rules',))
        self.assertIn('仅登记会员免费', result['answer'])
        self.assertNotIn('已读文本字符', result['answer'])
        self.assertFalse(result['upstream_handoff']['used_as_primary_evidence'])
