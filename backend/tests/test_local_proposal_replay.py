import sys,json,hashlib,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_proposal_replay import replay
class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.video=Path(self.tmp.name)/'video';self.video.write_bytes(b'source')
        self.sha=hashlib.sha256(b'source').hexdigest();self.path=Path(self.tmp.name)/'receipt'
        self.data={'source_video_sha256':self.sha,'scope':'LOCAL_PROPOSALS_ONLY_NOT_PLAYER_IDENTITY_OR_REPORT_PARITY',
                   'frames':1,'window_ms':[0,1000],'rows':[{'media_ms':500,'width':100,'height':100,'tracks':[],'detection_boxes':[]}]}
        self.selection={'source_video_sha256':self.sha,'taps':[{'t':.5,'target_point':{'x':.5,'y':.5}}]}
    def run_replay(self):
        self.path.write_text(json.dumps(self.data));sha=hashlib.sha256(self.path.read_bytes()).hexdigest()
        return replay(self.path,sha,self.video,self.selection)
    def test_replays_without_granting_identity(self):
        r=self.run_replay();self.assertEqual(r['new_detector_calls'],0);self.assertFalse(r['proof_eligible']);self.assertEqual(r['tap_candidates'][0]['status'],'UNRESOLVED')
    def test_changed_receipt(self):
        self.run_replay()
        with self.assertRaisesRegex(ValueError,'RECEIPT_CHANGED'):replay(self.path,'wrong',self.video,self.selection)
    def test_changed_source(self):
        self.video.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError,'SOURCE_MISMATCH'):self.run_replay()
    def test_incomplete_rows(self):
        self.data['frames']=2
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):self.run_replay()
    def test_timestamp_outside_window(self):
        self.data['rows'][0]['media_ms']=2000
        with self.assertRaisesRegex(ValueError,'TIMESTAMPS'):self.run_replay()
if __name__=='__main__':unittest.main()
