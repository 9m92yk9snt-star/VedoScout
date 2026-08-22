#!/usr/bin/env python3
"""Scratch-only asserted patch for canonical event telestration."""
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server.py"

OLD = '''    done = 0\n    for c in enriched:\n        if not (isinstance(c, dict) and c.get("anchor_locked") and isinstance(c.get("anchor_box"), dict)):\n            continue\n'''

NEW = '''    done = 0\n\n    # FIX09C — canonical event-native evidence already carries proof-grade\n    # GLOBAL_TARGET geometry for the exact extracted evidence frame. Render it\n    # directly; do not ask another detector/model to relocate the player and do\n    # not require a nearby user tap. Predicted/unresolved identity never reaches\n    # event_track_locked, and proof_frame_verified keeps exact event/time binding.\n    for c in enriched:\n        if not (isinstance(c, dict) and c.get("event_native")\n                and c.get("event_track_locked")\n                and c.get("proof_frame_verified") is True\n                and isinstance(c.get("event_track_box"), dict)):\n            continue\n        fu = str(c.get("frame_url") or "")\n        if not fu.startswith("/api/uploads/frames/"):\n            continue\n        frame_path = frames_dir / Path(fu).name\n        if not frame_path.exists():\n            continue\n        b = c["event_track_box"]\n        try:\n            x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))\n            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and w > 0 and h > 0\n                    and x + w <= 1.05 and y + h <= 1.05):\n                continue\n            box = {"x0": x, "y0": y, "x1": x + w, "y1": y + h}\n        except (KeyError, TypeError, ValueError):\n            continue\n        if await asyncio.to_thread(render_telestration, str(frame_path), box, label, True, y):\n            c["telestrated"] = True\n            c["tele_ring"] = True\n            c["tele_canonical_event"] = True\n            c["tele_box"] = {k: float(box[k]) for k in ("x0", "y0", "x1", "y1")}\n            done += 1\n\n    for c in enriched:\n        if not (isinstance(c, dict) and c.get("anchor_locked") and isinstance(c.get("anchor_box"), dict)):\n            continue\n'''

text = SERVER.read_text(encoding="utf-8")
count = text.count(OLD)
if count != 1:
    raise RuntimeError(f"expected exactly one telestration anchor, found {count}")
SERVER.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
print("FIX09C canonical event telestration patch applied")
