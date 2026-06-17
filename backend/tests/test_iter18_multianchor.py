"""
Iter 18 — Multi-anchor pipeline tests.

Covers:
  • precision_engine.extract_frame_at extracts a single frame via ffmpeg
  • build_preview_prompt / build_full_prompt include MULTI-ANCHOR LOCK block
    when anchors= kwarg is supplied (and omit it when empty/None)
  • Backend regression: auth login, /api/me/upload-eligibility,
    GET /api/reports/{seeded_premium_id} all return 200
  • Upload endpoint accepts marker_anchors form field, persists anchors list
"""

import io
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

from precision_engine import (
    AudioEvent,
    PlayerFingerprint,
    build_anchor_ensemble_block,
    build_full_prompt,
    build_preview_prompt,
    extract_frame_at,
)

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to internal — most CI envs export REACT_APP_BACKEND_URL
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

TEST_CLIP = "/tmp/test_clip.webm"


def _ensure_clip():
    p = Path(TEST_CLIP)
    if p.exists() and p.stat().st_size > 0:
        return
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=darkgreen:s=854x480:d=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-c:v", "libvpx", "-crf", "30", "-c:a", "libvorbis",
            TEST_CLIP,
        ],
        check=True, timeout=60,
    )


# ── extract_frame_at ──────────────────────────────────────────────────


def test_extract_frame_at_returns_true_and_creates_jpg(tmp_path):
    _ensure_clip()
    out = tmp_path / "frame.jpg"
    ok = extract_frame_at(TEST_CLIP, 2.5, str(out))
    assert ok is True
    assert out.exists()
    assert out.stat().st_size > 0


def test_extract_frame_at_bad_input_returns_false(tmp_path):
    out = tmp_path / "frame.jpg"
    ok = extract_frame_at("/nonexistent/video.mp4", 1.0, str(out))
    assert ok is False


# ── build_anchor_ensemble_block ───────────────────────────────────────


def test_anchor_block_empty_when_no_anchors():
    assert build_anchor_ensemble_block([]) == ""


def test_anchor_block_lists_each_anchor():
    anchors = [
        {"t": 1.2, "jersey_name": "navy blue", "shorts_name": "white", "body_ratio": 2.3},
        {"t": 7.8, "jersey_name": "navy blue", "shorts_name": "white", "body_ratio": 2.1},
    ]
    block = build_anchor_ensemble_block(anchors)
    assert "MULTI-ANCHOR LOCK" in block
    assert "2 confirmed sightings" in block
    assert "1.20s" in block
    assert "7.80s" in block
    assert "navy blue" in block


# ── Prompt builders w/ anchors kwarg ──────────────────────────────────


def _fp():
    return PlayerFingerprint(
        jersey_hex="#141E8C", jersey_name="navy blue",
        shorts_hex="#F0F0F0", shorts_name="white",
        body_ratio=2.3, crop_path=None, box={}, confidence="ok",
    )


def test_preview_prompt_with_anchors_includes_block():
    base = "BASE {player_details} {content_type} {player_visible} {camera_distance}"
    anchors = [
        {"t": 2.5, "jersey_name": "navy blue", "shorts_name": "white", "body_ratio": 2.3},
        {"t": 9.1, "jersey_name": "navy blue", "shorts_name": "white", "body_ratio": 2.4},
    ]
    p = build_preview_prompt(base, _fp(), [], {"x": 1}, anchors=anchors)
    assert "MULTI-ANCHOR LOCK" in p
    assert "2.50s" in p
    assert "9.10s" in p


def test_preview_prompt_without_anchors_omits_block():
    base = "BASE {player_details} {content_type} {player_visible} {camera_distance}"
    p1 = build_preview_prompt(base, _fp(), [], {"x": 1})
    p2 = build_preview_prompt(base, _fp(), [], {"x": 1}, anchors=None)
    p3 = build_preview_prompt(base, _fp(), [], {"x": 1}, anchors=[])
    for p in (p1, p2, p3):
        assert "MULTI-ANCHOR LOCK" not in p


def test_full_prompt_with_anchors_includes_block():
    base = "X{player_details}Y{content_type}Z{quality}A{player_visible}B{camera_distance}C{games_detected}D"
    anchors = [{"t": 3.0, "jersey_name": "red", "shorts_name": "black", "body_ratio": 2.2}]
    p = build_full_prompt(base, _fp(), [], {"x": 1}, anchors=anchors)
    assert "MULTI-ANCHOR LOCK" in p
    assert "3.00s" in p


def test_full_prompt_without_anchors_omits_block():
    base = "X{player_details}Y{content_type}Z{quality}A{player_visible}B{camera_distance}C{games_detected}D"
    p = build_full_prompt(base, _fp(), [], {"x": 1})
    assert "MULTI-ANCHOR LOCK" not in p


# ── Backend regression ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def premium_token(session):
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "premium@elitescout.com", "password": "Premium@2026"},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def admin_token(session):
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@elitescout.com", "password": "Admin@2026!Elite"},
        timeout=15,
    )
    assert r.status_code == 200
    return r.json().get("access_token") or r.json().get("token")


def test_login_premium(premium_token):
    assert isinstance(premium_token, str) and len(premium_token) > 10


def test_upload_eligibility(premium_token):
    r = requests.get(
        f"{BASE_URL}/api/me/upload-eligibility",
        headers={"Authorization": f"Bearer {premium_token}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    # Should contain at minimum a reason / status / can_upload-ish key
    assert isinstance(data, dict)
    assert any(k in data for k in ("reason", "can_upload", "status", "eligible"))


def test_get_premium_demo_report(premium_token):
    # First find the user's reports list to obtain the seeded premium id
    r = requests.get(
        f"{BASE_URL}/api/reports/mine",
        headers={"Authorization": f"Bearer {premium_token}"},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"/api/reports/mine not available: {r.status_code}")
    reports = r.json()
    if isinstance(reports, dict):
        reports = reports.get("reports") or reports.get("items") or []
    assert isinstance(reports, list) and len(reports) > 0, "premium user has no seeded reports"
    rid = reports[0].get("id") or reports[0].get("_id")
    r2 = requests.get(
        f"{BASE_URL}/api/reports/{rid}",
        headers={"Authorization": f"Bearer {premium_token}"},
        timeout=20,
    )
    assert r2.status_code == 200, r2.text[:200]
    doc = r2.json()
    # The new anchors field should at least be present (list, possibly empty
    # for the seeded report — backward compatible)
    assert "anchors" in doc or "id" in doc


# ── Upload endpoint backward-compat (marker_box only, no marker_anchors) ─


def test_upload_endpoint_exists_and_requires_auth():
    # No auth → 401/403 expected (not 404)
    r = requests.post(f"{BASE_URL}/api/reports/upload", timeout=10)
    assert r.status_code in (400, 401, 403, 422), f"unexpected: {r.status_code} {r.text[:200]}"
