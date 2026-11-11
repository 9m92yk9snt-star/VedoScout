import unittest
from sequence_deadline import bounded_deadline

class DeadlineTests(unittest.TestCase):
 def test_default_retains_original_allowance(self):
  self.assertEqual(bounded_deadline(100,420),520)
 def test_remaining_stage_cannot_restart_clock(self):
  first=bounded_deadline(100,420)
  self.assertEqual(bounded_deadline(255,420,first),520)
 def test_shared_deadline_cannot_extend_local_limit(self):
  self.assertEqual(bounded_deadline(100,420,9999),520)
 def test_expired_deadline_stays_expired(self):
  self.assertEqual(bounded_deadline(600,420,520),520)
 def test_zero_budget_is_immediately_expired(self):
  self.assertEqual(bounded_deadline(100,0,500),100)
 def test_rejects_nonfinite_or_invalid_budgets(self):
  for value in [True,None,'420',float('inf'),float('nan'),-1]:
   with self.subTest(value=value),self.assertRaises(ValueError):bounded_deadline(100,value)
  with self.assertRaises(ValueError):bounded_deadline(1e308,1e308)
 def test_rejects_invalid_shared_deadline(self):
  for value in [True,'520',float('inf'),float('nan')]:
   with self.subTest(value=value),self.assertRaises(ValueError):bounded_deadline(100,420,value)

if __name__=='__main__':unittest.main()
