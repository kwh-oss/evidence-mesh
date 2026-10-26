"""Map terminal task errors to short, safe user-visible reasons."""
def failed_task_result(task,entry):
    texts=[getattr(item,'text','') for item in (getattr(task,'dataItems',None) or [])]
    text='\n'.join(texts)
    known={
        'speech quote mismatch':('speech-quote-mismatch','语音引文未通过校验。'),
        'invalid observation':('video-output-invalid','视频分析结果格式未通过校验。'),
        'budget exhausted':('model-budget-exhausted','模型测试额度已用尽。'),
        'Model provider timed out':('model-timeout','内容分析超时。'),
        'DeepSeek request failed':('model-provider-failed','内容分析服务调用失败。'),
    }
    code,detail=next((v for k,v in known.items() if k.lower() in text.lower()),('leader-failed','内容分析未完成。'))
    return {'state':'failed','recoverable':False,'new_start_requests':0,'leader_task_id':entry['task'],
            'leader_session_id':entry['session'],'reason':code,'detail':detail}
