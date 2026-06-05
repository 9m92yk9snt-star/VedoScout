"""
Step 2 — StatsBomb Euro 2024 calibration tests.

Verifies the pro-calibration block lands correctly on the API response and
the data integrity of the underlying percentile dataset.
"""
import json
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com"
).rstrip("/")
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"

STATSBOMB_PATH = "/app/backend/data/statsbomb_percentiles.json"
EIGHT_POSITIONS = [
    "goalkeeper", "centre back", "full back", "defensive midfielder",
    "central midfielder", "attacking midfielder", "winger", "striker",
]


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASSWORD}, timeout=20)
    assert r.status_code == 200
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def lukas_report(token):
    h = {"Authorization": f"Bearer {token}"}
    rs = requests.get(f"{BASE_URL}/api/reports/mine", headers=h, timeout=20)
    paid = [r for r in rs.json() if r.get("is_paid") or r.get("manually_unlocked")]
    rid = paid[0]["id"]
    r = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=h, timeout=120)
    return r.json()


# ---------- Layer 1 (dataset integrity) ----------

def test_statsbomb_dataset_loaded():
    with open(STATSBOMB_PATH) as f:
        d = json.load(f)
    meta = d.get("_meta", {})
    assert meta.get("competition_id") == 55
    assert meta.get("season_id") == 282
    assert meta.get("matches", 0) >= 45  # we expect 51
    pcts = d.get("percentiles_by_position", {})
    # At minimum, the 4 main outfield positions must be present
    for required in ["attacking midfielder", "central midfielder", "centre back", "striker"]:
        assert required in pcts, f"missing position: {required}"
        block = pcts[required]
        assert block.get("_n_players", 0) >= 5
        # Must have key metrics
        for metric in ["pass_completion_pct", "progressive_passes_per_90", "xg_per_90"]:
            assert metric in block, f"{required} missing metric {metric}"
            mp = block[metric]
            # p25 <= p50 <= p75 <= p90 (data sanity)
            assert mp["p25"] <= mp["p50"] <= mp["p75"] <= mp["p90"]


def test_statsbomb_realistic_pro_pass_completion():
    """Spot-check: CB p75 pass completion should be ≥85% (centre backs are accurate)."""
    with open(STATSBOMB_PATH) as f:
        d = json.load(f)
    cb = d["percentiles_by_position"]["centre back"]["pass_completion_pct"]
    assert cb["p75"] >= 85.0, f"CB p75 pass completion suspiciously low: {cb['p75']}"
    assert cb["p75"] <= 99.0, "CB p75 unreasonably high"


def test_statsbomb_realistic_striker_xg():
    """Spot-check: striker p75 xG/90 should be 0.3-0.7 (real elite striker range)."""
    with open(STATSBOMB_PATH) as f:
        d = json.load(f)
    s = d["percentiles_by_position"]["striker"]["xg_per_90"]
    assert 0.20 <= s["p75"] <= 0.90, f"Striker p75 xG/90 looks wrong: {s['p75']}"


# ---------- API contract ----------

def test_calibration_attached_to_report(lukas_report):
    cal = lukas_report.get("statsbomb_calibration")
    assert isinstance(cal, dict)
    assert cal.get("position")
    assert cal.get("position_n") and cal["position_n"] >= 5
    assert isinstance(cal.get("rows"), list) and len(cal["rows"]) >= 6
    assert cal.get("source")
    assert "statsbomb" in cal.get("source_url", "").lower()
    assert cal.get("matches") and cal["matches"] >= 45


def test_calibration_rows_have_complete_data(lukas_report):
    cal = lukas_report["statsbomb_calibration"]
    for r in cal["rows"]:
        assert r.get("attribute_key") and r.get("attribute_label")
        assert isinstance(r.get("score"), (int, float))
        assert r.get("statsbomb_metric") and r.get("statsbomb_metric_label")
        assert r.get("bucket") in ("p90", "p75", "p50", "p25", "below_p25")
        assert r.get("bucket_label")
        for p in ("pro_p25", "pro_p50", "pro_p75", "pro_p90"):
            assert p in r, f"row missing {p}: {r}"


def test_calibration_summary_counts_match_rows(lukas_report):
    cal = lukas_report["statsbomb_calibration"]
    counts = {k: 0 for k in ("p90", "p75", "p50", "p25", "below_p25")}
    for r in cal["rows"]:
        counts[r["bucket"]] += 1
    assert counts == cal["summary"]


def test_calibration_buckets_anchored_to_score(lukas_report):
    """A score of 9+ should always land in p90; 8 in p75; 7 in p50; 6 in p25."""
    cal = lukas_report["statsbomb_calibration"]
    expected = {9: "p90", 8: "p75", 7: "p50", 6: "p25"}
    for r in cal["rows"]:
        s = int(r["score"])
        if s in expected:
            assert r["bucket"] == expected[s], (
                f"score {s} should bucket to {expected[s]} but got {r['bucket']} "
                f"for attr {r['attribute_key']}"
            )
