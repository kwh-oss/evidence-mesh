"""Expose completed supplemental answers on the readable AIP surface."""
def with_external_supplements(passport):
    if passport.get('external_supplement', {}).get('internal_answer_preserved') is not True:
        return passport
    parts=[]
    for peer in passport.get('external_collaboration', {}).get('reviews', [])[:3]:
        text=peer.get('text')
        if peer.get('supplementary') is not True or peer.get('aip_state')!='completed' or not isinstance(text,str) or not text.strip():
            continue
        if 'DSML' in text or '<tool_call' in text or '<｜tool' in text:
            parts.append(str(peer.get('partner_name','外部伙伴'))+'：返回包含工具协议标记，未作为有效答复展示。')
        else:
            parts.append(str(peer.get('partner_name','外部伙伴'))+'：\n'+text.strip()[:2000])
    if not parts:
        return passport
    value=dict(passport)
    base=passport.get('internal_answer',passport['answer'])
    value['internal_answer']=base
    value['answer']=base+'\n\n外部查询补充（待复核）\n'+'\n\n'.join(parts)
    return value
