"""Bounded discovery hints. Domain preference is never proof of authenticity."""
import re
from urllib.parse import urlsplit


def retrieval_profile(query):
    domains = []
    market_volume=bool(re.search(r'年销量|年销售|销售量|出货量|市场规模|annual sales|unit sales|market size',query,re.I))
    if re.search(r'论文|文献|学术|DOI|doi\s*[:：]|10\.\d{4,9}/|literature|journal|systematic review|'
                 r'研究(?:说|表明|显示|发现|证明|结论)|一项研究|最新研究|科学研究|'
                 r'实验(?:表明|显示|证明|结果)|\b(?:study|studies|research)\s+(?:says?|shows?|finds?|suggests?|claims?)\b', query, re.I):
        domains.append('academic')
    if 'academic' not in domains and re.search(r'科学依据|科学原理|实验证据|科学机制|有效性|功效|scientific evidence|scientific basis',query,re.I):
        domains.append('science')
    if re.search(r'法律|法规|法条|条款|民法典|司法解释|劳动法|合同法|消费者权益|legal|statute|legislation', query, re.I):
        domains.append('legal')
    if re.search(r'政策|通知|公告|补贴|办事|政务', query):
        domains.append('policy')
    if re.search(r'统计|数据集|年鉴|普查|statistics|dataset', query, re.I):
        domains.append('statistics')
    if re.search(r'产品|说明书|规格|售后|退款|退货|保修', query):
        domains.append('product')
    if not domains:
        domains = ['general']
    if market_volume and 'statistics' not in domains:
        domains=[d for d in domains if d!='general']+['statistics']
    terms = {
        'academic': ' 原始研究 论文 独立评测 方法 局限 original study independent evaluation',
        'science': ' 科学原理 实验证据 适用条件 局限',
        'legal': ' 法律 法规 条款 原文 生效 修订 site:gov.cn OR site:npc.gov.cn OR site:court.gov.cn',
        'policy': ' 官方 通知 政策 原文 发布日期 site:gov.cn',
        'statistics': ' 数据 来源 统计公报 方法 口径',
        'product': ' 官方 说明书 规格 售后 条款',
        'general': ' 公告 报道 核实 回应',
    }
    # Retain original query separately. Chinese official-source targeting is a
    # fallback lead, not an assumption that Chinese law governs every request.
    foreign_law = bool(re.search(r'美国|英国|欧盟|香港|澳门|台湾|US law|UK law|GDPR', query, re.I))
    suffix = ''.join(terms[d] for d in domains[:2])
    if foreign_law:
        suffix = suffix.replace(' site:gov.cn OR site:npc.gov.cn OR site:court.gov.cn', '')
    focused_query = None
    if market_volume:
        # Retain the asserted figure in the original query, but do not require
        # an independent report to repeat that number to become a search hit.
        neutral=re.sub(r'(?:达到|超过|高达|约|接近)?\s*[0-9零〇一二三四五六七八九十百千万亿两几数点.,，]+\s*(?:具|件|台|辆|套|吨|人次|美元|元)(?:以上|左右)?',' ',query)
        neutral=re.sub(r'是否达到|是不是|是否|能否|达到|的规模|规模[？?]|[？?！!，,。]',' ',neutral)
        focused_query=' '.join(neutral.split())+' 独立行业报告 实际销量 年份 地区 产品分类 统计口径 数据来源'
    if 'science' in domains:
        focused_query=query+' 科学依据 适用条件 (site:gov.cn OR site:edu.cn OR site:nih.gov OR site:cdc.gov OR site:usda.gov)'
    if 'legal' in domains:
        names = re.findall(r'《([^》]{2,100})》', query)
        articles = re.findall(r'第[零〇一二三四五六七八九十百千万两0-9]{1,14}条', query)
        if names:
            focused_query = ' '.join(names[:2] + articles[:2]) + ' 原文'
            if not foreign_law:
                focused_query += ' (site:npc.gov.cn OR site:gov.cn OR site:court.gov.cn)'
    return {'domains': domains, 'query_suffix': suffix,'market_volume':market_volume,
            'focused_query': focused_query,
            'scope': 'bounded-keyword-routing-not-domain-understanding',
            'jurisdiction': 'not-confirmed', 'exhaustive': False}


