"""Rank review requests across the whole report before spending its budget.

Semantic contacts select where to inspect, never decide the result. Physical
ownership/release relevance takes priority. Round-robin scenes prevent a noisy
early window from consuming every uncertain-owner clarification.
"""
from collections import defaultdict


def ordered_requests(requests, analysis):
    contacts = []
    for seq in (analysis or {}).get("sequences") or []:
        for a in seq.get("actions") or []:
            if a.get("kind") in {"SHOT", "PASS", "CROSS", "KEY_PASS"}:
                ms = a.get("contact_ms", a.get("start_ms"))
                if isinstance(ms, (int, float)):
                    contacts.append((seq.get("scene_id"), int(ms)))
    def relevance(job):
        s = job["strike"]
        scene, ms = s.get("scene_id"), int(s.get("media_ms") or 0)
        distance = min((abs(ms - t) for sc, t in contacts if sc == scene), default=1000000)
        role = s.get("contact_role") or {}
        return (0 if role.get("role") == "RELEASE" else 1,
                0 if distance <= 1200 else 1, distance,
                -float(s.get("post_speed") or 0), ms)
    result = []
    for lane in ("VERIFIED_CHAIN", "CLARIFICATION"):
        scenes = defaultdict(list)
        for job in requests:
            if job["review"].get("lane") == lane:
                scenes[str(job["window"].get("scene_id") or "")].append(job)
        for group in scenes.values():
            group.sort(key=relevance)
        # Choose strongest remaining scene, then visit every other scene before
        # admitting another request from that scene.
        while scenes:
            order = sorted(scenes, key=lambda scene: (relevance(scenes[scene][0]), scene))
            for scene in order:
                result.append(scenes[scene].pop(0))
                if not scenes[scene]:
                    del scenes[scene]
    return result
