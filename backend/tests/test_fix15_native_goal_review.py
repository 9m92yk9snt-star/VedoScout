"""Native provider integration and competing-ball tests using fixture pixels.

These tests do not assert acceptance of an original football-video event.
"""
from copy import deepcopy
import hashlib

import numpy as np
import pytest

import native_goal_review as review_pixels
import fix10a_vision_providers as vision
import dense_track_refinement as dense
from test_fix15_native_goal_reappearance import fixture, detected, VIDEO_SHA, MODEL_SHA


def inputs():
    pre,g,candidates,images=fixture()
    review={"response_coverage":{"status":"COMPLETED"},
        "occlusion_crossing_audit":deepcopy(g["occlusion_crossing_audit"]),
        "ball_evidence":deepcopy(g["ball_reappearance_audit"]["post_occlusion_rows"])}
    by_time={1000:[{"box":pre[-1]["box"],"confidence":.85},
                   {"box":candidates[1]["before_observation"]["box"],"confidence":.85}]}
    for ms in (1667,1717,1767):
        by_time[ms]=[{"box":r["box"],"confidence":r["confidence"]}
                     for c in candidates for r in c["observations"] if r["media_ms"]==ms]
    return pre,g,review,images,by_time


def measure(review,pre,images,by_time,model_sha=MODEL_SHA,camera=None):
    def detector(im,proposal):
        ms=next(ms for ms,image in images.items() if image is im)
        return [],deepcopy(by_time[ms])
    if camera is None:
        camera=lambda *_: (np.array([[1.,0.,0.],[0.,1.,0.]]),"fixture-background")
    return review_pixels.measure_review(review,pre[-1],images,video_sha256=VIDEO_SHA,
        model_sha256=model_sha,detect_frame=detector,camera_estimator=camera)


def test_review_identity_is_built_from_native_pixels_and_reserve_before_after():
    pre,g,review,images,by_time=inputs()
    review["ball_reappearance_identity"]={"status":"VERIFIED_SAME_BALL","made_up":True}
    before=deepcopy(review)
    audit=measure(review,pre,images,by_time)
    assert audit["identity_link"]["status"]=="VERIFIED_SAME_BALL"
    assert "made_up" not in audit["identity_link"]
    assert audit["native_sampling_audit"]["reader_identity_ignored"] is True
    assert len(audit["identity_link"]["stationary_ball_controls"])==1
    assert audit["identity_link"]["before_crop_sha256"]==g["ball_reappearance_audit"]["identity_link"]["before_crop_sha256"]
    assert review==before


@pytest.mark.parametrize("mutation", ["weak_ball","missing_pixels","after_gap","no_camera",
    "invalid_camera","missing_model_hash","partial_reader","no_body_occlusion",
    "reserve_missing_before","reserve_missing_after","native_box_disagrees"])
def test_reader_cannot_promote_missing_native_evidence(mutation):
    pre,g,review,images,by_time=inputs()
    camera=None;model_sha=MODEL_SHA
    if mutation=="weak_ball":by_time[1667][0]["confidence"]=.139145
    elif mutation=="missing_pixels":images.pop(1717)
    elif mutation=="after_gap":review["ball_evidence"][1]["media_ms"]=1720
    elif mutation=="no_camera":camera=lambda *_: (None,"features")
    elif mutation=="invalid_camera":camera=lambda *_: (np.zeros((2,3)),"invalid")
    elif mutation=="missing_model_hash":model_sha=None
    elif mutation=="partial_reader":review["response_coverage"]["status"]="PARTIAL_RESPONSE"
    elif mutation=="no_body_occlusion":review["occlusion_crossing_audit"]["status"]="UNRESOLVED"
    elif mutation=="reserve_missing_before":by_time[1000].pop()
    elif mutation=="reserve_missing_after":by_time[1717].pop()
    elif mutation=="native_box_disagrees":by_time[1667][0]["box"]=detected(1667,.60)["box"]
    audit=measure(review,pre,images,by_time,model_sha,camera)
    assert audit["status"]=="UNRESOLVED"
    assert audit["identity_link"]["proof_eligible"] is False


