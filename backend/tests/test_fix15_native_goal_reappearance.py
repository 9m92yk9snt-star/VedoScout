"""Synthetic rule/pixel tests, NOT claims that the five original actions pass."""
from copy import deepcopy
import json

import numpy as np
import pytest

import native_ball_reappearance as native
import goal_reappearance as reappearance
import fix10a_ball_proof_gate as ball_gate
import fix10a_goal_direction as direction
import fix10a_vision_providers as vision
import shot_outcome_engine as outcome_engine

W, H = 400, 300
VIDEO_SHA = "a"*64
MODEL_SHA = "b"*64


def box(cx, cy=.5):
    return {"x":cx-9/W,"y":cy-9/H,"w":18/W,"h":18/H}


def ball(ms, cx, cy=.5, proof=True):
    return {"media_ms":ms,"scene_id":"fixture-scene","state":"MEASURED",
            "box":box(cx,cy),"proof_eligible":proof,
            "time_authority":"ACTUAL_MEDIA_PTS","used_fallback":False,"cut_barrier":False}


def detected(ms, cx, cy=.5, shift=0):
    return {**ball(ms,cx,cy,proof=False),
        "class_id":32,"confidence":.85,
        "classification_source":"LOCAL_NATIVE_CLASS32_DETECTOR",
        "model_sha256":MODEL_SHA,"source":"LOCAL_NATIVE_DETECTOR",
        "camera_alignment":{"status":"MEASURED","reference_media_ms":1000,
                               "affine_to_reference":[[1.,0.,-shift],[0.,1.,0.]]}}


def canvas_with(*boxes):
    image=np.full((H,W,3),(40,125,40),dtype=np.uint8)
    for b in boxes:
        x=int(round(b["x"]*W));y=int(round(b["y"]*H))
        yy,xx=np.mgrid[:18,:18]
        disc=(xx-8.5)**2+(yy-8.5)**2 < 7.5**2
        black=((xx-8.5)**2+(yy-8.5)**2<2.8**2)|((xx<5)&(yy>10))
        patch=image[y:y+18,x:x+18]
        patch[disc]=210
        patch[disc&black]=35
    return image


def fixture(reserve=True):
    pre=[ball(900,.62),ball(950,.66),ball(1000,.70)]
    after=[detected(t,x) for t,x in zip([1667,1717,1767],[.83,.87,.91])]
    spare=[detected(t,.95,.65) for t in [1667,1717,1767]]
    frames={1000:canvas_with(pre[-1]["box"],spare[0]["box"])}
    for active,s in zip(after,spare):
        frames[active["media_ms"]]=canvas_with(active["box"],s["box"])
    candidates=[{"track_id":"moving-active","observations":after}]
    if reserve:candidates.append({"track_id":"stationary-reserve","observations":spare,
                                 "before_observation":detected(1000,.95,.65)})
    link=native.measure_native_link(pre[-1],candidates,frames,video_sha256=VIDEO_SHA)
    assert link["status"]=="VERIFIED_SAME_BALL",link
    occrows=[{"media_ms":t,"ball_visible":False,"relation":"OCCLUDED_GOAL_MOUTH",
              "occluder":"PLAYER_BODY","confidence":"high"} for t in range(1100,1601,100)]
    occ={"status":"VERIFIED_OCCLUSION","confidence":"high",
         "occlusion_start_media_ms":1100,"occlusion_end_media_ms":1600,
         "occlusion_rows":occrows,"same_ball_pre_occlusion":True,
         "visual_contradiction":False}
    post=[{"media_ms":r["media_ms"],"ball_box":deepcopy(r["box"]),
           "ball_visible":True,"relation":"BEYOND_LINE_INSIDE_MOUTH","confidence":"high"} for r in after]
    line={"p1":{"x":.80,"y":.20},"p2":{"x":.80,"y":.80}}
    times=[900,950,1000,*range(1100,1601,100),1667,1717,1767]
    geometry={"status":"VERIFIED","source":"INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "source_video_sha256":VIDEO_SHA,"response_coverage":{"status":"COMPLETED"},
        "line":line,"line_by_ms":[{"media_ms":t,"line":deepcopy(line),"confidence":"high"} for t in times],
        "field_side_status":"VERIFIED","field_side_by_ms":[
            {"media_ms":t,"point":{"x":.60,"y":.50},"confidence":"high"} for t in times],
        "occlusion_crossing_audit":occ,"reaction_support_evidence":{"status":"UNRESOLVED",
            "release_player_celebration":{"status":"NOT_OBSERVED","confidence":"high"},
            "goal_mouth_defender_response":{"status":"LATE_OR_NO_REACTION","confidence":"high"},
            "goal_mouth_defender_ball_contact":{"status":"NO_VISIBLE_CONTACT","confidence":"high"}},
        "visual_crossing_audit":{"status":"UNRESOLVED","confidence":"low",
                                "proof_ready":False,"structured_evidence":post}}
    geometry["ball_reappearance_audit"]=reappearance.build_audit(post,occ,link)
    return pre,geometry,candidates,frames


