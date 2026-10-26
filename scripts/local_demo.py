"""Loopback-only four-service AIP demo. No model, search or external peers."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SERVICES = [('source_partner',8021),('grader_partner',8022),
            ('contradiction_partner',8023),('leader_app',8010)]


def request(url, payload=None):
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req,timeout=10) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke',action='store_true',help='Check one synthetic audit and stop')
    args=parser.parse_args()
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),AIP_IDENTITY_BINDING_ENABLED='false',
        PUBLIC_RETRIEVAL_ENABLED='false',EVIDENCE_SEMANTIC_ENABLED='false',
        EXTERNAL_COLLABORATION_CONFIG='',GROUP_ENABLED='false',AMP_ENABLED='false',
        NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost',
        SOURCE_VERIFIER_URL='http://127.0.0.1:8021/rpc',
        EVIDENCE_GRADER_URL='http://127.0.0.1:8022/rpc',
        CONTRADICTION_SCOUT_URL='http://127.0.0.1:8023/rpc')
    for _,port in SERVICES:
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',port))
            except OSError:raise SystemExit(f'Port {port} unavailable; no services started.') from None
    children=[]
    try:
        for module,port in SERVICES:
            children.append(subprocess.Popen([sys.executable,'-m','uvicorn',
                f'evidence_mesh.{module}:app','--host','127.0.0.1','--port',str(port),
                '--no-access-log','--log-level','warning'],cwd=ROOT,env=env))
        deadline=time.monotonic()+30
        for _,port in SERVICES:
            while True:
                if any(c.poll() is not None for c in children):raise RuntimeError('Demo process exited')
                try:
                    if request(f'http://127.0.0.1:{port}/health').get('status')=='ok':break
                except (OSError,ValueError):pass
                if time.monotonic()>deadline:raise TimeoutError('Local readiness timed out')
                time.sleep(.15)
        print('LOCAL_DEMO_READY http://127.0.0.1:8010/ (no paid providers or external peers)',flush=True)
        if args.smoke:
            value=request('http://127.0.0.1:8010/audit',{
                'schema_version':'1.0','claim_id':'local-smoke',
                'claim_text':'处理导致细胞死亡',
                'source':{'source_id':'offline-fixture','title':'Synthetic example','locator':'line 1'},
                'source_excerpt':'结果提示处理与细胞死亡相关，可能涉及氧化应激。'})
            if len(value.get('task_ids',{}))!=3 or not isinstance(value.get('answer'),str):
                diagnostic={k:value.get(k) for k in ('decision','task_ids','risk_flags','routing')}
                raise RuntimeError('Expected three child tasks and an answer: '+json.dumps(diagnostic))
            if value.get('semantic_review',{}).get('status')!='disabled':
                raise RuntimeError('Unexpected model activity')
            print('LOCAL_AIP_SMOKE_PASS children=3 semantic=disabled',flush=True)
        else:
            while all(c.poll() is None for c in children):time.sleep(.5)
            raise RuntimeError('Demo process exited')
    except KeyboardInterrupt:pass
    finally:
        for c in children:
            if c.poll() is None:c.terminate()
        for c in children:
            try:c.wait(timeout=5)
            except subprocess.TimeoutExpired:c.kill();c.wait(timeout=5)


if __name__=='__main__':main()
