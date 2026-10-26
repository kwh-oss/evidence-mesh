import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from evidence_mesh.retrieval_archive import RetrievalArchive

spec = importlib.util.spec_from_file_location('runtime_verifier', Path(__file__).resolve().parents[1] /
    'scripts/verify_source_runtime_archive.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class RuntimeVerifierTests(unittest.TestCase):
    def make_run(self, root):
        archive = RetrievalArchive(root, 'runtime-task')
        archive.search('query', b'{"query":"query","results":[]}')
        raw, text = b'public page bytes', 'actual extracted public text'
        page = {'url': 'https://example.com/notice', 'body_sha256': hashlib.sha256(raw).hexdigest(),
                'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest()}
        archive.page(raw, page)
        product = {'payload': {'claim_id': 'claim-id'}, 'retrieval': {'queries': ['query'],
            'sources': [page], 'search_complete': True}}
        archive.finish(product)
        return archive

    def test_integrity_not_semantic_acceptance(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.make_run(Path(folder).resolve())
            report = verifier.audit(archive.path)
            self.assertEqual(report['partner_task_id'], 'runtime-task')
            self.assertTrue(report['all_attempted_queries_have_response'])
            self.assertFalse(report['semantic_acceptance'])
            self.assertFalse(report['deployed_aip_acceptance'])

    def test_tampering_and_unlisted_files_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.make_run(Path(folder).resolve())
            page = next(archive.path.glob('*-page.raw'))
            raw = page.read_bytes()
            page.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                verifier.audit(archive.path)
            page.write_bytes(raw)
            (archive.path / 'unexpected.txt').write_text('unlisted')
            with self.assertRaises(ValueError):
                verifier.audit(archive.path)
