import unittest
from evidence_mesh.contracts import AuditRequest, ContradictionStatus
from evidence_mesh.models import SourceRef
from evidence_mesh.processors import find_contradiction
from evidence_mesh.rule_signals import effective_contradiction_status, rule_signal_explanation


class DirectionBoundaryTests(unittest.TestCase):
    def test_complementary_goals_not_confirmed_conflict(self):
        request = AuditRequest('offline-boundary', '北京市指导意见是否适用于全国学校？',
            SourceRef('offline', '离线样例', '测试材料'),
            '北京市义务教育学校原则上安排15分钟课间，旨在提高活动质量、降低学生负担。')
        result = find_contradiction(request)
        self.assertEqual(result.status, ContradictionStatus.POSSIBLE)
        product = {'input_assessment': {'evidence_provided': True, 'inspection_performed': True,
                    'inspection_scope': 'supplied-text-rules'},
                   'payload': {'status': 'confirmed', 'indicators': list(result.indicators)}}
        self.assertEqual(effective_contradiction_status(product), 'possible')
        self.assertIn('不同对象', rule_signal_explanation(product))
        self.assertEqual(product['payload']['status'], 'confirmed')  # Preserve historical raw records.
