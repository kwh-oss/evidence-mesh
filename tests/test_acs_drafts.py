import unittest

from scripts.validate_acs_drafts import validate_drafts


class AcsDraftTests(unittest.TestCase):
    def test_all_four_drafts_validate_with_official_sdk(self) -> None:
        self.assertEqual(len(validate_drafts()), 4)


if __name__ == "__main__":
    unittest.main()
