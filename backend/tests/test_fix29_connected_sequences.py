"""Production continuity and sequence searches, without network/model calls."""
from copy import deepcopy

import pytest

import dense_identity_continuity as identity
import attack_sequence_search as attack
import sequence_observation_context as context
import action_evidence_review as inspection
import evidence_feedback as feedback
import goal_review_scheduler as scheduler
import goal_review_sampling as sampling
import fix10a_goal_direction as direction
import fix10a_vision_providers as vision
import test_fix10b_reconciliation as events
import test_fix13_cross_window_evidence as overlap
import test_fix13_evidence_feedback as feedback_fixture
import json
import unified_identity_authority as authority
import jersey_consensus
import shot_outcome_engine as outcomes
import video_timebase
import cv2


def frame(ms, *, seed=False, track="p", scene="scene"):
    return {"media_ms": ms, "scene_id": scene, "time_authority": "ACTUAL_MEDIA_PTS",
            "players": [{"local_track_id": track, "association_state": "VERIFIED_LOCAL",
                         "confidence": .9, "box": {"x": .3, "y": .4, "w": .1, "h": .2},
                         "jersey_crop_quality": {"source": "NATIVE_TORSO_PIXELS", "isolated": True}}],
            "global_target": {"status": "VERIFIED", "proof_eligible": True, "reason": "OK_EXACT",
                              "local_track_id": track} if seed else
                             {"status": "UNRESOLVED", "proof_eligible": False, "reason": "TARGET_GAP"}}


def series(seed_ms=0):
    return [frame(ms, seed=ms == seed_ms) for ms in range(0, 4001, 20)]


@pytest.mark.parametrize("seed_ms", [0, 4000])
def test_isolated_measured_body_retains_identity_beyond_old_clock_limit_in_both_directions(seed_ms):
    rows = series(seed_ms); original = deepcopy(rows)
    output = identity.apply(rows)["frames"]
    assert all(f["global_target"]["proof_eligible"] for f in output)
    far = output[-1] if seed_ms == 0 else output[0]
    assert far["global_target"]["reason"] == "MEASURED_VISIBLE_TRACK_CONTINUITY"
    assert far["global_target"]["continuity_evidence"]["seed_ms"] == seed_ms
    assert rows == original


@pytest.mark.parametrize("failure", ["cut", "scene", "fallback", "duplicate", "crossing", "hypothesis", "conflict", "missing_body"])
def test_long_identity_does_not_cross_a_broken_or_competing_body_track(failure):
    rows = series(); pivot = rows[80]
    if failure == "cut": pivot["cut"] = True
    elif failure == "scene": pivot["scene_id"] = "foreign"
    elif failure == "fallback": pivot["used_fallback"] = True
    elif failure == "missing_body": pivot["players"] = []
    elif failure == "duplicate": pivot["players"].append(deepcopy(pivot["players"][0]))
    elif failure == "crossing": pivot["players"].append({**deepcopy(pivot["players"][0]), "local_track_id": "other"})
    elif failure == "hypothesis": pivot["players"][0]["association_state"] = "HYPOTHESES"
    elif failure == "conflict": pivot["global_target"]["reason"] = "SOURCE_CONFLICT"
    output = identity.apply(rows)["frames"]
    assert not output[-1]["global_target"]["proof_eligible"]


def test_a_new_independent_seed_automatically_restarts_identity_after_a_cut():
    rows = series(); rows[75]["cut"] = True
    rows[100] = frame(2000, seed=True)
    output = identity.apply(rows)["frames"]
    assert not output[75]["global_target"]["proof_eligible"]
    assert output[-1]["global_target"]["proof_eligible"]
    assert output[-1]["global_target"]["continuity_evidence"]["seed_ms"] == 2000


def test_unmeasured_geometry_keeps_the_old_short_bridge_without_extending_it():
    rows = series()
    for f in rows: f["players"][0].pop("jersey_crop_quality")
    output = identity.apply(rows)["frames"]
    assert output[60]["global_target"]["proof_eligible"]
    assert not output[61]["global_target"]["proof_eligible"]


