"""Offline fixtures test extraction, not live source reliability."""
import unittest
import hashlib
from pathlib import Path
from evidence_mesh.page_document import VisibleHTML


class PageDocumentTests(unittest.TestCase):
    def test_archived_12306_body_and_unclassified_signoff_date(self):
        path = Path(__file__).parent / 'fixtures/12306-announcement-20241211-captured-20261012.html'
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '3ef8620dc213b88c6a54140c2c53c1941c371cc2c07708ba4799e212e42ab31b')
        parser = self.parse(raw.decode('utf-8'))
        text, method = parser.document()
        self.assertEqual(method, 'semantic-cms-content')
        self.assertEqual(len(text), 632)
        self.assertIn('从未授权任何第三方平台', text)
        self.assertIn('铁路12306科创中心\n2024年12月11日', text)
        self.assertNotIn('友情链接', text)
        self.assertNotIn('会员管理', text)
        self.assertNotIn('京ICP备', text)
        hint = next(h for h in parser.date_hints() if h['field'] == 'visible-document-tail-date')
        self.assertEqual(hint['value'], '2024-12-11')
        self.assertFalse(hint['verified'])
        self.assertEqual(hint['meaning'], 'unclassified-signoff-or-event-date')

    def test_prose_event_and_footer_dates_not_promoted_to_publication(self):
        parser = self.parse('<article>' + '正文' * 30 + '2025年1月14日开售。</article>'
                            '<div>2026年10月12日</div>')
        self.assertFalse(parser.date_hints())
        fallback = self.parse('<div>' + '导航与正文未划分' * 20 + '\n2024年12月11日</div>')
        self.assertFalse(fallback.date_hints())
    def parse(self, html):
        parser = VisibleHTML()
        parser.feed(html)
        return parser

    def test_article_preferred_over_navigation_and_footer(self):
        body = '公告正文明确说明只适用于这次调查样本，不能扩大到所有人。' * 3
        parser = self.parse('<nav>首页' * 1 + '</nav><main>侧栏广告<article><p>'
                            + body + '</p></article></main><footer>法律声明</footer>')
        text, method = parser.document()
        self.assertEqual(text, body)
        self.assertEqual(method, 'semantic-article')

    def test_main_used_when_no_article(self):
        body = '原始正文没有文章标签，但是使用了主内容区域。' * 4
        text, method = self.parse('<div>站点菜单</div><main>' + body + '</main>').document()
        self.assertEqual(text, body)
        self.assertEqual(method, 'semantic-main')

    def test_short_article_does_not_discard_long_visible_body(self):
        parser = self.parse('<article>短卡片</article><p>' + '实际正文' * 20 + '</p>')
        text, method = parser.document()
        self.assertIn('实际正文', text)
        self.assertEqual(method, 'visible-text-fallback')

    def test_head_title_scripts_hidden_and_self_closing_nodes(self):
        parser = self.parse('<head><title>标题</title><script>危险指令</script></head>'
                            '<div hidden><span>隐藏内容</span></div>'
                            '<p aria-hidden="true">隐藏二</p>'
                            '<div style="display: none">隐藏三</div>'
                            '<template>隐藏四</template><p>公开正文<br/>后一行</p>')
        text, _ = parser.document()
        self.assertEqual(text, '公开正文\n后一行')
        self.assertEqual(''.join(parser.title_parts), '标题')

    def test_block_ends_do_not_glue_paragraph_quotes(self):
        text, _ = self.parse('<p>第一句</p><p>第二句</p>').document()
        self.assertEqual(text, '第一句\n第二句')

    def test_date_and_author_are_unverified_hints(self):
        parser = self.parse('<meta property="article:published_time" content="2025-01-01">'
                            '<meta name="author" content="匿名用户"><p>正文</p>')
        self.assertEqual(len(parser.metadata), 2)
        self.assertTrue(all(not row['verified'] for row in parser.metadata))
        self.assertTrue(all(row['basis'] == 'page-declared' for row in parser.metadata))

    def test_conflicting_dates_preserved_not_chosen(self):
        parser = self.parse('<meta name="date" content="2024-01-01">'
                            '<meta name="pubdate" content="2025-01-01">')
        self.assertEqual([r['value'] for r in parser.metadata], ['2024-01-01', '2025-01-01'])

    def test_omitted_links_not_used_as_provenance(self):
        parser = self.parse('<nav><a href="/menu">菜单</a></nav>'
                            '<p><a href="/source">出处</a></p>'
                            '<div hidden><a href="/hidden">隐藏</a></div>')
        self.assertEqual(parser.links, ['/source'])

    def test_explicit_original_link_label_is_only_a_hint(self):
        parser = self.parse('<nav><a href="/menu">原文</a></nav>'
                            '<a href="/original"><span>查看原文</span></a>'
                            '<a href="/ad">购买商品</a>')
        hints = parser.source_link_hints()
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]['href'], '/original')
        self.assertFalse(hints[0]['verified'])

    def test_cms_region_is_extraction_hint_not_authentication(self):
        body = '公告正文明确说明适用对象及缓冲期，不表示已经完成。' * 3
        parser = self.parse('<div>菜单</div><div class="view TRS_UEDITOR"><p>'
                            + body + '</p></div><div>页脚</div>')
        text, method = parser.document()
        self.assertEqual(text, body)
        self.assertEqual(method, 'semantic-cms-content')

    def test_hidden_metadata_visible_publication_date_conflict_retained(self):
        parser = self.parse('<meta name="PubDate" content="2024-08-29">'
                            '<span>发布日期：</span><em>2024-08-30</em><p>正文</p>')
        self.assertTrue(parser.date_conflict())
        self.assertEqual([h['value'] for h in parser.date_hints()], ['2024-08-29', '2024-08-30'])

    def test_same_publication_day_and_time_not_conflict(self):
        parser = self.parse('<meta property="article:published_time" content="2024-08-30T10:00:00Z">'
                            '<p>发布日期：2024-8-30</p>')
        self.assertFalse(parser.date_conflict())
