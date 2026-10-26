import unittest
from types import SimpleNamespace
from evidence_mesh.task_outcome import failed_task_result
class TaskOutcomeTests(unittest.TestCase):
 def test_failed_task_has_specific_reason_not_pending(self):
  task=SimpleNamespace(dataItems=[SimpleNamespace(text='invalid-request: speech quote mismatch')])
  value=failed_task_result(task,{'task':'original','session':'session'})
  self.assertEqual(value['state'],'failed');self.assertFalse(value['recoverable'])
  self.assertEqual(value['detail'],'语音引文未通过校验。');self.assertEqual(value['new_start_requests'],0)
 def test_unknown_error_is_not_echoed_to_user(self):
  task=SimpleNamespace(dataItems=[SimpleNamespace(text='secret fixture content')])
  value=failed_task_result(task,{'task':'original','session':'session'})
  self.assertNotIn('secret',value['detail']);self.assertEqual(value['state'],'failed')
if __name__=='__main__':unittest.main()
