"""No-provider-call staging of exact previously approved Orman1000 duel tail."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from scripts import stage_orman1000_duel_tail as staged

RESULT = Path(__file__).resolve().parents[2] / "testdata/matchroom-completion/result.json"


def data():
    saved=json.loads(RESULT.read_text())
    doc={
        "canonical_events":{
            "source_video_sha256":staged.SOURCE,
            "events":[{
                "event_id":staged.DUEL,
                "source_video_sha256":staged.SOURCE,
                "proof":{"proof_start_ms":7500,"proof_end_ms":12133},
            }]
        },
        "raw_marker_anchors":[{"fictional_test_selection":True}],
        "full_report":{"match_stats":{"observed_goals":2,"observed_assists":2}},
        "match_room_localization":{
            "source_video_sha256":staged.SOURCE,
            "original_selection_values_sha256":staged.SELECTION,
            "events":{staged.DUEL:{
                "status":"OBSERVATIONS_RETURNED",
                "event_id":staged.DUEL,
                "source_video_sha256":staged.SOURCE,
                "original_selection_values_sha256":staged.SELECTION,
                "window_ms":[7500,10000],
                "frames":[{"media_ms":7500},{"media_ms":10000}],
                "completion":{},
            }}
        },
    }
    return doc,saved


def test_approved_same_source_completion_is_staged_without_mutating_video_facts(monkeypatch):
    doc,response=data()
    monkeypatch.setattr(staged,"selection_digest",lambda _:staged.SELECTION)
    # The original paid source response was independently validated and is
    # saved verbatim in result.json. This test isolates CHECKPOINT staging.
    monkeypatch.setattr(staged,"bound_samples",lambda *a,**kw:response["samples"])
    untouched=deepcopy((doc,response))
    result=staged.stage(doc,response)
    assert (doc,response)==untouched
    assert result["canonical_events"]==doc["canonical_events"]
    assert result["full_report"]==doc["full_report"]
    record=result["match_room_localization"]["events"][staged.DUEL]["completion"][staged.PACKET]
    assert record==response["record"]
    assert result["offline_checkpoint_staging"]["source_observations"]==17
    assert result["offline_checkpoint_staging"]["model_calls"]==0
    assert result["offline_checkpoint_staging"]["published"] is False
    assert result["offline_checkpoint_staging"]["status"].endswith("NOT_RENDERED")
    # An identical idempotent replay is safe. No new history or paid request.
    again=staged.stage(result,response)
    assert again==result


@pytest.mark.parametrize("break_it, reason",[
    ("source","DUEL_SOURCE_VIDEO_CHANGED"),
    ("selection","DUEL_ORIGINAL_HUMAN_SELECTION_CHANGED"),
    ("wrong_actor","DUEL_EVENT_IDENTITY_CHANGED"),
    ("primary_window","PRIMARY_DUEL_PROOF_WINDOW_CHANGED"),
    ("completion_source","COMPLETION_EVIDENCE_CROSS_SOURCE"),
    ("receipt_hash","PAID_COMPLETION_RECEIPT_NOT_IDENTICAL"),
    ("wrong_rows","COMPLETION_SOURCE_PTS_CHANGED"),
    ("overlap","COMPLETION_CHECKPOINT_CONFLICT"),
])
def test_wrong_video_receipt_or_cross_event_staging_fails_closed(monkeypatch,break_it,reason):
    doc,response=data()
    monkeypatch.setattr(staged,"selection_digest",lambda _:staged.SELECTION)
    monkeypatch.setattr(staged,"bound_samples",lambda *a,**kw:response["samples"])
    response=deepcopy(response)
    if break_it=="source":
        doc["match_room_localization"]["source_video_sha256"]="foreign"
    elif break_it=="selection":
        doc["match_room_localization"]["original_selection_values_sha256"]="foreign"
    elif break_it=="wrong_actor":
        doc["canonical_events"]["events"][0]["event_id"]="other"
    elif break_it=="primary_window":
        doc["match_room_localization"]["events"][staged.DUEL]["window_ms"]=[7700,10000]
    elif break_it=="completion_source":
        response["record"]["source_video_sha256"]="foreign"
    elif break_it=="receipt_hash":
        response["record"]["receipt"]["response_sha256"]="modified"
    elif break_it=="wrong_rows":
        response["samples"][0]["media_ms"]=10132
    elif break_it=="overlap":
        doc["match_room_localization"]["events"][staged.DUEL]["completion"][staged.PACKET]={"foreign":True}
    with pytest.raises(ValueError,match=reason):
        staged.stage(doc,response)
