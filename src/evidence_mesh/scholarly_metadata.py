"""One fixed-endpoint Crossref lookup, at most five bibliographic leads.

Metadata/abstracts remain separate from read webpage evidence. No full-text,
peer-review, retraction-status or relevance certification is implied.
"""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import re
import socket
import time
from urllib.parse import quote, urlencode


class PlainMarkup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def plain(value, limit=1000):
    if not isinstance(value, str):
        return ''
    parser = PlainMarkup()
    parser.feed(value[:20000])
    return ' '.join(' '.join(parser.parts).split())[:limit]


def parse_records(value, *, exact_doi=None):
    if not isinstance(value, dict) or value.get('status') != 'ok':
        raise ValueError('invalid Crossref response')
    message = value.get('message')
    rows = [message] if exact_doi else message.get('items') if isinstance(message, dict) else None
    if not isinstance(rows, list):
        raise ValueError('invalid Crossref items')
    records, seen = [], set()
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        doi = row.get('DOI', '')
        if not isinstance(doi, str) or not re.fullmatch(r'10\.\d{4,9}/[^\s<>"\x00-\x1f]{1,180}', doi, re.I):
            continue
        if exact_doi and doi.casefold() != exact_doi.casefold():
            raise ValueError('DOI response mismatch')
        if doi.casefold() in seen:
            continue
        title = row.get('title')
        title = plain(title[0]) if isinstance(title, list) and title else ''
        if not title:
            continue
        seen.add(doi.casefold())
        authors = row.get('author', [])
        authors = authors if isinstance(authors, list) else []
        journal = row.get('container-title', [])
        abstract = plain(row.get('abstract'), 3000)
        dates = {}
        for key in ('published', 'published-online', 'published-print', 'issued'):
            date = row.get(key)
            parts = date.get('date-parts') if isinstance(date, dict) else None
            if (isinstance(parts, list) and parts and isinstance(parts[0], list)
                    and 1 <= len(parts[0]) <= 3 and all(type(n) is int for n in parts[0])):
                dates[key] = parts[0]
        records.append({'doi': doi, 'url': 'https://doi.org/' + quote(doi, safe='/'),
            'title': title, 'authors': [plain(' '.join(str(a.get(k, '')) for k in ('given', 'family')), 150)
                for a in authors[:12] if isinstance(a, dict)],
            'authors_truncated': len(authors) > 12,
            'container_title': plain(journal[0]) if isinstance(journal, list) and journal else '',
            'publication_dates': dates, 'record_type': plain(row.get('type'), 80),
            'abstract': abstract, 'abstract_truncated': bool(abstract) and len(plain(row.get('abstract'), 3001)) > 3000,
            'read_scope': 'metadata-and-deposited-abstract' if abstract else 'metadata-only',
            'full_text_read': False, 'relevance_verified': False, 'peer_review_verified': False,
            'retraction_status': 'not-checked', 'claim_verified': False,
            'provenance': 'Crossref deposited metadata; not independent factual verification'})
    return records


def crossref_lookup(query, *, resolver=socket.getaddrinfo, connection_factory=None, capture=None):
    from .public_evidence import public_addresses, PinnedHTTPSConnection, MAX_BYTES
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
        raise ValueError('invalid scholarly query')
    match = re.search(r'10\.\d{4,9}/[^\s<>"，。；;]{1,180}', query, re.I)
    doi = match.group(0).rstrip('.,') if match else None
    titles = re.findall(r'《([^》]{2,200})》', query)
    bibliographic_query = ' '.join(titles[:2]) if titles else query
    parameters = {'query.title' if titles else 'query.bibliographic': bibliographic_query, 'rows': 5}
    if not re.search(r'书籍|图书|书章|book|chapter', query, re.I):
        parameters['filter'] = 'type:journal-article'
    path = '/works/' + quote(doi, safe='/') if doi else '/works?' + urlencode(parameters)
    host = 'api.crossref.org'
    deadline = time.monotonic() + 6
    addresses = public_addresses(host, resolver)
    if time.monotonic() >= deadline:
        raise TimeoutError('metadata deadline')
    conn = (connection_factory or PinnedHTTPSConnection)(host, addresses[0])
    try:
        conn.timeout = min(4, deadline - time.monotonic())
        conn.request('GET', path, headers={'Accept': 'application/json', 'Accept-Encoding': 'identity',
                     'User-Agent': 'EvidenceMesh/0.3 (https://api.linsixuan.cn/) scholarly-metadata'})
        response = conn.getresponse()
        if (response.status != 200 or response.getheader('Content-Type', '').split(';')[0].strip().lower() != 'application/json'
                or response.getheader('Content-Encoding', 'identity') != 'identity'):
            raise ValueError('Crossref unavailable or invalid media')
        raw = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('metadata deadline')
            if conn.sock is not None:
                conn.sock.settimeout(remaining)
            chunk = response.read1(min(32768, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise ValueError('metadata response too large')
        raw = bytes(raw)
        records = parse_records(json.loads(raw), exact_doi=doi)
        if capture:
            capture('Crossref metadata: ' + query, raw)
        return {'provider': 'Crossref', 'status': 'retrieved' if records else 'no-results',
            'request_url': 'https://' + host + path, 'request_count': 1,
            'bibliographic_query': doi or bibliographic_query,
            'fetched_at': datetime.now(timezone.utc).isoformat(),
            'body_sha256': hashlib.sha256(raw).hexdigest(), 'records': records,
            'full_text_read': False, 'claim_verified': False, 'exhaustive': False,
            'note': '书目和摘要来自登记元数据，不代表读过全文、完成综述或确认结论；中文与非Crossref收录资料可能漏检。'}
    finally:
        conn.close()
