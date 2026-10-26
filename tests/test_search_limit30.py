import os
import unittest
from unittest.mock import patch
from evidence_mesh.public_evidence import configured_collector


class AuthorizedSearchLimitTests(unittest.TestCase):
    def test_authorized_limit_reaches_adapter_and_ceiling_is_enforced(self):
        env={'PUBLIC_RETRIEVAL_ENABLED':'true','PUBLIC_SEARCH_PROVIDER':'tavily',
             'TAVILY_KEY_FILE':'/private/test.key','TAVILY_SEARCH_BUDGET_FILE':'/private/search-quota.sqlite3',
             'TAVILY_SEARCH_MAX_CALLS':'50'}
        with patch.dict(os.environ,env,clear=True), patch('evidence_mesh.tavily_search.TavilySearch') as provider:
            self.assertIsNotNone(configured_collector())
            self.assertEqual(provider.call_args.args[2],50)
        env['TAVILY_SEARCH_MAX_CALLS']='500'
        with patch.dict(os.environ,env,clear=True), patch('evidence_mesh.tavily_search.TavilySearch') as provider:
            self.assertIsNotNone(configured_collector())
            self.assertEqual(provider.call_args.args[2],500)
        env['TAVILY_SEARCH_MAX_CALLS']='501'
        with patch.dict(os.environ,env,clear=True), patch('evidence_mesh.tavily_search.TavilySearch') as provider:
            with self.assertRaises(ValueError):configured_collector()
            provider.assert_not_called()
