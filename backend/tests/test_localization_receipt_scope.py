import unittest
from match_room_localization import retained_localization_events

class ReceiptScopeTests(unittest.TestCase):
 def setUp(self):
  self.audit={'source_video_sha256':'source','original_selection_values_sha256':'selection','events':{'e':{'receipt':{'status':'COMPLETED'},'completion':{'extra':{'receipt':{'status':'COMPLETED'}}}}}}
 def test_matching_context_retains_primary_and_supplemental_receipts(self):
  result=retained_localization_events(self.audit,'source','selection')
  self.assertEqual(result,self.audit['events'])
  result['e']['completion'].clear()
  self.assertTrue(self.audit['events']['e']['completion'])
 def test_other_video_cannot_supply_receipts(self):
  self.assertEqual(retained_localization_events(self.audit,'other','selection'),{})
 def test_other_selection_cannot_supply_receipts(self):
  self.assertEqual(retained_localization_events(self.audit,'source','other'),{})
 def test_missing_context_does_not_match_missing_context(self):
  self.assertEqual(retained_localization_events({'events':self.audit['events']},None,None),{})
 def test_empty_audit_is_safe(self):
  self.assertEqual(retained_localization_events({},'source','selection'),{})

if __name__=='__main__':unittest.main()
