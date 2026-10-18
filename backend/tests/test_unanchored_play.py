"""Navigation/identity policy and preservation of the earlier actual assist reply."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
from scripts.probe_unanchored_play import temporal_references, source_question, contact_focus, geometry_cluster, limb_region, comparison_panels

ROOT=Path(__file__).resolve().parents[2]


def refs():
    return [{'reference_id':str(ms),'media_ms':ms} for ms in (100,1000,1400,3000,3300,4100)]


def test_original_in_play_selection_takes_precedence_without_inventing_a_mark():
    original=refs();unchanged=deepcopy(original)
    assert temporal_references(original,1300,2000)==[original[2]]
    assert original==unchanged


def test_unanchored_play_uses_nearest_before_after_and_only_their_temporal_neighbours():
    original=refs()
    assert temporal_references(original,1800,2600)==original[1:5]


@pytest.mark.parametrize('bounds',[(0,50),(4200,4500)])
def test_missing_bracketing_identity_cannot_silently_become_a_local_selection(bounds):
    with pytest.raises(ValueError,match='BRACKETING_ORIGINAL_SELECTIONS_REQUIRED'):
        temporal_references(refs(),*bounds)


def saved_gap():
    return p.read_json(ROOT/'docs/examples/native-unresolved-finisher-receipt.json')


def rehash(saved):
    saved['receipt']['response_sha256']=hashlib.sha256(saved['receipt']['raw_response'].encode()).hexdigest()


def test_actual_navigation_extends_detail_back_to_the_observed_reception():
    saved=saved_gap();unchanged=deepcopy(saved)
    question=source_question(saved)
    assert question['detail_start_ms']==48881 and question['detail_end_ms']==51465
    assert question['start_ms']==47265 and question['end_ms']==53014
    assert saved==unchanged


def test_modified_old_response_cannot_choose_new_source_windows():
    saved=saved_gap();saved['receipt']['raw_response']+=' '
    with pytest.raises(ValueError,match='INVALID_PRIOR_OBSERVATION'):
        source_question(saved)


@pytest.mark.parametrize('frame',['unknown','s000047000','s000053999'])
def test_invalid_or_out_of_play_observed_build_up_cannot_direct_source_sampling(frame):
    saved=saved_gap();raw=json.loads(saved['receipt']['raw_response'])
    raw['selected_player_actions'][0]['before_frame']=frame
    saved['receipt']['raw_response']=json.dumps(raw);rehash(saved)
    with pytest.raises(ValueError,match='SOURCE_CITED_BUILDUP_REQUIRED|BUILDUP_OUTSIDE_SOURCE_PLAY'):
        source_question(saved)


def test_unbounded_detail_interval_is_rejected_before_any_model_call():
    saved=saved_gap();raw=json.loads(saved['receipt']['raw_response'])
    raw['selected_player_actions'][0]['before_frame']='s000047300'
    saved['receipt']['raw_response']=json.dumps(raw);rehash(saved)
    with pytest.raises(ValueError,match='CONTINUOUS_DETAIL_BUDGET_EXCEEDED'):
        source_question(saved)


def test_actual_unapproved_reply_only_directs_focus_not_the_desired_actor_or_outcome():
    saved=p.read_json(ROOT/'docs/examples/native-unanchored-play-receipt.json')
    focus=contact_focus(saved,saved['source_video_sha256'])
    assert focus=={'start_ms':50281,'end_ms':50798,'navigation_response_sha256':saved['response_sha256']}
    raw=json.loads(saved['raw_response']);context=saved['result']
    from scripts.probe_continuous_pass import resolve_assist
    assert resolve_assist(raw,context,saved)==context['automatic_approval']
    assert context['automatic_approval']['target_events']==[]


def test_person_geometry_keeps_the_largest_cluster_and_records_source_coordinates():
    samples=[{'boxes_xywh_conf':[[.25,.5,.1,.12,.9],[.36,.5,.1,.12,.9],[.85,.5,.06,.1,.9]]}]
    box=geometry_cluster(samples,1080,1920,[0,700,1080,1300])
    assert box[0] <= .25*1080 and box[2] >= .46*1080 and box[2] < .8*1080
    # Top-left detector convention: preserve heads AND the bottom of the feet.
    assert box[1] <= .5*1920 and box[3] >= .62*1920
    assert 700 <= box[1] < box[3] <= 1300
    with pytest.raises(ValueError,match='NO_SEPARATE_PERSON_CLUSTER'):
        geometry_cluster([{'boxes_xywh_conf':[[.5,.5,.1,.1,.9]]}],1080,1920,[0,700,1080,1300])


def test_lower_body_view_records_human_navigation_without_encoding_an_action_or_side():
    samples=[{'media_ms':5000,'boxes_xywh_conf':[[.25,.5,.1,.12,.9],[.36,.5,.1,.12,.9]]}]
    result=limb_region(5000,{'detail_start_ms':4000,'detail_end_ms':6000},samples,1080,1920,[0,700,1080,1300])
    assert result['start_ms']==4650 and result['end_ms']==5350
    assert result['source_crop_box'][3]>=.62*1920
    assert result['source_crop_box'][1]>result['body_source_crop_box'][1]
    assert result['navigation_origin']=='USER_SUPPLIED_TIMESTAMP_ONLY'
    assert result['expected_action_or_side_supplied'] is False


@pytest.mark.parametrize('centre',[None,True,4000,6000])
def test_limb_navigation_outside_prepared_detail_stops_before_any_model_call(centre):
    with pytest.raises(ValueError,match='INTEGER_SOURCE_NAVIGATION_REQUIRED|LIMB_WINDOW_OUTSIDE_SOURCE_DETAIL'):
        limb_region(centre,{'detail_start_ms':4000,'detail_end_ms':6000},[],1080,1920,[0,700,1080,1300])


def test_actual_focused_reply_does_not_turn_a_hidden_actor_into_an_assist_or_selected_goal():
    from scripts.probe_continuous_pass import resolve_assist
    saved=p.read_json(ROOT/'docs/examples/native-contact-separation-receipt.json')
    raw=json.loads(saved['raw_response']);context=saved['result']
    result=resolve_assist(raw,context,saved)
    assert result==context['automatic_approval']
    assert result['status']=='UNRESOLVED' and result['counts']=={} and result['target_events']==[]
    assert raw['event_mapping']['finishing_actor_unique'] is None
    assert raw['link_assessment']['receiver_finishing_action']['status']=='UNCERTAIN'
    assert context['contact_focus']['source_crop_box'][3] > 1100  # feet remain in the focused source view


def test_comparison_panel_preserves_source_arrays_and_records_ordered_real_instants(tmp_path):
    import numpy as np
    frames=[(ms,np.full((12,24,3),ms,dtype=np.uint8)) for ms in range(8)]
    original=[pixels.copy() for _,pixels in frames]
    rows,audit=comparison_panels(frames,{'start_ms':0,'end_ms':7,'source_crop_box':[0,0,24,12]},tmp_path,85)
    assert len(audit)==1 and audit[0]['source_instants']==[0,2,4,6]
    assert audit[0]['native_pixels_not_resized'] and audit[0]['labels_outside_source_crop']
    assert rows[1]['sha256']==audit[0]['sha256']
    assert all(np.array_equal(before,after) for before,(_,after) in zip(original,frames))


def test_actual_limb_review_supports_distinct_finisher_but_cannot_invent_the_selected_release():
    from scripts.probe_continuous_pass import resolve_assist
    saved=p.read_json(ROOT/'docs/examples/native-limb-release-receipt.json');context=saved['result']
    raw=json.loads(saved['raw_response'])
    assert resolve_assist(raw,context,saved)==context['automatic_approval']
    assert raw['link_assessment']['receiver_finishing_action']['status']=='SUPPORTED'
    assert raw['contact_ownership_review']['status']=='UNCERTAIN'
    assert context['target_events']==[] and context['counts']=={}


def test_previously_documented_later_assist_still_resolves_from_its_unchanged_actual_reply():
    saved=p.read_json(ROOT/'docs/examples/gpt6-native-contact-receipt.json');receipt=saved['receipt']
    assert receipt['origin']=='LIVE_MODEL_REQUEST' and receipt['status']=='COMPLETED'
    assert hashlib.sha256(receipt['raw_response'].encode()).hexdigest()==receipt['response_sha256']
    raw=p.parse_response(receipt['raw_response'])
    # Structural regression using the immutable reply's source-ID time convention.
    # This checks attribution logic, not source-image coverage or a fresh model read.
    ids=sorted(set(re.findall(r's\d{9}',receipt['raw_response'])))
    reference_ids=sorted({rid for play in raw['plays'] for person in play['people'] for rid in person['reference_ids']})
    manifest={'source_video_sha256':saved['source_video_sha256'],
        'frames':[{'frame_id':fid,'media_ms':int(fid[1:])} for fid in ids],
        'identity_profile':{'canonical_reference_ids':reference_ids}}
    packet={'packet_id':receipt['packet_id'],'frame_ids':ids,'reference_ids':reference_ids}
    result=p.reconcile([p.resolve_response(raw,manifest,packet,
        {k:receipt[k] for k in ('packet_id','origin','payload_sha256','response_sha256')})])
    assert result['counts']=={'ASSIST':1} and not result['questions']
    event=result['target_events'][0]
    assert event['actor']!=event['receiver']==event['finisher']
    assert event['reason']=='VISIBLE_DIRECT_ASSIST' and not event['model_requested_clarification']
