"""Bounded private tab-audio input and an explicitly configured local ASR."""
import base64
import math
import os
from urllib.parse import urlsplit
import httpx

def validate_audio(value):
    if not isinstance(value,dict):raise ValueError('invalid audio sample')
    data=value.get('data_url');duration=value.get('duration_seconds');start=value.get('video_time')
    if not isinstance(data,str) or not data.startswith('data:audio/webm;base64,') or len(data)>350000:raise ValueError('bounded WebM audio required')
    raw=base64.b64decode(data.split(',',1)[1],validate=True)
    if not raw.startswith(b'\x1aE\xdf\xa3') or not 16<=len(raw)<=256000:raise ValueError('invalid WebM audio')
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=35:raise ValueError('invalid audio duration')
    if type(start) not in (int,float) or not math.isfinite(start) or not 0<=start<=86400:raise ValueError('invalid audio position')
    return {'data_url':data,'duration_seconds':duration,'video_time':start}

def validate_transcript(value):
    if not isinstance(value,dict) or value.get('source')!='local-asr':raise ValueError('invalid transcript')
    rows=value.get('segments')
    if not isinstance(rows,list) or len(rows)>80:raise ValueError('invalid speech segments')
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'start','end','text'}:raise ValueError('invalid speech segment')
        if not isinstance(row['text'],str) or not 1<=len(row['text'])<=500:raise ValueError('invalid speech text')
        if any(type(row[k]) not in (int,float) or not math.isfinite(row[k]) for k in ('start','end')) or not 0<=row['start']<=row['end']<=35:raise ValueError('invalid speech times')
    start=value.get('video_time')
    if type(start) not in (int,float) or not math.isfinite(start) or not 0<=start<=86400:raise ValueError('invalid speech position')
    return {'source':'local-asr','video_time':start,'segments':rows}

async def transcribe_audio(value):
    value=validate_audio(value)
    endpoint=os.getenv('VIDEO_ASR_URL','').strip()
    # ASR is an internal service, never an arbitrary URL supplied by a page.
    parsed=urlsplit(endpoint)
    if parsed.scheme!='http' or parsed.hostname!='evidence-audio-transcriber' or parsed.port!=8090 or parsed.path not in ('','/'):
        raise ValueError('声音转写服务尚未配置')
    raw=base64.b64decode(value['data_url'].split(',',1)[1],validate=True)
    async with httpx.AsyncClient(timeout=70,trust_env=False,follow_redirects=False) as client:
        response=await client.post(endpoint.rstrip('/')+'/transcribe',content=raw,headers={'Content-Type':'audio/webm'})
        response.raise_for_status()
        if len(response.content)>60000:raise ValueError('transcript too large')
    return validate_transcript({'source':'local-asr','video_time':value['video_time'],'segments':response.json()['segments']})
