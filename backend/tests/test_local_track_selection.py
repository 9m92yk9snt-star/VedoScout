import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_track_selection import bind_taps

class SelectionTests(unittest.TestCase):
    def fixture(self):
        box=[20.,20.,60.,80.]
        return [{'media_ms':1000,'width':100,'height':100,'barrier':False,
                 'detection_boxes':[box],'tracks':[{'id':'0:1','box':box}]}]
    def bind(self,rows,tap=None):
        return bind_taps(rows,[tap or {'t':1,'target_point':{'x':.4,'y':.5}}],source_sha='a',expected_source_sha='a')[0]
    def test_unique_is_candidate_never_identity_authority(self):
        r=self.bind(self.fixture())
        self.assertEqual(r['status'],'CANDIDATE_SEED');self.assertFalse(r['proof_eligible'])
    def test_overlap_is_unresolved_even_if_only_one_track(self):
        rows=self.fixture();rows[0]['detection_boxes'].append([30,30,70,90])
        self.assertEqual(self.bind(rows)['reason'],'AMBIGUOUS_OVERLAP')
    def test_prediction_without_detection_is_rejected(self):
        rows=self.fixture();rows[0]['detection_boxes']=[]
        self.assertEqual(self.bind(rows)['reason'],'NO_PERSON_AT_TAP')
    def test_cut_rejects_binding(self):
        rows=self.fixture();rows[0]['barrier']=True
        self.assertEqual(self.bind(rows)['reason'],'CUT_OR_TIME_GAP')
    def test_distant_frame_is_not_reused(self):
        rows=self.fixture();rows[0]['media_ms']=1100
        self.assertEqual(self.bind(rows)['reason'],'NO_NEARBY_SOURCE_FRAME')
    def test_source_mismatch(self):
        with self.assertRaises(ValueError):bind_taps([],[],source_sha='a',expected_source_sha='b')
    def test_nonfinite_point(self):
        self.assertEqual(self.bind(self.fixture(),{'t':1,'target_point':{'x':float('nan'),'y':.5}})['reason'],'INVALID_TAP')

if __name__=='__main__':unittest.main()
