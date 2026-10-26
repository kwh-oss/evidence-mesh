"""Protected browser bridge to the deployed Leader; no keys in browser assets."""
import asyncio
from dataclasses import replace
from collections import deque
import hmac
import json
import os
from pathlib import Path
import time
import tempfile
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
import httpx
from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient
from .contracts import request_from_json, request_from_caller_text, request_json
from .runtime_config import build_client_ssl_context, required_env
from .product_presentation import read_product
from .web_task_recovery import WebTaskRecovery
from .external_pending_state import pending_external_children

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
ASSET = Path(__file__).with_name('web_message.html')
TOKEN = Path(required_env('WEB_TEST_TOKEN_FILE')).read_text().strip()
if len(TOKEN) < 32:
    raise RuntimeError('test access token must contain at least 32 characters')
LEADER = required_env('WEB_TEST_LEADER_AIC')
CALLER = required_env('WEB_TEST_CALLER_AIC')
URL = required_env('WEB_TEST_LEADER_URL')
PARTNERS = json.loads(required_env('WEB_TEST_PARTNERS'))
TLS = build_client_ssl_context()
lock = asyncio.Lock()
recent = deque()
recovery = WebTaskRecovery(os.getenv('WEB_TEST_RECOVERY_DB', str(Path(tempfile.gettempdir()) / 'evidence-web-recovery.sqlite3')))


async def aip_wait_budget(request):
    # The installed SDK passes timeout=30 per call, overriding client defaults.
    # A public HTTPX request hook changes timeouts only, preserving its mTLS
    # client, certificate and expected-AIC verification.
    request.extensions['timeout'] = httpx.Timeout(75, connect=10, write=15, pool=10).as_dict()


def make_aip_client():
    client = AipRpcClient(URL, CALLER, ssl_context=TLS,
        expected_partner_aic=LEADER, identity_binding_enabled=True)
    if hasattr(client, 'http_client'):
        client.http_client.event_hooks.setdefault('request', []).append(aip_wait_budget)
    return client


def pending_result(entry, reason):
    return {'state': 'pending', 'recoverable': True, 'new_start_requests': 0,
        'leader_task_id': entry['task'], 'leader_session_id': entry['session'],
        'recovery_url': '/audit/' + entry['task'] + '/resume', 'reason': reason,
        'message': '暂未确认原任务完成，请查询原任务；无需重新提交问题。'}


def completed_result(final, entry, started=None):
    passport = read_product(final.products)
    expected = 'video-observation' if entry['observing'] else 'evidence-passport'
    if final.status.state != TaskState.Completed or not isinstance(passport, dict) or passport.get('product_type') != expected:
        raise ValueError('leader returned no completed valid product')
    value = {'test_only': True, 'not_organic_usage': True, 'leader_aic': LEADER, 'caller_aic': CALLER,
        'leader_task_id': entry['task'], 'leader_session_id': entry['session'], 'state': 'completed',
        'mtls_identity_binding': True,
        'partner_identity_basis': 'configured expected AIC; enforced by deployed Leader AIP client',
        'partner_trace': [] if entry['observing'] else partner_trace(passport),
        ('video_observation' if entry['observing'] else 'passport'): passport,
        'raw_product_texts': [i.text for p in final.products or [] for i in p.dataItems if isinstance(i, TextDataItem)],
        'raw_start_result': started.model_dump(mode='json') if started is not None and not entry['observing'] else None,
        'raw_final_result': None if entry['observing'] else final.model_dump(mode='json')}
    if pending_external_children(passport):
        value.update(state='pending',recoverable=True,new_start_requests=0,
            recovery_url='/audit/'+entry['task']+'/resume',reason='external-children-pending')
    else:
        recovery.finish(entry['task'], value)
    return value


async def settle_existing(client, entry, final, started=None):
    if final.status.state in (TaskState.Failed,TaskState.Canceled,TaskState.Rejected):
        from .task_outcome import failed_task_result
        value=failed_task_result(final,entry);recovery.finish(entry['task'],value);return value
    if final.status.state == TaskState.AwaitingCompletion:
        if not recovery.claim_completion(entry['task']):
            return pending_result(entry, 'completion-outcome-unconfirmed')
        final = await client.complete_task(entry['task'], entry['session'])
    if final.status.state == TaskState.Completed:
        return completed_result(final, entry, started)
    return pending_result(entry, 'leader-' + final.status.state.value)


def authorize_web(request):
    if not hmac.compare_digest(request.headers.get('x-test-token', ''), TOKEN):
        raise HTTPException(401, '测试访问口令错误')
    if request.headers.get('origin') not in (None, 'https://api.linsixuan.cn'):
        raise HTTPException(403, 'origin not allowed')


