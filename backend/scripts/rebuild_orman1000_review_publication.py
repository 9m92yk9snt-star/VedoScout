"""Regenerate the OFFLINE Orman1000 publication from a source-bound review copy.

Uses the EXISTING deterministic publication engine, not a hand-edited list of
titles or a paid model call. Proves that the original latest-ZIP publication
is reproducible before any preview. It does NOT publish, deploy or override
the original contradictory model receipts. A source-role review is still
required before anyone may treat a reclassified assist as verified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from report_publication import publish_report

ARCHIVE="3b27260511ed965952a497f97d1c6345a0f1b4bef1b89a60912a62e0f6530c0c"
SOURCE="fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
TARGET="47ad617d2ba76a4683cd"


def validate_projection(original_published,candidate,published):
    errors=[]
    def check(valid,label):
        if not valid:errors.append(label)
    check(candidate.get("canonical_events",{}).get("source_video_sha256")==SOURCE,
          "CANDIDATE_SOURCE_SHA_CHANGED")
    check(candidate.get("report_release_allowed") is False
          and candidate.get("adjudication_preview",{}).get("published") is False,
          "UNPUBLISHED_REVIEW_STATUS_REQUIRED")
    check(published.get("report_release_allowed") is False,
          "PUBLICATION_PREVIEW_MUST_NOT_ALLOW_RELEASE")
    pub=published.get("report_publication") or {}
    old=original_published.get("report_publication") or {}
    original_rows=old.get("key_actions") or []
    rows=pub.get("key_actions") or []
    check(len(original_rows)==len(rows)==5,
          "FIVE_SOURCE_VERIFIED_PUBLICATION_ACTIONS_REQUIRED")
    check([a.get("event_id") for a in original_rows]==[a.get("event_id") for a in rows],
          "PUBLICATION_SOURCE_ACTIONS_CHANGED")
    if len(rows)==5:
        indexed={a.get("event_id"):a for a in rows}
        check(indexed.get(TARGET,{}).get("title")=="Assist",
              "DISPUTED_PUBLICATION_CARD_NOT_ASSIST")
        check(sum(a.get("title")=="Goal" for a in rows)==1
              and sum(a.get("title")=="Assist" for a in rows)==3,
              "PUBLICATION_ACTION_TITLES_NOT_1_PLUS_3")
        for source in original_rows:
            eid=source["event_id"]
            if eid!=TARGET:
                # A missing/unexpected source action is an explicit
                # release blocker, never an unhandled KeyError.
                check(indexed.get(eid,{}).get("title")==source.get("title"),
                      "UNRELATED_PUBLICATION_ACTION_CHANGED:"+eid)
    view=pub.get("view") or {}
    by_label={x.get("label"):x.get("value") for x in (view.get("matchStats") or []) if isinstance(x,dict)}
    check(by_label.get("Goals")==1 and by_label.get("Assists")==3,
          "PUBLISHED_VIEW_STATS_STALE")
    # Presentation contract intentionally EXCLUDES assists from key passes.
    # The pre-publication verified_stats engine uses an inclusive measure.
    # Never mistake a zero "other key passes" count for lost assists.
    candidate_events=(candidate.get("canonical_events") or {}).get("events") or []
    other_key_passes=sum(e.get("canonical_event_type")=="PASS"
                         and e.get("canonical_outcome")=="TEAMMATE_SHOT"
                         for e in candidate_events)
    check(by_label.get("Key Passes (excluding assists)")==other_key_passes,
          "PUBLISHED_KEY_PASS_EXCLUSION_SEMANTICS_CHANGED")
    stats=published.get("full_report",{}).get("match_stats") or {}
    check(stats.get("key_passes")==other_key_passes,
          "PUBLISHED_KEY_PASS_EXCLUSION_STAT_STALE")
    verified=published.get("full_report",{}).get("verified_stats") or {}
    check(stats.get("observed_goals")==1 and stats.get("observed_assists")==3,
          "PUBLISHED_REPORT_OBSERVED_STATS_STALE")
    check(verified.get("coverage_status")=="PARTIAL"
          and verified.get("goals_assists_available") is False,
          "PUBLICATION_MUST_PRESERVE_PARTIAL_COVERAGE")
    check(pub.get("content_sha256") and pub.get("content_sha256")!=old.get("content_sha256"),
          "PUBLICATION_CONTENT_SIGNATURE_NOT_RECOMPUTED")
    check(pub.get("review",{}).get("human_status") == old.get("review",{}).get("human_status"),
          "UNRELATED_HUMAN_SCOUT_REVIEW_STATUS_CHANGED")
    return errors


def rebuild(original,published_original,candidate):
    # Idempotency of the existing authoritative publisher is proven on
    # original video first. If it cannot reproduce the uploaded publication,
    # no corrected projection is allowed.
    baseline=publish_report(original)
    for field in ("full_report","report_publication","score_meaning"):
        if baseline.get(field)!=published_original.get(field):
            raise ValueError("SOURCE_PUBLICATION_NOT_REPRODUCIBLE:"+field)
    corrected=publish_report(candidate)
    blockers=validate_projection(baseline,candidate,corrected)
    if blockers:raise ValueError("INCOMPLETE_SOURCE_PUBLICATION_PREVIEW:"+",".join(blockers))
    return corrected


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda:file.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--latest-zip",type=Path,required=True)
    p.add_argument("--review-candidate",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error("Output must be new")
    if sha(args.latest_zip)!=ARCHIVE:raise ValueError("SOURCE_ORMAN1000_ARCHIVE_CHANGED")
    with zipfile.ZipFile(args.latest_zip) as archive:
        if archive.testzip():raise ValueError("CORRUPT_ORIGINAL_ARCHIVE")
        original=json.loads(archive.read("report.json"))
        published_original=json.loads(archive.read("publication/current.json"))
    candidate=json.loads(args.review_candidate.read_text())
    corrected=rebuild(original,published_original,candidate)
    # Output report is labelled and NOT the source's original publication.
    result={
        "scope":"UNPUBLISHED_ORMAN1000_CORRECTED_PUBLICATION_PREVIEW",
        "source_video_sha256":SOURCE,
        "release_ready":False,
        "independent_finisher_review_complete":False,
        "full_report_status":corrected.get("full_report_status"),
        "full_report":corrected["full_report"],
        "report_publication":corrected["report_publication"],
        "score_meaning":corrected["score_meaning"],
        "model_calls":0,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")))
    print(json.dumps({
        "status":"SOURCE_PUBLICATION_REPRODUCED_AND_REVIEW_PREVIEW_BUILT",
        "publication_sha256":corrected["report_publication"]["content_sha256"],
        "published":False,"new_model_calls":0,
        "key_actions":[(x["event_id"],x["title"]) for x in corrected["report_publication"]["key_actions"]],
    }))


if __name__=="__main__":
    main()
