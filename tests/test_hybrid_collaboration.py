"""Internal work must survive every optional external outcome."""
import asyncio
from dataclasses import replace
import ssl,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch
from acps_sdk.aip import TaskState,TextDataItem
from evidence_mesh.contracts import request_from_caller_text,request_json
from evidence_mesh.external_collaboration import ExternalCollaborator
from evidence_mesh.leader import PartnerTarget,audit_claim

class HybridTests(unittest.IsolatedAsyncioTestCase):
 async def test_platform_addressing_runs_internal_and_screened_external(self):
  from evidence_mesh.leader_input import leader_command_text
  self.config['partners'][0]['fixed_questions']=['今天有哪些Agent热点']
  self.config['partners'][0]['claim_pattern']=r'^(最新Agent热点|今天有哪些Agent热点)$'
  command=NS(dataItems=[TextDataItem(text='请让证链·证据审查总控查询今天有哪些Agent热点，允许总控调用内外伙伴。\nDAG 指定的上游产物摘要：\n叮当已完成协作规划并开始按 DAG 派发。')])
  self.req=request_from_caller_text(leader_command_text(command,default_claim_id='platform-fixture'))
  result=await self.run_audit(self.collab)
  self.assertEqual(result['checked_claim'],'查询今天有哪些Agent热点')
  self.assertEqual(len(self.internal),3)
  self.assertEqual(self.starts,1)
  self.assertEqual(result['external_supplement']['status'],'completed')

 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.starts=0;self.internal=[]
  peer={'aic':'public-peer','name':'公开伙伴','role':'partner','directory_role':None,
        'url':'https://peer.example/rpc','skill':'news','capability':'public-agent-news-snapshot',
        'input_style':'fixed-readonly-text','fixed_questions':['最新Agent热点']}
  self.config={'partners':[peer],'allow_external_consultation':True,
       'consultation_partner_aics':['public-peer'],'journal':str(Path(self.tmp.name)/'journal.sqlite'),
       'max_tasks':4,'max_partners_per_task':1}
  owner=self
  class Client:
   async def start_task(self,*a,**k):
    owner.starts+=1
    return NS(status=NS(state=TaskState.Completed),products=[NS(dataItems=[TextDataItem(text='外部查询内容')])])
   async def close(self):pass
  ctx=ssl.create_default_context();ctx.minimum_version=ssl.TLSVersion.TLSv1_3
  self.collab=ExternalCollaborator(self.config,'leader',ctx,client_factory=lambda *a,**k:Client(),
       discovery=AsyncMock(return_value=True))
  self.targets=[PartnerTarget(n,'https://unused.example/rpc') for n in
       ('source-verifier','evidence-grader','contradiction-scout')]
  self.req=request_from_caller_text('最新Agent热点',default_claim_id='root-fixture')
 async def asyncTearDown(self):self.tmp.cleanup()
 async def internal_call(self,target,*a,**k):
  self.internal.append(target.name)
  payload={'source-verifier':{'status':'verified'},'evidence-grader':{'level':'direct'},
       'contradiction-scout':{'status':'none-found'}}[target.name]
  return {'state':'completed','task_id':'internal-fixture-'+target.name,'product':{'payload':payload}}
 async def run_audit(self,collab):
  with patch('evidence_mesh.leader._call_partner',side_effect=self.internal_call):
   return await audit_claim(request_json(self.req),self.targets,external_collaborator=collab)
 async def test_default_public_lookup_runs_all_internal_partners_and_keeps_their_answer(self):
  baseline=await self.run_audit(None);self.internal.clear()
  self.collab.review=AsyncMock(side_effect=AssertionError('not a material review'))
  result=await self.run_audit(self.collab)
  self.assertEqual(set(self.internal),{t.name for t in self.targets})
  self.assertEqual(len(self.internal),3);self.assertEqual(len(result['task_ids']),3)
  self.assertEqual(result['answer'],baseline['answer'])
  self.assertEqual(result['decision'],baseline['decision'])
  self.assertEqual(result['semantic_review'],baseline['semantic_review'])
  self.assertEqual(result['routing']['coordination_mode'],'internal-first-hybrid')
  self.assertEqual(result['external_supplement']['status'],'completed')
  self.assertEqual(self.starts,1);self.collab.review.assert_not_awaited()
 async def test_external_discovery_failure_cannot_remove_internal_result(self):
  baseline=await self.run_audit(None);self.internal.clear()
  self.collab.discovery=AsyncMock(side_effect=TimeoutError('directory unavailable'))
  result=await self.run_audit(self.collab)
  self.assertEqual(result['answer'],baseline['answer']);self.assertEqual(result['decision'],baseline['decision'])
  self.assertEqual(len(result['partner_products']),3);self.assertEqual(self.starts,0)
  self.assertEqual(result['external_supplement']['status'],'failed')
 async def test_external_hang_has_bounded_tail_and_cannot_skip_internal_calls(self):
  async def hang(*a):await asyncio.Event().wait()
  baseline=await self.run_audit(None);self.internal.clear();start=time.monotonic()
  with patch('evidence_mesh.hybrid_collaboration._supplement',side_effect=hang):
   result=await asyncio.wait_for(self.run_audit(self.collab),timeout=4)
  self.assertLess(time.monotonic()-start,4)
  self.assertEqual(result['answer'],baseline['answer']);self.assertEqual(len(self.internal),3)
  self.assertEqual(result['external_supplement']['status'],'not-invoked')
 async def test_external_journal_error_still_returns_internal_answer(self):
  async def hang(*a):await asyncio.Event().wait()
  with patch('evidence_mesh.hybrid_collaboration._supplement',side_effect=hang),patch(
      'evidence_mesh.hybrid_collaboration._reserved_rows',side_effect=OSError('journal fixture')):
   result=await asyncio.wait_for(self.run_audit(self.collab),timeout=4)
  self.assertEqual(len(result['partner_products']),3)
  self.assertEqual(result['external_supplement']['status'],'unavailable')
 async def test_known_unhealthy_review_peer_can_be_disabled_without_internal_changes(self):
  self.config['partners'][0].update(directory_role='partner',capability='evidence-boundary-review',review_enabled=False)
  req=replace(self.req,claim_text='研究证明所有人都适用',constraints=('允许外部协作',),
      source_excerpt='适用于部分参与者，尚未证明其他人群也适用。')
  result=await self.collab.review(req,{})
  self.assertEqual(result['reason'],'no-screened-partner');self.assertEqual(self.starts,0)


 async def test_pending_supplement_can_refresh_original_after_internal_finishes(self):
  pending={'decision_scope':'external-consultation','consultation_status':'pending',
       'external_collaboration':{'reviews':[{'partner_aic':'public-peer','task_id':'child-fixture','aip_state':'working'}]}}
  done={**pending,'consultation_status':'completed','external_collaboration':{'reviews':[
       {'partner_aic':'public-peer','task_id':'child-fixture','aip_state':'completed','text':'延迟原任务答复'}]}}
  with patch('evidence_mesh.hybrid_collaboration._supplement',new=AsyncMock(return_value=pending)),patch(
       'evidence_mesh.hybrid_collaboration.refresh_pending_consultation',new=AsyncMock(return_value=done)) as refresh:
   result=await self.run_audit(self.collab)
  self.assertEqual(len(result['partner_products']),3)
  self.assertEqual(result['external_supplement']['status'],'completed')
  self.assertEqual(result['external_collaboration']['reviews'][0]['task_id'],'child-fixture')
  refresh.assert_awaited_once()
