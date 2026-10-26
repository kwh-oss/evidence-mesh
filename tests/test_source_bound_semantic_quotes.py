"""Provenance regressions for identical text on different acquired pages."""
import copy
import json
import unittest
from evidence_mesh.semantic_review import run_semantic_review, bind_source_quotes, validate_review
from test_spread_semantic_workflow import review_v11


class SourceBoundQuotes(unittest.IsolatedAsyncioTestCase):
    async def test_redundant_candidate_fields_must_match_exactly(self):
        pages=[dict(source_id='a',url='https://a.example/',text='部分门店开放。')]
        class Reviewer:
            async def review(self,system,data):
                candidate=json.loads(data)['source_metadata']['quote_candidates']['q0']
                value=review_v11()
                value['claims'][0]['quotes']=[{'candidate_id':'q0',
                    'text':candidate['text'] if correct else '所有门店开放。','source_id':'a'}]
                return value
        for correct in (True,False):
            value=await run_semantic_review('所有门店开放',pages[0]['text'],Reviewer(),
                {'source_id':'retrieved-bundle'},source_pages=pages)
            if correct:
                self.assertEqual(value['status'],'model-suggestion')
                self.assertTrue(any(r['operation']=='verified-redundant-candidate-fields-removed'
                    for r in value['transport_normalization']))
            else:
                self.assertEqual(value['claims'],[])
                self.assertEqual(value['rejected_claims'][0]['reason_code'],'quote-candidate-content')
    async def test_candidate_disambiguates_repeated_text_inside_same_page(self):
        pages=[dict(source_id='a',url='https://a.example/',text='部分门店开放。\n部分门店开放。')]
        class Reviewer:
            async def review(self, system, data):
                data=json.loads(data)
                candidates=data['source_metadata']['quote_candidates']
                selected=[k for k,q in candidates.items() if q['text']=='部分门店开放。'][-1]
                value=review_v11()
                value['claims'][0]['quotes']=[{'candidate_id':selected}]
                return value
        result=await run_semantic_review('所有门店开放',pages[0]['text'],Reviewer(),
            {'source_id':'retrieved-bundle'},source_pages=pages)
        self.assertEqual(result['status'],'model-suggestion')
        q=result['claims'][0]['quotes'][0]
        self.assertEqual(q['start'],8)
        bound=bind_source_quotes(result,pages)
        self.assertEqual(bound['claims'][0]['quotes'][0]['source_url'],pages[0]['url'])
        damaged=copy.deepcopy(result);damaged['claims'][0]['quotes'][0]['start']=0
        self.assertEqual(bind_source_quotes(damaged,pages)['failure_stage'],'source-binding')

    async def test_unknown_candidate_cannot_supply_an_anchor(self):
        class Reviewer:
            async def review(self, system, data):
                value=review_v11();value['claims'][0]['quotes']=[{'candidate_id':'invented'}]
                return value
        result=await run_semantic_review('所有门店开放','部分门店开放。',Reviewer())
        self.assertEqual(result['claims'],[])
        self.assertEqual(result['status'],'failed-or-invalid')

    async def test_repeated_exact_quote_accepted_only_with_correct_source(self):
        pages=[dict(source_id='a',url='https://a.example/',text='部分门店开放。'),
               dict(source_id='b',url='https://b.example/',text='部分门店开放。')]
        excerpt='\n\n'.join(p['text'] for p in pages)
        value=review_v11()
        value['claims'][0]['quotes']=[dict(text='部分门店开放。',source_id='b')]
        class Reviewer:
            async def review(self, system, data):
                self.data=json.loads(data)
                return copy.deepcopy(value)
        reviewer=Reviewer()
        result=await run_semantic_review('所有门店开放',excerpt,reviewer,
            {'source_id':'retrieved-bundle'},source_pages=pages)
        self.assertEqual(result['status'],'model-suggestion')
        quote=result['claims'][0]['quotes'][0]
        self.assertEqual(quote['start'],len(pages[0]['text'])+2)
        bound=bind_source_quotes(result,pages)
        self.assertEqual(bound['claims'][0]['quotes'][0]['source_url'],pages[1]['url'])
        # Same bytes without a source id remain ambiguous.
        value['claims'][0]['quotes'][0].pop('source_id')
        with self.assertRaisesRegex(ValueError,'quote absent or ambiguous'):
            validate_review(value,'所有门店开放',excerpt)

    async def test_wrong_source_and_cross_page_text_fail_closed(self):
        pages=[dict(source_id='a',url='https://a.example/',text='甲材料中的完整句子。'),
               dict(source_id='b',url='https://b.example/',text='乙材料中的完整句子。')]
        class Reviewer:
            async def review(self,system,data):return value
        for quote in [dict(text=pages[0]['text'],source_id='b'),
                      dict(text=pages[0]['text'],source_id='unknown'),
                      dict(text='\n\n'.join(p['text'] for p in pages),source_id='a')]:
            value=review_v11();value['claims'][0]['quotes']=[quote]
            result=await run_semantic_review('所有门店开放','\n\n'.join(p['text'] for p in pages),
                Reviewer(),{'source_id':'retrieved-bundle'},source_pages=pages)
            self.assertFalse(result['coverage_complete'])
            self.assertEqual(result['claims'],[])

    async def test_supplied_metadata_cannot_create_page_bounds(self):
        class Never:
            async def review(self,*args):raise AssertionError('must not call model')
        result=await run_semantic_review('所有门店开放','不同正文',Never(),
            {'source_id':'retrieved-bundle'},source_pages=[dict(source_id='a',text='原文')])
        self.assertEqual(result['failure_stage'],'source-binding')
