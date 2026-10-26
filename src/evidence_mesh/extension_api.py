"""Opt-in single-worker, persistent jobs for the browser extension.

No automatic retry after process loss. Bearer credentials are deployment files,
not extension assets. This small private pilot supports one credential/owner.
"""
import asyncio
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware


class ExtensionJobs:
    def __init__(self, path, token_file, run, origins=()):
        self.path, self.token_file, self.run = str(path), Path(token_file), run
        self.origins, self.tasks = set(origins), {}
        if len(self.token_file.read_text().strip()) < 32:
            raise ValueError('extension credential must contain at least 32 characters')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL, result TEXT, created TEXT NOT NULL)')
            db.execute("UPDATE jobs SET state='interrupted' WHERE state IN ('queued','running')")

    def authorize(self, request):
        supplied = request.headers.get('authorization', '')
        expected = 'Bearer ' + self.token_file.read_text().strip()
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(401, '插件访问凭证无效，请检查访问设置')
        origin = request.headers.get('origin')
        if origin is not None and origin not in self.origins:
            raise HTTPException(403, 'extension origin not allowed')

    def read(self, job_id):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT state,result,created FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, '未找到此任务，请勿自动重新提交')
        return {'job_id': job_id, 'state': row[0], 'result': json.loads(row[1]) if row[1] else None, 'created_at': row[2]}

    def latest(self,video_url):
        with closing(sqlite3.connect(self.path)) as db:
            rows=db.execute("SELECT id,result FROM jobs WHERE state='done' ORDER BY created DESC LIMIT 30").fetchall()
        for ident,raw in rows:
            result=json.loads(raw or '{}')
            observed=result.get('video_observation') or result.get('original_video_observation') or {}
            if observed.get('source',{}).get('url')==video_url:return self.read(ident)
        raise HTTPException(404,'这段视频暂无保存的分析')

    async def create(self, body):
        job_id, text = body.get('job_id'), body.get('task_text')
        if not isinstance(job_id, str) or not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', job_id):
            raise HTTPException(422, 'invalid job ID')
        if body.get('mode') == 'observe-video':
            from .video_observation import validate_capture
            try:
                payload = {'video_capture':validate_capture(body.get('video_capture'))}
            except (ValueError,TypeError,KeyError):
                raise HTTPException(422, '原视频画面格式无效，尚未启动分析')
        else:
            if not isinstance(text, str) or not text.strip() or len(text) > 6000:
                raise HTTPException(422, '请填写不超过6000字的具体主张')
            payload = {'task_text': text.strip()}
            original = body.get('original_observation_job_id')
            if original is not None:
                if not isinstance(original,str):raise HTTPException(422,'invalid original video job')
                row=self.read(original)
                if row['state']!='done' or not isinstance((row.get('result') or {}).get('video_observation'),dict):
                    raise HTTPException(422,'原视频观察尚未完成，未启动外部核验')
                payload['original_observation_job_id']=original
                if body.get('automatic_video_check') is True:
                    observed=row['result']['video_observation'];plan=observed.get('verification_plan') or {}
                    if plan.get('status')!='search' or not plan.get('question') or not observed.get('verification_targets'):
                        raise HTTPException(422,'当前片段没有准备好需要补查的核心问题')
                    payload['task_text']=plan['question']
                    payload['automatic_video_check']=True
            elif body.get('automatic_video_check') is True:
                raise HTTPException(422,'自动核验需要已完成的原视频分析')
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT fingerprint FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise HTTPException(409, '同一任务编号不能用于不同内容')
                fresh = False
            else:
                if db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] >= 1000:
                    raise HTTPException(429, '本地验收记录已达上限，请联系维护者')
                if db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]:
                    raise HTTPException(429, '已有核验正在执行，请稍后再试')
                db.execute('INSERT INTO jobs VALUES (?,?,?,NULL,?)', (job_id, fingerprint, 'queued', datetime.now(timezone.utc).isoformat()))
                fresh = True
        if fresh:
            if 'video_capture' in payload:
                try:
                    folder=Path(self.path).parent/'video-captures'
                    folder.mkdir(exist_ok=True,mode=0o700)
                    with (folder/(job_id+'.json')).open('x',encoding='utf-8') as f:
                        json.dump(payload['video_capture'],f,ensure_ascii=False)
                except OSError:
                    self.write(job_id,'failed',{'detail':'原视频采样未能归档，未启动分析'})
                    raise HTTPException(503,'原视频采样未能归档，未启动分析')
            self.tasks[job_id] = asyncio.create_task(self.execute(job_id, payload))
            self.tasks[job_id].add_done_callback(lambda _: self.tasks.pop(job_id, None))
        return self.read(job_id)

    async def execute(self, job_id, payload):
        self.write(job_id, 'running', None)
        try:
            if payload.get('video_capture',{}).get('audio'):
                from .audio_transcription import transcribe_audio
                try:payload['video_speech']=await transcribe_audio(payload['video_capture'].pop('audio'))
                except Exception:raise HTTPException(503,'声音转写未完成，请稍后重试') from None
            if payload.get('original_observation_job_id'):
                # Only a saved, completed observation can supply the clip context.
                from .video_handoff import followup_text
                observed=self.read(payload['original_observation_job_id'])['result']['video_observation']
                payload['video_followup_text']=followup_text(payload['task_text'],observed,claim_id='video-followup-'+job_id)
            result = await self.run(json.dumps(payload, ensure_ascii=False).encode(), task_prefix='browser-extension')
            if payload.get('original_observation_job_id'):
                result['original_video_observation']=self.read(payload['original_observation_job_id'])['result']['video_observation']
                result['original_observation_job_id']=payload['original_observation_job_id']
            state = 'done' if result.get('state') == 'completed' else 'failed'
        except asyncio.CancelledError:
            self.write(job_id, 'interrupted', {'detail': '服务中断，任务结果未确认；没有自动重发'})
            raise
        except HTTPException as exc:
            state, result = 'failed', {'detail': exc.detail}
        except Exception:
            state, result = 'failed', {'detail': '核验未完成，未自动重试'}
        self.write(job_id, state, result)

    def write(self, job_id, state, result):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE jobs SET state=?,result=? WHERE id=?', (state, json.dumps(result, ensure_ascii=False) if result is not None else None, job_id))


def install_extension_api(app, run):
    token_file, database = os.getenv('EXTENSION_TOKEN_FILE'), os.getenv('EXTENSION_JOBS_DB')
    if not token_file and not database:
        return None
    if not token_file or not database:
        raise ValueError('both extension token and persistent database are required')
    origins = [x.strip() for x in os.getenv('EXTENSION_ALLOWED_ORIGINS', '').split(',') if x.strip()]
    if any(not re.fullmatch(r'chrome-extension://[a-p]{32}', x) for x in origins):
        raise ValueError('exact extension origins required')
    store = ExtensionJobs(database, token_file, run, origins)
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'])

    @app.post('/extension/jobs', status_code=202)
    async def submit(request: Request):
        store.authorize(request)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2200000:
                raise HTTPException(413, 'input too large')
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise HTTPException(422, 'JSON object required')
        if not isinstance(body, dict):
            raise HTTPException(422, 'JSON object required')
        return await store.create(body)

    @app.get('/extension/jobs/latest')
    async def latest(request:Request,video_url:str):
        store.authorize(request)
        return store.latest(video_url)

    @app.get('/extension/jobs/{job_id}')
    async def status(job_id: str, request: Request):
        store.authorize(request)
        return store.read(job_id)

    return store
