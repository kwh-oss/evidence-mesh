"""Carry the saved clip interpretation separately from external evidence."""
import json
import uuid
from dataclasses import replace
from .contracts import request_from_caller_text, request_json

PREFIX = '原视频核验上下文（采样分析，非外部事实证据）：'


def followup_text(text, observation, *, claim_id=None):
    context = {
        'main_point': observation.get('main_point', observation.get('summary', '')),
        'analysis': observation.get('analysis', ''),
        'verification_plan':observation.get('verification_plan'),
        'source': observation.get('source', {}).get('url', ''),
        'statements': [{k: row.get(k) for k in
            ('text', 'quote', 'role', 'kind', 'verification_scope', 'frame_indices', 'speech_indices')}
            for row in observation.get('candidate_claims', [])[:3]],
        'observations': observation.get('observations', [])[:6],
    }
    request = request_from_caller_text(text, default_claim_id=claim_id or 'video-followup-'+str(uuid.uuid4()))
    return request_json(replace(request, goal=PREFIX + json.dumps(context, ensure_ascii=False)))
