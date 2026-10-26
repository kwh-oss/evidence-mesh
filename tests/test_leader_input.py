import json
import unittest
from types import SimpleNamespace
from acps_sdk.aip import TextDataItem
from evidence_mesh.contracts import request_from_caller_text, MISSING_SOURCE_EXCERPT
from evidence_mesh.leader_input import leader_command_text


def parse(text):
    return request_from_caller_text(leader_command_text(SimpleNamespace(dataItems=[TextDataItem(text=text)]),default_claim_id='fixture'))


class LeaderInputTests(unittest.TestCase):
    def test_real_platform_capture(self):
        r=parse('请让证链·证据审查总控查询今天有哪些Agent热点，允许总控调用内外伙伴。\nDAG 指定的上游产物摘要：\n叮当已完成协作规划并开始按 DAG 派发。')
        self.assertEqual(r.claim_text,'查询今天有哪些Agent热点')
        self.assertEqual(r.source_excerpt,MISSING_SOURCE_EXCERPT)
        self.assertIn('允许调用内外伙伴',r.constraints)

    def test_article_question(self):
        self.assertEqual(parse('请让证链·证据审查总控查询民法典第五百七十七条原文和官方出处。').claim_text,'查询民法典第五百七十七条原文和官方出处。')

    def test_unavailable_history_rejected(self):
        with self.assertRaisesRegex(ValueError,'实际业务问题'):
            parse('请按名称查找证链·证据审查总控，只由它处理刚才的任务。')

    def test_plain_question_unchanged(self):
        self.assertEqual(parse('每天喝咖啡能延长寿命吗？').claim_text,'每天喝咖啡能延长寿命吗？')

    def test_agent_existence_is_still_a_valid_claim(self):
        self.assertEqual(parse('核验“证链总控已经发布”是否属实').claim_text,'核验“证链总控已经发布”是否属实')

    def test_explicit_evidence_preserved(self):
        r=parse(json.dumps({'claim_text':'请让证链总控检查活动是否免费','source_excerpt':'会员免费，其他人收费','constraints':['不联网']}))
        self.assertEqual(r.claim_text,'检查活动是否免费')
        self.assertEqual(r.source_excerpt,'会员免费，其他人收费')
        self.assertEqual(r.constraints,('不联网',))

    def test_default_has_no_external_prohibition(self):
        self.assertEqual(parse('查询今天有哪些Agent热点').constraints,())
