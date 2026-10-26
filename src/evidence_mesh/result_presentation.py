"""Present validated findings; keep diagnostics in the machine passport."""
import re
from urllib.parse import urlsplit


def plain(value):
    """Escape untrusted material for a Markdown text channel."""
    value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_\[\]!#|])', r'\\\1', value)


def source_link(page):
    url = page.get('url', '')
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or any(c.isspace() for c in url)):
            return plain(page.get('title') or '来源未提供可用链接')
    except ValueError:
        return '来源未提供可用链接'
    url = url.replace('(', '%28').replace(')', '%29').replace('<', '%3C').replace('>', '%3E')
    # Dingdang interprets Markdown links as downloadable artifact buttons.
    # Bare source URLs keep a citation from being mislabeled as a code file.
    return plain(page.get('title') or parsed.hostname) + '\n' + url


def _parts(explanation):
    # Some valid provider replies keep the required labels on one line.
    explanation = re.sub(r'(?<=[。；;])(?=(?:依据|边界)[：:])', '\n', explanation)
    parts = {}
    current = None
    for line in explanation.strip().splitlines():
        match = re.match(r'^(结论|依据|边界)[：:]\s*(.*)', line.strip())
        if match:
            current = match[1]
            parts[current] = parts.get(current, '') + match[2]
        elif current:
            parts[current] += '\n' + line
        else:
            parts['结论'] = parts.get('结论', '') + line + '\n'
    return {k: v.strip() for k, v in parts.items()}


def leader_answer(passport):
    if passport.get('decision_scope') == 'external-consultation':
        return passport.get('answer') or '本次未取得外部咨询答复。'
    if passport.get('product_type') == 'video-observation' or passport.get('clarification_required'):
        return passport.get('answer') or '请补充需要核验的具体问题。'
    if passport.get('batch'):
        return '\n\n'.join(f'### 问题 {i}\n{leader_answer(row)}'
            for i, row in enumerate(passport.get('claim_results', []), 1))
    review = passport.get('semantic_review', {})
    rows = review.get('claims', []) if review.get('status') in ('model-suggestion', 'partial-model-suggestion') else []
    if passport.get('message_assessment', {}).get('status') == 'unverified-sensitive':
        # Do not bypass the existing sensitive-allegation boundary with a more
        # confident model explanation from the same underlying material.
        return passport['message_assessment']['interpretation']['summary']
    if not rows:
        reason = review.get('reason')
        if not reason:
            interpretation = passport.get('message_assessment', {}).get('interpretation', {})
            reason = interpretation.get('summary')
        if not reason:
            reason = ('没有收到可供比较的材料正文。' if review.get('status') == 'not-inspected' else
                      '内容分析尚未完成。')
        return '本次未得出核验结论。\n\n原因：' + plain(reason)
    pages = {p.get('source_id'): p for p in passport.get('public_retrieval', {}).get('sources', [])}
    upstream = any(p.get('collaboration', {}).get('material_origin') == 'caller-upstream-unverified'
                   for p in passport.get('partner_products', {}).values() if isinstance(p, dict))
    lines = []
    if review.get('coverage_complete') is not True:
        lines.append('本次仅完成部分核验；以下结论不覆盖整段内容。\n')
    for i, row in enumerate(rows, 1):
        parts = _parts(row.get('explanation', ''))
        if len(rows) > 1:
            lines.append(f'### {i}. {plain(row["claim_span"])}')
        lines += ['结论：' + plain(parts.get('结论') or '该条分析未提供直接回答。')]
        if parts.get('依据'):
            lines += ['', '依据：' + plain(parts['依据'])]
        for quote in row.get('quotes', []):
            lines += ['', '> ' + plain(quote['text']).replace('\n', '\n> ')]
            page = pages.get(quote.get('source_id'))
            if page:
                lines.append('来源：' + source_link(page))
            elif upstream:
                lines.append('出处：调用方提供的上游报告；该引文尚未独立追溯原网页。')
            else:
                lines.append('出处：本次传入的材料正文。')
        if parts.get('边界') and parts['边界'] not in ('无', '无。', '无额外限制', '无额外限制。'):
            lines += ['', '适用条件：' + plain(parts['边界'])]
        # Suggested rewrites have not received a separate entailment check.
        # Keep them in the audit contract, not the default user-facing answer.
        lines.append('')
    if review.get('coverage_complete') is not True:
        pending = review.get('unreviewed_spans', [])
        if pending:
            lines.append('尚未核验：' + '；'.join(plain(s) for s in pending))
        for item in review.get('rejected_claims', []):
            lines.append('未采用的分析：' + plain(item.get('reason', '未通过校验')))
    retrieval = passport.get('public_retrieval', {})
    if retrieval.get('search_complete') is False:
        lines.append('部分检索未完成，以上只依据本次取得的材料。')
    peer = passport.get('external_collaboration', {})
    for item in peer.get('reviews', [peer]):
        if item.get('status') == 'grounded-suggestions' and item.get('issues'):
            lines.append('外部复核补充（' + plain(item.get('partner_name', '外部伙伴')) + '，未独立认证）：')
            lines.extend('- ' + plain(issue['explanation']) for issue in item['issues'])
        elif item.get('task_id') and item.get('status') in ('pending', 'unknown-outcome', 'completion-outcome-unknown'):
            lines.append('外部协作：' + plain(item.get('partner_name', '外部伙伴')) + '尚未交付结果，本次结论未采用其意见。')
    return '\n'.join(lines).strip()


def present_passport(passport):
    value = dict(passport)
    value.setdefault('technical_answer', value.get('answer', ''))
    value['answer'] = leader_answer(value)
    if value.get('external_supplement', {}).get('internal_answer_preserved') is True:
        # Re-rendering a new review invalidates the previous cached core prose.
        value['internal_answer'] = value['answer']
    value['human_summary'] = value['safe_utterance'] = value['answer']
    value['presentation_version'] = 'reader-first/1'
    value['suggested_rewrite_presentation'] = 'withheld-pending-independent-review'
    return value
