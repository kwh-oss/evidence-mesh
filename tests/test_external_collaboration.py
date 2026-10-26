import json
import asyncio
import ssl
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from acps_sdk.aip import TaskState, TextDataItem
from evidence_mesh.external_collaboration import ExternalCollaborator
from evidence_mesh.contracts import request_from_caller_text

PARTNER = {'aic': 'screened-peer', 'name': '独立复核', 'role': 'partner',
           'url': 'https://peer.example/rpc', 'skill': 'review', 'capability': 'evidence-boundary-review'}


class CollaborationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.starts = 0
        self.response = {'issues': [{'source_id': 's', 'quote': '只适用于登记会员', 'explanation': '不能扩展到所有人。'}]}
        outer = self
        class Client:
            async def start_task(self, *args, **kwargs):
                outer.starts += 1
                return NS(status=NS(state=TaskState.Completed), products=[NS(dataItems=[TextDataItem(text=json.dumps(outer.response))])])
            async def close(self):
                pass
        self.discovery = AsyncMock(return_value=True)
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        self.config = {'journal': str(Path(self.tmp.name)/'journal.sqlite'), 'partners': [PARTNER], 'max_tasks': 1}
        self.collab = ExternalCollaborator(self.config, 'our-leader', ctx, client_factory=lambda *a, **k: Client(), discovery=self.discovery)
        self.req = request_from_caller_text('政策要求所有人免费', default_claim_id='root')
        self.passport = {'public_retrieval': {'status': 'retrieved', 'sources': [
            {'source_id': 's', 'text': '本次优惠只适用于登记会员，其他人不享受。'}]}}

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_grounded_review_is_suggestion_and_deduplicated(self):
        out = await self.collab.review(self.req, self.passport)
        self.assertEqual(out['status'], 'grounded-suggestions')
        self.assertFalse(out['affects_core_verdict'])
        self.assertFalse(out['claim_verified'])
        await self.collab.review(self.req, self.passport)
        self.assertEqual(self.starts, 1)

    async def test_fabricated_quote_rejected(self):
        self.response['issues'][0]['quote'] = '所有人免费'
        out = await self.collab.review(self.req, self.passport)
        self.assertEqual(out['status'], 'unusable-review')
        self.assertEqual(out['issues'], [])

    async def test_one_bad_external_quote_does_not_remove_valid_issue(self):
        self.response['issues'].append({'source_id':'s','quote':'全部都免费',
                                       'explanation':'DO-NOT-RENDER'})
        out=await self.collab.review(self.req,self.passport)
        self.assertEqual(out['status'],'grounded-suggestions')
        self.assertEqual(len(out['issues']),1)
        self.assertEqual(out['rejected_issue_count'],1)
        self.assertFalse(out['coverage_complete'])
        self.assertNotIn('DO-NOT-RENDER',str(out))

    async def test_private_supplied_material_not_forwarded_automatically(self):
        out = await self.collab.review(self.req, {})
        self.assertFalse(out['invoked'])
        self.assertEqual(self.starts, 0)

    async def test_caller_no_network_prevents_call(self):
        from dataclasses import replace
        out = await self.collab.review(replace(self.req, constraints=('不联网',)), self.passport)
        self.assertEqual(out['reason'], 'caller-opted-out')
        self.assertEqual(self.starts, 0)

    async def test_changed_discovery_prevents_call(self):
        self.discovery.return_value = False
        out = await self.collab.review(self.req, self.passport)
        self.assertEqual(out['reason'], 'discovery-no-longer-matches-screened-capability')
        self.assertEqual(self.starts, 0)

    async def test_task_cap_survives_distinct_root(self):
        from dataclasses import replace
        await self.collab.review(self.req, self.passport)
        out = await self.collab.review(replace(self.req, claim_id='root-2'), self.passport)
        self.assertEqual(out['reason'], 'external-task-budget-exhausted')
        self.assertEqual(self.starts, 1)

    async def test_nonmatching_task_skipped(self):
        from dataclasses import replace
        out = await self.collab.review(replace(self.req, claim_text='今天下午的天气怎样'), self.passport)
        self.assertEqual(out['reason'], 'no-matching-capability-gap')

    async def test_coordinator_rejected_to_avoid_loops(self):
        with self.assertRaises(ValueError):
            ExternalCollaborator({**self.config, 'partners': [{**PARTNER, 'role': 'leader'}]}, 'our-leader', ssl.create_default_context())

    async def test_actual_sdk_span_command_and_task_identity_are_normalized_once(self):
        from acps_sdk.amp import AccessBody, AccessRequest, AccessResponse, AccessParticipant
        from evidence_mesh.external_collaboration import CanonicalAipAccess
        emitter = NS(emit=AsyncMock())
        body = AccessBody(request=AccessRequest(method='start', url='https://peer.example/rpc', route='/rpc'),
            response=AccessResponse(statusCode=200), caller=AccessParticipant(aic='caller'),
            callee=AccessParticipant(aic='peer'), durationMs=12)
        await CanonicalAipAccess(emitter).emit(body, correlation_id='retrieval-session-abc', trace_id='original-trace')
        emitter.emit.assert_awaited_once()
        args, kwargs = emitter.emit.await_args
        self.assertEqual(args[0].request.method, 'Start')
        self.assertEqual(args[0].response.status_code, 200)
        self.assertEqual(kwargs['correlation_id'], 'retrieval-abc')
        self.assertEqual(kwargs['trace_id'], 'original-trace')
        self.assertEqual(body.request.method, 'start')

    async def test_two_peers_overlap_and_deduplicate_per_peer(self):
        second = {**PARTNER, 'aic': 'second-peer', 'name': '研究复核',
                  'url': 'https://second.example/rpc', 'claim_pattern': '政策|研究'}
        self.config.update(partners=[PARTNER, second], max_tasks=4, max_partners_per_task=2)
        both_started = asyncio.Event()
        started = set()
        outer = self
        class Client:
            def __init__(self, peer): self.peer = peer
            async def start_task(self, *args, **kwargs):
                outer.starts += 1
                started.add(self.peer)
                if len(started) == 2: both_started.set()
                await asyncio.wait_for(both_started.wait(), timeout=1)
                return NS(status=NS(state=TaskState.Completed), products=[NS(dataItems=[
                    TextDataItem(text=json.dumps(outer.response))])])
            async def close(self): pass
        ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        collab = ExternalCollaborator(self.config, 'our-leader', ctx,
            client_factory=lambda *a, **kw: Client(kw['expected_partner_aic']), discovery=self.discovery)
        out = await collab.review(self.req, self.passport)
        self.assertEqual(out['dispatch'], 'parallel')
        self.assertEqual(out['completed_count'], 2)
        self.assertEqual([p['status'] for p in out['reviews']], ['grounded-suggestions'] * 2)
        self.assertFalse(out['affects_core_verdict'])
        await collab.review(self.req, self.passport)
        self.assertEqual(self.starts, 2)

    async def test_three_peers_overlap_with_distinct_review_focus(self):
        all_started=asyncio.Event();prompts={};outer=self
        class Client:
            def __init__(self,peer): self.peer=peer
            async def start_task(self,sid,prompt,**kwargs):
                outer.starts+=1;prompts[self.peer]=prompt
                if len(prompts)==3:all_started.set()
                await asyncio.wait_for(all_started.wait(),1)
                return NS(status=NS(state=TaskState.Completed),products=[NS(dataItems=[TextDataItem(text=json.dumps(outer.response))])])
            async def close(self):pass
        self.config.update(max_tasks=5,max_partners_per_task=3,
            partners=[{**PARTNER,'aic':'peer-'+str(i),'url':'https://peer'+str(i)+'.example/rpc','review_focus':focus}
                for i,focus in enumerate(('source-scope','research-evidence','argument-quality'))])
        ctx=ssl.create_default_context();ctx.minimum_version=ssl.TLSVersion.TLSv1_3
        collab=ExternalCollaborator(self.config,'our-leader',ctx,
            client_factory=lambda *a,**kw:Client(kw['expected_partner_aic']),discovery=self.discovery)
        out=await collab.review(self.req,self.passport)
        self.assertEqual(out['selected_count'],3);self.assertEqual(out['completed_count'],3)
        self.assertEqual(self.starts,3);self.assertIn('论证链',prompts['peer-2'])
        self.assertNotEqual(prompts['peer-0'],prompts['peer-1'])
        await collab.review(self.req,self.passport)
        self.assertEqual(self.starts,3)

    async def test_unknown_focus_rejected_before_client(self):
        with self.assertRaises(ValueError):
            ExternalCollaborator({**self.config,'partners':[{**PARTNER,'review_focus':'arbitrary'}]},
                'our-leader',ssl.create_default_context())

    async def test_parallel_admission_never_exceeds_total_budget(self):
        self.config.update(partners=[PARTNER, {**PARTNER, 'aic': 'second-peer',
            'url': 'https://second.example/rpc'}], max_partners_per_task=2)
        ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        collab = ExternalCollaborator(self.config, 'our-leader', ctx,
            client_factory=self.collab.factory if hasattr(self.collab, 'factory') else
                self.collab.adapters[PARTNER['aic']].factory, discovery=self.discovery)
        out = await collab.review(self.req, self.passport)
        self.assertEqual(self.starts, 1)
        self.assertEqual(sum(p.get('reason') == 'external-task-budget-exhausted' for p in out['reviews']), 1)

    async def test_one_failed_peer_does_not_discard_other_review(self):
        self.config.update(partners=[PARTNER, {**PARTNER, 'aic': 'second-peer',
            'url': 'https://second.example/rpc'}], max_tasks=3, max_partners_per_task=2)
        ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        collab = ExternalCollaborator(self.config, 'our-leader', ctx,
            client_factory=self.collab.adapters[PARTNER['aic']].factory, discovery=self.discovery)
        collab.adapters['second-peer'].retrieve = AsyncMock(side_effect=RuntimeError('peer down'))
        out = await collab.review(self.req, self.passport)
        self.assertEqual(out['reviews'][0]['status'], 'grounded-suggestions')
        self.assertEqual(out['reviews'][1]['reason'], 'unavailable')

    async def test_existing_pending_task_is_polled_without_new_start(self):
        adapter = self.collab.adapters[PARTNER['aic']]
        await self.collab.review(self.req, self.passport)
        adapter.retrieve = AsyncMock(return_value={'status': 'pending', 'invoked': True})
        adapter.recover = AsyncMock(return_value={'status': 'unparsed', 'invoked': False,
            'aip_state': 'completed', 'raw_text': json.dumps(self.response)})
        out = await self.collab.review(self.req, self.passport)
        self.assertEqual(out['status'], 'grounded-suggestions')
        self.assertEqual(self.starts, 1)
        adapter.recover.assert_awaited_once()
