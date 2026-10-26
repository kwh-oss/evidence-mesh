import unittest
from evidence_mesh.message_result import assess_public_message, retrieval_progress


class MessageResultTests(unittest.TestCase):
    def test_conclusion_is_exact_model_text_and_keeps_bounds(self):
        review = {'coverage_complete':True, 'claims':[{'claim_span':'能力评价',
            'status':'opinion', 'explanation':'结论：不能依据这项成绩认定该评价。\n依据：材料记载考试存在协助。\n边界：不能推断完全没有能力。',
            'quotes':[{'source_id':'s','text':'考试存在协助。'}]}]}
        result = assess_public_message(review, {'sources':[{'source_id':'s',
            'url':'https://example.com/a','text':'考试存在协助。'}]})
        self.assertEqual(result['interpretation']['direct_answer'], '不能依据这项成绩认定该评价。')
        self.assertTrue(result['interpretation']['summary'].startswith('不能依据这项成绩认定该评价。'))
        self.assertIn('核对该评价所依赖的事实', result['interpretation']['summary'])
        self.assertNotIn('不能决定观点本身的真假', result['interpretation']['summary'])
        self.assertFalse(result['claim_verified'])
        self.assertIn('不能推断完全没有能力', result['claims'][0]['explanation'])
        review['coverage_complete']=False
        self.assertIsNone(assess_public_message(review, {'sources':[{'source_id':'s',
            'url':'https://example.com/a','text':'考试存在协助。'}]})['interpretation']['direct_answer'])

    def test_model_failure_is_not_material_insufficiency(self):
        retrieval={'search_complete':True, 'sources':[{'source_id':'s','url':'https://example.com/a','text':'正文'}]}
        for code, wording in [('model-budget-exhausted','额度已用尽'),
                              ('model-timeout','超时'), ('unknown-code','服务调用失败')]:
            result=assess_public_message({'failure_stage':'provider','failure_code':code}, retrieval)
            self.assertEqual(result['interpretation']['code'], 'analysis-failed')
            self.assertEqual(result['interpretation']['analysis_status'], 'failed')
            self.assertIn(wording,result['interpretation']['summary'])
            self.assertNotIn('不是对消息真假的判断',result['interpretation']['summary'])
            self.assertIsNone(result['interpretation']['direct_answer'])
        rejected=assess_public_message({'failure_stage':'output-validation'},retrieval)
        self.assertEqual(rejected['interpretation']['code'],'analysis-rejected')

    def test_uncertain_review_is_retained_as_completed_analysis(self):
        result = self.assessment(status='uncertain')
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['claims'][0]['status'], 'uncertain')
        self.assertEqual(result['interpretation']['code'], 'assessed-uncertain')
        self.assertNotIn('尚未完成内容核验', result['interpretation']['title'])
        self.assertFalse(result['claim_verified'])

    def test_uncertain_analysis_can_coexist_with_supported_facts_and_failed_page(self):
        review = {'coverage_complete': True, 'claims': [
            {'claim_span':'成绩说明', 'status':'supported', 'explanation':'仅材料支持',
             'quotes':[{'text':'记录中的说明', 'source_id':'s'}]},
            {'claim_span':'能力评价', 'status':'uncertain', 'explanation':'评价标准不明确', 'quotes':[]}]}
        result = assess_public_message(review, {'search_complete':True,
            'sources':[{'source_id':'s', 'url':'https://example.com/a', 'text':'记录中的说明'}],
            'failures':[{'stage':'page', 'reason':'insufficient-readable-text'}]})
        self.assertEqual(len(result['claims']), 2)
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['interpretation']['execution_status'], 'partial')
        self.assertEqual(result['interpretation']['code'], 'assessed-uncertain')
        self.assertEqual([r['status'] for r in result['claims']], ['supported', 'uncertain'])

    def test_uncertain_does_not_bypass_quote_validation(self):
        result = self.assessment(status='uncertain', source_id='invented')
        self.assertEqual(result['claims'], [])
        self.assertFalse(result['coverage_complete'])

    def test_failed_acquisition_and_empty_success_have_different_interpretations(self):
        failed = assess_public_message({}, {'search_complete': True, 'sources': [],
            'failures':[{'stage':'page','error_type':'SSLError'}]})['interpretation']
        empty = assess_public_message({}, {'search_complete': True, 'sources': []})['interpretation']
        self.assertEqual(failed['code'], 'execution-incomplete')
        self.assertEqual(failed['summary'], '本次未能读取相关正文，暂时无法核验。')
        self.assertEqual(empty['code'], 'no-evidence-found')
        self.assertEqual(failed['execution_status'], 'failed')
        self.assertIn('限定范围', empty['title'])
        self.assertEqual(empty['summary'], '本次检索暂未找到直接依据。')
        self.assertFalse(empty['claim_verified'])

    def test_background_material_unsupported_is_not_a_false_verdict_or_execution_failure(self):
        review = {'status':'model-suggestion', 'coverage_complete':True, 'claims':[
            {'claim_span':'会议期间会放假吗', 'status':'unsupported',
             'explanation':'材料只说明会议举办，未说明放假安排。',
             'quotes':[{'source_id':'s1','text':'会议将在本市举办。'}]}]}
        result = assess_public_message(review, {'search_complete':True,
            'sources':[{'source_id':'s1','url':'https://example.com/a','text':'会议将在本市举办。'}],
            'failures':[{'stage':'page','error_type':'TimeoutError'}]})
        item=result['interpretation']
        self.assertEqual(item['code'], 'no-direct-support')
        self.assertEqual(item['execution_status'], 'partial')
        self.assertIn('暂未找到支持该说法的直接依据', item['summary'])
        self.assertIn('部分搜索或网页读取失败', item['summary'])
        self.assertFalse(item['background_only_established'])
        self.assertEqual(result['claims'][0]['explanation'], review['claims'][0]['explanation'])

    def test_read_pages_without_valid_review_are_not_automatically_background(self):
        result=assess_public_message({'status':'failed-or-invalid'}, {'search_complete':True,
            'sources':[{'source_id':'s1','url':'https://example.com/a','text':'正文'}]})
        self.assertEqual(result['interpretation']['code'], 'material-not-assessed')
        self.assertFalse(result['interpretation']['background_only_established'])

    def test_counterevidence_requires_existing_anchored_claim_and_keeps_partial_scope(self):
        result=self.assessment(status='contradicted', coverage=False)
        self.assertEqual(result['interpretation']['code'], 'counterevidence')
        self.assertIn('模型建议', result['interpretation']['title'])
        self.assertIn('其余内容尚未完整核验', result['interpretation']['summary'])
        self.assertFalse(result['claim_verified'])
        invalid=self.assessment(status='contradicted', source_id='fabricated')
        self.assertEqual(invalid['interpretation']['code'], 'material-not-assessed')

    def test_overstatement_is_not_counterevidence(self):
        self.assertEqual(self.assessment(status='overstated')['interpretation']['code'], 'beyond-evidence')

    def test_no_sources_cannot_be_reported_as_read_material_even_with_unsupported_row(self):
        result=assess_public_message({'coverage_complete':True,'claims':[
            {'claim_span':'说法','status':'unsupported','explanation':'没有证据','quotes':[]}]},
            {'sources':[],'search_complete':True})
        self.assertEqual(result['interpretation']['code'], 'no-evidence-found')
        self.assertNotIn('已读到相关材料', result['interpretation']['summary'])

    def test_search_success_is_distinct_from_page_read_failure(self):
        result = retrieval_progress({'search_complete': True, 'search_diagnostics':[{},{}],
            'leads':[{}, {}, {}], 'sources':[], 'failures':[{'stage':'page','error_type':'SSLError'}]})
        self.assertIn('2轮联网搜索返回', result)
        self.assertIn('3个网页，取得0份可读正文', result)
        self.assertIn('候选网页读取失败', result)
        self.assertNotIn('未开启', result)

    def test_model_label_does_not_become_unqualified_whole_message_headline(self):
        # Live holiday case: supported label coexisted with explicit unknowns.
        review = {'coverage_complete': True, 'claims': [{'claim_span': '全年13天是否意味着春节13天？',
            'status': 'supported', 'explanation': '材料没有支持春节连续13天，生效日期无法确认。',
            'quotes': [{'text': '全年13天', 'source_id': 's1'}]}]}
        result = assess_public_message(review, {'sources': [{'source_id': 's1',
            'url': 'https://example.com/a', 'text': '全年13天'}]})
        self.assertEqual(result['status'], 'supported-by-material')
        self.assertFalse(result['interpretation']['claim_verified'])
        self.assertNotIn('支持这条消息的事实表述', result['headline'])
        self.assertFalse(result['claim_verified'])
        self.assertEqual(result['claims'][0]['explanation'], review['claims'][0]['explanation'])

    def test_search_failure_is_not_hidden_by_full_claim_coverage(self):
        review = {'coverage_complete': True, 'claims': [{'claim_span': '消息',
            'status': 'supported', 'explanation': '材料级解释',
            'quotes': [{'text': '引用', 'source_id': 's1'}]}]}
        retrieval = {'search_complete': False, 'sources': [{'source_id': 's1',
            'url': 'https://example.com/a', 'text': '引用'}]}
        result = assess_public_message(review, retrieval)
        self.assertTrue(result['coverage_complete'])
        self.assertFalse(result['search_complete'])
        self.assertEqual(result['status'], 'supported-by-material')
        self.assertTrue(any('未完成' in gap for gap in result['unresolved']))
        self.assertFalse(result['claim_verified'])

    def assessment(self, status='supported', coverage=True, sensitive=False, source_id='s1'):
        review = {'coverage_complete': coverage, 'claims': [{'claim_span': '消息原句',
            'status': status, 'explanation': '离线解释',
            'quotes': [{'text': '离线引文', 'source_id': source_id}]}]}
        return assess_public_message(review, {'sources': [{'source_id': 's1',
            'url': 'https://example.com/a', 'text': '正文：离线引文。', 'original_source_identified': False}]},
            {'sensitive_allegation': sensitive})

    def test_public_support_not_authenticated_fact(self):
        result = self.assessment()
        self.assertEqual(result['status'], 'supported-by-material')
        self.assertFalse(result['claim_verified'])
        self.assertIsNone(result['independent_source_count'])

    def test_partial_is_not_complete_verdict(self):
        self.assertEqual(self.assessment(coverage=False)['status'], 'partial')

    def test_private_allegation_not_verified_by_text_match(self):
        self.assertEqual(self.assessment(sensitive=True)['status'], 'unverified-sensitive')

    def test_unknown_quote_source_not_adopted(self):
        self.assertEqual(self.assessment(source_id='invented')['status'], 'unverified')

    def test_counterevidence_attributed_to_material(self):
        self.assertEqual(self.assessment(status='contradicted')['status'], 'contradicted-by-material')

    def test_no_model_rows_not_false(self):
        result = assess_public_message({'status': 'disabled'}, {'sources': []})
        self.assertEqual(result['status'], 'unverified')
        self.assertFalse(result['claim_verified'])

    def test_quote_must_exist_uniquely_in_actual_page(self):
        review = {'coverage_complete': True, 'claims': [{'claim_span': '消息', 'status': 'supported',
                  'explanation': '解释', 'quotes': [{'text': '引用', 'source_id': 's1'}]}]}
        for body in ('不含引文的正文', '引用和引用', '', None):
            result = assess_public_message(review, {'sources': [{'source_id': 's1', 'url': 'https://example.com/a', 'text': body}]})
            self.assertEqual(result['status'], 'unverified')
            self.assertFalse(result['coverage_complete'])

    def test_duplicate_source_identifier_rejected(self):
        review = {'coverage_complete': True, 'claims': [{'claim_span': '消息', 'status': 'supported',
                  'explanation': '解释', 'quotes': [{'text': '引用', 'source_id': 's1'}]}]}
        sources = [{'source_id': 's1', 'url': 'https://example.com/a', 'text': '引用'},
                   {'source_id': 's1', 'url': 'https://example.com/b', 'text': '引用'}]
        self.assertEqual(assess_public_message(review, {'sources': sources})['status'], 'unverified')

    def test_unknown_status_not_adopted(self):
        self.assertEqual(self.assessment(status='fact-certified')['status'], 'unverified')

    def test_malformed_rows_are_not_complete(self):
        result = assess_public_message({'coverage_complete': True, 'claims': [None, {'status': 'supported', 'quotes': 'bad'}]}, {'sources': []})
        self.assertEqual(result['status'], 'unverified')
