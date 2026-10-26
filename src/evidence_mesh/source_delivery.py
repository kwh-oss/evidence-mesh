"""Deliver acquired text, never upgrade search hits into verified conclusions."""
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit


def retrieval_question(text):
    """Remove a known appended scheduler block, only outside quoted data."""
    quoted = list(re.finditer(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"', text))
    for match in re.finditer(r'\s+DAG\s*指定的上游产物摘要\s*[:：]', text):
        if not any(q.start() <= match.start()+1 < q.end() for q in quoted):
            return text[:match.start()].strip()
    return text.strip()



def _label(value):
    return re.sub(r'([\\`*{}\[\]<>#|])', r'\\\1', str(value)).replace('\n', ' ')[:240]


def _url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return None
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password:
            return None
    except ValueError:
        return None
    return value.replace('(', '%28').replace(')', '%29').replace('<', '%3C').replace('>', '%3E')


def _query_terms(query):
    terms = set(re.findall(r'[a-zA-Z][a-zA-Z0-9-]{2,}', query.lower()))
    for run in re.findall(r'[\u4e00-\u9fff]+', query):
        terms.update(run[i:i+2] for i in range(len(run)-1))
    terms -= {'我想','想知','知道','网上','上说','说的','真的','的是','是不','不是','帮我','一下'}
    return terms


def _block_kind(value):
    """Structural reading hints only; these never determine support or truth."""
    if re.fullmatch(r'(?:首页|导航|打印(?:页面)?|分享(?:到)?|收藏|相关新闻|相关文章|联系我们|打开)[\s：:|]*', value):
        return 'navigation'
    if re.match(r'^(?:发布时间|抓取时间|字号|字体|责任编辑|来源)\s*[:：]', value):
        return 'navigation'
    if re.search(r'[？?][”」』"\s→]*$', value):
        return 'question'
    if re.match(r'^#{1,6}\s', value):
        return 'heading'
    if re.match(r'^(?:[（(][一二三四五六七八九十\d]+[）)]|\d+[.、．]|[-•])\s*', value):
        # Numbered titles such as "1.拆封问题" are locators, not evidence.
        return 'body' if re.search(r'[。；;：:]|应当|不得|可以|不适用|除外|确认|仅|除|须', value) else 'heading'
    if len(value) <= 50 and not re.search(r'[。；;！!]', value):
        # Conditional/list introductions must travel with the following text.
        if value.endswith(('：', ':')) and re.search(r'经|如果|除|须|仅|不适用|可以|下列|以下|应当|不得|包括', value):
            return 'introduction'
        if not re.search(r'规定|应当|不得|可以|不适用|需|仅|不包括|不代表|尚未|未建立|必须', value):
            return 'heading'
    return 'body'


def _excerpts(text, query):
    """Select contiguous answer context and attached conditions, never headings alone.

    Exact offsets address the acquired readable text. Relevance scores allocate
    reading space, not truth or entailment. Separated windows remain separate.
    """
    terms = _query_terms(query)
    blocks = []
    for block in re.finditer(r'[^\n]+', text):
        pieces = [block] if len(block.group()) <= 1800 else list(re.finditer(r'.+?(?:[。！？!?]+|$)', block.group()))
        for piece in pieces:
            offset = 0 if piece is block else block.start()
            start, end = offset + piece.start(), offset + piece.end()
            while start < end and text[start].isspace(): start += 1
            while end > start and text[end-1].isspace(): end -= 1
            if end == start:
                continue
            value = text[start:end]
            blocks.append({'start': start, 'end': end, 'kind': _block_kind(value), 'text': value})
    # Extraction often drops punctuation at the end of list items. Treat
    # numbered lines as list content only after an explicit body introduction;
    # standalone numbered headings must remain locators.
    list_context = False
    for block in blocks:
        numbered = bool(re.match(r'^(?:[（(][一二三四五六七八九十\d]+[）)]|\d+[.、．])\s*', block['text']))
        if list_context and numbered:
            block['kind'] = 'body'
            block['list_item'] = True
        else:
            list_context = (block['kind'] in ('body', 'introduction')
                            and block['text'].endswith(('：', ':'))
                            and bool(re.search(r'下列|以下|包括|如下', block['text'])))
    candidates = []
    for index, block in enumerate(blocks):
        if block['kind'] not in ('body', 'introduction'):
            continue
        # A nearby title/question is a locator. It may boost relevance of its
        # actual answer, but is never returned by itself as an evidence quote.
        heading = None
        if index and blocks[index-1]['kind'] in ('heading', 'question'):
            heading = blocks[index-1]
        start, end = block['start'], block['end']
        count, cut = 1, end - start > 1800
        end = min(end, start + 1800)
        if not cut:
            for following_index, following in enumerate(blocks[index+1:], index+1):
                if following['kind'] in ('navigation', 'heading', 'question'):
                    break
                # Keep list introductions and their entire list together.
                is_list = following.get('list_item', False) or bool(re.match(r'^[（(][一二三四五六七八九十\d]+[）)]', following['text']))
                if (count >= 5 and not is_list
                        and following['kind'] != 'introduction'
                        and blocks[following_index-1]['kind'] != 'introduction'):
                    break
                if following['end'] - start > 1800:
                    cut = True
                    break
                end = following['end']
                count += 1
        quote = text[start:end]
        # A dangling colon alone is still not a useful answer.
        if block['kind'] == 'introduction' and end == block['end']:
            continue
        hits = sum(term in quote.lower() for term in terms)
        heading_hits = sum(term in heading['text'].lower() for term in terms) if heading else 0
        rule = bool(re.search(r'规定|应当|不得|不适用|除外|仅|条件|例外|不包括|未建立|不代表', quote))
        narrative = bool(re.match(r'^(?:案例[：:]|近日[，,]|某[先生女士]{2})', block['text']))
        score = hits + 1.5 * heading_hits + 2 * rule - 4 * narrative
        candidates.append({'text': quote, 'start': start, 'end': end,
            'query_term_matches': hits, 'truncated': cut,
            'heading_locator': heading['text'] if heading else None,
            'selection_basis': 'contiguous-body-with-conditions', '_score': score})
    ranked = sorted(candidates, key=lambda row: (-row['_score'], row['start']))
    chosen, size = [], 0
    for row in ranked:
        if any(row['start'] < old['end'] and old['start'] < row['end'] for old in chosen):
            continue
        if chosen and (row['query_term_matches'] == 0 or size + len(row['text']) > 2200):
            continue
        row.pop('_score')
        chosen.append(row)
        size += len(row['text'])
        if len(chosen) == 2:
            break
    return sorted(chosen, key=lambda row: row['start'])


def _read_date(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d（北京时间）')
    except (ValueError, TypeError, AttributeError):
        pass
    return '时间未确认'


def source_delivery(retrieval, question):
    pages = retrieval.get('sources', [])
    delivered = []
    for page in pages:
        if not isinstance(page, dict): continue
        text, url = page.get('text'), _url(page.get('url'))
        if not isinstance(text, str) or not text.strip() or not url: continue
        delivered.append({'source_id': page.get('source_id', '未提供编号'),
            'title': str(page.get('title') or '未提供标题'), 'url': url,
            'fetched_at': page.get('fetched_at'), 'published_at': page.get('published_at'),
            'provider_received_at': page.get('provider_received_at'),
            'excerpts': _excerpts(text, question), 'page_truncated': page.get('truncated', False)})
    usable = [page for page in delivered if page['excerpts']]
    result = {'schema_version': 'source-delivery/1', 'sources': delivered,
        'selection_method': 'answer-context-with-heading-locators-not-verdict',
        'material_available': bool(usable), 'semantic_answer_produced': False,
        'unusable_excerpt_source_ids': [p['source_id'] for p in delivered if not p['excerpts']],
        'verdict_produced': False, 'source_authenticity_verified': False}
    if usable:
        lines = ['与问题相关的原文及条件如下：']
        for index, page in enumerate(delivered, 1):
            if not page['excerpts']:
                continue
            lines += ['', f'### 来源 {index}：{_label(page["title"])}',
                      f'出处：<{page["url"]}>']
            if page['fetched_at']: lines.append('抓取时间：' + _read_date(page['fetched_at']))
            elif page.get('provider_received_at'):
                lines.append('正文提取服务返回时间：' + _read_date(page['provider_received_at']))
            if page['published_at']: lines.append('页面标注的发布日期（未认证）：' + _label(page['published_at']))
            for quote in page['excerpts']:
                lines.append('材料原文：')
                lines.extend('> ' + _label_quote(line) for line in quote['text'].splitlines())
                if quote['truncated']: lines.append('该处上下文超出展示范围，条件或例外可能未完整交付，需要读取完整材料后再作判断。')
            if not any(q['query_term_matches'] for q in page['excerpts']):
                lines.append('此摘录未命中明显检索词，相关性需要进一步核对。')
        lines += ['', '以上为与问题相关的正文摘录。']
    else:
        lines = ['暂未取得可用正文。']
        if delivered:
            lines.append('当前只定位到标题、问句或栏目线索，未交付有效回答段落；需要补读正文。')
        if retrieval.get('scholarly_metadata', {}).get('records'):
            lines.append('目前仅取得书目信息，尚未读取全文。')
    if retrieval.get('search_complete') is False:
        lines.append('部分查询或搜索引擎失败，检索尚未完整完成。')
    if retrieval.get('failures'):
        lines.append(f'另有 {len(retrieval["failures"])} 项读取或处理记录未能转为可用正文，未将搜索摘要当作证据。')
    result['answer'] = '\n'.join(lines)
    return result


def _label_quote(value):
    # Metadata preserves exact text; escaping only affects Markdown transport.
    escaped = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_\[\]!#|])', r'\\\1', escaped)


def retrieval_search_text(question):
    """Drop a complete conversational wrapper; retain its exact quoted claim."""
    match = re.fullmatch(
        r'(?:我想知道[，,\s]*)?(?:网上说的?|听说|有人说|网传|传言)[\s，,：:]*'
        r'[“「『"](.{4,500}?)[”」』"](?:的说法)?[\s，,]*'
        r'(?:是真的吗|属实吗|靠谱吗|是否属实|真假如何)[？?。]*', question)
    return match.group(1) if match else question
