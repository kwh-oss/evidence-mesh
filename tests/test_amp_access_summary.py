import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('access_summary', Path(__file__).resolve().parents[1]/'scripts/summarize_amp_access.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class AccessSummaryTests(unittest.TestCase):
    def row(self, task='t', aic='old', callee='old', status=200, timestamp='2026-10-10T00:00:00Z'):
        return dict(log_type='access', aic=aic, correlation_id=task, timestamp=timestamp,
                    body=dict(callee=dict(aic=callee), response=dict(statusCode=status)))

    def run_summary(self, rows, known=()):
        return m.summarize(rows, {'old'}, m.instant('2026-10-10T00:00:00Z'), m.instant('2026-10-11T00:00:00Z'), known)

    def test_duplicate_task_not_multiple_visits(self):
        result = self.run_summary([self.row(), self.row()], {'t'})['agents']['old']
        self.assertEqual(result['unique_incoming_tasks'], 1)
        self.assertEqual(result['known_self_test'], 1)
        self.assertEqual(result['extra_records_for_same_task'], 1)

    def test_outgoing_and_other_identity_excluded(self):
        report = self.run_summary([self.row(callee='child'), self.row(aic='new')])
        self.assertEqual(report['agents']['old'], {})
        self.assertEqual(report['excluded'], {'not_incoming': 1, 'other_identity': 1})

    def test_unknown_origin_and_mixed_transport(self):
        result = self.run_summary([self.row(), self.row(status=500)])['agents']['old']
        self.assertEqual(result['unknown_origin'], 1)
        self.assertEqual(result['mixed_http_outcomes'], 1)
        self.assertNotIn('organic', result)

    def test_time_boundaries_and_missing_task(self):
        report = self.run_summary([self.row(timestamp='2026-10-11T00:00:00Z'), self.row(task=None), self.row(timestamp='invalid')])
        self.assertEqual(report['excluded'], {'outside_window': 1, 'missing_task_id': 1, 'invalid_record': 1})


if __name__ == '__main__': unittest.main()
