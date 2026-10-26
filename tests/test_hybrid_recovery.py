import copy
import unittest
from unittest.mock import AsyncMock, patch
from evidence_mesh.external_pending_state import pending_external_children
from evidence_mesh.external_consultation import refresh_pending_consultation
from evidence_mesh.leader_delivery import with_external_supplements


class HybridRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self):
        return {'claim_id':'core-id','checked_claim':'查询民法典第五百七十八条原文。',
                'answer':'内部结论','decision':'needs-review','semantic_review':{'status':'model-suggestion'},
                'decision_scope':'internal-evidence','routing':{'coordination_mode':'internal-first-hybrid'},
                'partner_products':{'source':'kept'},'task_ids':['internal-task'],
                'public_retrieval':{'sources':['original']},
                'external_supplement':{'status':'pending','scope':'public-lookup-only-not-internal-evidence',
                    'internal_answer_preserved':True,'affects_core_verdict':False,
                    'coordination_request_id':'original-request'},
                'external_collaboration':{'reviews':[{'partner_aic':'peer','task_id':'original-child',
                    'status':'pending','invoked':True}]}}

    async def test_hybrid_preserves_core_and_recovers_original_identity_only(self):
        original=self.fixture();snapshot=copy.deepcopy(original)
        updated={'answer':'必须不覆盖','decision':'wrong','consultation_status':'completed',
                 'external_collaboration':{'reviews':[{'partner_aic':'peer','task_id':'original-child',
                    'aip_state':'completed','text':'补充原文'}]}}
        mock=AsyncMock(return_value=updated)
        with patch('evidence_mesh.external_consultation.consult_external',mock):
            result=await refresh_pending_consultation(original,object())
        self.assertEqual(mock.call_args.args[0].claim_id,'original-request')
        self.assertEqual(mock.call_args.kwargs,{'recover_only':True,'partner_aics':{'peer'}})
        for key,value in snapshot.items():
            if key not in ('external_collaboration','external_supplement'):
                self.assertEqual(result[key],value)
        self.assertEqual(original,snapshot)
        row=result['external_collaboration']['reviews'][0]
        self.assertEqual(row['new_start_requests'],0)
        self.assertTrue(row['supplementary']);self.assertFalse(row['affects_core_verdict'])
        self.assertFalse(pending_external_children(result))
        display=with_external_supplements(result)
        self.assertEqual(with_external_supplements(display)['answer'],display['answer'])

    async def test_legacy_without_verified_identity_does_not_query(self):
        original=self.fixture();del original['external_supplement']['coordination_request_id']
        with patch('evidence_mesh.external_consultation.consult_external',AsyncMock()) as mock:
            self.assertIs(await refresh_pending_consultation(original,object()),original)
            mock.assert_not_awaited()

    async def test_changed_child_id_cannot_replace_original(self):
        original=self.fixture()
        with patch('evidence_mesh.external_consultation.consult_external',AsyncMock(return_value={
                'external_collaboration':{'reviews':[{'partner_aic':'peer','task_id':'different'}]}})):
            self.assertIs(await refresh_pending_consultation(original,object()),original)

    def test_only_bounded_hybrid_or_consultation_is_pending(self):
        p=self.fixture();self.assertTrue(pending_external_children(p))
        p['external_supplement']['affects_core_verdict']=True
        self.assertFalse(pending_external_children(p))
        self.assertTrue(pending_external_children({'decision_scope':'external-consultation',
            'consultation_status':'pending'}))
