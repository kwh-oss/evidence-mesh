"""Opt-in server-side DeepSeek adapter. No network access during configuration."""
import asyncio
from functools import lru_cache
import json
import os
from pathlib import Path

import httpx

from .runtime_config import env_flag
from .model_budget import PersistentAttemptBudget, BudgetExhausted


class DeepSeekReviewer:
    def __init__(self, *, model, key_file, max_calls=4, transport=None, evaluation_mode=False,
                 budget_file=None):
        if not model or not model.strip() or len(model) > 100:
            raise ValueError('DEEPSEEK_MODEL must be explicitly configured')
        ceiling = 24 if evaluation_mode is True else (300 if budget_file else 4)
        if type(max_calls) is not int or not 1 <= max_calls <= ceiling:
            raise ValueError('DeepSeek request budget exceeds allowed mode limit')
        self.model = model.strip()
        try:
            self._key = Path(key_file).read_text(encoding='utf-8-sig').strip()
        except (OSError, ValueError):
            raise ValueError('DeepSeek private key file is missing or unreadable') from None
        if not self._key or any(c.isspace() for c in self._key):
            raise ValueError('DeepSeek private key file must contain one nonempty key')
        self._remaining = max_calls
        self._budget = (PersistentAttemptBudget(budget_file, max_calls)
                        if budget_file else None)
        self._lock = asyncio.Lock()
        self._transport = transport
        self.attempts = []  # Safe metadata only; never credentials or provider error bodies.

    async def review(self, system, data):
        async with self._lock:
            if self._remaining <= 0:
                raise BudgetExhausted('DeepSeek preparation request budget exhausted')
            if self._budget is not None:
                self._budget.reserve()
            self._remaining -= 1  # Failed attempts also consume the local budget.
            record = {'status': 'started', 'http_status': None, 'usage': {}}
            self.attempts.append(record)
            body = {'model': self.model, 'messages': [
                {'role': 'system', 'content': system}, {'role': 'user', 'content': data}],
                'response_format': {'type': 'json_object'}, 'max_tokens': 3000,
                'stream': False, 'thinking': {'type': 'disabled'}}
            try:
                async with httpx.AsyncClient(timeout=20, follow_redirects=False,
                                             trust_env=False, transport=self._transport) as client:
                    async with client.stream('POST', 'https://api.deepseek.com/chat/completions',
                            headers={'Authorization': 'Bearer ' + self._key}, json=body) as response:
                        record['http_status'] = response.status_code
                        response.raise_for_status()
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 262144:
                                raise ValueError('response too large')
                value = json.loads(raw)
                usage = value.get('usage', {})
                if isinstance(usage, dict):
                    record['usage'] = {k: v for k, v in usage.items() if k in (
                        'prompt_tokens', 'completion_tokens', 'total_tokens',
                        'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens') and type(v) is int and v >= 0}
                choice = value['choices'][0]
                if choice['finish_reason'] != 'stop':
                    raise ValueError('incomplete response')
                content = choice['message']['content']
                if not isinstance(content, str) or not content.strip():
                    raise ValueError('empty content')
                result = json.loads(content)
                record['status'] = 'received'
                return result
            except httpx.TimeoutException:
                record['status'] = 'failed'
                raise TimeoutError('Model provider timed out') from None
            except Exception:
                record['status'] = 'failed'
                # Never expose request headers, body, key, or provider response.
                raise ValueError('DeepSeek request failed or returned invalid output') from None
            finally:
                if record['status'] == 'started':
                    record['status'] = 'interrupted'


@lru_cache(maxsize=1)
def configured_semantic_reviewer():
    if not env_flag('EVIDENCE_SEMANTIC_ENABLED', default=False):
        return None
    budget_file = os.getenv('DEEPSEEK_BUDGET_FILE', '').strip()
    if not budget_file:
        raise ValueError('Persistent model budget file is required when enabling semantic review')
    return DeepSeekReviewer(model=os.getenv('DEEPSEEK_MODEL', ''),
        key_file=os.getenv('DEEPSEEK_API_KEY_FILE', ''),
        max_calls=int(os.getenv('DEEPSEEK_MAX_CALLS', '4')),
        budget_file=budget_file)
