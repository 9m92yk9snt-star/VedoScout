"""Offline publication parity; corrected version is always UNPUBLISHED.

Uses the five actual source-bound Orman1000 event IDs. Synthetic publications
are only for adversarial tests; the real ZIP publisher is independently replayed
by the source-archive CLI. No provider calls or live state.
"""
from copy import deepcopy

import pytest

from scripts import rebuild_orman1000_review_publication as preview

FIVE = [
    ("9a392fb19c052dfe6719", "Saved shot"),
    ("d1a34d11944defe8c2ce", "Goal"),
    ("006dbd71ed71d464f19d", "Assist"),
    (preview.TARGET, "Goal"),
    ("16b70d6326506d906e7d", "Assist"),
]


def original_doc():
    return {
        "canonical_events": {
            "source_video_sha256": preview.SOURCE,
            "events": [{"event_id":eid} for eid,_ in FIVE],
        },
        "full_report": {
            "match_stats": {"observed_goals":2, "observed_assists":2},
            "verified_stats": {
                "coverage_status":"PARTIAL", "goals_assists_available":False,
            },
        },
        "full_report_status":"ready",
        "report_release_allowed":False,
    }


def corrected_doc():
    revised = original_doc()
    revised["canonical_events"]["events"][3]["canonical_event_type"]="ASSIST"
    revised["full_report"]["match_stats"] = {
        "observed_goals":1, "observed_assists":3,
    }
    revised["full_report_status"]="REVIEW_ONLY_NOT_PUBLISHED"
    revised["report_release_allowed"]=False
    revised["adjudication_preview"]={"published":False}
    return revised


def fake_publisher(report):
    doc=deepcopy(report)
    corrected=(doc["full_report"]["match_stats"]["observed_goals"] == 1)
    changes=[(eid,"Assist" if corrected and eid==preview.TARGET else label)
             for eid,label in FIVE]
    doc["report_publication"]={
        "key_actions":[{"event_id":e,"title":t} for e,t in changes],
        "view":{"matchStats":[
            {"label":"Goals","value":doc["full_report"]["match_stats"]["observed_goals"]},
            {"label":"Assists","value":doc["full_report"]["match_stats"]["observed_assists"]},
        ]},
        "content_sha256":"corrected" if corrected else "original",
        "review":{"human_status":"Scout review awaiting delivery"},
    }
    doc["score_meaning"]={"assessment":"partial evidence"}
    return doc


def test_exact_source_derived_five_actions_rebuild_only_as_unpublished_preview(monkeypatch):
    monkeypatch.setattr(preview, "publish_report", fake_publisher)
    source=original_doc()
    previous=fake_publisher(source)
    candidate=corrected_doc()
    before=deepcopy((source,previous,candidate))
    reprojected=preview.rebuild(source,previous,candidate)
    assert [x["title"] for x in reprojected["report_publication"]["key_actions"]] == [
        "Saved shot","Goal","Assist","Assist","Assist"
    ]
    assert reprojected["report_publication"]["content_sha256"] == "corrected"
    assert reprojected["report_release_allowed"] is False
    assert reprojected["full_report_status"] == "REVIEW_ONLY_NOT_PUBLISHED"
    assert (source,previous,candidate) == before


def test_source_publisher_must_exactly_reproduce_uploaded_original(monkeypatch):
    monkeypatch.setattr(preview, "publish_report", fake_publisher)
    original=original_doc()
    previous=fake_publisher(original)
    for changed in ("full_report","report_publication","score_meaning"):
        falsified=deepcopy(previous)
        falsified[changed]["different_value"]="not-in-the-original-export"
        with pytest.raises(ValueError,match="SOURCE_PUBLICATION_NOT_REPRODUCIBLE:"+changed):
            preview.rebuild(original,falsified,corrected_doc())


def test_stale_publication_stats_and_50s_card_are_rejected(monkeypatch):
    monkeypatch.setattr(preview, "publish_report", fake_publisher)
    original=original_doc()
    baseline=fake_publisher(original)
    candidate=corrected_doc()
    valid=fake_publisher(candidate)
    corruptions=[
        ("CANDIDATE_SOURCE_SHA_CHANGED",lambda _,c,p: c["canonical_events"].update(
            source_video_sha256="foreign")),
        ("UNPUBLISHED_REVIEW_STATUS_REQUIRED",lambda _,c,p:c.update(
            report_release_allowed=True)),
        ("PUBLICATION_PREVIEW_MUST_NOT_ALLOW_RELEASE",lambda _,c,p:p.update(
            report_release_allowed=True)),
        ("DISPUTED_PUBLICATION_CARD_NOT_ASSIST",lambda _,c,p:p["report_publication"]["key_actions"][3].update(
            title="Goal")),
        ("PUBLICATION_ACTION_TITLES_NOT_1_PLUS_3",lambda _,c,p:p["report_publication"]["key_actions"][1].update(
            title="Assist")),
        ("PUBLISHED_VIEW_STATS_STALE",lambda _,c,p:p["report_publication"]["view"]["matchStats"][1].update(
            value=2)),
        ("PUBLISHED_REPORT_OBSERVED_STATS_STALE",lambda _,c,p:p["full_report"]["match_stats"].update(
            observed_assists=2)),
        ("PUBLICATION_MUST_PRESERVE_PARTIAL_COVERAGE",lambda _,c,p:p["full_report"]["verified_stats"].update(
            coverage_status="COMPLETE")),
        ("PUBLICATION_CONTENT_SIGNATURE_NOT_RECOMPUTED",lambda _,c,p:p["report_publication"].update(
            content_sha256="original")),
        ("UNRELATED_HUMAN_SCOUT_REVIEW_STATUS_CHANGED",lambda _,c,p:p["report_publication"]["review"].update(
            human_status="Approved by someone else")),
        ("PUBLICATION_SOURCE_ACTIONS_CHANGED",lambda _,c,p:p["report_publication"]["key_actions"][0].update(
            event_id="foreign_event")),
        ("UNRELATED_PUBLICATION_ACTION_CHANGED:",lambda _,c,p:p["report_publication"]["key_actions"][0].update(
            title="Goal")),
    ]
    for expected,change in corruptions:
        a,b,c=deepcopy(baseline),deepcopy(candidate),deepcopy(valid)
        change(a,b,c)
        failures=preview.validate_projection(a,b,c)
        assert any(expected in message for message in failures), (expected,failures)
