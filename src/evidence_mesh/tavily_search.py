"""Explicitly configured basic search. Snippets are leads, never evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import httpx
from .model_budget import PersistentAttemptBudget

ENDPOINT = 'https://api.tavily.com/search'
MAX_BYTES = 512 * 1024


class SearchQuotaUnavailable(ValueError):
    pass


class SearchProviderUnavailable(ValueError):
    pass


def routed_query(query):
    """Compile our finite site suffixes to provider filters, preserving echo checks.

    Tavily removes site: operators from the echoed query. Sending the textual
    operators caused a genuine query mismatch; do not relax response validation.
    """
    for suffix, domains in (
        (' (site:gov.cn OR site:edu.cn OR site:nih.gov OR site:cdc.gov OR site:usda.gov)', ['gov.cn','edu.cn','nih.gov','cdc.gov','usda.gov']),
        (' (site:npc.gov.cn OR site:gov.cn OR site:court.gov.cn)', ['npc.gov.cn', 'gov.cn', 'court.gov.cn']),
        (' site:gov.cn OR site:npc.gov.cn OR site:court.gov.cn', ['gov.cn', 'npc.gov.cn', 'court.gov.cn']),
        (' site:gov.cn', ['gov.cn']),
    ):
        if query.endswith(suffix) and query[:-len(suffix)].strip():
            return query[:-len(suffix)].strip(), domains
    return query, []


def private_key(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise ValueError('Private search key path is invalid')
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError()
            if os.name == 'posix' and (info.st_mode & 0o077 or info.st_uid not in (0, os.geteuid())):
                raise ValueError()
            raw = f.read(513)
        key = raw.decode('ascii').strip()
        if len(raw) > 512 or not re.fullmatch(r'tvly-[A-Za-z0-9_-]{8,}', key):
            raise ValueError()
        return key
    except (OSError, UnicodeError, ValueError):
        raise ValueError('Private search key unavailable or invalid') from None


class TavilySearch:
    full_page_content = True
    def __init__(self, key_file, budget_file, max_calls=20, *, transport=None, capture=None):
        # This database must be separately mounted, never the DeepSeek ledger.
        if Path(budget_file).name != 'search-quota.sqlite3':
            raise ValueError('Dedicated search-quota.sqlite3 ledger required')
        self._key = private_key(key_file)
        self._budget = PersistentAttemptBudget(budget_file, max_calls)
        self.transport, self.capture = transport, capture

    async def __call__(self, query):
        from .public_evidence import SearchBatch, public_url
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1100:
            raise ValueError('Invalid search query')
        try:
            self._budget.reserve()  # Count attempts before dispatch, including errors.
        except ValueError:
            raise SearchQuotaUnavailable('Search attempt limit unavailable or exhausted') from None
        wire_query, domain_filters = routed_query(query)
        parameters = dict(query=wire_query, search_depth='basic', auto_parameters=False,
                          topic='general', max_results=5, include_answer=False,
                          include_raw_content=True, include_images=False, include_usage=True)
        if domain_filters:
            parameters['include_domains'] = domain_filters
        try:
            async with httpx.AsyncClient(timeout=14, trust_env=False, follow_redirects=False,
                                         transport=self.transport) as client:
                async with client.stream('POST', ENDPOINT, json=parameters,
                        headers={'Authorization': 'Bearer ' + self._key}) as response:
                    if response.status_code != 200:
                        raise SearchProviderUnavailable('Search provider returned no usable response')
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            raise ValueError('Search response too large')
            raw = bytes(raw)
        except httpx.HTTPError:
            # Do not expose request headers, URLs with credentials or provider error bodies.
            raise SearchProviderUnavailable('Search transport failed; not retried') from None
        if self._key.encode() in raw:
            raise ValueError('Search response rejected for private data')
        if self.capture is not None:
            self.capture(wire_query, raw)
        value = json.loads(raw)
        if (not isinstance(value, dict) or value.get('query') != wire_query
                or not isinstance(value.get('results'), list) or len(value['results']) > 5):
            raise ValueError('Invalid search response schema')
        usage = value.get('usage')
        if (not isinstance(usage, dict) or type(usage.get('credits')) not in (int, float)
                or not 0 <= usage['credits'] <= 1):
            raise ValueError('Basic search usage missing or outside permitted bound')
        request_id = value.get('request_id')
        if request_id is not None and (not isinstance(request_id, str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request_id)):
            raise ValueError('Invalid search request identifier')
        rows, discarded, documents = [], [], []
        for index, row in enumerate(value['results']):
            if not isinstance(row, dict) or not isinstance(row.get('url'), str):
                raise ValueError('Invalid search result')
            try:
                url = public_url(row['url'])
            except ValueError:
                # One unsafe/HTTP lead must not poison otherwise valid HTTPS
                # leads. Never rewrite it to HTTPS or relax fetch safeguards.
                discarded.append({'result_index': index,
                    'reason': 'url-not-permitted-by-https-public-policy'})
                continue
            if not isinstance(row.get('title', ''), str):
                raise ValueError('Invalid search result title')
            # answer/content and scores are never evidence. Only the separate
            # full-page field may produce a provenance-labelled page document.
            from .provider_documents import full_page_document
            document = full_page_document(url, row.get('title', '')[:300], row.get('raw_content'),
                hashlib.sha256(raw).hexdigest(), datetime.now(timezone.utc).isoformat(), query)
            if document is not None:
                documents.append(document)
            rows.append({'url': url, 'title': row.get('title', '')[:300],
                         'discovery': 'search'})
        return SearchBatch(rows, page_documents=documents, search_metadata={
            'provider': 'tavily', 'request_id': request_id, 'usage_credits': usage['credits'],
            'query_sent': wire_query, 'include_domains': domain_filters,
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'response_sha256': hashlib.sha256(raw).hexdigest(),
            'discarded_result_count': len(discarded), 'discarded_results': discarded,
            'search_depth': 'basic', 'response_is_evidence': False})
