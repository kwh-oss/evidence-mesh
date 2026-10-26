"""Private bounded CPU ASR. No host port, credentials or paid API."""
from contextlib import asynccontextmanager
from io import BytesIO
import asyncio
import av
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel

model=None
lock=asyncio.Lock()
@asynccontextmanager
async def lifespan(app):
    global model
    model=await asyncio.to_thread(WhisperModel,'small',device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,download_root='/models')
    yield

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
@app.get('/health')
def health():return {'ready':model is not None,'model':'whisper-small-int8','device':'cpu'}

def decode_bounded(raw):
    chunks=[];size=0;resampler=av.AudioResampler(format='flt',layout='mono',rate=16000)
    with av.open(BytesIO(raw)) as container:
        if not container.streams.audio:raise ValueError('no audio stream')
        for frame in container.decode(audio=0):
            for item in resampler.resample(frame):
                data=item.to_ndarray().reshape(-1);size+=len(data)
                if size>35*16000:raise ValueError('audio exceeds 35 seconds')
                chunks.append(data)
        for item in resampler.resample(None):
            data=item.to_ndarray().reshape(-1);size+=len(data)
            if size>35*16000:raise ValueError('audio exceeds 35 seconds')
            chunks.append(data)
    return np.concatenate(chunks).astype(np.float32) if chunks else np.zeros(0,dtype=np.float32)

def transcribe(raw):
    data=decode_bounded(raw)
    if not len(data) or float(np.sqrt(np.mean(data*data)))<.0001:return {'segments':[]}
    segments,_=model.transcribe(data,beam_size=3,vad_filter=True,condition_on_previous_text=False)
    rows=[]
    for s in segments:
        text=s.text.strip()
        if not text or s.no_speech_prob>.75:continue
        if len(text)>500 or len(rows)>=80:raise ValueError('transcript too large')
        rows.append({'start':max(0,float(s.start)),'end':min(35,float(s.end)),'text':text})
    return {'segments':rows}

@app.post('/transcribe')
async def endpoint(request:Request):
    if lock.locked():raise HTTPException(429,'声音转写正在使用中')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>256000:raise HTTPException(413,'声音片段过大')
    if not raw.startswith(b'\x1aE\xdf\xa3'):raise HTTPException(422,'需要WebM声音片段')
    async with lock:
        try:return await asyncio.to_thread(transcribe,bytes(raw))
        except (ValueError,av.error.FFmpegError):raise HTTPException(422,'声音片段无法解码或超过时长') from None