def test_provider_automatically_measures_reappearance_after_reader_returns(monkeypatch,tmp_path):
    pre,g,review,images,by_time=inputs()
    for r in pre:
        r.update(confidence=.85,provenance="RELEASE_ANCHORED_NATIVE_CAMERA_MOTION",
                 frame_dimensions={"width":400,"height":300,"source":"DECODED_NATIVE_PIXELS"})
    anchor={**deepcopy(pre[0]),"remote_spare_ball_used":False}
    strike={"media_ms":900,"scene_id":"fixture-scene","status":"VERIFIED_PHYSICAL_RELEASE",
            "proof_eligible":True,"active_ball_anchor":anchor,
            "_goal_review_ball_path":{"source":"VERIFIED_RELEASE_ANCHOR","seed_ms":900,
                "rows":pre,"contact_binding":{"status":"VERIFIED",
                    "reason":"MEASURED_CONTACT_TO_EXACT_RELEASE_ANCHOR","contact_ms":900,"seed_ms":900}}}
    video=tmp_path/'fixture-video';video.write_bytes(b'original-fixture-source')
    provider=vision.build_shadow_providers('fixture-no-sdk','native-review',str(video))
    provider._native_goal_detector=type('FixtureDetector',(),{'ok':True,'model_sha256':MODEL_SHA})()
    # Fake decoding returns original arrays, identified by ACTUAL PTS. No SDK,
    # network or production video is used in this integration fixture.
    images[900]=images[1000].copy();images[950]=images[1000].copy()
    times=sorted(images)
    monkeypatch.setattr(vision,'_goal_review_times',lambda *a,**k:times)
    monkeypatch.setattr(vision,'_read_frames',lambda *a: {ms:(ms,im) for ms,im in images.items()})
    review.update(geometry_status='VERIFIED',frames=[{'media_ms':ms,'line':deepcopy(g['line']),
                  'confidence':'high'} for ms in times],crossing='UNRESOLVED')
    review['ball_reappearance_audit']={'identity_link':{'status':'VERIFIED_SAME_BALL','forged':True}}
    monkeypatch.setattr(vision.support_vision_runner,'run_support_vision',lambda *a,**k:[deepcopy(review)])

    def detect(_detector,im):
        ms=next(ms for ms,image in images.items() if image is im)
        return [],deepcopy(by_time[ms])
    monkeypatch.setattr(dense,'_detect_dense_people_and_ball',detect)
    monkeypatch.setattr(vision,'_native_ball_roi',lambda *a:([],None))
    monkeypatch.setattr(dense,'_default_camera_estimator',lambda *_:
                        (np.array([[1.,0.,0.],[0.,1.,0.]]),'fixture-background'))
    result=provider.goal_geometry_provider({'dense_window_id':'fixture','start_ms':800,'end_ms':2800},strike)
    audit=result['ball_reappearance_audit']
    assert audit['identity_link']['status']=='VERIFIED_SAME_BALL',audit
    assert 'forged' not in audit['identity_link']
    assert audit['identity_link']['source_video_sha256']==hashlib.sha256(video.read_bytes()).hexdigest()
    assert provider.goal_calls==1
    assert audit['post_occlusion_rows'][0]['box_source']=='INDEPENDENT_NATIVE_CLASS32_DETECTION'


def test_binding_another_video_invalidates_goal_and_pixel_fingerprint_caches():
    provider=vision.build_shadow_providers(None,'fixture','first.mp4')
    provider._goal_cache['old']={'status':'VERIFIED'}
    provider._native_video_fingerprint=(('old',1,1),'a'*64)
    provider.bind_video_path('second.mp4')
    assert provider._goal_cache=={}
    assert provider._native_video_fingerprint is None
