import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_track_selection import review_windows
class ReviewTests(unittest.TestCase):
    def plan(self,times,**kw):return review_windows([{'media_ms':t} for t in times],start_ms=0,end_ms=10000,**kw)
    def test_related_frames_share_context(self):
        r=self.plan([1000,1016,1033]);self.assertEqual(len(r),1);self.assertEqual(r[0]['start_ms'],750);self.assertEqual(r[0]['end_ms'],1283)
    def test_no_flags_lost_when_splitting(self):
        times=list(range(0,10001,16));r=self.plan(times)
        self.assertEqual([t for w in r for t in w['review_frames_ms']],times)
        self.assertTrue(all(w['end_ms']-w['start_ms']<=2500 for w in r))
    def test_separate_situations_remain_separate(self):self.assertEqual(len(self.plan([1000,5000])),2)
    def test_empty_means_no_plan_not_approval(self):self.assertEqual(self.plan([]),[])
    def test_invalid_timestamp_rejected(self):
        with self.assertRaises(ValueError):self.plan([10001])
if __name__=='__main__':unittest.main()
