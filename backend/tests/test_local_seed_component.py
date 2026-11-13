import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_track_selection import seed_component

def row(ms, visible=True, barrier=False):
    b=[1,2,3,4]
    return {'media_ms':ms,'barrier':barrier,'tracks':[{'id':'0:7','box':b}] if visible else [],'detection_boxes':[b] if visible else []}

class ComponentTests(unittest.TestCase):
    seed={'status':'CANDIDATE_SEED','track_id':'0:7','media_ms':200}
    def test_missing_frame_splits_same_id(self):
        r=seed_component([row(100),row(116,False),row(183),row(200),row(216)],self.seed)
        self.assertEqual((r['start_ms'],r['end_ms'],r['observed_frames']),(183,216,3))
        self.assertFalse(r['identity_verified'])
    def test_cut_cannot_join(self):
        r=seed_component([row(100),row(183,barrier=True),row(200)],self.seed)
        self.assertEqual(r['start_ms'],200)
    def test_prediction_not_observation(self):
        r=row(200);r['detection_boxes']=[]
        self.assertIsNone(seed_component([r],self.seed))
    def test_duplicate_timestamp_rejected(self):
        with self.assertRaises(ValueError):seed_component([row(200),row(200)],self.seed)

if __name__=='__main__':unittest.main()