def attack_case():
    target = events.strike(1000, "p", target=True)
    target["active_ball_anchor"] = {"media_ms": 1000, "box": {"x": .3, "y": .58, "w": .01, "h": .01},
                                    "proof_eligible": True, "state": "MEASURED", "time_authority": "ACTUAL_MEDIA_PTS"}
    scorer = events.strike(4200, "receiver")
    trace = events.trace([events.touch(1000, "p", target=True), events.touch(3000, "receiver"),
                          events.touch(4200, "receiver")], [target, scorer],
                         [events.outcome(target, goal=False), events.outcome(scorer, crossing_ms=5400)])
    trace.update(trace_id="w", source_video={"sha256": "video"})
    trace["window"] = {"dense_window_id": "w", "scene_id": "scene_007", "start_ms": 0, "end_ms": 7000}
    trace["decoded_frames"] = [frame(ms, scene="scene_007") for ms in range(0, 7001, 20)]
    return trace


def test_observed_terminal_opens_a_backward_contact_search_and_keeps_forward_receiver():
    trace = attack_case(); original = deepcopy(trace)
    plan = attack.build(trace)
    root = next(e for e in plan["episodes"] if e["contact_ms"] == 4200)
    assert root["terminal_observed_ms"] == 5400 and root["end_ms"] == 5800
    reverse = next(q for q in plan["questions"] if q["reason"] == "BACKTRACK_FROM_OBSERVED_TERMINAL")
    assert reverse["media_ms"] == 1000 and reverse["question"] == "CONTACT"
    assert any(q["question"] == "RECEIVER" and q["media_ms"] == 3000 for q in plan["questions"])
    assert all(q["canonical_authority"] is False for q in plan["questions"])
    assert trace == original


def test_attack_context_extends_past_old_goal_clock_without_moving_contact_time():
    trace = attack_case(); strike = trace["strike_evidence"][0]
    job = {"window": trace["window"], "strike": strike, "touch_graph": trace["touch_graph"],
           "review": {"lane": "VERIFIED_CHAIN"}, "sequence_context": context.build(trace["window"], trace["decoded_frames"], trace=trace),
           "attack_review_context": attack.review_context(trace, strike)}
    scheduled = scheduler.ordered_requests([job], {})[0]
    native = sampling.provider_strike(scheduled)
    assert native["media_ms"] == 1000 and native["_review_context"]["end_ms"] == 7000
    times = vision._goal_review_times(1000, 7000, 12, start_ms=850, include_terminal=True)
    assert len(times) == 12 and {1000, 1050, 1100, 7000} <= set(times)
    seen = []
    provider = direction.GoalDirectionProvider(lambda w, s: seen.append((w, s)) or {}, "", "fixture", "unused")
    provider(scheduled["window"], native)
    assert seen[0][0]["end_ms"] == 7000 and seen[0][1]["media_ms"] == 1000


@pytest.mark.parametrize("failure", ["cut", "scene", "gap", "fallback"])
def test_long_attack_context_stops_at_actual_source_barriers(failure):
    trace = attack_case(); f = trace["decoded_frames"][100]
    if failure == "cut": f["cut"] = True
    elif failure == "scene": f["scene_id"] = "foreign"
    elif failure == "fallback": f["used_fallback"] = True
    elif failure == "gap": trace["decoded_frames"] = [r for r in trace["decoded_frames"] if not 2000 <= r["media_ms"] <= 2120]
    bounds = attack.review_context(trace, trace["strike_evidence"][0])
    assert bounds["end_ms"] == 1980


def test_model_hypotheses_use_only_supplied_actual_images_and_body_labels():
    parsed = {"hypotheses": [{"kind": "PASS_CHAIN", "steps": [
        {"idx": 1, "body_id": "body_1", "observation": "RELEASE"},
        {"idx": 2, "body_id": "invented", "observation": "RECEIVE"},
        {"idx": 99, "observation": "TURN"}]}],
        "review_requests": [{"idx": 1, "question": "RECEIVER", "direction": "AFTER"}]}
    result = context.parse_reasoning(parsed, [1000, 1200], [{"media_ms": 1000, "bodies": [{"body_id": "body_1"}]}])
    assert result["hypotheses"][0]["steps"] == [{"media_ms": 1000, "body_id": "body_1", "observation": "RELEASE"}]
    assert result["review_requests"][0]["media_ms"] == 1000
    assert not result["canonical_authority"] and "contacts" not in result


