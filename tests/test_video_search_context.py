import json,unittest
from unittest.mock import AsyncMock
from evidence_mesh.video_search_context import focused_video_query,PREFIX
from evidence_mesh.public_evidence import PublicEvidenceCollector


class VideoSearchContextTests(unittest.IsolatedAsyncioTestCase):
    def test_focused_lead_keeps_subject_and_ignores_background(self):
        goal=PREFIX+json.dumps({'statements':[
            {'text':'作者开车一小时','role':'background','verification_scope':'personal-account'},
            {'text':'用面粉和醋清洗排骨能去腥','role':'core','verification_scope':'public-fact'}]})
        self.assertEqual(focused_video_query(goal),'用面粉和醋清洗排骨能去腥')

    def test_malformed_or_unrelated_context_does_not_create_search_instruction(self):
        for goal in ['',PREFIX+'bad',PREFIX+'null',PREFIX+'{"statements":null}',PREFIX+'{"verification_plan":{"search_query":"https://example.com"}}']:
            self.assertIsNone(focused_video_query(goal))

    async def test_original_question_preserved_and_second_query_uses_actual_core_fact(self):
        search=AsyncMock(return_value=[])
        question='视频这些方法在除血水腥味上是否有科学依据？'
        result=await PublicEvidenceCollector(search).collect(question,focused_query='面粉 醋 清洗 排骨 去腥')
        self.assertEqual(search.await_args_list[0].args[0],question)
        self.assertTrue(search.await_args_list[1].args[0].startswith('面粉 醋 清洗 排骨 去腥'))
        self.assertFalse(result['search_plan']['reformulation']['is_evidence'])
