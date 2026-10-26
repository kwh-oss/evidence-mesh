"""Bounded retry leads and known landing-page filters, never factual verdicts."""
import re
from urllib.parse import urlsplit


def institution_names(query):
    # These suffixes identify query subjects, not authoritative institutions.
    text = re.sub(r'就是|是不是|是否为|是否|以及|与|和|及', ' ', query)
    names = []
    for token in re.split(r'[\s，,。:：；;？?、“”「」『』"《》()（）]+', text):
        token = re.sub(r'^(?:(?:请|帮我|帮忙|检索|查询|查找|返回|核实|查证|比较|介绍|查|并))+', '', token)
        match = re.match(r'[\u4e00-\u9fff]{2,20}?(?:博物院|博物馆|大学|学院|医院|图书馆|纪念馆|研究所)', token)
        if match and match.group() not in names:
            names.append(match.group())
    return names[:2]


def missing_institutions(query, pages):
    names = institution_names(query)
    text = '\n'.join(str(p.get('title',''))+'\n'+str(p.get('text','')) for p in pages)
    return [name for name in names if name not in text] if len(names) == 2 else []


def recovery_queries(query, subjects=None):
    names = subjects or institution_names(query)
    if names:
        return [name + ' 官方 简介 地址 机构' for name in names]
    subject = re.sub(r'^(?:请)?(?:用|让)?证链(?:帮我)?(?:核实|查证|查|检索)(?:一下)?[：:\s]*', '', query).strip()
    return [subject[:450] + ' 官方 原文 说明']


def non_evidence_page(page):
    """Reject only recognizable service stubs; absence of keywords is not falsity."""
    p = urlsplit(page.get('url', ''))
    text = page.get('text', '')
    if p.hostname == 'mp.weixin.qq.com' and p.path.startswith('/miniprogram/landing_page/'):
        return 'mini-program-service-landing'
    if len(text) < 1800 and ('本页面信息内容仅供参考' in text
            and '小程序服务由开发者向微信用户提供' in text):
        return 'service-notice-without-article'
    if len(text) < 160 and 'ICP备' in text and '网站标识码' in text and '公网安备' in text:
        remaining = re.sub(r'[\u4e00-\u9fff]ICP备\d+(?:号(?:-\d+)?)?|网站标识码[：:\s]*\d+|[\u4e00-\u9fff]公网安备[：:\s]*\d+号?', '', text)
        if len(re.sub(r'[\W\dA-Za-z_]+', '', remaining)) < 8:
            return 'registration-footer-without-article'
    return None