@pytest.mark.parametrize("parsed", [None, [], {"hypotheses": {}}, {"hypotheses": [{"kind": []}]},
    {"review_requests": {}}, {"review_requests": [{"question": []}]}])
def test_malformed_optional_reasoning_does_not_break_pixel_evidence(parsed):
    assert context.parse_reasoning(parsed, [1000], [])["hypotheses"] == []


def test_goal_explanations_are_bound_to_images_and_do_not_certify_a_crossing():
    result = context.outcome_explanations({"outcome_explanations": [{"hypothesis": "GOAL_AFTER_OCCLUSION",
        "supporting_indices": [1, 2, True, 99], "contradicting_indices": [2]}]}, [1000, 1200])
    assert result[0]["supporting_media_ms"] == [1000, 1200]
    assert result[0]["status"] == "EXPLANATION_ONLY" and result[0]["canonical_authority"] is False


def test_native_focus_keeps_the_exact_focus_endpoints_and_same_image_budget():
    rows = series()
    for f in rows:
        f["frame_dimensions"] = {"width": 640, "height": 360, "source": "DECODED_NATIVE_PIXELS"}
        f["ball_candidates"] = [{"box": {"x": .345, "y": .595, "w": .01, "h": .01}, "confidence": .9}]
    job = {"scene_id": "scene", "start_ms": 0, "end_ms": 4000, "center_ms": 2000}
    plan = context.sampling_plan(job, rows)
    assert len(plan["media_ms"]) == 12 and {0, 4000} <= set(plan["media_ms"])
    focus = plan["focuses"][0]["media_ms"]
    assert focus in plan["media_ms"] and sum(abs(t-focus) <= 100 for t in plan["media_ms"]) >= 4


def test_body_labels_remain_stable_when_players_exchange_image_order():
    a, b = frame(1000), frame(1200)
    for f, x in [(a, .7), (b, .05)]:
        other = deepcopy(f["players"][0]); other["local_track_id"] = "other"; other["box"]["x"] = x
        f["players"].append(other)
    labels = context.labels([a, b])
    assert [{r["local_track_id"]: r["body_id"] for r in inspection.measured_body_candidates(f, body_labels=labels)}
            for f in [a, b]][0] == {r["local_track_id"]: r["body_id"] for r in inspection.measured_body_candidates(b, body_labels=labels)}


def test_compact_context_does_not_repeat_raw_reader_responses_or_expected_number():
    trace = attack_case(); trace["attack_search_plan"] = attack.build(trace)
    trace["action_inspections"] = [{"raw_response": "private" * 1000, "expected_jersey_number": "15"}]
    trace["role_evidence"] = {"keeper": {"status": "VERIFIED", "role": "GOALKEEPER", "raw_response": "private"}}
    packet = context.build(trace["window"], trace["decoded_frames"], trace=trace)
    view = context.reader_view(packet)
    assert len(json.dumps(view)) < len(json.dumps(packet))
    assert "private" not in json.dumps(view) and "expected_jersey_number" not in json.dumps(view)
    assert view["contacts"] and view["searches"]["questions"]


def test_changed_measured_context_reopens_goal_cache_but_identical_context_reuses_it():
    calls = []; provider = direction.GoalDirectionProvider(lambda *_: calls.append(True) or {}, "", "fixture", "unused")
    strike = {"media_ms": 1000, "scene_id": "s", "_review_episode_id": "same", "_sequence_context": {"fingerprint": "first"}}
    window = {"start_ms": 0, "end_ms": 4000}
    provider(window, strike); provider(window, deepcopy(strike))
    assert len(calls) == 1
    provider(window, {**strike, "_sequence_context": {"fingerprint": "new_measurement"}})
    assert len(calls) == 2


