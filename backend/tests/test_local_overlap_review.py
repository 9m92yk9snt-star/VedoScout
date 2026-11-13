import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_track_selection import overlap_review_frames
class OverlapTests(unittest.TestCase):
    def check(self, other, ms=100):
        box=[0,0,10,10]
        return overlap_review_frames([{'media_ms':ms,'tracks':[{'id':'a','box':box}],
            'detection_boxes':[box,other]}],{'start_ms':100,'end_ms':200,'track_id':'a'})
    def test_overlap_flagged_not_approved(self):
        r=self.check([5,0,15,10]);self.assertEqual(len(r),1);self.assertFalse(r[0]['proof_eligible'])
    def test_separate_boxes(self):self.assertEqual(self.check([20,0,30,10]),[])
    def test_outside_component(self):self.assertEqual(self.check([5,0,15,10],300),[])
    def test_zero_area(self):self.assertEqual(self.check([5,0,5,10]),[])
if __name__=='__main__':unittest.main()
