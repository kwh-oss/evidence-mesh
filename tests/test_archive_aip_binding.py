from evidence_mesh.product_presentation import read_product
"""Local ASGI AIP tests, not deployed mTLS or public semantic acceptance."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid
import httpx
from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient
from evidence_mesh.public_evidence import PublicEvidenceCollector
from evidence_mesh.retrieval_archive import AIP_TASK_ID, RetrievalArchive
from evidence_mesh.source_partner import app


class AipArchiveBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_rpc_task_id_not_caller_claim_id(self):
        with tempfile.TemporaryDirectory() as folder:
            def factory():
                archive = RetrievalArchive(Path(folder).resolve(), AIP_TASK_ID.get())
                async def search(query):
                    archive.search(query, json.dumps({'query': query, 'results': []}).encode())
                    return []
                collector = PublicEvidenceCollector(search)
                collector.archive = archive
                return collector
            client = AipRpcClient('http://partner.test/rpc', 'offline-test-caller',
                transport=httpx.ASGITransport(app=app), identity_binding_enabled=False)
            task_id, session_id = 'task-' + str(uuid.uuid4()), 'session-' + str(uuid.uuid4())
            try:
                with patch('evidence_mesh.source_partner.configured_collector', side_effect=factory):
                    started = await client.start_task(session_id,
                        json.dumps({'claim_id': 'user-chosen-not-task',
                                    'claim_text': '2025年铁路12306提前90天售票是真的吗'}), task_id=task_id)
                    self.assertEqual(started.status.state, TaskState.AwaitingCompletion)
                    completed = await client.complete_task(task_id, session_id)
                product = read_product(completed.products)
                self.assertEqual(product['retrieval']['archive']['partner_task_id'], completed.taskId)
                manifest_path = next(Path(folder).glob('*/manifest.json'))
                manifest = json.loads(manifest_path.read_text())
                self.assertEqual(manifest['partner_task_id'], completed.taskId)
                self.assertEqual(manifest['claim_id'], 'user-chosen-not-task')
                self.assertEqual(manifest['task_id_origin'], 'aip-runtime')
                self.assertEqual(manifest['task_transport'], 'aip-rpc')
                self.assertFalse(manifest['semantic_acceptance'])
                self.assertIsNone(AIP_TASK_ID.get())
            finally:
                await client.close()