def test_a_model_question_uses_the_existing_round_and_budget_only():
    trace = feedback_fixture.trace()
    trace["action_inspections"][0]["sequence_reasoning"] = context.parse_reasoning({"review_requests": [
        {"idx": 1, "question": "RECEIVER", "direction": "AFTER"}]}, [1500], [])
    plan = feedback.build_plan([trace], budget=1)
    assert plan["selected"] == 1 and plan["jobs"][0]["center_ms"] == 1750
    trace["evidence_feedback"] = {"round": 1}
    assert not feedback.build_plan([trace])["jobs"]


def test_richer_observed_terminal_chain_is_prioritized_without_expected_action_labels():
    trace = attack_case(); trace.update(action_inspections=[], contacts={"accepted": [], "unresolved": []})
    plan = feedback.build_plan([trace], budget=1)
    chosen = next(j for j in plan["jobs"] if j["selected"])
    assert chosen["reason"] == "CHAIN_SEARCH_CONTACT" and chosen["center_ms"] == 1000
    assert plan["budget"] == 1 and plan["rounds"] == 1
    assert "expected" not in json.dumps(chosen) and "ASSIST" not in json.dumps(chosen)


def test_an_unidentified_contact_alone_does_not_override_specific_existing_followups():
    trace = attack_case()
    for s in trace["strike_evidence"]: s["global_target_id"] = None
    for o in trace["outcome_evidence"]: o["goal_plane_crossing"] = {"status": "UNRESOLVED"}
    assert attack.build(trace)["questions"] == []


@pytest.mark.parametrize("same_source", [True, False])
def test_followup_question_routes_only_between_same_source_and_scene(same_source):
    owner, reader = feedback_fixture.trace(name="left"), feedback_fixture.trace(name="right")
    owner["source_video"] = {"sha256": "video"}; reader["source_video"] = {"sha256": "video" if same_source else "other"}
    owner["decoded_frames"] = [f for f in owner["decoded_frames"] if f["media_ms"] < 1400]
    owner["contacts"] = {"accepted": [], "unresolved": []}; owner["action_inspections"] = []
    owner["outcome_evidence"] = [{"goal_geometry_evidence": {"goal_review_requests": context.parse_reasoning(
        {"review_requests": [{"idx": 1, "question": "BALL_REAPPEARANCE", "direction": "AFTER"}]}, [1500], [])["review_requests"]}}]
    plan = feedback.build_plan([owner, reader])
    routed = [j for j in plan["jobs"] if j["reason"] == "MODEL_SEQUENCE_BALL_REAPPEARANCE"]
    assert bool(routed) is same_source


async def test_actual_readers_receive_context_and_return_optional_searches(monkeypatch, tmp_path):
    sent = []
    class Chat:
        def __init__(self, **_): pass
        def with_model(self, *_): return self
        def with_params(self, **_): return self
        async def send_message(self, message):
            sent.append(message.text)
            return json.dumps({"frames": [{"idx": 1, "balls": [], "selected_body_ids": []}],
                "hypotheses": [{"kind": "PASS_CHAIN", "steps": [{"idx": 1, "body_id": "body_1", "observation": "RELEASE"}]}],
                "review_requests": [{"idx": 1, "question": "RECEIVER", "direction": "AFTER"}],
                "outcome_explanations": [{"hypothesis": "OTHER_BALL", "supporting_indices": [2]}]})
    monkeypatch.setattr(vision, "LlmChat", Chat)
    paths = []
    for i in range(2):
        p = tmp_path / f"pixels-{i}.jpg"; p.write_bytes(b"fixture"); paths.append(str(p))
    packet = context.build({"scene_id": "scene", "start_ms": 0, "end_ms": 2000}, [frame(1000), frame(1200)])
    result = await vision.read_action_pixel_evidence("fixture", "s", paths, [1000, 1200],
        body_candidates=[{"media_ms": 1000, "bodies": [{"body_id": "body_1"}]}], sequence_context=packet)
    assert result["sequence_reasoning"]["hypotheses"]
    assert "Do not infer identity, a pass, a shot" not in sent[-1] and "backward" in sent[-1]
    result = await vision.read_goal_scene_evidence("fixture", "s", paths, [1000, 1200], sequence_context=packet)
    assert result["goal_review_requests"] and result["outcome_explanations"][0]["supporting_media_ms"] == [1200]
    assert result["proof_ready"] is False


