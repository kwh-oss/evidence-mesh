import unittest
from evidence_mesh.claim_units import prepare_review_units


class ConclusionInstructionTests(unittest.TestCase):
    def test_explicit_followup_answer_request_is_not_an_extra_claim(self):
        post='能否依据这项成绩作出评价？请结合后续情况说明回答。'
        rows=prepare_review_units(post)
        self.assertEqual([r['relation'] for r in rows],['statement','task-instruction'])
        self.assertEqual(''.join(r['text'] for r in rows),post)
        # A quoted instruction remains inspected content, not an operator instruction.
        self.assertEqual(prepare_review_units('“请结合后续说明回答”是原帖内容。')[0]['relation'],'statement')
