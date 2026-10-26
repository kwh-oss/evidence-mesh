import base64,json,unittest
from unittest.mock import AsyncMock,patch
from evidence_mesh.audio_transcription import validate_audio,validate_transcript,transcribe_audio
from evidence_mesh.video_observation import observe_video,validate_observation
from test_video_observation import capture

def claim(**changes):
    row={'text':'这款饮料完全无糖。','frame_indices':[],'speech_indices':[0],
         'origin':'speech','role':'core','kind':'fact','quote':'这款饮料完全无糖'}
    row.update(changes);return row
def observation(rows):
    return {'summary':'介绍饮料含糖情况。','main_point':'声称这款饮料完全无糖。',
            'content_type':'fact-claim','observations':[], 'candidate_claims':rows,'limitations':[]}
SPEECH={'source':'local-asr','video_time':10,'segments':[{'start':0,'end':3,'text':'这款饮料完全无糖'}]}
class VideoUnderstandingTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_scientific_proof_is_a_reason_to_search_not_a_blocker(self):
        reviewer=AsyncMock();value=observation([claim(text='醋能去除水垢',verification_scope='public-fact')])
        value.update(content_type='opinion',analysis='视频未提供实验数据。',verification_plan={
            'question':'醋清洁水垢是否有科学依据？','status':'needs-details',
            'missing_information':['未提供科学原理或权威来源','未提供实验数据','没有说明浓度'],
            'evidence_to_find':['权威清洁指南','适用材质和浓度条件']})
        reviewer.review.return_value=value
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual(result['verification_plan']['status'],'search')
        self.assertEqual(result['verification_plan']['missing_information'],[])
        self.assertIn('没有说明浓度',result['verification_plan']['conditions_to_check'])
        self.assertEqual([x['text'] for x in result['verification_targets']],['醋能去除水垢'])

    async def test_clip_only_cannot_stop_public_effect_claims(self):
        reviewer=AsyncMock();value=observation([claim(verification_scope='public-fact')])
        value.update(analysis='视频声称该产品无糖。',verification_plan={
            'question':'这款饮料是否无糖？','status':'clip-only','missing_information':[]})
        reviewer.review.return_value=value
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual(result['verification_plan']['status'],'search')
        self.assertEqual(len(result['verification_targets']),1)

    async def test_missing_shop_details_keeps_analysis_on_service_experience(self):
        reviewer=AsyncMock()
        value=observation([claim(text='我坐了一小时车到店',quote={'speech_index':0},verification_scope='personal-account'),
            claim(text='店内桌子收起',origin='visual',frame_indices=[0],speech_indices=[],quote='桌子收起',verification_scope='clip-observation')])
        value.update(main_point='作者认为这次到店白跑一趟。',analysis='片段以一次到店经历说明服务不便；未展示其他门店的经营情况。',content_type='story')
        value['verification_plan']={'question':'该店地图营业状态与到店服务是否一致？','status':'needs-details','missing_information':['门店名称','到访时间']}
        reviewer.review.return_value=value
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual(result['verification_targets'],[])
        self.assertEqual(result['analysis'],value['analysis'])
        self.assertEqual(len(result['candidate_claims']),2)

    async def test_public_fact_inside_personal_story_still_requires_verification(self):
        reviewer=AsyncMock()
        value=observation([claim(text='我排队一小时',role='background',verification_scope='personal-account'),
            claim(text='该产品已被全国召回',verification_scope='public-fact')])
        value.update(content_type='story',analysis='作者将个人使用经历与产品召回消息联系起来。')
        reviewer.review.return_value=value
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual([x['text'] for x in result['verification_targets']],['该产品已被全国召回'])

    async def test_personal_experience_is_not_blanket_excluded_when_core_and_locatable(self):
        reviewer=AsyncMock()
        value=observation([claim(text='地图显示营业但现场无法用餐',verification_scope='personal-account'),
            claim(text='坐了一小时车',role='background',verification_scope='personal-account')])
        value.update(main_point='门店营业信息可能误导到访者。',analysis='视频展示的到访与地图信息有差异，需核对该店当时安排。',
            verification_plan={'question':'甲店10月24日地图营业信息与现场服务是否一致？','status':'search','missing_information':[]})
        reviewer.review.return_value=value
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual([x['text'] for x in result['verification_targets']],['地图显示营业但现场无法用餐'])
        self.assertEqual(result['verification_plan']['question'],value['verification_plan']['question'])

    async def test_new_analysis_schema_cannot_silently_default_missing_scope_to_public_fact(self):
        reviewer=AsyncMock();value=observation([claim()]);value['analysis']='介绍饮料。';reviewer.review.return_value=value
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual(result['verification_targets'],[])
        self.assertEqual(result['rejected_items'][0]['reason'],'missing verification scope')

    async def test_search_label_cannot_override_missing_required_details(self):
        reviewer=AsyncMock();value=observation([claim(verification_scope='personal-account')])
        value.update(analysis='到访经历反映服务信息不一致。',verification_plan={
            'question':'地图显示营业但现场无法用餐是否属实？','status':'search','missing_information':['门店具体地址','到访时间']})
        reviewer.review.return_value=value
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual(result['verification_plan']['status'],'needs-details')
        self.assertEqual(result['verification_targets'],[])
        self.assertEqual(result['analysis'],value['analysis'])

    async def test_core_speech_is_used_and_background_or_danmaku_not_auto_checked(self):
        reviewer=AsyncMock();reviewer.review.return_value=observation([
            claim(),claim(text='背板写着2019年',frame_indices=[0],speech_indices=[],origin='on-screen',role='background',quote='2019'),
            claim(text='弹幕说饮料有糖',frame_indices=[0],speech_indices=[],origin='danmaku',quote='有糖')])
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual([x['text'] for x in result['verification_targets']],['这款饮料完全无糖。'])
        self.assertEqual(result['main_point'],'声称这款饮料完全无糖。')
        self.assertEqual(result['speech'],SPEECH)
        parts=reviewer.review.call_args.args[1]
        self.assertEqual(json.loads(parts[0]['text'])['speech'],SPEECH)
        self.assertEqual(parts[1]['image_url']['detail'],'high')
        self.assertNotIn(capture()['title'],parts[0]['text'])
    async def test_debate_opinion_does_not_create_search_target(self):
        reviewer=AsyncMock();reviewer.review.return_value=observation([claim(kind='opinion')])
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual(result['verification_targets'],[])
    async def test_fabricated_speech_quote_rejected(self):
        with self.assertRaises(ValueError):validate_observation(observation([claim(quote='保证治病')]),1,SPEECH)
    async def test_quote_reference_uses_actual_transcript_without_copying_or_simplifying(self):
        speech={'source':'local-asr','video_time':1,'segments':[{'start':0,'end':3,'text':'這款飲料完全無糖。'}]}
        reviewer=AsyncMock();reviewer.review.return_value=observation([claim(quote={'speech_index':0})])
        result=await observe_video(capture(),reviewer,speech=speech)
        self.assertEqual(result['verification_targets'][0]['quote'],'這款飲料完全無糖。')
    async def test_one_bad_quote_does_not_discard_the_main_point(self):
        reviewer=AsyncMock();reviewer.review.return_value=observation([claim(quote='模型改写后的引文')])
        result=await observe_video(capture(),reviewer,speech=SPEECH)
        self.assertEqual(result['main_point'],'声称这款饮料完全无糖。')
        self.assertEqual(result['verification_targets'],[])
        self.assertEqual(result['rejected_items'][0]['reason'],'speech quote mismatch')
    async def test_missing_audio_does_not_claim_speech_was_read(self):
        reviewer=AsyncMock();reviewer.review.return_value=observation([])
        result=await observe_video(capture(),reviewer)
        self.assertNotIn('speech',result);self.assertIn('没有取得可识别的语音',''.join(result['limitations']))
    async def test_audio_bounds(self):
        audio={'data_url':'data:audio/webm;base64,'+base64.b64encode(b'\x1aE\xdf\xa3'+b'0'*20).decode(),'duration_seconds':30,'video_time':10}
        self.assertEqual(validate_audio(audio)['video_time'],10)
        for delta in [{'duration_seconds':100},{'duration_seconds':float('nan')},{'data_url':'https://example.org/audio'}]:
            with self.assertRaises(ValueError):validate_audio({**audio,**delta})
        with self.assertRaises(ValueError):validate_transcript({**SPEECH,'segments':[{'start':0,'end':90,'text':'x'}]})
    async def test_no_implicit_paid_asr_or_user_endpoint(self):
        with patch.dict('os.environ',{'VIDEO_ASR_URL':'https://example.org'}):
            with self.assertRaises(ValueError):await transcribe_audio({'data_url':'data:audio/webm;base64,'+base64.b64encode(b'\x1aE\xdf\xa3'+b'0'*20).decode(),'duration_seconds':1,'video_time':0})
if __name__=='__main__':unittest.main()
