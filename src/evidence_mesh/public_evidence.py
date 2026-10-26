"""Bounded public-web acquisition. Retrieved text is data, never instructions.

Search snippets are leads only. HTTPS connections pin validated public IPs
while retaining hostname certificate verification, including each redirect.
No cookies, credentials, private-network fetching, or automatic model calls.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx
from .page_document import VisibleHTML
from .source_review import review_sources
from .retrieval_recovery import recovery_queries, non_evidence_page, institution_names, missing_institutions
from .retrieval_profiles import retrieval_profile, domain_priority, legal_reading_context, select_reading_window, is_access_interstitial

MAX_BYTES = 512 * 1024
MAX_TEXT = 5000


class SearchBatch(list):
    """Search leads plus bounded engine failures; neither is factual evidence."""
    def __init__(self, rows, engine_failures=(), search_metadata=None, page_documents=()):
        super().__init__(rows)
        self.engine_failures = list(engine_failures)
        self.search_metadata = search_metadata
        self.page_documents = list(page_documents)

_COLLECT_SLOTS = threading.BoundedSemaphore(2)
_PAGE_SLOTS = threading.BoundedSemaphore(2)
_PAGE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='public-page')


async def bounded_fetch(fetch, url, timeout=7):
    if not _PAGE_SLOTS.acquire(blocking=False):
        raise RuntimeError('page reader capacity exhausted')
    try:
        future = _PAGE_EXECUTOR.submit(fetch, url)
    except BaseException:
        _PAGE_SLOTS.release()
        raise
    # Release only when the actual worker exits, NOT when its observer times out.
    future.add_done_callback(lambda _: _PAGE_SLOTS.release())
    return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), timeout=timeout)


def public_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ValueError('invalid URL')
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.port not in (None, 443) or '\\' in url or '%' in p.netloc):
        raise ValueError('only credential-free HTTPS on port 443 is supported')
    host = p.hostname.encode('idna').decode('ascii')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('non-public address')
    except ValueError:
        # Reject literals that are private, and private hostname aliases.
        if ':' in host or host.replace('.', '').isdigit() or '.' not in host:
            raise ValueError('public hostname required') from None
    if host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('private hostname')
    def component(value, safe):
        if re.search(r'%(?![0-9a-fA-F]{2})', value):
            raise ValueError('invalid URL escape')
        encoded = quote(value, safe=safe, encoding='utf-8', errors='strict')
        # Decode only unreserved ASCII; encoded delimiters retain their meaning.
        return re.sub(r'%([0-9a-fA-F]{2})', lambda m:
            chr(int(m[1], 16)) if chr(int(m[1], 16)) in
            'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
            else '%' + m[1].upper(), encoded)
    authority = '[' + host.lower() + ']' if ':' in host else host.lower()
    normalized = urlunsplit(('https', authority,
        component(p.path or '/', "/%:@!$&'()*+,;=-._~"),
        component(p.query, "/?%:@!$&'()*+,;=-._~"), ''))
    if len(normalized) > 2048:
        raise ValueError('encoded URL exceeds limit')
    return normalized


class PageReadError(ValueError):
    """Bounded diagnostics without exception text from untrusted web content."""
    def __init__(self, reason, *, http_status=None):
        super().__init__(reason)
        self.reason, self.http_status = reason, http_status


def page_failure(url, exc):
    item = {'stage': 'page', 'url': url, 'error_type': type(exc).__name__}
    if isinstance(exc, PageReadError):
        item['reason'] = exc.reason
        if exc.http_status is not None:
            item['http_status'] = exc.http_status
    elif isinstance(exc, ssl.SSLCertVerificationError):
        item['reason'] = 'tls-certificate-verification-failed'
        item['verify_code'] = exc.verify_code
    elif isinstance(exc, ssl.SSLError):
        item['reason'] = 'tls-handshake-failed'
        reason = getattr(exc, 'reason', None)
        if isinstance(reason, str) and re.fullmatch(r'[A-Z0-9_]{1,100}', reason):
            item['tls_reason'] = reason
    elif isinstance(exc, UnicodeError):
        item['reason'] = 'text-or-url-encoding-failed'
    elif isinstance(exc, (TimeoutError, socket.timeout)):
        item['reason'] = 'page-timeout'
    elif isinstance(exc, socket.gaierror):
        item['reason'] = 'dns-lookup-failed'
    else:
        item['reason'] = 'page-read-failed'
    return item


def public_addresses(host, resolver=socket.getaddrinfo):
    rows = resolver(host, 443, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(row[4][0] for row in rows))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('DNS includes a non-public address')
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, timeout=4, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the checked numeric address: do not resolve the hostname again.
        sock = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fetch_page(url, *, resolver=socket.getaddrinfo, connection_factory=PinnedHTTPSConnection,
               capture=None, focus_query=None):
    original = public_url(url)
    current, redirects = original, []
    deadline = time.monotonic() + 6
    for hop in range(3):
        p = urlsplit(current)
        addresses = public_addresses(p.hostname, resolver)
        if time.monotonic() >= deadline:
            raise TimeoutError('page deadline')
        conn = connection_factory(p.hostname, addresses[0])
        try:
            conn.timeout = min(4, deadline - time.monotonic())
            conn.request('GET', urlunsplit(('', '', p.path or '/', p.query, '')),
                         headers={'User-Agent': 'EvidenceMesh/0.3 source-audit',
                                  'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                if hop == 2:
                    raise PageReadError('redirect-limit')
                current = public_url(urljoin(current, response.getheader('Location') or ''))
                redirects.append(current)
                continue
            if response.status != 200:
                raise PageReadError('http-status-not-200', http_status=response.status)
            media = response.getheader('Content-Type') or ''
            if media.split(';')[0].strip().lower() not in ('text/html', 'text/plain'):
                raise PageReadError('unsupported-content-type')
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise PageReadError('unsupported-content-encoding')
            length = response.getheader('Content-Length')
            if length and int(length) > MAX_BYTES:
                raise PageReadError('page-too-large')
            chunks = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('page deadline')
                if conn.sock is not None:
                    conn.sock.settimeout(remaining)
                chunk = response.read1(min(32768, MAX_BYTES + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
                if len(chunks) > MAX_BYTES:
                    raise PageReadError('page-too-large')
            raw = bytes(chunks)
            charset = response.headers.get_content_charset() or 'utf-8'
            decoded = raw.decode(charset, errors='strict')
            parser = VisibleHTML()
            if media.lower().startswith('text/html'):
                parser.feed(decoded)
                text, extraction = parser.document()
                title = ''.join(parser.title_parts).strip()[:300]
            else:
                text, title, extraction = decoded.strip(), '', 'plain-text'
            if len(text) < 40:
                raise PageReadError('insufficient-readable-text')
            if is_access_interstitial(title, text):
                raise PageReadError('access-control-interstitial')
            references = []
            for href in parser.links[:100]:
                try:
                    link = public_url(urljoin(current, href))
                    if link != current and link not in references:
                        references.append(link)
                except ValueError:
                    pass
            source_links = []
            for hint in parser.source_link_hints():
                try:
                    link = public_url(urljoin(current, hint['href']))
                    if link != current:
                        source_links.append({**hint, 'url': link})
                except ValueError:
                    pass
            selected, selection = select_reading_window(text, focus_query, MAX_TEXT)
            document = {'requested_url': original, 'url': current, 'redirects': redirects,
                    'title': title, 'text': selected, 'truncated': len(selected) < len(text),
                    'text_selection': selection,
                    'fetched_at': datetime.now(timezone.utc).isoformat(),
                    'body_sha256': hashlib.sha256(raw).hexdigest(),
                    'text_sha256': hashlib.sha256(selected.encode()).hexdigest(),
                    'published_at': None, 'publisher_authenticated': False,
                    'page_metadata_hints': parser.date_hints(),
                    'publication_date_conflict': parser.date_conflict(),
                    'source_link_hints': source_links,
                    'extraction_method': extraction,
                    'extraction_verified': False,
                    'independence': 'unknown', 'instructions_are_data': True,
                    'reference_links': references[:8], 'reference_links_verified': False,
                    'original_source_identified': False,
                    'locator': '服务端提取的可读文本；非完整页面' if len(text) > MAX_TEXT else '服务端提取的可读文本'}
            if capture is not None:
                # Operator-supplied archival callback, never accepted from tasks.
                capture(raw, document)
            return document
        finally:
            conn.close()
    raise ValueError('redirect limit')


def public_search_plan(query):
    """Finite query reformulation, not an assertion or semantic interpretation."""
    focus = []
    subject = query
    profile = retrieval_profile(query)
    names = institution_names(query)
    if len(names) == 2 and re.search(r'就是|同一|区别|两者|关系|机构|正式名称', query):
        return {'queries': [query, ' '.join(names) + ' 区别 正式名称 地址 官方'],
                'focus_terms': names, 'profile': profile,
                'scope': 'institution-identity-discovery-not-a-verdict'}
    if profile['domains'] != ['general']:
        return {'queries': [query, profile.get('focused_query') or query + profile['query_suffix']],
                'focus_terms': (['原始研究', '独立评测', '论文', '实验', '评估', 'benchmark',
                                 'evaluation', 'study'] if 'academic' in profile['domains'] else []), 'profile': profile,
                'scope': 'bounded-keyword-heuristic-not-fact-verification'}
    # Assertions and questions need the same follow-up retrieval. These hints
    # allocate reading slots; they never establish a verdict about the subject.
    evaluative = re.fullmatch(
        r'\s*([^，,。；;！？?\n]{1,80}?)\s*(?:是不是|不是|是)\s*'
        r'[^，,。；;！？?\n]{0,30}(?:天才|权威|靠谱|神医|骗局)'
        r'(?:吗|么)?\s*[。！？!?]?\s*', query)
    if evaluative:
        subject = evaluative.group(1).strip()
    if evaluative or re.search(r'事件|争议|后续|调查|辟谣', query):
        focus = ['情况说明', '调查', '通报', '回应', '更正', '核查', '后续']
        terms = ' 事件 后续 调查 情况说明 通报 核查'
    elif re.search(r'放假|调休|休假|假期', query):
        focus = ['放假', '调休', '休假', '假期']
        terms = ' 放假 调休 安排 通知 报道 核实'
    elif re.search(r'开放时间|营业时间|闭馆|开馆|入馆|参观|预约规则|开放日|营业日', query):
        focus = ['开放时间', '参观须知', '开放安排', '营业时间', '预约须知', '参观导览']
        terms = ' 官网 现行 开放时间 营业时间 参观须知 例外'
    else:
        terms = ' 公告 报道 核实 回应'
    return {'queries': [query, subject + terms], 'focus_terms': focus, 'profile': profile,
            'scope': 'bounded-keyword-heuristic-not-fact-verification'}


def next_public_lead(queue, attempted_hosts, focus_terms, domains=()):
    """Allocate existing slots across relevant titles and hosts, not truth scores."""
    if queue[0].get('discovery') in ('caller-link', 'source-link', 'recovery-search'):
        return queue.popleft()
    def priority(lead):
        title = str(lead.get('title', ''))[:300]
        hits = sum(term in title for term in focus_terms)
        parts = urlsplit(lead['url'])
        host = (parts.hostname or '').removeprefix('www.')
        media = bool(re.search(r'/(?:video|shorts|watch)(?:/|$)', parts.path))
        statement = any(word in title for word in ('情况说明', '情况通报', '调查结果', '更正', '声明全文'))
        if 'academic' in domains:
            # A second paper on the same repository must not lose its reading
            # slot just because another vendor blog is on a different host.
            # These are discovery hints only, not relevance/authenticity checks.
            return (not media, domain_priority(lead['url'], domains), bool(hits),
                    host not in attempted_hosts, hits)
        if any(term in focus_terms for term in ('开放时间', '营业时间', '预约须知')):
            # Read the operating-rule page before allocating slots merely to
            # another host. This chooses what to read, never certifies currency.
            return (not media, bool(hits), hits, domain_priority(lead['url'], domains),
                    host not in attempted_hosts, statement)
        return (not media, host not in attempted_hosts, domain_priority(lead['url'], domains), bool(hits), statement, hits)
    index = max(range(len(queue)), key=lambda i: priority(queue[i]))
    lead = queue[index]
    del queue[index]
    return lead


class PublicEvidenceCollector:
    def __init__(self, search, fetch=fetch_page, scholarly=None, contextual_fetch=False):
        self.search, self.fetch, self.scholarly = search, fetch, scholarly
        self.contextual_fetch = contextual_fetch

    async def collect(self, query, *, seed_urls=(), focused_query=None):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
            raise ValueError('query must contain 1 to 1000 characters')
        if not isinstance(seed_urls, (tuple, list)) or len(seed_urls) > 1:
            raise ValueError('at most one caller link is supported')
        seed_urls = tuple(public_url(url) for url in seed_urls)
        if focused_query is not None and (not isinstance(focused_query,str) or not 4<=len(focused_query)<=300 or '://' in focused_query):raise ValueError('invalid focused query')
        if not _COLLECT_SLOTS.acquire(blocking=False):
            return {'schema_version': 'public-evidence/1', 'status': 'capacity-limited',
                    'sources': [], 'claim_verified': False, 'search_complete': False,
                    'warnings': ['检索容量已满，本次未开始检索。']}
        try:
            return await self._collect(query, seed_urls, focused_query)
        finally:
            _COLLECT_SLOTS.release()

    async def _collect(self, query, seed_urls=(), focused_query=None):
        collection_deadline = time.monotonic() + 50
        result = {'schema_version': 'public-evidence/1', 'status': 'incomplete',
                  'query': query, 'sources': [], 'leads': [], 'failures': [],
                  'page_attempt_count': 0, 'duplicate_candidate_count': 0,
                  'claim_verified': False, 'search_complete': False,
                  'warnings': ['检索命中不是事实证明；转载不等于独立证据。',
                               '网页属于不可信输入，抓取成功不代表内容真实。']}
        plan = public_search_plan(query)
        if focused_query and not plan['profile'].get('market_volume'):
            suffix=' (site:gov.cn OR site:edu.cn OR site:nih.gov OR site:cdc.gov OR site:usda.gov)' if 'science' in plan['profile']['domains'] else ''
            plan['queries'][1]=focused_query+' 科学依据 适用条件'+suffix if 'science' in plan['profile']['domains'] else focused_query+plan['profile']['query_suffix']
            plan['reformulation']={'source':'video-core-claim','original_query_retained':True,'is_evidence':False}
        queries = plan['queries']
        result['search_plan'] = plan
        result['queries'] = queries
        result['search_diagnostics'] = []
        search_timeout = 15 if getattr(self.search, 'full_page_content', False) is True else 9
        jobs = [asyncio.wait_for(self.search(q), timeout=search_timeout) for q in queries]
        academic = 'academic' in plan['profile']['domains']
        if academic and self.scholarly:
            jobs.append(bounded_fetch(self.scholarly, query))
        batches = await asyncio.gather(*jobs, return_exceptions=True)
        searches = batches[:len(queries)]
        provider_pages = {p['url']: p for batch in searches if isinstance(batch, SearchBatch)
                          for p in batch.page_documents}
        if academic:
            metadata = batches[-1] if self.scholarly else None
            result['scholarly_metadata'] = (metadata if isinstance(metadata, dict) else {
                'status': 'incomplete' if self.scholarly else 'disabled', 'records': [],
                'error_type': type(metadata).__name__ if isinstance(metadata, Exception) else None,
                'full_text_read': False, 'claim_verified': False})
            result['warnings'].append('论文元数据与摘要不等于全文或研究结论；命中记录仍需核对主题相关性。')
        leads = [{'url': url, 'title': '', 'discovery': 'caller-link'} for url in seed_urls]
        for index, found in enumerate(searches):
            if isinstance(found, Exception) or not isinstance(found, list):
                result['failures'].append({'stage': 'search', 'query_index': index,
                    'error_type': type(found).__name__ if isinstance(found, Exception) else 'InvalidSchema'})
            elif isinstance(found, SearchBatch):
                if found.search_metadata:
                    result['search_diagnostics'].append({'query_index': index, **found.search_metadata})
                for failure in found.engine_failures:
                    result['failures'].append({'stage': 'search-engine',
                        'query_index': index, **failure})
        result['search_complete'] = not result['failures']
        # Round-robin gives neutral and response searches equal slots.
        for index in range(8):
            for found in searches:
                if isinstance(found, list) and index < len(found):
                    leads.append(found[index])
        records = result.get('scholarly_metadata', {}).get('records', [])
        # Read DOI landing pages only within the existing three page attempts.
        leads.extend({'url': r['url'], 'title': r['title'], 'discovery': 'bibliographic-lead'} for r in records)
        if academic and result['scholarly_metadata']['status'] not in ('retrieved', 'no-results'):
            result['search_complete'] = False
        domains = plan['profile']['domains']
        max_attempts = 5 if any(d in domains for d in ('academic', 'legal')) else 3
        if 'legal' in domains:
            result['warnings'].append('法律资料需另核对适用地区、版本、条号及施行/废止状态；不提供法律意见。')
        seen, hashes, attempts, trace_scheduled = set(), {}, 0, False
        queue, candidates = deque(), set()
        for lead in leads[:16]:
            try:
                url = public_url(lead['url'])
            except (KeyError, TypeError, ValueError):
                continue
            if url in candidates:
                result['duplicate_candidate_count'] += 1
                continue
            candidates.add(url)
            queue.append({**lead, 'url': url})
        attempted_hosts = set()
        result['source_selection'] = {
            'method': 'readable-page-then-topic-statement-host-diversity',
            'candidate_count': len(candidates), 'max_page_attempts': max_attempts, 'max_read_sources': 3,
            'attempted_hosts': [], 'independence_established': False,
            'note': '标题关键词只用于分配读取机会，不证明相关事实；不同主机不代表独立来源。'}
        result['source_relations'] = []
        recovery_used = False
        while True:
            missing_subjects = missing_institutions(query, result['sources'])
            if len(result['sources']) >= 3:
                if recovery_used or not missing_subjects:
                    break
                result.setdefault('supplementary_sources', []).append(result['sources'].pop())
            if time.monotonic() >= collection_deadline:
                result['failures'].append({'stage': 'collection', 'reason': 'time-budget'})
                break
            if not queue or attempts >= max_attempts:
                # An ordinary successful collection keeps its existing budget.
                # Only a failed reading round gets one bounded recovery phase.
                if recovery_used or (result['sources'] and not missing_subjects) or not candidates:
                    break
                recovery_used = True
                retry_queries = recovery_queries(query, subjects=missing_subjects or None)
                remaining = collection_deadline - time.monotonic()
                if remaining < 2:
                    break
                extra_attempts = 2 if academic else 3  # Keep archive below 12 acquisitions including Crossref.
                result['recovery'] = {'status': 'attempted', 'queries': retry_queries,
                    'reason': 'missing-institution-material' if result['sources'] else 'no-substantive-readable-evidence', 'max_extra_page_attempts': extra_attempts}
                start_index = len(result['queries'])
                result['queries'].extend(retry_queries)
                retry_batches = await asyncio.gather(*[
                    asyncio.wait_for(self.search(q), timeout=min(search_timeout, remaining))
                    for q in retry_queries], return_exceptions=True)
                provider_pages.update({p['url']: p for batch in retry_batches if isinstance(batch, SearchBatch)
                                       for p in batch.page_documents})
                fresh = []
                for index, found in enumerate(retry_batches):
                    if not isinstance(found, list):
                        result['failures'].append({'stage': 'recovery-search',
                            'query_index': start_index + index, 'error_type': type(found).__name__})
                        result['search_complete'] = False
                    elif isinstance(found, SearchBatch):
                        if found.search_metadata:
                            result['search_diagnostics'].append({'query_index': start_index+index, **found.search_metadata})
                        for failure in found.engine_failures:
                            result['failures'].append({'stage': 'recovery-search-engine',
                                'query_index': start_index+index, **failure})
                            result['search_complete'] = False
                for index in range(5):
                    for found in retry_batches:
                        if not isinstance(found, list) or index >= len(found):
                            continue
                        lead = found[index]
                        try:
                            url = public_url(lead['url'])
                        except (KeyError, TypeError, ValueError):
                            continue
                        if url in candidates:
                            continue
                        candidates.add(url)
                        fresh.append({**lead, 'url': url, 'discovery': 'recovery-search'})
                # New subject-specific results precede the remaining old leads.
                queue.extendleft(reversed(fresh))
                max_attempts = attempts + extra_attempts
                result['source_selection'].update(candidate_count=len(candidates), max_page_attempts=max_attempts)
                if not queue:
                    break
            lead = next_public_lead(queue, attempted_hosts, plan['focus_terms'], domains)
            url = None
            try:
                url = public_url(lead['url'])
                if url in seen:
                    result['duplicate_candidate_count'] += 1
                    continue
                seen.add(url)
                attempted_hosts.add((urlsplit(url).hostname or '').removeprefix('www.'))
                result['source_selection']['attempted_hosts'] = sorted(attempted_hosts)
                attempts += 1
                result['page_attempt_count'] = attempts
                # Never carry search-result summaries into evidentiary text.
                result['leads'].append({'url': url, 'title': str(lead.get('title', ''))[:300],
                                       'discovery': lead.get('discovery', 'search'),
                                       'linked_from': lead.get('linked_from')})
                # A delayed DNS resolver must not stall the AIP task forever.
                # fetch_page checks its own deadline before any later connection.
                reader = (lambda target: self.fetch(target, focus_query=query)) if self.contextual_fetch else self.fetch
                if url in provider_pages:
                    await bounded_fetch(lambda target: public_addresses(urlsplit(target).hostname), url,
                                        timeout=min(7, max(.1, collection_deadline-time.monotonic())))
                    page = dict(provider_pages[url])
                else:
                    page = await bounded_fetch(reader, url, timeout=min(7, max(.1, collection_deadline-time.monotonic())))
                rejected = non_evidence_page(page)
                if rejected:
                    result['failures'].append({'stage': 'content-filter', 'url': url, 'reason': rejected})
                    continue
                if 'legal' in domains:
                    page['legal_context'] = legal_reading_context(page)
                digest = page['text_sha256']
                if lead.get('linked_from'):
                    result['source_relations'].append({
                        'from_url': lead['linked_from'], 'to_url': page['url'],
                        'relationship': 'page-declared-source-link',
                        'label': lead.get('label', ''), 'target_read': True,
                        'original_source_verified': False, 'independence_verified': False})
                if digest in hashes:
                    result['failures'].append({'url': url, 'stage': 'deduplicate',
                                               'duplicate_of': hashes[digest]})
                    continue
                hashes[digest] = page['url']
                page['source_id'] = 'web-' + digest[:16]
                page['discovery'] = lead.get('discovery', 'search')
                result['sources'].append(page)
                # At most one follow-up per collection, within the SAME three
                # page attempts. Keep remaining slots for a separate search lead.
                if not trace_scheduled and lead.get('discovery') != 'source-link':
                    for hint in page.get('source_link_hints', [])[:8]:
                        try:
                            linked = public_url(hint['url'])
                        except (KeyError, ValueError, TypeError):
                            continue
                        if linked not in seen:
                            queue.appendleft({'url': linked, 'title': '',
                                'discovery': 'source-link', 'linked_from': page['url'],
                                'label': str(hint.get('label', ''))[:200]})
                            trace_scheduled = True
                            break
            except Exception as exc:
                result['failures'].append(page_failure(url, exc))
        result['status'] = ('retrieved' if result['sources'] else 'metadata-only' if records else
                            'no-readable-evidence' if not result['failures'] else 'incomplete')
        result['source_review'] = review_sources(result)
        return result


class SearxSearch:
    """Operator-owned search endpoint; never set by a task or scraped page."""
    def __init__(self, endpoint, transport=None, capture=None):
        p = urlsplit(endpoint)
        if (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password
                or p.query or p.fragment or '\\' in endpoint):
            raise ValueError('invalid operator search endpoint')
        self.endpoint, self.transport = endpoint, transport
        self.capture = capture

    async def __call__(self, query):
        async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False,
                                     transport=self.transport) as client:
            async with client.stream('GET', self.endpoint,
                    params={'q': query, 'format': 'json', 'language': 'zh-CN'}) as response:
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise ValueError('search response too large')
        if self.capture is not None:
            self.capture(query, bytes(raw))
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get('results'), list):
            raise ValueError('invalid search schema')
        if 'query' in value and value['query'] != query:
            raise ValueError('search query mismatch')
        failed = value.get('unresponsive_engines', [])
        if not isinstance(failed, list) or len(failed) > 64:
            raise ValueError('invalid engine failure schema')
        failures = []
        for row in failed:
            if (not isinstance(row, list) or len(row) != 2
                    or not all(isinstance(item, str) for item in row)):
                raise ValueError('invalid engine failure schema')
            engine = row[0] if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', row[0]) else 'unknown'
            reason = row[1].lower()
            kind = ('Captcha' if 'captcha' in reason else
                    'Timeout' if 'timeout' in reason else
                    'AccessDenied' if any(x in reason for x in ('denied', 'forbidden', 'blocked'))
                    else 'EngineUnavailable')
            failures.append({'engine': engine, 'error_type': kind})
        return SearchBatch(value['results'][:8], failures)


def configured_collector():
    if os.getenv('PUBLIC_RETRIEVAL_ENABLED', 'false').lower() != 'true':
        return None
    provider = os.getenv('PUBLIC_SEARCH_PROVIDER', 'searx').strip().lower()
    if provider == 'tavily':
        from .tavily_search import TavilySearch
        key = os.getenv('TAVILY_KEY_FILE', '').strip()
        budget = os.getenv('TAVILY_SEARCH_BUDGET_FILE', '').strip()
        if not key or not budget:
            raise ValueError('Explicit private search key and persistent search budget required')
        if budget == os.getenv('DEEPSEEK_BUDGET_FILE'):
            raise ValueError('Search and model budget paths must differ')
        limit = os.getenv('TAVILY_SEARCH_MAX_CALLS', '20')
        if not limit.isdecimal() or not 1 <= int(limit) <= 500:
            raise ValueError('Search preparation limit must be 1 to 500')
        archive_root = os.getenv('PUBLIC_RETRIEVAL_ARCHIVE_ROOT', '').strip()
        archive = None
        if archive_root:
            from .retrieval_archive import RetrievalArchive, AIP_TASK_ID
            archive = RetrievalArchive(archive_root, AIP_TASK_ID.get())
        search = TavilySearch(key, budget, int(limit), capture=archive.search if archive else None)
        collector = PublicEvidenceCollector(search,
            fetch=(lambda url, **kwargs: fetch_page(url, capture=archive.page, **kwargs)) if archive else fetch_page,
            contextual_fetch=True)
        if os.getenv('SCHOLARLY_METADATA_ENABLED', 'false').lower() == 'true':
            from .scholarly_metadata import crossref_lookup
            collector.scholarly = lambda query: crossref_lookup(query, capture=archive.search if archive else None)
        collector.archive = archive
        return collector
    if provider != 'searx':
        raise ValueError('Unknown explicitly configured search provider')
    endpoint = os.getenv('PUBLIC_SEARCH_ENDPOINT', '').strip()
    if not endpoint:
        raise ValueError('PUBLIC_SEARCH_ENDPOINT is required; no default external provider')
    collector = PublicEvidenceCollector(SearxSearch(endpoint), contextual_fetch=True)
    if os.getenv('SCHOLARLY_METADATA_ENABLED', 'false').lower() == 'true':
        from .scholarly_metadata import crossref_lookup
        collector.scholarly = crossref_lookup
    return collector


def bind_public_quotes(review, pages):
    """Do not permit a model quote to cross source boundaries or cite metadata."""
    pending = []
    for row in review.get('claims', []):
        for quote in row.get('quotes', []):
            matches = [p for p in pages if p['text'].count(quote['text']) == 1]
            if len(matches) != 1:
                return {'status': 'failed-or-invalid', 'failure_stage': 'source-binding',
                        'reason': '引用不能唯一对应实际读取的网页，未采用模型结论。'}
            pending.append((quote, matches[0]))
    for quote, page in pending:
        quote['source_id'], quote['source_url'] = page['source_id'], page['url']
    return review
