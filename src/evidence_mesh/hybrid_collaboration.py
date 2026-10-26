"""Keep the internal audit authoritative; a screened public lookup is optional."""
import asyncio
from .external_consultation import consult_external, refresh_pending_consultation
from .external_pending_state import pending_external_children
from .external_retrieval import journal_connection
from .public_peer_profiles import native_public_match

_background = set()


async def _supplement(request,collaborator):
    try:
        async with asyncio.timeout(50):
            return await consult_external(request,collaborator)
    except Exception as exc:
        return {'consultation_status':'unavailable','external_collaboration':{
            'status':'unavailable','invoked':False,'reviews':[],
            'error_type':type(exc).__name__}}


def _reserved_rows(request,collaborator):
    allowed=collaborator.config.get('consultation_partner_aics',[])
    rows=[]
    for peer in collaborator.config['partners']:
        if peer['aic'] not in allowed or not native_public_match(peer,request.claim_text):
            continue
        token=collaborator.adapters[peer['aic']]._token(request.claim_id)
        with journal_connection(collaborator.journal.path) as db:
            found=db.execute('SELECT 1 FROM retrieval WHERE key=?',(token,)).fetchone()
        if found:
            rows.append({'partner_aic':peer['aic'],'partner_name':peer['name'],
                'task_id':'retrieval-'+token,'status':'pending','invoked':True,
                'supplementary':True,'affects_core_verdict':False})
    return rows


async def audit_with_supplement(request,collaborator,internal_audit):
    # Both are independent. External errors cannot skip or cancel internal work.
    peer=asyncio.create_task(_supplement(request,collaborator))
    _background.add(peer);peer.add_done_callback(_background.discard)
    try:
        core=await internal_audit()
    except BaseException:
        peer.cancel()
        await asyncio.gather(peer,return_exceptions=True)
        raise
    try:
        deadline=asyncio.get_running_loop().time()+3
        await asyncio.wait({peer},timeout=3)
        if peer.done():
            value=peer.result()
            if pending_external_children(value):
                remaining=max(0,deadline-asyncio.get_running_loop().time())
                if remaining:
                    refresh=asyncio.create_task(refresh_pending_consultation(value,collaborator))
                    _background.add(refresh);refresh.add_done_callback(_background.discard)
                    await asyncio.wait({refresh},timeout=remaining)
                    if refresh.done():value=refresh.result()
            external=value.get('external_collaboration',{})
            supplement_status=value.get('consultation_status','unavailable')
        else:
            rows=_reserved_rows(request,collaborator)
            if not rows:
                # No business task exists; stop discovery instead of starting late.
                peer.cancel();await asyncio.gather(peer,return_exceptions=True)
            external={'status':'supplement-pending' if rows else 'not-invoked',
                'reviews':rows,'invoked':bool(rows),'selected_count':len(rows),
                'completed_count':0,'reason':'optional-tail-budget-ended'}
            supplement_status='pending' if rows else 'not-invoked'
    except Exception as exc:
        peer.cancel();await asyncio.gather(peer,return_exceptions=True)
        external={'status':'unavailable','reviews':[],'invoked':False,
            'invocation_unconfirmed':True,'error_type':type(exc).__name__}
        supplement_status='unavailable'
    for row in external.get('reviews',[]):
        row.update(supplementary=True,affects_core_verdict=False)
    core['external_collaboration']=external
    core['external_supplement']={'status':supplement_status,'affects_core_verdict':False,
        'scope':'public-lookup-only-not-internal-evidence','internal_answer_preserved':True,
        'coordination_request_id':request.claim_id}
    core.setdefault('routing',{}).update(coordination_mode='internal-first-hybrid',
        external_affects_core_verdict=False)
    return core
