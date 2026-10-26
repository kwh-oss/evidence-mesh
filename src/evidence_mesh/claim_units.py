"""Finite structural preprocessing; no factual classifications or new statements."""
import re


def is_task_instruction(text):
    """Only explicit sentence-leading review instructions, never quoted content."""
    return bool(re.match(r'\s*(?:请(?:根据|依据|结合|仅|只|分别|核对|指出|保留|不要|勿)|查不到的部分|无法确认的部分)', text))


def prepare_review_units(post):
    units = []
    for sentence in re.finditer(r'[^。！？!?\n]+[。！？!?]?', post):
        boundaries = [sentence.start()]
        instruction = is_task_instruction(sentence.group())
        for match in re.finditer(r'[，,；;]\s*(所以|因此|是否意味着|是不是意味着)', sentence.group()):
            if instruction:
                continue
            boundaries.append(sentence.start() + match.start(1))
        boundaries.append(sentence.end())
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            while start < end and post[start].isspace():
                start += 1
            if start == end:
                continue
            previous = units[-1]['unit_id'] if index else None
            units.append({'unit_id': f'unit-{len(units)+1}', 'start': start, 'end': end,
                          'text': post[start:end], 'relation': ('task-instruction' if instruction else
                              'inference-question' if index and post[start:end].startswith(('是否意味着', '是不是意味着')) else
                              'inferred-conclusion' if index else 'statement'),
                          'premise_unit_id': previous})
    return units
