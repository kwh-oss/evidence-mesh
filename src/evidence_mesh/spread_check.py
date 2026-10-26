"""Conservative lexical distortion cues, not independent truth verification."""
import re


def compare_spread(claim, excerpt):
    normalize = lambda s: re.sub(r'[\s。！!？?，,]', '', s)
    text = normalize(claim)
    # Only compare entire corresponding sentences; do not mix unrelated topics,
    # strip arbitrary qualifiers, or assert that a negative sentence is positive.
    pairs = [('可能', '一定', '确定程度'), ('可能', '必然', '确定程度'),
             ('部分', '所有', '适用范围'), ('部分', '全部', '适用范围')]
    for sentence in re.split(r'[。；;\n]', excerpt):
        ref = normalize(sentence)
        if not ref or any(word in ref + text for word in ('并非', '不可能', '不一定', '不是', '未证实', '没有')):
            continue
        for weak, strong, field in pairs:
            if ref.count(weak) != 1 or text.count(strong) != 1:
                continue
            if ref.replace(weak, '<boundary>', 1) == text.replace(strong, '<boundary>', 1):
                return {'status': 'spread-boundary-difference',
                    'basis': 'explicit-corresponding-sentence-boundaries-v1',
                    'evidence_spans': [sentence.strip()],
                    'differences': [{'field': field, 'claim': strong, 'evidence': weak}],
                    'suggested_wording': sentence.strip() + '。',
                    'answer': f'这句话存在传播失真线索：把原文的“{weak}”改成了“{strong}”，改变了{field}。'
                        f'\n依据：{sentence.strip()}。\n建议保留原文边界：{sentence.strip()}。'
                        ''}
    return None
