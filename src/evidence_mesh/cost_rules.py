"""Compare explicit two-branch cost rules; no inferred policy or open-ended NLP."""
import re

EVENT = r'退货|换货|维修|取消订单'
FEE = r'运费|维修费|手续费|取消费|费用'
PAYER = r'消费者|买家|商家|卖家|平台|用户|申请人'
RULE = re.compile(rf'(?P<condition>[^，,。；;]+)(?P<event>{EVENT})[，,](?P<payer>{PAYER})承担(?P<fee>{FEE})')
ALIASES = {'买家':'消费者', '卖家':'商家'}


def compare_cost(claim, excerpt):
    if any(word in excerpt for word in ('除非', '除外', '例外', '另行', '另有', '免运费', '免维修费', '特殊情况')):
        return None
    rules = []
    for span in re.split(r'[。；;\n]', excerpt):
        match = RULE.fullmatch(span.strip())
        if match:
            rules.append((match, span.strip()))
    # Require exactly one positive cause and its explicit "other causes" branch.
    positives = [(m,s) for m,s in rules if m['condition'].startswith('因')]
    others = [(m,s) for m,s in rules if m['condition'] == '其他原因']
    if len(rules) != 2 or len(positives) != 1 or len(others) != 1:
        return None
    positive, first = positives[0]
    other, second = others[0]
    if (positive['event'], positive['fee']) != (other['event'], other['fee']):
        return None
    cause = positive['condition'][1:]
    if not cause or any(x in cause for x in ('除非', '如果', '但', '并非', '不')):
        return None
    simple = re.fullmatch(rf'(?:无|非){re.escape(cause)}(?:的)?{re.escape(other["event"])}[，,](?:需要)?(?P<payer>{PAYER})承担{re.escape(other["fee"])}', claim.strip().rstrip('。'))
    canonical = lambda p: ALIASES.get(p, p)
    if simple:
        if canonical(simple['payer']) != canonical(other['payer']):
            return {'status':'cost-payer-difference', 'evidence_spans':[first,second],
                'differences':[{'field':'费用承担方', 'claim':simple['payer'], 'evidence':other['payer']}],
                'suggested_wording':second + '。',
                'answer':f'费用承担方与原文不同：回答写“{simple["payer"]}”，原文对其他原因的{other["event"]}规定由“{other["payer"]}”承担{other["fee"]}。\n依据：{second}。\n建议按原文表述：{second}。'}
        return {'status':'conditional-correspondence', 'evidence_spans':[first,second], 'differences':[],
            'suggested_wording':second + '。',
            'answer':f'在这两项费用条款的范围内，这句话与原文的“其他原因”分支对应。原文先列出“因{cause}”的情形，再规定其他原因的承担方。\n依据：{first}；{second}。\n这里将“{simple["payer"]}”按“{other["payer"]}”理解；如果实际付款主体不同，需要另行确认。\n更准确的表述：{second}。'}
    unqualified = rf'{re.escape(other["event"])}{re.escape(other["fee"])}由(?P<payer>{PAYER})承担'
    clauses = re.split(r'[，,]', claim.strip().rstrip('。'))
    head = re.fullmatch(unqualified, clauses[0])
    if not head or canonical(head['payer']) != canonical(other['payer']):
        return None
    if len(clauses) > 2:
        return None
    if len(clauses) == 2:
        tail = re.fullmatch(rf'{re.escape(cause)}{re.escape(other["event"])}{re.escape(other["fee"])}由(?P<payer>{PAYER})承担', clauses[1])
        if not tail or canonical(tail['payer']) != canonical(positive['payer']):
            return None
    if canonical(positive['payer']) == canonical(other['payer']):
        return None
    return {'status':'scope-clarification', 'evidence_spans':[first,second],
        'differences':[{'field':'条件范围', 'claim':clauses[0], 'evidence':second}],
        'suggested_wording':first + '；' + second + '。',
        'answer':f'这段回答需要把首句的适用条件说清楚，不能单独把它理解成所有{other["event"]}都由“{head["payer"]}”承担{other["fee"]}。原文按原因区分了不同承担方。\n依据：{first}；{second}。\n建议完整保留条件：{first}；{second}。'}
