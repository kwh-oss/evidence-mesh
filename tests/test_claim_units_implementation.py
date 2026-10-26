import copy
import json
import unittest
from evidence_mesh.claim_units import prepare_review_units
from evidence_mesh.semantic_review import validate_partial_review, run_semantic_review
from test_spread_semantic_workflow import review_v11


class UnitTests(unittest.TestCase):
    def test_question_premise_and_instruction_are_distinct_exact_spans(self):
        post = '全年假日13天，是否意味着春节连续13天？请根据原文分别核对；查不到的部分保留未知。'
        units = prepare_review_units(post)
        self.assertEqual([u['relation'] for u in units],
                         ['statement', 'inference-question', 'task-instruction'])
        self.assertEqual(units[1]['premise_unit_id'], 'unit-1')
        for unit in units:
            self.assertEqual(post[unit['start']:unit['end']], unit['text'])
        value = review_v11()
        value['claims'][0].update(claim_span=post, status='supported',
                                 quotes=[{'text':'全年假日13天。'}])
        result = validate_partial_review(value, post, '全年假日13天。')
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['claims'], [])
        self.assertEqual(result['rejected_claims'][0]['reason_code'], 'instruction-boundary')

    def test_separate_rows_can_cover_claims_without_reviewing_task_instruction(self):
        post = '全年假日13天，是否意味着春节连续13天？请根据原文核对。'
        units = prepare_review_units(post)
        rows = []
        for unit in units[:2]:
            row = copy.deepcopy(review_v11()['claims'][0])
            row.update(claim_span=unit['text'], status='unsupported',
                       quotes=[], suggested_wording=None)
            rows.append(row)
        result = validate_partial_review({'schema_version':'1.1','claims':rows}, post, '全年假日13天。')
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(len(result['claims']), 2)
        self.assertEqual(result['unreviewed_spans'], [])

    def test_polite_words_inside_quote_are_not_ignored_as_instructions(self):
        post = '公告写道“请根据实际情况申请”，是否意味着保证获批？'
        self.assertFalse(any(u['relation']=='task-instruction' for u in prepare_review_units(post)))

    def test_explicit_unknown_date_cannot_keep_supported_label(self):
        claim = '2025年1月1日起全年假日13天。'
        value = review_v11()
        value['claims'][0].update(claim_span=claim, status='supported',
            quotes=[{'text':'全年假日13天。'}], explanation='该时间点无法据此确认。', suggested_wording=None)
        result = validate_partial_review(value, claim, '全年假日13天。')
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['rejected_claims'][0]['reason_code'], 'support-boundary')
        value['claims'][0]['explanation']='原文明确记载2025年1月1日生效。'
        self.assertTrue(validate_partial_review(value, claim, '全年假日13天。')['coverage_complete'])

    def test_split_preserves_exact_positions_and_premise_link(self):
        post = '北京出台安排，所以全国所有学校必须执行。普通高中可参考，因此所有高中必须执行。'
        units = prepare_review_units(post)
        self.assertEqual(len(units), 4)
        for unit in units:
            self.assertEqual(unit['text'], post[unit['start']:unit['end']])
        self.assertEqual(units[1]['premise_unit_id'], 'unit-1')
        self.assertEqual(units[3]['premise_unit_id'], 'unit-3')
        self.assertTrue(units[1]['text'].startswith('所以'))

    def test_no_connector_does_not_invent_split(self):
        self.assertEqual(prepare_review_units('统计不能证明人人通过')[0]['text'], '统计不能证明人人通过')

    def test_recorded_schedule_counterevidence_rejected(self):
        claim = '按照这份文件，北京所有学校从2024年秋季开学第一天就已经全部完成调整。'
        material = '文件设置一个月调整缓冲期，自2024年秋季学期起，各区在开学后一个月内指导学校结合实际逐步落实安排。文件未提供全国学校的安排，也未提供每所学校实际完成调整的统计。'
        value = review_v11()
        value['schema_version'] = '1.2'
        row = value['claims'][0]
        row.update(claim_span=claim, status='contradicted', contradiction_basis='direct-negation',
                   quotes=[{'text': material.split('。')[0]+'。'}, {'text': material.split('。')[1]+'。'}],
                   suggested_wording=None)
        result = validate_partial_review(value, claim, material)
        self.assertEqual(result['rejected_claims'][0]['reason_code'], 'implementation-boundary')
        row.update(status='unsupported', contradiction_basis='none')
        self.assertEqual(validate_partial_review(value, claim, material)['claims'][0]['status'], 'unsupported')
        row.update(status='contradicted', contradiction_basis='direct-negation', quotes=[{'text': '开学第一天仍有学校未完成调整。'}])
        self.assertEqual(validate_partial_review(value, claim, material+'开学第一天仍有学校未完成调整。')['claims'][0]['status'], 'contradicted')


class UnitWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_units_delivered_in_single_request(self):
        calls = []
        class Model:
            async def review(self, system, data):
                payload = json.loads(data)
                calls.append(payload)
                rows = []
                for unit in payload['review_units']:
                    row = copy.deepcopy(review_v11()['claims'][0])
                    row.update(claim_span=unit['text'], quotes=[{'text':'北京出台安排。'}], suggested_wording=None)
                    rows.append(row)
                return {'schema_version':'1.1', 'claims':rows}
        result = await run_semantic_review('北京出台安排，所以全国所有学校必须执行。', '北京出台安排。', Model())
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]['review_units']), 2)
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(result['input_review_units'][1]['premise_unit_id'], 'unit-1')