def run_full(rows, geometry, touches=None):
    strike={"media_ms":900,"strike_id":"synthetic-strike","touch_id":"synthetic-touch",
            "scene_id":"fixture-scene","player_track_id":"fixture-player",
            "status":"VERIFIED_PHYSICAL_RELEASE"}
    result=outcome_engine.reconstruct_post_strike_outcome(
        strike,rows,{"touches":touches or []},goal_geometry=geometry,role_evidence={})
    result=direction.apply_direction_gate(result,rows,geometry)
    return ball_gate.apply_ball_proof_gate(result,rows)


def test_synthetic_667ms_gap_with_reappearance_certifies_without_celebration():
    rows,g,_,_=fixture()
    result=run_full(rows,g)
    assert result["physical_outcome"]=="GOAL_PLANE_CROSSING"
    assert result["ball_proof_gate"]["status"]=="VERIFIED"
    evidence=result["goal_plane_crossing"]["evidence"][0]
    assert evidence["proof_lane"]==reappearance.LANE
    assert evidence["crossing_interval_ms"]==[1000,1667]
    assert evidence["crossing_ms"]==1667
    assert evidence["crossing_time_authority"]=="FIRST_OBSERVED_WHOLE_BALL_GOAL_SIDE"
    assert g["reaction_support_evidence"]["release_player_celebration"]["status"]=="NOT_OBSERVED"


def test_stationary_identical_reserve_is_excluded_from_native_identity():
    _,g,_,_=fixture()
    link=g["ball_reappearance_audit"]["identity_link"]
    assert link["after_track_id"]=="moving-active"
    assert [c["track_id"] for c in link["stationary_ball_controls"]]==["stationary-reserve"]
    assert link["stationary_ball_controls"][0]["motion_diameters"]==0


def test_exterior_pixels_do_not_affect_ball_appearance_identity():
    rows,g,candidates,frames=fixture()
    modified=deepcopy(frames)
    rng=np.random.default_rng(19)
    for ms,image in modified.items():
        keep=np.zeros((H,W),dtype=bool)
        boxes=[rows[-1]["box"],*[c["before_observation"]["box"] for c in candidates
                               if "before_observation" in c]] if ms==1000 else [
            next(o["box"] for o in c["observations"] if o["media_ms"]==ms) for c in candidates]
        for b in boxes:
            x0=int(np.floor(b["x"]*W));x1=int(np.ceil((b["x"]+b["w"])*W))
            y0=int(np.floor(b["y"]*H));y1=int(np.ceil((b["y"]+b["h"])*H))
            keep[y0:y1,x0:x1]=True
        image[~keep]=rng.integers(0,256,size=(int((~keep).sum()),3),dtype=np.uint8)
    actual=native.measure_native_link(rows[-1],candidates,modified,video_sha256=VIDEO_SHA)
    assert actual==g["ball_reappearance_audit"]["identity_link"]