@app.post('/audit/{task_id}/resume')
async def resume_audit(task_id: str, request: Request):
    authorize_web(request)
    entry = recovery.read(task_id)
    if entry is None:
        raise HTTPException(404, '未找到可查询的原任务，请勿自动重新提交')
    if entry['result'] is not None and not pending_external_children(entry['result'].get('passport',{})):
        return entry['result']
    if lock.locked():
        return pending_result(entry, 'bridge-busy')
    async with lock:
        client = make_aip_client()
        try:
            async with asyncio.timeout(85):
                current = await client.get_task(entry['task'], entry['session'])
                return await settle_existing(client, entry, current)
        except Exception as exc:
            return pending_result(entry, type(exc).__name__)
        finally:
            await client.close()

def partner_trace(passport):
    rows = passport.get('claim_results') or [passport]
    traces = [{'role': role, **identity, 'claim_id': row.get('claim_id'),
             'task_id': row.get('task_ids', {}).get(role)}
            for row in rows for role, identity in PARTNERS.items()]
    for row in rows:
        external = row.get('external_collaboration', {})
        for peer in external.get('reviews', [external]):
            if peer.get('task_id'):
                traces.append({'role': 'external-evidence-review', 'aic': peer['partner_aic'],
                               'name': peer.get('partner_name'), 'task_id': peer['task_id'],
                               'claim_id': row.get('claim_id'), 'status': peer.get('status'),
                               'scope': peer.get('capability'), 'external': True})
    return traces

def caller_text(payload):
    if 'task_text' in payload:
        value = payload['task_text']
        if not isinstance(value, str) or not value.strip():
            raise ValueError('完整任务必须是非空文本')
        source = payload.get('source')
        if source is not None and not isinstance(source, dict):
            raise ValueError('来源信息必须是对象')
        if source and any(source.get(key) for key in ('source_id', 'title', 'locator')):
            if any(not isinstance(source.get(key, ''), str) for key in ('source_id', 'title', 'locator')):
                raise ValueError('来源字段必须是文本')
            parsed = request_from_caller_text(value, default_claim_id=payload.get('claim_id') or str(uuid.uuid4()))
            updated_source = replace(parsed.source, **{key: source[key].strip()
                for key in ('source_id', 'title', 'locator') if source.get(key, '').strip()})
            return request_json(replace(parsed, source=updated_source))
        return value.strip()
    payload['task_type'] = 'full_preflight'
    text = json.dumps(payload, ensure_ascii=False)
    request_from_json(text)
    return text

@app.get('/')
async def index():
    return FileResponse(ASSET, headers={'Cache-Control': 'no-store',
        'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"})

@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'protected-new-leader-test-bridge'}

@app.post('/audit')
async def audit(request: Request):
    authorize_web(request)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 65536:
            raise HTTPException(413, 'input exceeds 64 KiB')
    return await audit_raw(raw)


async def audit_raw(raw, *, task_prefix='web-test'):
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('JSON object required')
        payload['claim_id'] = task_prefix + '-' + str(uuid.uuid4())
        observing = task_prefix == 'browser-extension' and 'video_capture' in payload
        if observing:
            from .video_observation import validate_capture
            envelope={'task_type':'observe_video','capture':validate_capture(payload['video_capture'])}
            if payload.get('video_speech') is not None:
                from .audio_transcription import validate_transcript
                envelope['speech']=validate_transcript(payload['video_speech'])
            text=json.dumps(envelope,ensure_ascii=False)
        elif task_prefix == 'browser-extension' and payload.get('video_followup_text'):
            text=payload['video_followup_text']
            request_from_json(text)
        else:
            text = caller_text(payload)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(422, '输入格式错误：' + str(exc)) from exc
    now = time.monotonic()
    while recent and recent[0] < now - 3600:
        recent.popleft()
    if lock.locked() or len(recent) >= 60:
        raise HTTPException(429, '测试繁忙或已达到每小时60次上限')
    recent.append(now)
    async with lock:
        task_id, session_id = task_prefix + '-' + str(uuid.uuid4()), task_prefix + '-session-' + str(uuid.uuid4())
        recovery.register(task_id, session_id, observing)
        entry = recovery.read(task_id)
        client = make_aip_client()
        try:
            async with asyncio.timeout(90):
                started = await client.start_task(session_id, text, task_id=task_id)
                return await settle_existing(client, entry, started, started)
        except Exception as exc:
            # Start outcome is unknown. Query the same ID, never repeat Start.
            try:
                async with asyncio.timeout(12):
                    current = await client.get_task(task_id, session_id)
                    return await settle_existing(client, entry, current)
            except Exception:
                return pending_result(entry, type(exc).__name__)
        finally:
            await client.close()


# Separate, opt-in credentials; ordinary website authentication remains unchanged.
from .extension_api import install_extension_api
install_extension_api(app, audit_raw)
