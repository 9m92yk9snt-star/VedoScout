"""No-model audit: stage budgets must never be mistaken for actual elapsed."""
from copy import deepcopy
import pytest

from scripts.profile_orman1000_asset_time import audit, VIDEO_SHA


def fixture():
    source=VIDEO_SHA
    timings={"source_analysis_seconds":245.088,
             "facts_writer_and_projection_seconds":155.729,
             "before_assets_seconds":400.817,
             "assets_seconds":1166.845,
             "total_processing_seconds":1567.662}
    names=("00:50","00:31","00:24","00:44",
           "00:56","00:13","00:04","00:08")
    budgets={"00:31":106.79546785800085,
             "00:44":160.7015437530008,
             "00:08":419.99999821500023}
    timed_out={"00:50","00:31","00:44","00:56","00:13","00:08"}
    cards=[]
    for k,name in enumerate(names):
        eid="unique:"+str(k)
        t={"event_id":eid,"source_video_sha256":source,
           "contour_diagnostics":{"windows":[{
               "status":"TIME_BUDGET" if name in timed_out
                        else "SUPPORTED_SOURCE_OBSERVATIONS"
           }]},
           "segments":[{"id":str(i)} for i in range(k+1)]}
        if name in budgets:
            t["refinement_diagnostics"]={
                "budget_seconds":budgets[name],"windows":[{"status":"TIME_BUDGET"}]}
        cards.append({"event_id":eid,"timestamp":name,
                     "source_video_sha256":source,
                     "match_room":{"event_id":eid,"source_video_sha256":source,
                                   "tracking_status":"COMPLETED","tracking":t}})
    return {"sequence_timings":timings,
            "canonical_events":{"source_video_sha256":source,
                                "events":[{"event_id":"source-event:"+str(i)} for i in range(21)]},
            "match_room_localization":{"source_video_sha256":source,
                                       "elapsed_seconds":259.352},
            "full_report":{"video_comments":cards}}


def test_exact_timing_accounting_is_additive_without_fake_medium_elapsed():
    record=fixture()
    untouched=deepcopy(record)
    result=audit(record)
    assert record==untouched
    assert result["clip_count"]==8
    assert result["seconds"]=={
      "source_analysis":245.088,
      "facts_writer_and_projection":155.729,
      "before_assets":400.817,
      "assets_total":1166.845,
      "match_room_localization_elapsed":259.352,
      "assets_after_localization_unpartitioned":907.493,
      "complete_report":1567.662}
    assert result["initial_contour_timeout_card_count"]==6
    assert result["medium_refinement_allocated_budget_seconds"]==687.497
    assert result["medium_refinement_elapsed_seconds"] is None
    assert result["asset_encoding_and_upload_elapsed_seconds"] is None
    assert result["new_provider_calls"]==0
    assert result["production_changed"] is False


@pytest.mark.parametrize("mutation,exception",[
 ("foreign_source","SOURCE_21_EVENTS_8_CARDS"),
 ("foreign_card","CROSS_VIDEO_TRACKING_CARD"),
 ("pretend_complete","TIMING_TOTALS_NOT_CONSISTENT"),
 ("localization_overrun","INVALID_REAL_LOCALIZATION_DURATION"),
 ("invented_medium","INVALID_MEDIUM_BUDGET"),
])
def test_wrong_source_or_fabricated_time_is_rejected(mutation,exception):
    data=fixture()
    if mutation=="foreign_source":
        data["canonical_events"]["source_video_sha256"]="different-video"
    elif mutation=="foreign_card":
        data["full_report"]["video_comments"][0]["match_room"]["source_video_sha256"]="foreign"
    elif mutation=="pretend_complete":
        data["sequence_timings"]["total_processing_seconds"]=600
    elif mutation=="localization_overrun":
        data["match_room_localization"]["elapsed_seconds"]=9999
    elif mutation=="invented_medium":
        data["full_report"]["video_comments"][7]["match_room"]["tracking"]["refinement_diagnostics"]["budget_seconds"]=-1
    with pytest.raises(ValueError, match=exception):
        audit(data)