@pytest.mark.parametrize("mutation",[
    "class","confidence","user_source","fallback","cut","scene","model","camera","camera_nan","missing_frame","too_few","bad_span"
])
def test_unqualified_after_candidates_never_become_same_ball(mutation):
    rows,_,candidates,frames=fixture(reserve=False)
    observations=candidates[0]["observations"]
    if mutation=="class":observations[0]["class_id"]=0
    elif mutation=="confidence":observations[0]["confidence"]=.139145
    elif mutation=="user_source":observations[0]["source"]="USER_ANNOTATION"
    elif mutation=="fallback":observations[0]["used_fallback"]=True
    elif mutation=="cut":observations[0]["cut_barrier"]=True
    elif mutation=="scene":observations[0]["scene_id"]="other-clip"
    elif mutation=="model":observations[0].pop("model_sha256")
    elif mutation=="camera":observations[0]["camera_alignment"]["status"]="UNRESOLVED"
    elif mutation=="camera_nan":observations[0]["camera_alignment"]["affine_to_reference"][0][0]=float("nan")
    elif mutation=="missing_frame":frames.pop(1667)
    elif mutation=="too_few":observations.pop()
    elif mutation=="bad_span":observations[2]["media_ms"]=1720
    result=native.measure_native_link(rows[-1],candidates,frames,video_sha256=VIDEO_SHA)
    assert result["status"]=="UNRESOLVED"
    assert result["proof_eligible"] is False


def test_camera_pan_does_not_turn_stationary_reserve_into_active_ball():
    before=ball(1000,.70)
    after=[detected(t,.70+shift/W,.5,shift) for t,shift in [(1667,0),(1717,20),(1767,40)]]
    frames={1000:canvas_with(before["box"]),**{r["media_ms"]:canvas_with(r["box"]) for r in after}}
    result=native.measure_native_link(before,[{"track_id":"spare","observations":after}],frames,video_sha256=VIDEO_SHA)
    assert result["status"]=="UNRESOLVED"
    assert result["stationary_ball_controls"][0]["motion_diameters"]==0


def test_two_equal_moving_balls_remain_ambiguous():
    rows,_,candidates,frames=fixture(reserve=False)
    other=[detected(t,x,.6) for t,x in zip([1667,1717,1767],[.30,.34,.38])]
    for active,alt in zip(candidates[0]["observations"],other):
        frames[active["media_ms"]]=canvas_with(active["box"],alt["box"])
    candidates.append({"track_id":"other-moving","observations":other})
    result=native.measure_native_link(rows[-1],candidates,frames,video_sha256=VIDEO_SHA)
    assert result["status"]=="UNRESOLVED"
    assert result["reason"]=="NATIVE_BALL_APPEARANCE_AMBIGUOUS"


@pytest.mark.parametrize("mutation",["absent_before","active_before","unclassified_before","moved_before"])
def test_stationary_ball_cannot_be_excluded_as_reserve_without_before_measurement(mutation):
    rows,_,candidates,frames=fixture()
    reserve=candidates[1]
    if mutation=="absent_before":reserve.pop("before_observation")
    elif mutation=="active_before":reserve["before_observation"]=detected(1000,.70)
    elif mutation=="unclassified_before":reserve["before_observation"]["class_id"]=0
    elif mutation=="moved_before":reserve["before_observation"]=detected(1000,.84,.65)
    result=native.measure_native_link(rows[-1],candidates,frames,video_sha256=VIDEO_SHA)
    assert result["status"]=="UNRESOLVED"
    assert result["reason"]=="ALTERNATIVE_BALL_PATH_COVERAGE_UNRESOLVED"


@pytest.mark.parametrize("mutation",["flat_before","flat_after","singular_camera","reflected_camera","null_candidate","null_camera"])
def test_uninformative_or_malformed_native_pixels_never_prove_identity(mutation):
    rows,_,candidates,frames=fixture(reserve=False)
    if mutation=="flat_before":frames[1000][:]=127
    elif mutation=="flat_after":frames[1667][:]=127
    elif mutation=="singular_camera":candidates[0]["observations"][0]["camera_alignment"]["affine_to_reference"]=[[0,0,1],[0,0,1]]
    elif mutation=="reflected_camera":candidates[0]["observations"][0]["camera_alignment"]["affine_to_reference"]=[[-1,0,W],[0,1,0]]
    elif mutation=="null_candidate":candidates.append(None)
    elif mutation=="null_camera":candidates[0]["observations"][0]["camera_alignment"]=None
    result=native.measure_native_link(rows[-1],candidates,frames,video_sha256=VIDEO_SHA)
    assert result["status"]=="UNRESOLVED"


