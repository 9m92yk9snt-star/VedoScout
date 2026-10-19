"""Run the actual server orchestration with an isolated in-memory report store.

No production database, payments, emails, deployment or dashboard messages.
Model calls and source frame/clip encoding are real unless explicitly injected
by offline tests. AST extraction avoids importing unrelated app integrations.
"""
import argparse
import ast
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import time

import sequence_report_runtime


class ReportStore:
    def __init__(self, doc):
        self.doc = deepcopy(doc)
        self.states = []

    async def find_one(self, query):
        assert query == {"id": self.doc["id"]}
        return deepcopy(self.doc)

    async def update_one(self, query, update):
        assert query == {"id": self.doc["id"]}
        self.doc.update(deepcopy(update.get("$set") or {}))
        for key in update.get("$unset") or {}:
            self.doc.pop(key, None)
        if "full_report_status" in (update.get("$set") or {}):
            self.states.append(update["$set"]["full_report_status"])


def server_harness(video, doc, directory, *, runtime=sequence_report_runtime):
    tree = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text())
    names = {"generate_full_report_task", "_persist_video_frames", "_finalize_full_report"}
    selected = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
    template = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "FULL_REPORT_PROMPT" for t in n.targets))
    store, trace, notifications = ReportStore(doc), [], []

    async def source(_):
        return Path(video)

    async def record(_, phase):
        trace.append({"phase": phase, "at": time.monotonic()})

    async def suppressed_notification(*args):
        notifications.append("SUPPRESSED_IN_SANDBOX")

    namespace = {"asyncio": asyncio, "datetime": datetime, "timezone": timezone, "Optional": __import__('typing').Optional,
                 "db": SimpleNamespace(reports=store), "logger": logging.getLogger("sequence-report-trial"),
                 "_ensure_report_video_local": source, "_trace": record,
                 "sequence_report_runtime": runtime, "FULL_REPORT_PROMPT": template,
                 "now_iso": lambda: datetime.now(timezone.utc).isoformat(),
                 "UPLOAD_DIR": Path(directory),
                 "_analysis_frames_dir": lambda rid: Path(directory) / "frames" / rid,
                 "r2_storage": SimpleNamespace(is_configured=lambda: False),
                 "_send_report_ready_email": suppressed_notification,
                 "_notify_dashboard_report": suppressed_notification,
                 "_identity_gate_required": lambda stats: False}
    exec(compile(ast.Module(body=selected, type_ignores=[]), "server-orchestration", "exec"), namespace)
    return namespace, store, trace, notifications


async def trial(video, anchors, output):
    output.mkdir(parents=True, exist_ok=False)
    os.environ["FULL_REPORT_ENGINE"] = "sequence_v1"
    doc = {"id": "sequence-full-report-trial", "raw_marker_anchors": anchors["raw_marker_anchors"],
           "anchors": [], "player_details": {"age": 12}, "is_paid": False}
    ns, store, trace, suppressed = server_harness(video, doc, output)
    started = time.monotonic()
    await ns["generate_full_report_task"](doc["id"])
    wall = round(time.monotonic()-started, 3)
    (output / "report-document.json").write_text(json.dumps(store.doc, indent=2))
    full = store.doc.get("full_report") or {}
    summary = {"status": store.doc.get("full_report_status"), "total_wall_seconds": wall,
               "timings": store.doc.get("sequence_timings"), "states": store.states,
               "source_video_sha256": (store.doc.get("canonical_events") or {}).get("source_video_sha256"),
               "verified_stats": full.get("verified_stats"), "match_stats": full.get("match_stats"),
               "evidence_rows": len(full.get("video_comments") or []),
               "exact_proof_frames": sum(c.get("proof_frame_verified") is True for c in full.get("video_comments") or []),
               "clips": sum(bool(c.get("tele_clip_url")) for c in full.get("video_comments") or []),
               "writer_calls": len((store.doc.get("sequence_audit") or {}).get("writer_receipts") or []),
               "notifications_sent": 0, "production_database_used": False,
               "legacy_reconstruction_called": False,
               "trace": [{"phase": r["phase"], "elapsed": round(r["at"]-started, 3)} for r in trace]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    if summary["status"] != "ready":
        raise RuntimeError("SEQUENCE_FULL_REPORT_TRIAL_FAILED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--anchors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(trial(args.video, json.loads(args.anchors.read_text()), args.output))
