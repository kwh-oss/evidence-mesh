import unittest
from scripts.review_public_test import summarize


class PublicExportTests(unittest.TestCase):
    def fixture(self):
        return {'state':'completed', 'mtls_identity_binding':True, 'passport':{
            'checked_claim':'示例', 'source_excerpt':'示例材料', 'answer':'说明', 'source_authenticity_verified':False,
            'risk_flags':['claim:source-not-verified'], 'atomic_claims':[{'original_span':'示例'}],
            'semantic_review':{'status':'model-suggestion','coverage_complete':True,
                'claims':[{'claim_span':'示例','status':'supported','quotes':[{'start':0,'end':2,'text':'示例'}]}],
                'input_review_units':[{'unit_id':'unit-1','start':0,'end':2,'text':'示例','premise_unit_id':None}]}},
            'raw_final_result':{'products':[{'name':'中文核验说明','dataItems':[{'type':'text','text':'说明'}]}]}}

    def test_structure_not_semantic_certification(self):
        result=summarize(self.fixture())
        self.assertTrue(result['structural_pass'])
        self.assertEqual(result['semantic_acceptance'],'requires-human-evidence-review')
        self.assertIsNone(result['quota_remaining'])

    def test_invalid_offsets_and_forward_premise_fail(self):
        value=self.fixture()
        unit=value['passport']['semantic_review']['input_review_units'][0]
        unit['premise_unit_id']='unit-2'
        self.assertFalse(summarize(value)['structural_pass'])
        unit['premise_unit_id']=None
        unit['text']='非原文'
        self.assertFalse(summarize(value)['structural_pass'])

    def test_partial_and_duplicated_summary_fail(self):
        value=self.fixture()
        value['passport']['semantic_review']['coverage_complete']=False
        self.assertFalse(summarize(value)['structural_pass'])
        value=self.fixture()
        value['raw_final_result']['products'][0]['dataItems'][0]['text']='说明\n\n说明'
        self.assertFalse(summarize(value)['structural_pass'])

    def test_empty_claims_do_not_pass_vacuously(self):
        value=self.fixture()
        value['passport']['semantic_review']['claims']=[]
        value['passport']['atomic_claims']=[]
        self.assertFalse(summarize(value)['structural_pass'])

    def test_quote_anchor_must_match_supplied_material(self):
        value=self.fixture()
        value['passport']['semantic_review']['claims'][0]['quotes'][0]['text']='其他'
        self.assertFalse(summarize(value)['structural_pass'])

    def test_support_without_quote_and_absent_claim_fail(self):
        value=self.fixture()
        value['passport']['semantic_review']['claims'][0]['quotes']=[]
        self.assertFalse(summarize(value)['structural_pass'])
        value=self.fixture()
        value['passport']['semantic_review']['claims'][0]['claim_span']='帖子中不存在'
        self.assertFalse(summarize(value)['structural_pass'])

    def test_export_without_material_is_missing_not_mismatch(self):
        value=self.fixture()
        del value['passport']['source_excerpt']
        result=summarize(value)
        self.assertIsNone(result['structural_checks']['quote_offsets_match_material'])
        self.assertFalse(result['structural_pass'])
        self.assertTrue(summarize(value, '示例材料')['structural_pass'])