def domain_priority(url, domains):
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    def within(root):
        return host == root or host.endswith('.' + root)
    if 'legal' in domains or 'policy' in domains:
        return int(any(within(root) for root in ('gov.cn', 'npc.gov.cn', 'court.gov.cn')))
    if 'academic' in domains:
        return int(any(within(root) for root in ('doi.org', 'pubmed.ncbi.nlm.nih.gov',
            'pmc.ncbi.nlm.nih.gov', 'arxiv.org', 'aclanthology.org', 'openreview.net')))
    if 'science' in domains:
        return int(host.endswith('.edu') or any(within(root) for root in
            ('edu.cn','gov.cn','nih.gov','cdc.gov','usda.gov','doi.org','nature.com','science.org')))
    if 'statistics' in domains:
        return int(within('stats.gov.cn'))
    return 0


def research_reference(url):
    """Recognize a few citation locators, not a paper's identity or quality.

    Used only to offer a bounded follow-up read. Home pages and lookalike hosts
    must not consume a citation slot merely by containing a familiar string.
    """
    try:
        parts = urlsplit(url)
        host, path = (parts.hostname or '').lower().rstrip('.'), parts.path
        if parts.scheme != 'https' or parts.username or parts.password:
            return False
        return bool(
            (host in ('doi.org', 'dx.doi.org') and re.match(r'/10\.\d{4,9}/\S+', path)) or
            (host in ('arxiv.org', 'www.arxiv.org') and re.match(r'/(?:abs|html|pdf)/\S+', path)) or
            (host == 'pubmed.ncbi.nlm.nih.gov' and re.fullmatch(r'/\d+/?', path)) or
            (host == 'pmc.ncbi.nlm.nih.gov' and re.match(r'/articles/PMC\d+', path)) or
            (host == 'aclanthology.org' and re.fullmatch(r'/(?:[A-Z]\d{2}-\d{4}|\d{4}\.[A-Za-z0-9.-]+)/?', path)) or
            (host == 'openreview.net' and path in ('/forum', '/pdf') and re.search(r'(?:^|&)id=[^&]+', parts.query)))
    except ValueError:
        return False


def legal_reading_context(page):
    """Expose outstanding checks; never infer validity from a domain or date."""
    return {'official_domain_hint': bool(domain_priority(page['url'], ['legal'])),
            'jurisdiction': 'not-confirmed', 'effective_status': 'not-verified',
            'version_verified': False, 'article_match_verified': False,
            'article_window_located': page.get('text_selection', {}).get('method') == 'explicit-article-window',
            'requested_article': page.get('text_selection', {}).get('requested_article'),
            'publication_hints': page.get('page_metadata_hints', []),
            'note': '需核对适用地区、条号、施行日期和修订/废止状态；抓取日期不是施行日期。本结果不是法律意见。'}


def select_reading_window(text, query, limit):
    """Select an explicitly named Chinese article without paraphrase or inference.

    Retain offsets into the extracted document so a late statute clause is not
    lost to the ordinary first-5000-character cut. Multiple matches stay unknown.
    """
    start, label, located = 0, None, False
    requested = re.findall(r'第[零〇一二三四五六七八九十百千万两0-9]{1,14}条', query or '')
    if len(set(requested)) == 1:
        label = requested[0]
        matches = list(re.finditer(r'(?:^|\n)[ \t\u3000]*' + re.escape(label) + r'(?=[\s：:])', text))
        if len(matches) == 1:
            start = matches[0].start()
            located = True
    selected = text[start:start + limit]
    return selected, {'method': 'explicit-article-window' if located else 'document-prefix',
        'requested_article': label, 'start': start, 'end': start + len(selected),
        'document_characters': len(text), 'article_interpretation_verified': False}


def is_access_interstitial(title, text):
    """Conservative known block-page signatures, not general relevance scoring."""
    title = title.lower().strip()
    short = text[:1800].lower()
    if re.search(r'error\s*blocked|error.*diagnostic|access denied|just a moment|security verification|安全验证|访问受限|访问验证', title):
        return True
    return (len(text) < 2500 and any(marker in short for marker in (
        'temporarily blocked due to a possible misuse', 'verify you are human',
        'enable javascript and cookies to continue', 'checking your browser before accessing')))
