import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from registry_preflight import inspect_all  # noqa: E402


class RegistryPreflightTests(unittest.TestCase):
    def test_drafts_are_saveable_but_not_submission_ready(self) -> None:
        results = inspect_all()

        self.assertEqual(len(results), 4)
        self.assertTrue(all(item.draft_save_ready for item in results))
        self.assertTrue(all(not item.submission_ready for item in results))
        self.assertTrue(
            all(
                item.post_approval_pending
                == ("AIC will be assigned after Registry approval",)
                for item in results
            )
        )
        self.assertTrue(
            all(
                not any("AIC" in blocker for blocker in item.submission_blockers)
                for item in results
            )
        )
        self.assertTrue(
            all(
                any("non-routable" in blocker for blocker in item.submission_blockers)
                for item in results
            )
        )
        self.assertTrue(
            all(
                any("DNS SAN" in blocker for blocker in item.submission_blockers)
                for item in results
            )
        )


if __name__ == "__main__":
    unittest.main()
