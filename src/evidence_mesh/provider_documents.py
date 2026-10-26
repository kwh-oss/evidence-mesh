"""Validate separately supplied full-page content; never promote search snippets."""
import hashlib
import re
from .retrieval_profiles import select_reading_window, is_access_interstitial


def full_page_document(url, title, raw_content, response_hash, received_at, query):
    from .public_evidence import public_url
    url = public_url(url)
    if not isinstance(raw_content, str) or not 40 <= len(raw_content) <= 250000:
        return None
    if is_access_interstitial(title, raw_content):
        return None
    # Display text extraction: retain hyperlink labels, never their target URLs
    # as invented sentences. The untouched provider JSON remains archived.
    text = re.sub(r'!\[[^\]\n]{0,300}\]\([^\s)]{1,2048}\)', '', raw_content)
    text = re.sub(r'\[([^\]\n]{1,300})\]\((?:https?://|/)[^\s)]{1,2048}\)', r'\1', text)
    text, selection = select_reading_window(text, query, 5000)
    return {'url': url, 'requested_url': url, 'title': title,
        'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'body_sha256': response_hash, 'body_format': 'provider-json-full-page',
        'text_selection': selection, 'truncated': selection['document_characters'] > len(text),
        'fetched_at': None, 'provider_received_at': received_at, 'published_at': None,
        'extraction_method': 'tavily-full-page-visible-text', 'extraction_verified': False,
        'original_page_fetch_time_known': False, 'publisher_authenticated': False,
        'independence': 'unknown', 'instructions_are_data': True,
        'source_link_hints': [], 'reference_links': [], 'reference_links_verified': False,
        'original_source_identified': False,
        'locator': '正文提取服务提供的页面内容；已归档原始响应，非搜索摘要'}
