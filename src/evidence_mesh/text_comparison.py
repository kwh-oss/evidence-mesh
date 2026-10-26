"""Bounded text comparisons. Abstain outside explicit supported patterns.

This is a Leader-owned rule result, not a model inference or a Partner product.
Matched spans are always retained; synthetic test answers are never looked up.
"""
import re
from .cost_rules import compare_cost
from .spread_check import compare_spread

DEADLINE = re.compile(r'(?P<topic>退款|配送|发货|维修|审核|报销)在(?P<trigger>[^。；;\n]{2,60}?)后(?P<duration>\d+|[一二三四五六七八九十]+)(?P<unit>个工作日|工作日|天|小时)内(?P<action>处理|到账|完成|发出|送达)')


def compare_text(claim, excerpt):
    finding = {'status': 'undetermined', 'basis': 'leader-explicit-text-rules-v1',
        'evidence_spans': [], 'differences': [], 'suggested_wording': None,
        'answer': '目前无法可靠判断所提供材料是否支持这句话；不能把文字相关或未发现冲突当作材料支持。'}
    if not excerpt or excerpt.startswith('未提供证据摘录'):
        finding.update(status='not-inspected', answer='尚未核验：没有收到可用于比对的原文。请提供原始公告、报道或其他引用材料；这不是对帖子正确与否的判断。')
        return finding
    spread = compare_spread(claim, excerpt)
    if spread:
        finding.update(spread)
        return finding
    proposed = DEADLINE.fullmatch(claim.strip().rstrip('。'))
    if proposed:
        references = [m for span in re.split(r'[。；;\n]', excerpt)
                      if (m := DEADLINE.fullmatch(span.strip())) and m['topic'] == proposed['topic']]
        # Multiple relevant rules can encode exceptions; do not arbitrarily pick one.
        if len(references) == 1:
            ref = references[0]
            fields = {'trigger': '起算条件', 'duration': '期限数值', 'unit': '期限单位', 'action': '承诺的动作'}
            digits = dict(zip('一二三四五六七八九', range(1, 10)))
            def canonical(key, value):
                if key == 'unit':
                    return value.removeprefix('个')
                if key == 'duration':
                    if value.isdigit():
                        return int(value)
                    if value in digits:
                        return digits[value]
                    if '十' in value:
                        left, right = value.split('十', 1)
                        return (digits.get(left, 1) * 10) + digits.get(right, 0)
                return value
            diffs = [{'field': label, 'claim': proposed[key], 'evidence': ref[key]}
                     for key,label in fields.items() if canonical(key, proposed[key]) != canonical(key, ref[key])]
            if diffs:
                finding.update(status='wording-difference', evidence_spans=[ref.group()],
                    differences=diffs, suggested_wording=ref.group() + '。',
                    answer='这句话不能直接作为原文的等义表述。' + ''.join(
                        f'{d["field"]}不同：回答写的是“{d["claim"]}”，原文写的是“{d["evidence"]}”。' for d in diffs)
                        + '\n依据：' + ref.group() + '。\n建议按原文表述：' + ref.group() + '。')
                return finding
    # A universal permission contradicts an explicit unqualified exception.
    # Do not infer subset relations beyond a shared, explicit category suffix.
    universal = re.fullmatch(r'所有(?P<category>商品|订单|用户|申请)(?:都能|都可以|均可|都可)(?P<permission>.+)', claim.strip().rstrip('。'))
    if universal:
        category = re.escape(universal['category'])
        excluded = re.compile(r'(?P<scope>[^。；;，,\n]{1,16}' + category + r')不(?:支持|允许)(?P<permission>[^。；;，,\n]{2,24})')
        for sentence in re.split(r'[。；;\n]', excerpt):
            ref = excluded.fullmatch(sentence.strip())
            if ref and not ref['scope'].startswith(('并非', '不是', '不能说')) and ref['permission'] in universal['permission']:
                finding.update(status='explicit-exception', evidence_spans=[sentence.strip()],
                    differences=[{'field':'适用范围', 'claim':'所有' + universal['category'], 'evidence':ref['scope'] + '被明确排除'}],
                    answer='这句话把适用范围扩大了，不能说“所有' + universal['category'] + '”都适用。\n原文明确规定：' + sentence.strip() + '。\n修改时应保留这项例外，不能把有限条件的许可改成全部适用。')
                return finding
    cost = compare_cost(claim, excerpt)
    if cost:
        finding.update(cost)
        return finding
    # Complete sentence correspondence only; never remove conditions or negation.
    normalized = lambda s: re.sub(r'[\s。；;，,：:！!？?]', '', s).replace('可以', '可')
    sentences = re.split(r'[。；;\n]', excerpt)
    if normalized(claim) and any(normalized(claim) == normalized(s) for s in sentences):
        finding.update(status='textually-supported', evidence_spans=[excerpt],
            answer='这句话的完整文字内容可以在你提供的原文中找到。就文字对应关系而言有依据；这不认证政策来源真实性。')
        return finding
    subject = re.search(r'(?:^|[，,]|后)(?P<object>[^后，,。；;]{2,12}?)(?:会退回|可退回|会退还|会返还)', claim.strip().rstrip('。'))
    if subject and subject['object'] not in excerpt:
        item = subject['object']
        finding.update(status='no-explicit-reference',
            answer=f'无法依据这段原文确认“{item}”是否会退回：原文中没有找到“{item}”的明确文字或对应条款。请补充对应条款。')
    return finding
