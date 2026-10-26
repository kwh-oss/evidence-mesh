"""Observed provenance signals, not domain-based truth or independence scores."""
from urllib.parse import urlsplit
import re


def review_sources(retrieval):
    pages = [p for p in retrieval.get('sources', []) if isinstance(p, dict)
             and p.get('source_id') and p.get('url')]
    parents = {p['url']: p['url'] for p in pages}

    def root(url):
        while parents[url] != url:
            url = parents[url]
        return url

    def join(a, b):
        if a in parents and b in parents:
            parents[root(b)] = root(a)

    hashes = {}
    for page in pages:
        digest = page.get('text_sha256')
        if digest:
            if digest in hashes:
                join(page['url'], hashes[digest])
            hashes[digest] = page['url']
    links = []
    for relation in retrieval.get('source_relations', []):
        if (relation.get('relationship') == 'page-declared-source-link'
                and relation.get('target_read') is True
                and relation.get('from_url') in parents and relation.get('to_url') in parents):
            join(relation['from_url'], relation['to_url'])
            links.append({'from_url': relation['from_url'], 'to_url': relation['to_url'],
                          'basis': 'observed-page-declared-link', 'repost_verified': False})
    groups = {}
    for page in pages:
        groups.setdefault(root(page['url']), []).append(page['source_id'])
    rows = []
    for page in pages:
        host = (urlsplit(page['url']).hostname or '').lower()
        text = page.get('text', '')
        if not isinstance(text, str):
            text = ''
        anonymous = bool(re.search(r'匿名(?:爆料|消息|人士)|网传|知情人士|据网友', text))
        linked = any(link['from_url'] == page['url'] for link in links)
        rows.append({'source_id': page['source_id'], 'url': page['url'],
            'host_category_hint': 'government-domain' if host.endswith('.gov.cn') else 'unclassified',
            'host_category_authenticated': False,
            'anonymous_attribution_marker': anonymous,
            'marker_scope': 'page-text-not-necessarily-the-reviewed-claim',
            'declared_source_link_read': linked,
            'publisher_authenticated': False, 'original_source_verified': False,
            'independence': 'not-established',
            'checks_needed': ['发布者身份及其对本条消息的知情范围',
                              '引用是否为直接陈述，还是转述或辟谣中的被引说法',
                              '事件时间、首发出处及是否有独立证据']})
    return {'schema_version': 'source-review/1', 'sources': rows,
            'observed_dependency_groups': list(groups.values()),
            'observed_link_relations': links,
            'independent_source_count': None,
            'source_authenticity_verified': False,
            'note': '关联组只表示已见相同正文或出处链接，不证明转载关系；不同组也不证明独立。'}