def reference_case():
    known = [frame(ms, seed=True, scene="early") for ms in (0, 200)]
    for f in known:
        f["players"][0].update(team="target_team", team_confidence=.95, team_source="KIT_CHROMA_DENSE_TAP_CLUSTER")
    votes = [{"media_ms": ms, "number": "15", "readable": True, "confidence": "high"} for ms in (0, 200)]
    reference = authority.selected_jersey_reference(known, {"p": jersey_consensus.aggregate_jersey_votes(votes)}, "15", "video")
    frames = [frame(ms, scene="later", track="new_id") for ms in range(9800, 10201, 20)]
    for f in frames:
        f["players"][0].update(team="target_team", team_confidence=.95, team_source="KIT_CHROMA_DENSE_TAP_CLUSTER")
    identity_authority = {"identity_profile": {"stated_jersey_number": "15"}, "automatic_jersey_reference": reference,
        "scenes": [{"scene_id": "early", "start_ms": 0, "end_ms": 2000},
                   {"scene_id": "later", "start_ms": 9000, "end_ms": 12000}],
        "target_points": [{"media_ms": 0, "scene_id": "early", "tap_authority": True,
                           "proof_eligible": True, "primary_source": "USER_TAP"}]}
    graph = {"touches": [{"touch_id": "new", "media_ms": 10000, "representative_ms": 10000,
        "scene_id": "later", "player_track_id": "new_id", "status": "VERIFIED", "proof_eligible": True}]}
    votes = [{"media_ms": ms, "number": "15", "readable": True, "confidence": "high"} for ms in (9900, 10100)]
    consensus = {"new_id": jersey_consensus.aggregate_jersey_votes(votes)}
    return identity_authority, frames, graph, consensus


def test_new_actual_number_reads_and_target_kit_reidentify_after_cut_without_another_tap():
    a, frames, graph, votes = reference_case()
    assert a["automatic_jersey_reference"]["evidence_ms"] == [0, 200]
    output = authority.apply_verified_jersey_handoff(a, frames, graph, votes, source_sha256="video")
    touch = output["touches"][0]
    assert touch["global_target_id"] == "GLOBAL_TARGET"
    assert touch["global_target_resolution"]["reason"] == "UNIQUE_MULTI_FRAME_JERSEY_REID_FROM_VERIFIED_REFERENCE"
    assert touch["global_target_resolution"]["tap_media_ms"] is None
    refreshed = identity.apply(frames, output)
    assert all(f["global_target"]["proof_eligible"] for f in refreshed["frames"])
    assert "global_target_id" not in graph["touches"][0]


@pytest.mark.parametrize("failure", ["reference_missing", "source", "future_reference", "unreadable", "duplicate_image",
    "kit", "kit_source", "cut_in_votes", "competing_target", "competing_number"])
def test_automatic_reidentification_requires_fresh_independent_body_and_number_evidence(failure):
    a, frames, graph, votes = reference_case()
    if failure == "reference_missing": a.pop("automatic_jersey_reference")
    elif failure == "source": a["automatic_jersey_reference"]["source_video_sha256"] = "foreign"
    elif failure == "future_reference": a["automatic_jersey_reference"]["evidence_ms"] = [11000, 11200]
    elif failure == "unreadable": votes["new_id"]["votes"][0]["readable"] = False
    elif failure == "duplicate_image": votes["new_id"]["votes"][1]["media_ms"] = 9900
    elif failure == "kit":
        for f in frames: f["players"][0]["team"] = "opponent"
    elif failure == "kit_source":
        for f in frames: f["players"][0]["team_source"] = "MODEL_GUESS"
    elif failure == "cut_in_votes": frames[10]["cut_barrier"] = True
    elif failure == "competing_target": frames[10]["global_target"] = {
        "status": "VERIFIED", "proof_eligible": True, "local_track_id": "someone_else"}
    elif failure == "competing_number":
        for f in frames:
            f["players"].append({**deepcopy(f["players"][0]), "local_track_id": "duplicate"})
        votes["duplicate"] = deepcopy(votes["new_id"])
    output = authority.apply_verified_jersey_handoff(a, frames, graph, votes, source_sha256="video")
    assert not output["touches"][0].get("global_target_id")


