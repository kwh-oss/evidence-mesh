"""Offline transport scenarios; real provider acceptance is separate."""
import unittest
import hashlib
from unittest.mock import AsyncMock
from evidence_mesh.public_evidence import PublicEvidenceCollector
from evidence_mesh.retrieval_recovery import institution_names, non_evidence_page

def page(url):
    text='这是离线模拟的机构介绍原文，用于检查读取和传递，不是真实机构信息。'
    return {'url':url,'title':'离线介绍','text':text,
            'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'fetched_at':'2026-10-25T00:00:00Z','publisher_authenticated':False}


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_round_and_service_stub_trigger_separate_entity_queries(self):
        initial=[{'url':'https://blocked.example/1'}, {'url':'https://blocked.example/2'},
                 {'url':'https://mp.weixin.qq.com/miniprogram/landing_page/test/zh_CN'}]
        async def search(query):
            if query == '南京博物院 官方 简介 地址 机构':return [{'url':'https://first.example/about'}]
            if query == '南京博物馆 官方 简介 地址 机构':return [{'url':'https://second.example/about'}]
            return initial
        def fetch(url):
            if 'blocked.example' in url:raise TimeoutError('fixture')
            p=page(url)
            p['text_sha256']=url
            if 'weixin.qq.com' in url:p['text']='本页面信息内容仅供参考，小程序服务由开发者向微信用户提供。'
            return p
        engine=AsyncMock(side_effect=search)
        result=await PublicEvidenceCollector(engine,fetch).collect('用证链帮我查：南京博物院就是南京博物馆吗？')
        self.assertEqual(engine.await_count,4)
        self.assertEqual([p['url'] for p in result['sources']],['https://first.example/about','https://second.example/about'])
        self.assertTrue(any(f.get('reason')=='mini-program-service-landing' for f in result['failures']))
        self.assertEqual(result['page_attempt_count'],5)
        self.assertFalse(result['claim_verified'])

    async def test_already_readable_collection_does_not_add_search_cost(self):
        search=AsyncMock(return_value=[{'url':'https://first.example/about'}])
        result=await PublicEvidenceCollector(search,page).collect('某机构是什么？')
        self.assertEqual(search.await_count,2)
        self.assertNotIn('recovery',result)

    async def test_recovery_is_bounded_and_does_not_use_search_snippets(self):
        calls=[]
        async def search(query):
            calls.append(query)
            return [{'url':'https://blocked.example/'+str(len(calls))+'-'+str(i),'content':'假的答案'} for i in range(5)]
        def fetch(url):raise TimeoutError('fixture')
        result=await PublicEvidenceCollector(search,fetch).collect('某消息可信吗？')
        self.assertEqual(len(calls),3)
        self.assertEqual(result['page_attempt_count'],6)
        self.assertEqual(result['sources'],[])
        self.assertNotIn('假的答案',str(result))

    async def test_recovery_cannot_fetch_private_urls(self):
        engine=AsyncMock(side_effect=[ [{'url':'https://blocked.example/1'}], [],
            [{'url':'https://127.0.0.1/private'},{'url':'http://public.example/a'}] ])
        visited=[]
        def fetch(url):visited.append(url);raise TimeoutError('fixture')
        await PublicEvidenceCollector(engine,fetch).collect('查一下原文')
        self.assertEqual(visited,['https://blocked.example/1'])

    def test_subject_extraction_is_not_specific_to_nanjing(self):
        self.assertEqual(institution_names('检索“甲城大学”与“乙城学院”的官方介绍'),['甲城大学','乙城学院'])
        self.assertEqual(institution_names('帮我查：南京博物院就是南京博物馆吗？'),['南京博物院','南京博物馆'])
        self.assertIsNone(non_evidence_page({'url':'https://example.org/article','text':'一篇不包含原查询词但可能相关的正常正文。'}))
