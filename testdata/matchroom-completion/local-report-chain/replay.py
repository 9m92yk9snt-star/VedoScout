import sys,json,zipfile,copy,time,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('VedoScout/backend').resolve()))
from match_room import presentation
from match_room_reviewed_direction import attach_reviewed_direction
import cv2
cv2.setNumThreads(2)
Path('local_chain').mkdir(exist_ok=True)
z=zipfile.ZipFile(next(Path('source_inputs').glob('*.zip')));canonical=json.loads(z.read('canonical.json'));events=canonical['canonical_events']['events'];print(type(events).__name__,flush=True)
e=next(e for e in events if e['event_id']=='47ad617d2ba76a4683cd');original=copy.deepcopy(e)
decision=json.load(open('VedoScout/testdata/matchroom-completion/orman1000-third-assist-owner-accepted-2026-11-07.json'))['decision'];assert e['source_video_sha256']==decision['source_video_sha256']
review=json.load(open('VedoScout/testdata/matchroom-completion/local-report-chain/review_input.json'))
video=next(Path('source_audit/video').glob('*.mp4'))
old={**e,'reviewed_direction_review':review};oldroom=presentation(old);attach_reviewed_direction(oldroom,old,video,time.monotonic()+20);assert oldroom['reviewed_direction_diagnostics']['status']=='REJECTED'
# Local replay applies only the separately retained accepted assertion, not new perception.
a=decision['accepted_assertion'];accepted={**copy.deepcopy(e),'canonical_action_type':a['action'],'canonical_event_type':a['event_type'],'canonical_outcome':a['outcome'],'contact_ms':a['contact_ms'],'reviewed_direction_review':review};before=copy.deepcopy(accepted)
room=presentation(accepted);t=time.monotonic();attach_reviewed_direction(room,accepted,video,time.monotonic()+20)
assert accepted==before and e==original
assert len(room['reviewed_direction']['samples'])==30
assert room['reviewed_direction']['playback_status']=='PENDING'
Path('local_chain/room.json').write_text(json.dumps(room))
result={'status':'LOCAL_REPLAY_PASS','original_zip_event_rejected':True,'accepted_assertion_source':'retained owner-adjudicated decision, not a new model finding','event_unchanged_by_graphics':True,'source_sha256':e['source_video_sha256'],'samples':30,'elapsed_seconds':time.monotonic()-t,'llm_calls':0,'deployed':False,'playback_status':'PENDING','scope':'presentation plus same attachment helper now called by runtime; full render_assets not run; no automatic producer of reviewed_direction_review yet'}
Path('local_chain/result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
