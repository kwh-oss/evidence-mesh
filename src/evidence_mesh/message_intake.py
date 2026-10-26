"""Conservative intake hints, not entity resolution or factual judgment."""
import re
from datetime import datetime, timezone


def assess_message(text, *, provided_link=False):
    compact = re.sub(r'[\s，。！？、,:;：；?!]+', '', text)
    missing_referent = (not provided_link and bool(re.fullmatch(
        r'(?:请问|帮我看看|帮我查一下|帮我核实一下|帮我确认一下)?'
        r'(?:这|这个|这些|这件事|这条消息|这个说法|这个视频|这段视频|上面说的|上述说法|它)?'
        r'(?:是真的吗|是真的么|真的假的|真假|靠谱吗|可信吗|属实吗|是否属实|是真是假|是不是真的)',
        compact)))
    vague_subject = bool(re.search(
        r'(?:某博主|某网红|某明星|那位博主|那个人)\s*'
        r'(?:被|涉嫌|出轨|造假|去世|说|真的|是不是|是否)', text))
    vague_subject = vague_subject or bool(re.search(
        r'(?:^|[，。！？：\s])(?:请问|听说|最近刷到|我刷到|网上说|据说|我看到)?\s*'
        r'(?:他|她)\s*(?:被|涉嫌|出轨|造假|去世|说|真的|是不是|是否)', text.strip()))
    sensitive = any(word in text for word in ('出轨', '绿帽', '被捕', '诈骗', '性侵', '犯罪'))
    personal_relationship = any(word in text for word in ('出轨', '绿帽'))
    # A role plus a nickname is not a unique account identifier. This limited
    # heuristic is not general named-entity resolution; links also remain unverified.
    nickname_ambiguity = (personal_relationship and
                          any(word in text for word in ('博主', '网红', '主播')) and
                          not provided_link and
                          not re.search(r'https?://[^\s]+', text))
    time_expressions = [word for word in ('最近', '近日', '今天', '昨天', '前天', '刚刚', '这几天',
                                         '上周', '本周', '上个月', '去年', '今年') if word in text]
    relative_time = bool(time_expressions)
    needs_clarification = missing_referent or vague_subject or nickname_ambiguity
    questions, hints = [], []
    if missing_referent:
        questions.append('请补充要核验的具体说法或原文链接，并说明想确认哪一点；目前“这”没有明确指向，尚未开始检索或真假判断。')
    elif needs_clarification:
        questions.append('你指的是哪位人物或哪个账号？请提供姓名、账号主页或原帖链接，避免核验到同名或无关对象。')
    if sensitive:
        hints.append('涉及名誉敏感指控：匿名爆料、截图和转载不能单独证明指控成立。')
    if relative_time:
        hints.append('消息使用相对时间，事件日期尚未确认；检索时间不能代替事件发生时间。')
    reasons = []
    if missing_referent:
        reasons.append('missing-claim-or-referent')
    if vague_subject:
        reasons.append('unspecified-person')
    if nickname_ambiguity:
        reasons.append('role-or-nickname-not-unique-account')
    return {'schema_version': 'message-intake/1', 'clarification_required': needs_clarification,
            'ambiguity_reasons': reasons, 'relative_time_expressions': time_expressions,
            'questions': questions, 'sensitive_allegation': sensitive,
            'relative_time_unresolved': relative_time,
            'entity_identity_resolved': False, 'hints': hints,
            'assessed_at': datetime.now(timezone.utc).isoformat(), 'claim_verified': False}