@pytest.mark.parametrize("field",["response_coverage","occlusion_crossing_audit","visual_crossing_audit","reaction_support_evidence","line_by_ms","field_side_by_ms"])
@pytest.mark.parametrize("invalid",[None,"malformed",True])
def test_malformed_or_missing_goal_review_fails_closed(field,invalid):
    rows,g,_,_=fixture()
    g[field]=invalid
    result=reappearance.resolve(rows,g,900)
    assert result["status"]!="VERIFIED"


def test_missing_image_coverage_cannot_default_to_completed():
    rows,g,_,_=fixture()
    g.pop("response_coverage")
    assert reappearance.resolve(rows,g,900)["reason"]=="REAPPEARANCE_IMAGE_COVERAGE_INCOMPLETE"


@pytest.mark.parametrize("mutation",[
    "geometry","coverage","field_orientation","wrong_orientation","body","native_source",
    "identity","appearance","margin","stationary","before_box","before_time","before_proof",
    "after_count","after_box","after_not_inside","after_straddles","after_outside_mouth",
    "after_duplicate","hash","video","native_model","native_scene","native_classifier","no_crossing","keeper_contact"
])
def test_reappearance_rule_fails_closed_on_missing_or_conflicting_proof(mutation):
    rows,g,_,_=fixture()
    audit=g["ball_reappearance_audit"];link=audit["identity_link"]
    if mutation=="geometry":g["status"]="UNRESOLVED"
    elif mutation=="coverage":g["response_coverage"]["status"]="INCOMPLETE"
    elif mutation=="field_orientation":g["field_side_status"]="UNRESOLVED"
    elif mutation=="wrong_orientation":
        for r in g["field_side_by_ms"]:r["point"]["x"]=.95
    elif mutation=="body":g["occlusion_crossing_audit"]["occlusion_rows"][0]["occluder"]="OTHER"
    elif mutation=="native_source":link["source"]="USER_OBSERVATION"
    elif mutation=="identity":link["status"]="UNRESOLVED"
    elif mutation=="appearance":link["appearance_similarity"]=.80
    elif mutation=="margin":link["appearance_margin"]=.9
    elif mutation=="stationary":link["motion_diameters"]=0
    elif mutation=="before_box":link["before_box"]=box(.50)
    elif mutation=="before_time":link["before_media_ms"]=950
    elif mutation=="before_proof":rows[-1]["proof_eligible"]=False
    elif mutation=="after_count":audit["post_occlusion_rows"].pop()
    elif mutation=="after_box":audit["post_occlusion_rows"][0]["ball_box"]=box(.90)
    elif mutation in {"after_not_inside","after_straddles","after_outside_mouth"}:
        b=box(.72) if mutation=="after_not_inside" else box(.80) if mutation=="after_straddles" else box(.83,.90)
        audit["post_occlusion_rows"][0]["ball_box"]=deepcopy(b);link["after_observations"][0]["box"]=b
    elif mutation=="after_duplicate":link["after_observations"][1]["media_ms"]=1667
    elif mutation=="hash":link["after_crop_sha256"][0]="not-a-source-hash"
    elif mutation=="video":g["source_video_sha256"]="f"*64
    elif mutation=="native_model":link["after_observations"][0]["model_sha256"]="unbound"
    elif mutation=="native_scene":link["after_observations"][0]["scene_id"]="other-scene"
    elif mutation=="native_classifier":link["after_observations"][0]["classification_source"]="USER_ANNOTATION"
    elif mutation=="no_crossing":g["visual_crossing_audit"]["status"]="VERIFIED_NO_CROSSING"
    elif mutation=="keeper_contact":g["reaction_support_evidence"]["goal_mouth_defender_ball_contact"]["status"]="OBSERVED_CONTACT"
    result=reappearance.resolve(rows,g,900)
    assert result["status"]!="VERIFIED",mutation


