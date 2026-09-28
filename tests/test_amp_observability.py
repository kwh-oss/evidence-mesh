import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evidence_mesh.amp_observability import AmpObservability


class AmpObservabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_and_audit_use_registered_aic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {
                "AMP_LOG_DIR": temp_dir,
                "AMP_HEARTBEAT_INTERVAL_SECONDS": "3600",
                "AMP_AUDIT_CERT_FILE": str(Path(temp_dir) / "missing-cert.pem"),
                "AMP_AUDIT_KEY_FILE": str(Path(temp_dir) / "missing-key.pem"),
            },
            clear=False,
        ):
            amp = AmpObservability(aic="1.2.156.test.agent", agent_name="test agent")
            await amp.start()
            await amp.emit_task_result(
                actor_aic="1.2.156.test.caller",
                task_id="task-1",
                session_id="session-1",
                success=True,
                reason="structured-product-ready",
            )
            await amp.stop()

            heartbeat = json.loads(
                (Path(temp_dir) / "amp_heartbeat_test-agent.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[-1]
            )
            audit = json.loads(
                (Path(temp_dir) / "amp_audit_test-agent.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()[-1]
            )

        self.assertEqual(heartbeat["log_type"], "heartbeat")
        self.assertEqual(heartbeat["aic"], "1.2.156.test.agent")
        self.assertEqual(audit["log_type"], "audit")
        self.assertEqual(audit["aic"], "1.2.156.test.agent")
        self.assertEqual(audit["correlation_id"], "task-1")
        self.assertEqual(audit["body"]["result"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
