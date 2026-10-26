"""Use saved video claims as search leads, never as independent proof."""
import json

PREFIX='原视频核验上下文（采样分析，非外部事实证据）：'


def focused_video_query(goal):
    if not isinstance(goal,str) or not goal.startswith(PREFIX):return None
    try:context=json.loads(goal[len(PREFIX):])
    except (ValueError,TypeError):return None
    if not isinstance(context,dict):return None
    plan=context.get('verification_plan') or {}
    text=plan.get('search_query') if isinstance(plan,dict) else None
    if not text:
        rows=context.get('statements',[])
        if not isinstance(rows,list):return None
        text=next((r.get('text') for r in rows[:3] if isinstance(r,dict)
            and r.get('role')=='core' and r.get('kind','fact')=='fact' and r.get('verification_scope')=='public-fact'),None)
    if not isinstance(text,str):return None
    text=' '.join(text.split())
    if not 4<=len(text)<=300 or '://' in text:return None
    return text
