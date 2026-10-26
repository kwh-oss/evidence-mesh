"""Extract an explicitly addressed business request without inventing history."""
import re
from dataclasses import replace

from .collaboration_input import command_text
from .contracts import request_from_caller_text, request_json

_NAME = r'(?:证链[·・]?证据审查总控|证链总控|总控智能体)'
_ADDRESSED = re.compile(r'^(?:请)?(?:让|用|由|交给|找)' + _NAME + r'(?:来|帮我|为我)?[：:\s，,]*')
_REFERENCE = re.compile(r'^(?:请)?(?:按名称)?(?:查找|找到|定位)' + _NAME)
_TAIL = re.compile(r'[，,；;]\s*((?:允许|可以)(?:总控)?调用(?:内外伙伴|内外部伙伴|内部和外部智能体))[。.!！\s]*$')


def leader_command_text(command, *, default_claim_id):
    """Only the Leader interprets addressing; Partners retain their contracts."""
    request = request_from_caller_text(command_text(command), default_claim_id=default_claim_id)
    text = request.claim_text
    if _REFERENCE.match(text) and re.search(r'刚才|上一个|上述|此前', text):
        raise ValueError('未收到实际业务问题；无法访问此前对话，请把要查询的问题直接写入本次消息。')
    constraints = list(request.constraints)
    tail = _TAIL.search(text)
    if tail:
        constraints.append('允许调用内外伙伴')
        text = text[:tail.start()].strip()
    text = _ADDRESSED.sub('', text, count=1).strip()
    if not text or text in ('处理刚才的任务', '处理上述任务', '处理上一个任务'):
        raise ValueError('请提供本次需要处理的实际问题，不要只引用此前任务。')
    return request_json(replace(request, claim_text=text, constraints=tuple(constraints)))
