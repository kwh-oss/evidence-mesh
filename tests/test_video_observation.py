import base64,json,struct,unittest
from unittest.mock import AsyncMock
from evidence_mesh.video_observation import validate_capture,validate_observation,observe_video

def capture():
    # Header-only fixture validates structural bounds; no image decoding is claimed.
    raw=b'\x89PNG\r\n\x1a\n'+b'\0'*8+struct.pack('>II',320,180)
    return {'url':'https://www.douyin.com/video/123','title':'fixture','frames':[{'video_time':1,'data_url':'data:image/png;base64,'+base64.b64encode(raw).decode()}],'captions':[]}

class VideoObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_observe_is_image_analysis_without_search_or_fact_certification(self):
        reviewer=AsyncMock()
        reviewer.review.return_value={'summary':'画面看起来有车辆','observations':[{'text':'车辆画面','frame_indices':[0]}],'candidate_claims':[{'text':'车辆出现离地动作','frame_indices':[0]}],'limitations':[]}
        result=await observe_video(capture(),reviewer)
        self.assertEqual(result['product_type'],'video-observation')
        self.assertFalse(result['claim_verified']);self.assertFalse(result['search_performed'])
        parts=reviewer.review.call_args.args[1]
        self.assertEqual(parts[1]['type'],'image_url')
        self.assertIn('没有取得可识别的语音', ''.join(result['limitations']))
        self.assertNotIn('data_url',json.dumps(result))

    async def test_bad_capture_rejected_before_model(self):
        for change in [{'frames':[]},{'url':'file:///secret'},{'url':'https://user:secret@example.org/video'},{'captions':['x'*501]}]:
            value=capture();value.update(change);reviewer=AsyncMock()
            with self.assertRaises(ValueError):await observe_video(value,reviewer)
            reviewer.review.assert_not_awaited()

    async def test_external_image_urls_and_nonfinite_times_rejected(self):
        for frame in [{'video_time':1,'data_url':'https://example.org/image.png'},{'video_time':float('nan'),'data_url':capture()['frames'][0]['data_url']}]:
            value=capture();value['frames']=[frame]
            with self.assertRaises(ValueError):validate_capture(value)

    async def test_out_of_range_frame_citation_rejected(self):
        with self.assertRaises(ValueError):validate_observation({'summary':'x','observations':[{'text':'x','frame_indices':[1]}],'candidate_claims':[],'limitations':[]},1)

if __name__=='__main__':unittest.main()
