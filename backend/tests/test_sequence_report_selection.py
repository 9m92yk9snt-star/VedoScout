import unittest, random
from collections import Counter
from copy import deepcopy
from sequence_report_selection import select_report_cards, guaranteed_graphics_event_ids

class SelectionTests(unittest.TestCase):
 def test_matches_previous_selection_and_guarantees(self):
  rng=random.Random(834)
  for _ in range(1000):
   events=[{'event_id':str(i),'canonical_event_type':rng.choice(['GOAL','ASSIST','SHOT','RUN','DUEL'])} for i in range(rng.randrange(30))]
   cards=[{'event_id':e['event_id'],'evidence_time_ms':rng.randrange(5)} for e in events]
   mentions=Counter({e['event_id']:rng.randrange(8) for e in events})
   original=deepcopy((cards,events,mentions))
   priority={e['event_id']:0 if e['canonical_event_type'] in {'GOAL','ASSIST','SHOT'} else 1 for e in events}
   expected=sorted(cards,key=lambda c:(priority[c['event_id']],-mentions[c['event_id']],c['evidence_time_ms']))[:8]
   actual=select_report_cards(cards,events,mentions)
   self.assertEqual(actual,expected)
   self.assertTrue(set(guaranteed_graphics_event_ids({'events':events})) <= {c['event_id'] for c in actual})
   self.assertEqual((cards,events,mentions),original)
 def test_priority_overflow_does_not_speculate(self):
  events=[{'event_id':str(i),'canonical_event_type':'GOAL'} for i in range(9)]
  self.assertEqual(guaranteed_graphics_event_ids({'events':events}),[])
 def test_all_eight_survive_including_low_priority(self):
  events=[{'event_id':str(i),'canonical_event_type':'RUN'} for i in range(8)]
  self.assertEqual(guaranteed_graphics_event_ids({'events':events}),[str(i) for i in range(8)])
 def test_five_priority_survive_prose_favoring_others(self):
  events=[{'event_id':str(i),'canonical_event_type':'SHOT' if i<5 else 'RUN'} for i in range(21)]
  cards=[{'event_id':e['event_id'],'evidence_time_ms':0} for e in events]
  mentions=Counter({str(i):1000 if i>=5 else 0 for i in range(21)})
  selected=select_report_cards(cards,events,mentions)
  self.assertEqual([r['event_id'] for r in selected[:5]],[str(i) for i in range(5)])
  self.assertEqual(guaranteed_graphics_event_ids({'events':events}),[str(i) for i in range(5)])

if __name__=='__main__':unittest.main()
