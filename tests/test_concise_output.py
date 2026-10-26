import unittest
from types import SimpleNamespace
from evidence_mesh.message_result import interpret_public_result
from evidence_mesh.partner_answer import partner_answer
from evidence_mesh.result_presentation import leader_answer
from evidence_mesh.source_delivery import source_delivery
from evidence_mesh.semantic_review import render_review
class ConciseOutputTests(unittest.TestCase):
 def test_failed_read_is_one_sentence(self):
  r=interpret_public_result({}, {'sources':[],'failures':[{'stage':'page'}]},[],False)
  self.assertEqual(r['summary'],'本次未能读取相关正文，暂时无法核验。')
  self.assertEqual(r['code'],'execution-incomplete')
 def test_no_match_does_not_become_false(self):
  r=interpret_public_result({}, {'sources':[],'search_complete':True},[],False)
  self.assertEqual(r['code'],'no-evidence-found');self.assertFalse(r['claim_verified'])
  self.assertEqual(r['summary'],'本次检索暂未找到直接依据。')
 def test_source_empty_is_short(self):
  answer=source_delivery({'sources':[]},'政策生效时间')['answer']
  self.assertEqual(answer,'暂未取得可用正文。')
 def test_leader_keeps_specific_conditions_and_quote(self):
  quote='无糖不等于零蔗糖。'
  row={'claim_span':'零蔗糖是无糖吗','status':'unsupported','explanation':'结论：不是。\n依据：两者定义不同。\n边界：仅限该标签定义。','quotes':[{'text':quote}]}
  p={'semantic_review':{'status':'model-suggestion','coverage_complete':True,'claims':[row]}}
  answer=leader_answer(p)
  self.assertIn(quote,answer);self.assertIn('仅限该标签定义',answer)
  self.assertNotIn('独立认证',answer)
 def test_review_has_no_blanket_footer(self):
  row={'claim_span':'观点','kind':'fact','status':'unsupported','explanation':'缺少直接依据。','quotes':[]}
  answer=render_review({'claims':[row],'coverage_complete':True})
  self.assertIn('缺少直接依据',answer)
  for phrase in ['不等于虚假','独立事实认证','引用存在不代表']:self.assertNotIn(phrase,answer)
 def test_source_field_role_remains_explicit(self):
  a,scope=partner_answer('source-check',SimpleNamespace(),{'input_assessment':{'missing_fields':[]}})
  self.assertIn('未打开链接',a);self.assertEqual(scope,'source-field-completeness')
if __name__=='__main__':unittest.main()
