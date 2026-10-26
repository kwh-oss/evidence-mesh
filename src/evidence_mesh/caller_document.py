"""Explicit section parsing only; no model inference or invented provenance."""
import re

LABEL = re.compile(r'(?:^|\n|(?<=\s)|(?<=[。；;]))[ \t]*(政策原文|政策材料|原始材料|材料原文|对照材料|证据原文|参考材料|原文|依据|待核验客服回答|待核验回答|待检查文本|待核验主张|待核验帖子|待核验说法|帖子内容|客服回答|主张|回答|结论)[ \t]*[：:]')
EVIDENCE = {'政策原文', '政策材料', '原始材料', '材料原文', '对照材料', '证据原文', '参考材料', '原文', '依据'}
META = re.compile(r'(?:^|\s)(?:DAG\s*指定的上游产物摘要|请展示实际调用|请展示|请逐条输出)\s*[:：]?')

QUOTED = re.compile(r'“([^“”\n]{2,4000})”|「([^「」\n]{2,4000})」|『([^『』\n]{2,4000})』|"([^"\n]{2,4000})"')


def quoted_comparison(text):
    """Extract two explicitly quoted texts, never infer their relationship."""
    clean = META.split(text, maxsplit=1)[0].strip()
    matches = list(QUOTED.finditer(clean))
    if len(matches) != 2:
        return None
    # Determine the requested operation from outside the quoted material.
    outside = QUOTED.sub('【引文】', clean)
    if not re.search(r'矛盾|冲突|一致|等义|是否相同|意思.{0,8}(?:一样|相同)|contradict|inconsistent|same meaning', outside, re.I):
        return None
    if re.search(r'(?:不要|不必|无需|不用).{0,8}(?:对比|比较|检查|判断|核对)', outside):
        return None
    values = []
    for match in matches:
        group = next(i for i in range(1, 5) if match.group(i) is not None)
        values.append((match.group(group), match.start(group), match.end(group)))
    # Extra or unmatched quote marks make the two-text boundary ambiguous.
    remainder = QUOTED.sub('', clean)
    if any(mark in remainder for mark in '“”「」『』"'):
        return None
    first, second = values
    return {'claim_text': first[0], 'source_excerpt': second[0],
            'task_type': 'cross_text_conflict', 'goal': clean,
            'source': {'source_id': 'caller:quoted-comparison',
                       'title': '调用方提供的第二段引文（未认证）',
                       'locator': f'输入文本字符[{second[1]}:{second[2]}]，不含引号'}}

def document_sections(text):
    matches = list(LABEL.finditer(text))
    if not matches:
        return None
    evidence, claims = [], []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = META.split(text[match.end():end], maxsplit=1)[0].strip()
        if match.group(1) in {'主张', '结论', '回答', '原文', '依据'}:
            section = section.rstrip('。；;')
        (evidence if match.group(1) in EVIDENCE else claims).append(section)
    if not claims:
        return None
    if any(not section for section in evidence + claims):
        raise ValueError('已标注的原文或待核验回答为空，请补充内容')
    result = {'claim_text': '\n'.join(claims)}
    if evidence:
        result['source_excerpt'] = '\n'.join(evidence)
    return result

def numbered_claims(text):
    matches = list(re.finditer(r'(?:^|\s)(\d+)[.、．)][ \t]*(?!\d)', text))
    if len(matches) < 2 or text[:matches[0].start()].strip():
        return []
    if len(matches) > 20:
        raise ValueError('一次最多核验20条回答，请分批提交')
    if [int(m.group(1)) for m in matches] != list(range(1, len(matches) + 1)):
        raise ValueError('回答编号必须从1开始连续递增，避免把日期或数值误作回答编号')
    claims = [text[m.end():(matches[i+1].start() if i+1 < len(matches) else len(text))].strip()
              for i, m in enumerate(matches)]
    if any(not claim for claim in claims):
        raise ValueError('编号回答不能为空')
    return claims
