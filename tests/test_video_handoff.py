import json
import unittest
from evidence_mesh.video_handoff import followup_text
from evidence_mesh.contracts import request_from_json, MISSING_SOURCE_EXCERPT


class VideoHandoffTests(unittest.TestCase):
    def test_clip_context_never_becomes_external_evidence_or_replaces_claim(self):
        observed={'main_point':'作者谈论服务不便','analysis':'只展示一次到访',
            'source':{'url':'https://example.com/video','frames':[{'data_url':'private-frame'}]},
            'candidate_claims':[{'text':'所有门店都24小时营业','quote':'24小时营业',
                'verification_scope':'public-fact','role':'core'}],
            'observations':[{'text':'桌面收起','frame_indices':[0]}]}
        raw=followup_text('所有门店都24小时营业',observed)
        request=request_from_json(raw)
        self.assertEqual(request.claim_text,'所有门店都24小时营业')
        self.assertEqual(request.source_excerpt,MISSING_SOURCE_EXCERPT)
        self.assertIn('作者谈论服务不便',request.goal)
        self.assertIn('桌面收起',request.goal)
        self.assertNotIn('private-frame',raw)
