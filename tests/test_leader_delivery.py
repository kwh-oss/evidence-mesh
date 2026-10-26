import unittest
from evidence_mesh.leader_delivery import with_external_supplements

class DeliveryTests(unittest.TestCase):
 def fixture(self,text='近24小时没有合格动态。',state='completed'):
  return {'answer':'内部材料没有当日清单。','decision':'needs-review','external_supplement':{'internal_answer_preserved':True},'external_collaboration':{'reviews':[{'partner_name':'热点伙伴','text':text,'supplementary':True,'aip_state':state}]}}
 def test_completed_supplement_is_readable_without_replacing_internal_decision(self):
  original=self.fixture();value=with_external_supplements(original)
  self.assertIn('近24小时没有合格动态',value['answer'])
  self.assertEqual(value['internal_answer'],original['answer'])
  self.assertEqual(value['decision'],original['decision'])
  self.assertEqual(original['answer'],'内部材料没有当日清单。')
 def test_pending_is_not_invented_as_an_answer(self):
  original=self.fixture(state='working');self.assertIs(with_external_supplements(original),original)
 def test_tool_markup_is_not_leaked(self):
  value=with_external_supplements(self.fixture('<｜DSML｜tool_calls>'))
  self.assertNotIn('DSML',value['answer']);self.assertIn('未作为有效答复展示',value['answer'])
 def test_plain_internal_output_is_unchanged(self):
  p={'answer':'内部结果'};self.assertIs(with_external_supplements(p),p)
 def test_fresh_core_render_replaces_stale_failure_prose(self):
  from evidence_mesh.result_presentation import present_passport
  p=self.fixture();p['internal_answer']='旧失败说明'
  p['semantic_review']={'status':'model-suggestion','coverage_complete':True,'claims':[
   {'claim_span':'待查问题','status':'supported','explanation':'结论：新分析结论\n依据：本次材料。',
    'quotes':[]}]}
  value=with_external_supplements(present_passport(p))
  self.assertNotIn('旧失败说明',value['answer'])
  self.assertIn('新分析结论',value['answer'])
  self.assertEqual(with_external_supplements(value)['answer'],value['answer'])