def late_ball_path():
    rows = [{"media_ms": ms, "scene_id": "scene", "time_authority": "ACTUAL_MEDIA_PTS", "proof_eligible": True,
        "state": "MEASURED", "used_fallback": False,
        "box": {"x": .4+.55*(ms-1000)/4000, "y": .45, "w": .02, "h": .02}}
        for ms in range(1000, 5001, 20)]
    strike = {"media_ms": 1000, "scene_id": "scene", "strike_id": "late", "player_track_id": "p",
        "active_ball_anchor": {**deepcopy(rows[0]), "source": "VERIFIED_RELEASE_CONTACT_BALL_AFTER", "remote_spare_ball_used": False},
        "_measured_attack_limit": {"source": "CONTIGUOUS_MEASURED_ATTACK_CONTEXT", "scene_id": "scene", "end_ms": 7000}}
    return strike, rows


def test_continuous_contact_ball_can_prove_a_crossing_after_the_old_three_second_limit():
    strike, rows = late_ball_path()
    geometry = {"line": {"p1": {"x": .90, "y": .30}, "p2": {"x": .90, "y": .65}}}
    result = outcomes.reconstruct_post_strike_outcome(strike, rows, {}, goal_geometry=geometry)
    assert result["goal_plane_crossing"]["status"] == "VERIFIED"
    assert result["goal_plane_crossing"]["crossing_ms"] > 4000 and result["observation_end_ms"] == 5900
    legacy = deepcopy(strike); legacy.pop("_measured_attack_limit")
    assert outcomes.reconstruct_post_strike_outcome(legacy, rows, {}, goal_geometry=geometry)["goal_plane_crossing"]["status"] != "VERIFIED"


@pytest.mark.parametrize("failure", ["gap", "predicted", "fallback", "foreign_scene", "wrong_seed", "rejected_ball"])
def test_search_context_alone_cannot_extend_the_same_ball_proof_horizon(failure):
    strike, rows = late_ball_path()
    if failure == "gap": rows = [r for r in rows if not 2000 <= r["media_ms"] <= 2100]
    elif failure == "predicted": rows[50]["state"] = "PREDICTED_SHORT_GAP"
    elif failure == "fallback": rows[50]["used_fallback"] = True
    elif failure == "foreign_scene": rows[50]["scene_id"] = "other"
    elif failure == "wrong_seed": strike["active_ball_anchor"]["box"]["x"] = .8
    elif failure == "rejected_ball": rows[50]["identity_rejection"] = "other_ball"
    assert outcomes._measured_outcome_end(strike, rows) == 4000


class Capture:
    """Variable-PTS fake with real seek/grab/retrieve contracts."""
    def __init__(self, fallback=False):
        self.times = [0, 33, 71, 110, 160, 190, 240, 2000, 2040, 2080]
        self.index = -1; self.seeks = 0; self.fallback = fallback
    def set(self, prop, value):
        assert prop == cv2.CAP_PROP_POS_MSEC
        self.seeks += 1
        self.index = next((i for i, ms in enumerate(self.times) if ms >= value), len(self.times))-1
    def grab(self):
        self.index += 1
        return self.index < len(self.times)
    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_MSEC: return 0 if self.fallback else self.times[self.index]
        if prop == cv2.CAP_PROP_POS_FRAMES: return self.index+1
        return 30
    def retrieve(self): return True, ("pixels", self.index)


def test_batched_decoding_preserves_random_access_pixels_and_actual_variable_pts():
    wanted = [10, 33, 40, 69, 120, 180, 2020, 2040]
    legacy = Capture()
    expected = {}
    for ms in wanted:
        ok, pixels, t = video_timebase.read_frame_at(legacy, ms/1000, fps=30)
        assert ok
        expected[ms] = (round(t*1000), pixels)
    current = Capture()
    result = video_timebase.read_frames_at(current, wanted, fps=30)
    assert result == expected and result[40][0] == result[69][0] == 71
    assert current.seeks == 2 and current.seeks < legacy.seeks


def test_batched_decoding_does_not_relabel_frame_rate_fallback_as_actual_pts():
    assert video_timebase.read_frames_at(Capture(fallback=True), [40, 69], fps=30) == {}