def test_competing_verified_touch_blocks_unopposed_reappearance_rule():
    rows,g,_,_=fixture()
    touch={"status":"VERIFIED","representative_ms":1400,"player_track_id":"other"}
    result=reappearance.resolve(rows,g,900,{"touches":[touch]})
    assert result["reason"]=="REAPPEARANCE_COMPETING_VERIFIED_POST_RELEASE_TOUCH"


def test_late_keeper_and_no_outside_ball_are_support_not_goal_alone():
    rows,g,_,_=fixture()
    g["ball_reappearance_audit"]["identity_link"]=None
    g["user_observations"]={"right_foot":True,"only_one_kicked_ball":True,"no_save":True,"goal":True}
    assert run_full(rows,g)["goal_plane_crossing"]["status"]!="VERIFIED"


@pytest.mark.parametrize("mutation",["time","interval","after_list","direction","native_identity"])
def test_final_ball_gate_rechecks_reappearance_certificate(mutation):
    rows,g,_,_=fixture()
    out=run_full(rows,g)
    segment=out["goal_plane_crossing"]["evidence"][0]
    if mutation=="time":segment["crossing_ms"]-=100
    elif mutation=="interval":segment["crossing_interval_ms"]=[1000,1400]
    elif mutation=="after_list":segment["after_media_ms"]=[1667]
    elif mutation=="direction":out["direction_gate"]["status"]="UNRESOLVED"
    elif mutation=="native_identity":out["goal_geometry_evidence"]["ball_reappearance_audit"]["identity_link"]["status"]="UNRESOLVED"
    assert ball_gate.apply_ball_proof_gate(out,rows)["ball_proof_gate"]["status"]!="VERIFIED"


def test_parser_ignores_identity_certificate_in_text_response_without_calling_sdk(monkeypatch):
    _,g,_,_=fixture()
    def forbid(*a,**k):raise AssertionError("No model or network call authorised")
    monkeypatch.setattr(vision,"LlmChat",forbid)
    times=[900,950,1000,*range(1100,1601,100),1667,1717,1767]
    evidence=[{"media_ms":r["media_ms"],"ball_visible":True,"relation":"FIELD_SIDE",
               "confidence":"high","ball_box":r["box"]} for r in [ball(900,.62),ball(950,.66),ball(1000,.70)]]
    evidence+=g["occlusion_crossing_audit"]["occlusion_rows"]+g["ball_reappearance_audit"]["post_occlusion_rows"]
    for r in evidence:r["idx"]=times.index(r["media_ms"])+1
    payload={"frames":[{"idx":i+1,"visible":True,"p1":g["line"]["p1"],"p2":g["line"]["p2"],
                        "confidence":"high"} for i in range(len(times))],
             "ball_evidence":evidence,"same_ball_continuity":False,"crossing":"UNRESOLVED",
             "ball_reappearance_identity":g["ball_reappearance_audit"]["identity_link"]}
    parsed=vision.parse_goal_scene_response(json.dumps(payload),times,{"provider":"LOCAL_NATIVE_CPU"})
    assert parsed["proof_ready"] is False  # no fake continuous trajectory
    assert "ball_reappearance_audit" not in parsed
    assert "ball_reappearance_identity" not in parsed


@pytest.mark.parametrize("field", ["cut", "support_only"])
def test_cut_or_support_only_reference_cannot_certify_reappearance(field):
    rows,g,_,_=fixture()
    for row in rows:row[field]=True
    assert reappearance.resolve(rows,g,900)["status"]!="VERIFIED"


def test_foreign_scene_before_rows_cannot_certify_reappearance():
    rows,g,_,_=fixture()
    rows[-1]["scene_id"]="other-clip"
    assert reappearance.resolve(rows,g,900)["reason"]=="REAPPEARANCE_REFERENCE_SCENE_MISMATCH"


@pytest.mark.parametrize("touches", [True, {}, "not-a-list"])
def test_malformed_competing_touch_list_fails_closed(touches):
    rows,g,_,_=fixture()
    assert reappearance.resolve(rows,g,900,{"touches":touches})["status"]!="VERIFIED"
