"""Readable Partner output without upgrading baseline rules into fact checks."""
from .text_comparison import compare_text
from .result_presentation import plain


def partner_answer(product_type, request, output):
    assessment = output['input_assessment']
    if product_type == 'source-check':
        missing = assessment['missing_fields']
        labels = {'source_excerpt': '原始材料', 'source.source_id': '来源编号或链接',
                  'source.title': '来源标题', 'source.locator': '原文位置'}
        text = ('来源信息尚不完整，请补充：' + '、'.join(labels.get(k, k) for k in missing) + '。'
                if missing else '来源字段已检查，信息齐全。')
        return text + '\n本次仅检查来源字段，未打开链接。', 'source-field-completeness'
    if not assessment['evidence_provided']:
        return ('尚未比较：没有收到材料正文。\n'
                '请同时提供待核对的说法和引用原文；只有链接或任务说明不足以比较。'), 'not-inspected'
    comparison = compare_text(request.claim_text, request.source_excerpt)
    text = comparison['answer']
    if product_type == 'evidence-finding':
        scope = 'bounded-rule-evidence-comparison'
        if comparison['status'] == 'undetermined':
            return ('初筛未得出结论，需要进一步比较含义。\n'
                    '已收到材料，仍需语义分析。\n\n'
                    '待核对说法：' + plain(request.claim_text) + '\n'
                    '下一步：需由语义审查核对材料中的对象、条件和结论是否与说法一致。'), scope
        boundary = '检查范围：所提供的文字。'
    else:
        scope = 'bounded-rule-difference-comparison'
        boundary = '检查方式：文字差异初筛。'
    quotes = comparison.get('evidence_spans', [])
    text = plain(text)
    if quotes:
        text += '\n\n对应原文：\n' + '\n'.join('> ' + plain(q).replace('\n', '\n> ') for q in quotes)
    return text + '\n\n' + boundary, scope
