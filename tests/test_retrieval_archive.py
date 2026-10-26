import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx

from evidence_mesh.retrieval_archive import RetrievalArchive, AIP_TASK_ID, ArchiveCapacityError
from evidence_mesh.public_evidence import configured_collector
from evidence_mesh.source_partner import source_product
from evidence_mesh.contracts import request_from_caller_text


class ArchiveTests(unittest.TestCase):
    def test_full_archive_can_expand_without_purging_or_changing_old_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            for n in range(64):
                run=root/str(n);run.mkdir(mode=0o700)
                (run/'manifest.json').write_bytes(b'preserve-exact-original')
            with patch.dict(os.environ,{'PUBLIC_RETRIEVAL_ARCHIVE_MAX_RUNS':'64'}):
                with self.assertRaises(ArchiveCapacityError):RetrievalArchive(root)
            with patch.dict(os.environ,{'PUBLIC_RETRIEVAL_ARCHIVE_MAX_RUNS':'256'}):
                archive=RetrievalArchive(root,'new-real-task')
                archive.finish({'payload':{'claim_id':'new-claim'}})
            self.assertEqual(len(list(root.iterdir())),65)
            for n in range(64):
                self.assertEqual((root/str(n)/'manifest.json').read_bytes(),b'preserve-exact-original')

    def test_invalid_capacity_fails_before_creating_a_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            for value in ('0','4097','unlimited','1.5','-1'):
                with patch.dict(os.environ,{'PUBLIC_RETRIEVAL_ARCHIVE_MAX_RUNS':value}):
                    with self.assertRaises(ValueError):RetrievalArchive(root)
                self.assertEqual(list(root.iterdir()),[])

    def test_frozen_artifacts_hashes_and_real_id(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = RetrievalArchive(Path(folder).resolve(), 'actual-aip-task')
            archive.search('公告', b'{"results":[]}')
            raw = b'actual-page'
            archive.page(raw, {'body_sha256': hashlib.sha256(raw).hexdigest(), 'text': '正文'})
            result = archive.finish({'payload': {'claim_id': 'caller-claim'}})
            manifest = json.loads((archive.path / 'manifest.json').read_text())
            self.assertEqual(manifest['partner_task_id'], 'actual-aip-task')
            self.assertEqual(manifest['claim_id'], 'caller-claim')
            self.assertFalse(manifest['semantic_acceptance'])
            self.assertEqual(result['manifest_sha256'], hashlib.sha256((archive.path / 'manifest.json').read_bytes()).hexdigest())
            for record in manifest['artifacts']:
                for item in (record['raw'], record['sidecar']):
                    self.assertEqual(item['sha256'], hashlib.sha256((archive.path / item['file']).read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                archive.search('late', b'late')
            with self.assertRaises(ValueError):
                archive.finish({})

    def test_missing_root_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / 'missing'
            with self.assertRaises(OSError):
                RetrievalArchive(path)
            self.assertFalse(path.exists())

    def test_raw_limits_and_page_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = RetrievalArchive(Path(folder).resolve())
            with self.assertRaises(ValueError):
                archive.page(b'page', {'body_sha256': 'wrong'})
            with self.assertRaises(ValueError):
                archive.search('q', b'x' * (512 * 1024 + 1))
            self.assertEqual(archive.records, [])

    @unittest.skipUnless(os.name == 'posix', 'POSIX privacy permissions')
    def test_public_root_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve()
            path.chmod(0o755)
            with self.assertRaises(ValueError):
                RetrievalArchive(path)


class ArchiveFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_runtime_records_search_task_and_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            key = root / 'tavily.key'
            key.write_text('tvly-offline-test-key')
            key.chmod(0o600)
            archive_root = root / 'archive'
            archive_root.mkdir(mode=0o700)
            env = {'PUBLIC_RETRIEVAL_ENABLED': 'true', 'PUBLIC_SEARCH_PROVIDER': 'tavily',
                   'TAVILY_KEY_FILE': str(key), 'TAVILY_SEARCH_BUDGET_FILE': str(root / 'search-quota.sqlite3'),
                   'TAVILY_SEARCH_MAX_CALLS': '2', 'PUBLIC_RETRIEVAL_ARCHIVE_ROOT': str(archive_root)}
            token = AIP_TASK_ID.set('runtime-generated-id')
            try:
                with patch.dict(os.environ, env, clear=True):
                    collector = configured_collector()
                def response(request):
                    query = json.loads(request.content)['query']
                    return httpx.Response(200, json={'query': query, 'results': [], 'usage': {'credits': 1}})
                collector.search.transport = httpx.MockTransport(response)
                request = request_from_caller_text('2025年铁路12306提前90天售票是真的吗', default_claim_id='not-aip-id')
                product = json.loads(await source_product(request, collector))
            finally:
                AIP_TASK_ID.reset(token)
            self.assertEqual(product['retrieval']['archive']['partner_task_id'], 'runtime-generated-id')
            self.assertFalse(product['retrieval']['archive']['semantic_acceptance'])
            raw_files = list(collector.archive.path.glob('*-search.raw'))
            self.assertEqual(len(raw_files), 2)
            self.assertTrue((collector.archive.path / 'source-product.json').is_file())
            self.assertNotIn('tvly-offline-test-key', ''.join(p.read_text() for p in collector.archive.path.iterdir()))

    async def test_task_context_isolated_between_concurrent_tasks(self):
        async def value(task_id):
            token = AIP_TASK_ID.set(task_id)
            try:
                await asyncio.sleep(0)
                return AIP_TASK_ID.get()
            finally:
                AIP_TASK_ID.reset(token)
        self.assertEqual(await asyncio.gather(value('one'), value('two')), ['one', 'two'])
        self.assertIsNone(AIP_TASK_ID.get())
