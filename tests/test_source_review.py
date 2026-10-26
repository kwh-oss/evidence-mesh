import unittest
from evidence_mesh.source_review import review_sources
from evidence_mesh.message_result import assess_public_message


def page(identifier, url, text='测试正文', digest=None):
    return {'source_id': identifier, 'url': url, 'text': text, 'text_sha256': digest}


class SourceReviewTests(unittest.TestCase):
    def test_official_looking_host_not_truth(self):
        result = review_sources({'sources': [page('a', 'https://jw.beijing.gov.cn/a')]})
        self.assertEqual(result['sources'][0]['host_category_hint'], 'government-domain')
        self.assertFalse(result['source_authenticity_verified'])
        self.assertFalse(result['sources'][0]['publisher_authenticated'])

    def test_suffix_spoof_not_government_hint(self):
        result = review_sources({'sources': [page('a', 'https://gov.cn.evil.test/a')]})
        self.assertEqual(result['sources'][0]['host_category_hint'], 'unclassified')

    def test_identical_body_groups_hosts_but_not_independence(self):
        result = review_sources({'sources': [page('a', 'https://one.test/a', digest='x'),
                                             page('b', 'https://two.test/b', digest='x')]})
        self.assertEqual(result['observed_dependency_groups'], [['a', 'b']])
        self.assertIsNone(result['independent_source_count'])

    def test_read_declared_link_not_verified_repost(self):
        result = review_sources({'sources': [page('a', 'https://one.test/a'), page('b', 'https://two.test/b')],
            'source_relations': [{'from_url': 'https://one.test/a', 'to_url': 'https://two.test/b',
             'relationship': 'page-declared-source-link', 'target_read': True}]})
        self.assertEqual(result['observed_dependency_groups'], [['a', 'b']])
        self.assertFalse(result['observed_link_relations'][0]['repost_verified'])

    def test_unread_or_invented_links_not_counted(self):
        result = review_sources({'sources': [page('a', 'https://one.test/a')],
            'source_relations': [{'from_url': 'https://one.test/a', 'to_url': 'https://two.test/b',
             'relationship': 'page-declared-source-link', 'target_read': True}]})
        self.assertEqual(result['observed_link_relations'], [])

    def test_different_hosts_not_independence_proof(self):
        result = review_sources({'sources': [page('a', 'https://one.test/a'), page('b', 'https://two.test/b')]})
        self.assertEqual(len(result['observed_dependency_groups']), 2)
        self.assertIsNone(result['independent_source_count'])

    def test_debunk_quoting_rumor_not_anonymous_verdict(self):
        retrieval = {'sources': [page('a', 'https://one.test/a', '网传消息已被否认。')]}
        row = review_sources(retrieval)['sources'][0]
        self.assertTrue(row['anonymous_attribution_marker'])
        self.assertIn('not-necessarily', row['marker_scope'])
        result = assess_public_message({'claims': [], 'coverage_complete': False}, retrieval)
        self.assertEqual(result['status'], 'unverified')
