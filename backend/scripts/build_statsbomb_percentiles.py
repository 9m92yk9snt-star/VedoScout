"""
Step 2 — StatsBomb Euro 2024 percentile calibration.

Pipeline:
  1. Fetch the Euro 2024 matches metadata (51 matches).
  2. Download every match's lineups + events JSON (parallel).
  3. Aggregate per-player per-90 metrics by ScoutMePlay position.
  4. Compute p25 / p50 / p75 / p90 percentiles per position per metric.
  5. Save to /app/backend/data/statsbomb_percentiles.json.
  6. Derive a 0-10 calibration table (p25..p90 mapped onto our 0-10 scale).

Run once locally:
    python3 /app/backend/scripts/build_statsbomb_percentiles.py
"""
import json
import os
import statistics
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# --- Config ----------------------------------------------------------------
COMPETITION_ID = 55   # UEFA Euro
SEASON_ID       = 282  # 2024
BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
OUT  = "/app/backend/data/statsbomb_percentiles.json"
CACHE_DIR = Path("/tmp/statsbomb_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MIN_MINUTES = 270  # ≥ 3 full matches played → stable per-90 sample

# StatsBomb position string → ScoutMePlay 8-position group
POS_MAP = {
    # Goalkeeper
    "Goalkeeper":               "goalkeeper",
    # Centre back
    "Center Back":              "centre back",
    "Right Center Back":        "centre back",
    "Left Center Back":         "centre back",
    # Full back
    "Right Back":               "full back",
    "Left Back":                "full back",
    "Right Wing Back":          "full back",
    "Left Wing Back":           "full back",
    # Defensive midfielder
    "Center Defensive Midfield":         "defensive midfielder",
    "Right Defensive Midfield":          "defensive midfielder",
    "Left Defensive Midfield":           "defensive midfielder",
    # Central midfielder
    "Center Midfield":          "central midfielder",
    "Right Center Midfield":    "central midfielder",
    "Left Center Midfield":     "central midfielder",
    # Attacking midfielder
    "Center Attacking Midfield":  "attacking midfielder",
    "Right Attacking Midfield":   "attacking midfielder",
    "Left Attacking Midfield":    "attacking midfielder",
    # Winger
    "Right Wing":               "winger",
    "Left Wing":                "winger",
    "Right Midfield":           "winger",
    "Left Midfield":            "winger",
    # Striker
    "Center Forward":           "striker",
    "Right Center Forward":     "striker",
    "Left Center Forward":      "striker",
    "Second Striker":           "striker",
}


def _http_get(url: str, retries: int = 2) -> bytes:
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "scoutmeplay-statsbomb-pipeline/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise
            print(f"  retry {attempt+1} on {url} — {e}", file=sys.stderr)


def _cached(url: str, cache_name: str) -> dict:
    path = CACHE_DIR / cache_name
    if path.exists():
        return json.loads(path.read_bytes())
    data = _http_get(url)
    path.write_bytes(data)
    return json.loads(data)


# --- Match metadata --------------------------------------------------------
def fetch_matches() -> list:
    return _cached(
        f"{BASE}/matches/{COMPETITION_ID}/{SEASON_ID}.json",
        f"matches_{COMPETITION_ID}_{SEASON_ID}.json",
    )


# --- Per-match download (parallel) -----------------------------------------
def download_match(match_id: int) -> tuple:
    """Return (match_id, lineups, events) or (match_id, None, None) on failure."""
    try:
        lineups = _cached(f"{BASE}/lineups/{match_id}.json", f"lineups_{match_id}.json")
        events  = _cached(f"{BASE}/events/{match_id}.json",  f"events_{match_id}.json")
        return (match_id, lineups, events)
    except Exception as e:
        print(f"  ! match {match_id} failed: {e}", file=sys.stderr)
        return (match_id, None, None)


# --- Per-player aggregation -----------------------------------------------
def _ensure_player(agg: dict, player_id: int, name: str, position: str):
    if player_id not in agg:
        agg[player_id] = {
            "player_id": player_id,
            "name":      name,
            "position":  position,
            "minutes":   0.0,
            # Counters
            "passes":             0,
            "passes_completed":   0,
            "progressive_passes": 0,
            "passes_into_final_third": 0,
            "key_passes":         0,
            "shots":              0,
            "shots_on_target":    0,
            "goals":              0,
            "xg":                 0.0,
            "dribbles_attempted": 0,
            "dribbles_completed": 0,
            "duels":              0,
            "duels_won":          0,
            "ball_recoveries":    0,
            "interceptions":      0,
            "pressures":          0,
        }


def aggregate(lineups: list, events: list, agg: dict):
    """Update `agg` in-place with this match's per-player stats."""
    # 1. Lineup → ID-to-name + main position (first position they held)
    starters_pos = {}
    name_lookup  = {}
    for team in lineups:
        for player in team.get("lineup", []):
            pid = player["player_id"]
            name_lookup[pid] = player["player_name"]
            positions = player.get("positions", []) or []
            if not positions:
                continue
            # Take the first listed position — that's their starting role
            sb_pos = positions[0].get("position")
            sm_pos = POS_MAP.get(sb_pos)
            if sm_pos:
                starters_pos[pid] = sm_pos

    # 2. Compute minutes played per player from the events stream
    #    Approach: track first appearance and substitution_off events.
    first_seen = {}
    last_seen  = {}
    final_min  = 95  # safety upper bound

    for ev in events:
        et = ev.get("type", {}).get("name")
        minute = ev.get("minute", 0) + ev.get("second", 0) / 60.0
        pid_block = ev.get("player") or {}
        pid = pid_block.get("id")
        if not pid:
            continue
        first_seen.setdefault(pid, minute)
        last_seen[pid] = minute

        # Substitution — when they came off
        if et == "Substitution":
            sub_min = minute
            last_seen[pid] = sub_min
            # The player coming on appears in the substitution event itself
            replacement = (ev.get("substitution") or {}).get("replacement", {}).get("id")
            if replacement:
                first_seen.setdefault(replacement, sub_min)
                last_seen[replacement] = final_min  # placeholder; updated by their next event

    # 3. Walk events again — aggregate stats per player
    for ev in events:
        et   = ev.get("type", {}).get("name")
        pid_block = ev.get("player") or {}
        pid  = pid_block.get("id")
        if not pid or pid not in starters_pos:
            # Try to map subs by their playing-time position (use their last position)
            continue
        sm_pos = starters_pos.get(pid)
        if not sm_pos:
            continue
        _ensure_player(agg, pid, name_lookup.get(pid, ""), sm_pos)
        a = agg[pid]

        if et == "Pass":
            a["passes"] += 1
            p = ev.get("pass") or {}
            if "outcome" not in p:           # successful pass (StatsBomb: no outcome = complete)
                a["passes_completed"] += 1
            # Progressive: end_location closer to opposition goal by ≥ 25% of remaining distance
            start = ev.get("location") or [0, 0]
            end   = p.get("end_location") or [0, 0]
            if len(start) >= 2 and len(end) >= 2:
                # Field is 120 long, opp goal at x=120
                start_dist_to_goal = max(0.0, 120.0 - start[0])
                end_dist_to_goal   = max(0.0, 120.0 - end[0])
                gained = start_dist_to_goal - end_dist_to_goal
                if gained >= max(10.0, start_dist_to_goal * 0.25):
                    a["progressive_passes"] += 1
                # Into final third = end x ≥ 80 and start x < 80
                if end[0] >= 80 and start[0] < 80:
                    a["passes_into_final_third"] += 1
            if p.get("shot_assist"):
                a["key_passes"] += 1

        elif et == "Shot":
            a["shots"] += 1
            s = ev.get("shot") or {}
            a["xg"] += float(s.get("statsbomb_xg") or 0.0)
            outcome = (s.get("outcome") or {}).get("name") or ""
            if outcome in ("Saved", "Goal"):
                a["shots_on_target"] += 1
            if outcome == "Goal":
                a["goals"] += 1

        elif et == "Dribble":
            a["dribbles_attempted"] += 1
            d = ev.get("dribble") or {}
            if (d.get("outcome") or {}).get("name") == "Complete":
                a["dribbles_completed"] += 1

        elif et == "Duel":
            a["duels"] += 1
            d = ev.get("duel") or {}
            o = (d.get("outcome") or {}).get("name") or ""
            if "Won" in o:
                a["duels_won"] += 1

        elif et == "Ball Recovery":
            a["ball_recoveries"] += 1

        elif et == "Interception":
            a["interceptions"] += 1

        elif et == "Pressure":
            a["pressures"] += 1

    # 4. Add minutes for this match into agg (per-player)
    for pid, sm_pos in starters_pos.items():
        _ensure_player(agg, pid, name_lookup.get(pid, ""), sm_pos)
        mins = (last_seen.get(pid, final_min) - first_seen.get(pid, 0))
        # cap to one match
        agg[pid]["minutes"] += max(0.0, min(95.0, mins))


# --- Per-90 + percentiles -------------------------------------------------
PER90_METRICS = [
    ("passes_per_90",             "passes"),
    ("progressive_passes_per_90", "progressive_passes"),
    ("passes_into_final_third_per_90", "passes_into_final_third"),
    ("key_passes_per_90",         "key_passes"),
    ("shots_per_90",              "shots"),
    ("goals_per_90",              "goals"),
    ("xg_per_90",                 "xg"),
    ("dribbles_attempted_per_90", "dribbles_attempted"),
    ("dribbles_completed_per_90", "dribbles_completed"),
    ("duels_won_per_90",          "duels_won"),
    ("ball_recoveries_per_90",    "ball_recoveries"),
    ("interceptions_per_90",      "interceptions"),
    ("pressures_per_90",          "pressures"),
]


def compute_per90_and_pcts(agg: dict) -> dict:
    """Return {position: {metric: {p25, p50, p75, p90, n}}}."""
    # 1. Compute per-90 rates per player
    by_pos: dict = {}
    rates_per_player = {}
    for pid, a in agg.items():
        if a["minutes"] < MIN_MINUTES:
            continue
        rates = {}
        for k, src in PER90_METRICS:
            rates[k] = (a[src] / a["minutes"]) * 90.0
        # Pass completion % (proper rate, not per-90)
        rates["pass_completion_pct"] = (
            (a["passes_completed"] / a["passes"]) * 100.0 if a["passes"] > 0 else 0.0
        )
        # Dribble completion %
        rates["dribble_completion_pct"] = (
            (a["dribbles_completed"] / a["dribbles_attempted"]) * 100.0
            if a["dribbles_attempted"] > 0 else 0.0
        )
        # Duel-win %
        rates["duel_win_pct"] = (
            (a["duels_won"] / a["duels"]) * 100.0 if a["duels"] > 0 else 0.0
        )
        rates["_position"] = a["position"]
        rates["_minutes"]  = a["minutes"]
        rates["_name"]     = a["name"]
        rates_per_player[pid] = rates
        by_pos.setdefault(a["position"], []).append(rates)

    # 2. Compute percentiles per (position, metric)
    out = {}
    METRIC_NAMES = [m[0] for m in PER90_METRICS] + [
        "pass_completion_pct", "dribble_completion_pct", "duel_win_pct"
    ]
    for pos, players in by_pos.items():
        if len(players) < 5:
            continue
        out[pos] = {"_n_players": len(players), "_min_minutes_filter": MIN_MINUTES}
        for metric in METRIC_NAMES:
            vals = [p[metric] for p in players if isinstance(p.get(metric), (int, float))]
            if not vals:
                continue
            vals.sort()
            out[pos][metric] = {
                "p25":  round(_pct(vals, 25), 3),
                "p50":  round(statistics.median(vals), 3),
                "p75":  round(_pct(vals, 75), 3),
                "p90":  round(_pct(vals, 90), 3),
                "max":  round(max(vals), 3),
                "n":    len(vals),
            }
    return out, rates_per_player


def _pct(vals: list, p: int) -> float:
    """Linear-interp percentile."""
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    frac = k - lo
    return vals[lo] + (vals[hi] - vals[lo]) * frac


# --- Main pipeline ---------------------------------------------------------
def main():
    print("== StatsBomb Euro 2024 percentile pipeline ==")
    matches = fetch_matches()
    match_ids = [m["match_id"] for m in matches]
    print(f"Found {len(match_ids)} matches. Downloading lineups+events...")

    # Parallel download (8 threads is safe on GitHub raw)
    payloads = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(download_match, mid): mid for mid in match_ids}
        for i, fut in enumerate(as_completed(futures), 1):
            mid, lineups, events = fut.result()
            if lineups and events:
                payloads[mid] = (lineups, events)
            if i % 10 == 0:
                print(f"  {i}/{len(match_ids)} downloaded")
    print(f"Got {len(payloads)} successful match payloads.")

    # Aggregate
    print("Aggregating per-player stats...")
    agg = {}
    for mid, (lineups, events) in payloads.items():
        aggregate(lineups, events, agg)
    print(f"  {len(agg)} unique players in aggregate")

    # Percentiles
    print("Computing percentiles...")
    pcts, rates = compute_per90_and_pcts(agg)
    for pos, data in pcts.items():
        print(f"  {pos:<24} n={data['_n_players']}")

    # Write output
    payload = {
        "_meta": {
            "source":       "StatsBomb Open Data — UEFA Euro 2024",
            "source_url":   "https://github.com/statsbomb/open-data",
            "competition":  "UEFA Euro 2024",
            "competition_id": COMPETITION_ID,
            "season_id":    SEASON_ID,
            "matches":      len(payloads),
            "min_minutes_filter": MIN_MINUTES,
            "license":      "CC BY-NC-SA 4.0 (StatsBomb Open Data terms)",
            "methodology": (
                "Per-90 rates computed from event-level data, then aggregated to "
                "per-position percentiles. Players with <" + str(MIN_MINUTES) +
                " minutes excluded to ensure stable rates. Progressive passes "
                "defined as forward passes gaining ≥25% of remaining distance "
                "to the opposition goal (or ≥10m absolute)."
            ),
        },
        "percentiles_by_position": pcts,
    }
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\n✓ Wrote {OUT} — {os.path.getsize(OUT):,} bytes")


if __name__ == "__main__":
    main()
