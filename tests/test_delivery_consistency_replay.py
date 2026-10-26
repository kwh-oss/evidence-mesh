"""Replay supplied public response offline, no provider request."""
import json
from pathlib import Path
import unittest
from evidence_mesh.leader import audit_claim
from test_evidence_leader import request_json, local_targets


class PublicReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_survey_model_result_consistent(self):
        fixture = json.loads(Path('tests/fixtures/survey-semantic-replay.json').read_text(encoding='utf-8'))
        class Model:
            async def review(self, *args):
                return fixture['model_result']
        result = await audit_claim(request_json(fixture['post'], fixture['material']),
                                   local_targets(), semantic_reviewer=Model())
        self.assertEqual(len(result['atomic_claims']), 3)
        self.assertEqual(len(result['legacy_rule_assessment']['atomic_claims']), 1)
        self.assertIn('claim:source-not-verified', result['risk_flags'])
        self.assertEqual(result['semantic_assessment']['claim_statuses'], ['supported', 'supported', 'opinion'])
        self.assertEqual(result['decision'], 'needs-review')
        self.assertIn('semantic-review', result['decision_basis'])
        self.assertEqual(result['answer'], result['human_summary'])

    def test_aip_readable_product_does_not_duplicate_answer(self):
        from evidence_mesh.leader_app import caller_summary
        self.assertEqual(caller_summary({'answer': '核验说明', 'human_summary': '核验说明'}), '核验说明')
        self.assertEqual(caller_summary({'human_summary': '备用说明'}), '备用说明')
