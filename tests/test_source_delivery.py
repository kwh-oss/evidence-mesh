import json
import unittest
from unittest.mock import AsyncMock
from evidence_mesh.source_delivery import source_delivery, retrieval_question, retrieval_search_text


def page(text, **extras):
    return {'source_id':'web-fixture', 'title':'测试公告', 'url':'https://example.com/rule',
            'text':text, 'fetched_at':'2026-10-19T00:00:00Z', **extras}


class SourceDeliveryTests(unittest.TestCase):
    def test_conversational_query_keeps_exact_claim_without_invented_keywords(self):
        self.assertEqual(retrieval_search_text('我想知道，网上说的“某设备每年都必须更换”是真的吗？'),'某设备每年都必须更换')
        self.assertEqual(retrieval_search_text('听说“隔夜茶一定致癌”属实吗？'),'隔夜茶一定致癌')
        question='比较“产品甲”和“产品乙”是否适合学生'
        self.assertEqual(retrieval_search_text(question),question)

    def test_scheduler_suffix_removed_without_cutting_quoted_content(self):
        original='我想知道，“某产品是否每年更换”是真的吗？'
        self.assertEqual(retrieval_question(original+' DAG 指定的上游产物摘要：叮当已开始派发。'),original)
        literal='帮我查“术语 DAG 指定的上游产物摘要：例子”的意思'
        self.assertEqual(retrieval_question(literal),literal)

    def test_actual_read_text_with_url_offsets_and_no_truth_verdict(self):
        text='首页 导航 联系我们\n关于活动入场的规定：仅学生免费入场，其他人需购票。\n其他栏目'
        value=source_delivery({'status':'retrieved','sources':[page(text)]},'活动是否所有人免费入场')
        answer=value['answer']
        self.assertIn('https://example.com/rule',answer)
        self.assertIn('仅学生免费入场，其他人需购票。',answer)
        self.assertIn('抓取时间',answer)
        self.assertFalse(value['verdict_produced'])
        self.assertFalse(value['source_authenticity_verified'])
        for quote in value['sources'][0]['excerpts']:
            self.assertEqual(text[quote['start']:quote['end']],quote['text'])

    def test_generic_topics_and_no_search_snippet_promoted_to_evidence(self):
        for topic,body in [('退款','审核后七个工作日内退款，节假日顺延。'),('开放','周一闭馆，法定节假日除外。')]:
            value=source_delivery({'status':'retrieved','sources':[page(body)],
                                  'leads':[{'content':'未经读取的搜索摘要，不可作证据'}]},topic)
            self.assertIn(body,value['answer'])
            self.assertNotIn('未经读取的搜索摘要',value['answer'])
        value=source_delivery({'status':'retrieved','sources':[{'url':'https://example.com','title':'只有标题'}]},'问题')
        self.assertFalse(value['sources'])
        self.assertIn('暂未取得可用正文',value['answer'])

    def test_partials_failures_and_unsafe_markdown_are_explicit(self):
        value=source_delivery({'sources':[page('# 假标题 ![远程图](https://example.com/img) <script>')],
                              'search_complete':False,'failures':[{'stage':'fetch'}]},'标题')
        self.assertIn('部分查询',value['answer'])
        self.assertIn('1 项',value['answer'])
        self.assertNotIn('![远程图]',value['answer'])
        self.assertNotIn('<script>',value['answer'])
        value=source_delivery({'sources':[page('正文',url='javascript:alert(1)')]},'正文')
        self.assertFalse(value['sources'])

    def test_long_text_is_bounded_and_offsets_stay_exact(self):
        text='无关导航。\n' * 100 + '退款条款：仅支持已登记的订单退款，不包括赠品。\n' + '其他。\n' * 100
        value=source_delivery({'sources':[page(text)]},'订单退款条件')
        self.assertIn('不包括赠品',value['answer'])
        for quote in value['sources'][0]['excerpts']:
            self.assertEqual(text[quote['start']:quote['end']],quote['text'])
        self.assertLess(len(value['answer']),2500)


class SourceDeliveryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_collector_receives_question_not_scheduler_notes(self):
        from evidence_mesh.source_partner import source_product
        from evidence_mesh.contracts import request_from_caller_text
        collector=AsyncMock();collector.collect.return_value={'status':'retrieved','sources':[page('公告要求两年检修一次。')]}
        question='网上说“设备每年都要更换”是真的吗？'
        request=request_from_caller_text(question+' DAG 指定的上游产物摘要：已开始调度。',default_claim_id='fixture')
        value=json.loads(await source_product(request,collector))
        collector.collect.assert_awaited_once_with('设备每年都要更换')
        self.assertNotIn('DAG 指定',value['answer'])

    async def test_real_source_builder_and_protocol_preserve_retrieval(self):
        from evidence_mesh.source_partner import source_product
        from evidence_mesh.contracts import request_from_caller_text
        from evidence_mesh.product_presentation import readable_product_item, read_product
        from acps_sdk.aip import Product
        collector=AsyncMock()
        text='产品保修期为两年，不包括人为损坏。'
        collector.collect.return_value={'status':'retrieved','sources':[page(text)],'claim_verified':False}
        req=request_from_caller_text('产品保修包括人为损坏吗',default_claim_id='fixture')
        value=json.loads(await source_product(req,collector))
        wire=Product(id='test',dataItems=[readable_product_item(value)])
        decoded=Product.model_validate_json(wire.model_dump_json())
        self.assertIn(text,decoded.dataItems[0].text)
        self.assertIn('https://example.com/rule',decoded.dataItems[0].text)
        self.assertEqual(read_product([decoded])['retrieval']['sources'][0]['text'],text)
        self.assertFalse(value['source_delivery']['verdict_produced'])

    async def test_metadata_and_pages_both_remain_visible(self):
        from evidence_mesh.source_partner import source_product
        from evidence_mesh.contracts import request_from_caller_text
        collector=AsyncMock()
        collector.collect.return_value={'status':'retrieved','sources':[page('正文：只报告相关性，未建立因果关系。')],
            'scholarly_metadata':{'records':[{'title':'登记题名','doi':'10.1/example','url':'https://doi.org/10.1/example'}]}}
        value=json.loads(await source_product(request_from_caller_text('检索相关研究',default_claim_id='fixture'),collector))
        self.assertIn('只报告相关性',value['answer'])
        self.assertIn('登记题名',value['answer'])
        self.assertIn('仅书目信息',value['answer'])
