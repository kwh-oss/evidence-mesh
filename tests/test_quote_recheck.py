import copy
import unittest
from evidence_mesh.semantic_review import run_semantic_review
from evidence_mesh.model_budget import BudgetExhausted

def response(quote='部分門店開放。'):
    return {'schema_version':'1.1','claims':[{'claim_span':'所有门店开放','kind':'fact',
        'status':'overstated','quotes':[{'text':quote}],
        'explanation':'材料仅描述部分门店，不能推到所有门店。',
        'mechanisms':['scope'],'suggested_wording':None}]}

class QuoteRecheckTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, outputs):
        class Reviewer:
            def __init__(self): self.calls=0
            async def review(self, system, data):
                item=outputs[self.calls];self.calls+=1
                if isinstance(item,Exception):raise item
                return copy.deepcopy(item)
        reviewer=Reviewer()
        result=await run_semantic_review('所有门店开放','部分門店開放。',reviewer)
        return result, reviewer.calls

    async def test_original_traditional_quote_succeeds_without_retry(self):
        out,n=await self.execute([response()])
        self.assertEqual(n,1);self.assertTrue(out['coverage_complete'])

    async def test_simplified_paraphrase_requires_new_exact_quote(self):
        out,n=await self.execute([response('部分门店开放。'),response()])
        self.assertEqual(n,2);self.assertEqual(out['quote_recheck']['status'],'recovered')
        self.assertEqual(out['claims'][0]['quotes'][0]['text'],'部分門店開放。')

    async def test_two_bad_replies_never_adopt_or_loop(self):
        out,n=await self.execute([response('部分门店开放。')]*2)
        self.assertEqual(n,2);self.assertEqual(out['claims'],[])
        self.assertEqual(out['quote_recheck']['status'],'not-recovered')

    async def test_other_invalid_output_does_not_trigger_quote_retry(self):
        item=response();item['claims'][0]['kind']='invalid'
        out,n=await self.execute([item])
        self.assertEqual(n,1);self.assertEqual(out['claims'],[])

    async def test_exhausted_budget_preserves_original_rejection(self):
        out,n=await self.execute([response('部分门店开放。'),BudgetExhausted('empty')])
        self.assertEqual(n,2);self.assertEqual(out['claims'],[])
        self.assertEqual(out['quote_recheck']['status'],'budget-unavailable')
