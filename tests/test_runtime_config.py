import os
import unittest
from unittest.mock import patch

from evidence_mesh.runtime_config import env_flag, leader_identity, partner_identity


class RuntimeConfigTests(unittest.TestCase):
    def test_local_mode_uses_safe_development_ids(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                partner_identity("source-verifier"), ("source-verifier", False)
            )
            self.assertEqual(
                leader_identity(), ("evidence-audit-leader", False)
            )

    def test_identity_binding_requires_real_aics(self) -> None:
        with patch.dict(
            os.environ, {"AIP_IDENTITY_BINDING_ENABLED": "true"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "AGENT_AIC"):
                partner_identity("source-verifier")
            with self.assertRaisesRegex(ValueError, "LEADER_AIC"):
                leader_identity()

    def test_invalid_boolean_is_rejected(self) -> None:
        with patch.dict(os.environ, {"FLAG": "sometimes"}, clear=True):
            with self.assertRaisesRegex(ValueError, "FLAG"):
                env_flag("FLAG")


if __name__ == "__main__":
    unittest.main()
