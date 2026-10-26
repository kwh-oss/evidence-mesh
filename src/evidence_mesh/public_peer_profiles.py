"""Bounded native text contracts for screened public read-only peers."""
import re

SCOPED_PROFILES = {'cn-statute-article-v1': 'public-statute-article-lookup'}
_ARTICLE = re.compile(
    r'^(?:(?:请帮我|帮我|麻烦|请)?(?:查找|查询|检索|查一下|提供|取回|给我|找|查)\s*)?'
    r'《?(?:中华人民共和国)?(?:民法典|刑法|公司法|税收征收管理法|增值税法|'
    r'企业所得税法|个人所得税法|专利法)》?的?'
    r'第[一二三四五六七八九十百千万零〇两0-9]{1,12}条的?(?:原文|内容|条文)'
    r'(?:和官方(?:出处|来源))?[。？?！!]*$')


def valid_scoped_peer(peer):
    return (peer.get('input_style') == 'scoped-readonly-text'
            and SCOPED_PROFILES.get(peer.get('request_profile')) == peer.get('capability')
            and peer.get('request_profile') in SCOPED_PROFILES)


def native_public_match(peer, question):
    if peer.get('input_style') == 'fixed-readonly-text':
        return native_public_question(peer, question) in peer.get('fixed_questions', [])
    if not valid_scoped_peer(peer) or not isinstance(question, str) or len(question) > 180:
        return False
    return bool(_ARTICLE.fullmatch(question.strip()))


def native_public_question(peer, question):
    # Normalize only the screened read-only news command, not arbitrary prompts.
    if (peer.get('input_style') == 'fixed-readonly-text' and isinstance(question, str)
            and re.fullmatch(r'(?:查询|查一下|看看)?今天有哪些\s*Agent\s*热点[。？?]*', question.strip(), re.I)
            and '今天有哪些Agent热点' in peer.get('fixed_questions', [])):
        return '今天有哪些Agent热点'
    return question


def native_public_peer(peer):
    return peer.get('input_style') == 'fixed-readonly-text' or valid_scoped_peer(peer)
