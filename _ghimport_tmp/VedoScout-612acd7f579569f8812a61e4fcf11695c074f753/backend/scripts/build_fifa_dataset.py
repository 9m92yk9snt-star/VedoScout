"""
Offline pre-processor for the Kaggle FIFA dataset.

Pulls the public mirror of `fifa.csv` (16k players, 81 columns) once,
filters to senior pros worth comparing against (overall >= 68), maps the
FIFA attribute columns to ScoutMePlay's 0-10 schema, and emits a compact
JSON blob the backend can load once on startup.

Run once locally:
    python3 /app/backend/scripts/build_fifa_dataset.py

Output:
    /app/backend/data/fifa_players.json  (~250 KB, ~5k players)
"""
import csv
import json
import os
import sys
import urllib.request

SRC = "https://raw.githubusercontent.com/mbdelaresma/football-position-classification/main/players_22.csv"
OUT = "/app/backend/data/fifa_players.json"
MIN_OVERALL = 68  # keeps every senior pro worth referencing

# FIFA col -> ScoutMePlay attribute key. Maps to the lowest-friction FIFA-22
# equivalent from FULL_REPORT_PROMPT / age_profiles.json. Multi-source = average.
ATTR_MAP = {
    "first_touch":          ["ball_ctrl"],
    "ball_control":         ["ball_ctrl"],
    "dribbling":            ["dribbling"],
    "passing":              ["short_pass"],
    "long_passing":         ["long_pass"],
    "shooting":             ["finishing", "long_shots"],
    "one_v_one":            ["dribbling", "curve"],
    "crossing":             ["crossing"],
    "timing_of_runs":       ["positioning"],
    "off_ball_movement":    ["positioning"],
    "scanning":             ["vision"],
    "decision_making":      ["composure"],
    "positioning":          ["positioning"],
    "vision":               ["vision"],
    "composure":            ["composure"],
    "acceleration":         ["acceleration"],
    "speed":                ["sprint"],
    "agility":              ["agility"],
    "balance":              ["balance"],
    "intensity":            ["stamina"],
    "work_rate":            ["stamina"],
    "courage_in_duels":     ["aggression"],
    "body_control":         ["balance", "agility"],
    "confidence":           ["composure"],
}

# FIFA player_positions strings -> ScoutMePlay position groups
POS_MAP = {
    "GK":  "goalkeeper",
    "CB":  "centre back",
    "RB":  "full back", "LB": "full back", "RWB": "full back", "LWB": "full back",
    "CDM": "defensive midfielder",
    "CM":  "central midfielder", "RM": "central midfielder", "LM": "central midfielder",
    "CAM": "attacking midfielder",
    "RW":  "winger", "LW": "winger", "RF": "winger", "LF": "winger",
    "ST":  "striker", "CF": "striker",
}


def first_pos(player_positions: str) -> str:
    """FIFA stores 'ST, LW, RW' — take the first listed (primary)."""
    if not player_positions:
        return ""
    primary = player_positions.split(",")[0].strip().upper()
    return POS_MAP.get(primary, "")


def fifa_to_10(v: int) -> float:
    """FIFA 0-99 → ScoutMePlay 0-10."""
    return round(float(v) / 9.9, 2)


def derive_build(height_cm: int, weight_kg: int, accel: int, drib: int) -> str:
    """Same 4-bucket build classifier the matcher uses for the kid."""
    h = int(height_cm or 0)
    if h <= 175 and int(drib) >= 80:
        return "small_technical"
    if h >= 188:
        return "tall_powerful"
    if int(accel) >= 85:
        return "athletic_runner"
    return "compact_balanced"


def main():
    print(f"Downloading {SRC} ...")
    try:
        req = urllib.request.Request(SRC, headers={"User-Agent": "scoutmeplay-offline-pipeline"})
        raw = urllib.request.urlopen(req, timeout=90).read().decode("utf-8")
    except Exception as e:
        print(f"FAIL download: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Got {len(raw):,} bytes — parsing...")
    reader = csv.DictReader(raw.splitlines())
    out_players = []
    skipped = 0

    for row in reader:
        try:
            overall = int(row.get("overall") or 0)
        except ValueError:
            skipped += 1
            continue
        if overall < MIN_OVERALL:
            skipped += 1
            continue
        position = first_pos(row.get("player_positions", ""))
        if not position:
            skipped += 1
            continue

        # Map FIFA → ScoutMePlay 0-10
        attrs = {}
        for sm_key, sources in ATTR_MAP.items():
            vals = []
            for col in sources:
                v = row.get(col)
                if v and v.strip() and v != "":
                    try:
                        vals.append(int(float(v)))
                    except ValueError:
                        pass
            if vals:
                avg = sum(vals) / len(vals)
                attrs[sm_key] = fifa_to_10(avg)

        # Build derivation
        try:
            height = int(row.get("height_cm") or 0)
            weight = int(row.get("weight_kg") or 0)
            accel  = int(row.get("acceleration") or 0)
            drib   = int(row.get("dribbling") or 0)
        except ValueError:
            height = weight = accel = drib = 0
        build = derive_build(height, weight, accel, drib)

        out_players.append({
            "name":       row.get("short_name", "").strip(),
            "long_name":  row.get("long_name", "").strip(),
            "age":        int(row.get("age") or 0),
            "height_cm":  height,
            "weight_kg":  weight,
            "club":       (row.get("club_name") or "").strip(),
            "league":     (row.get("league_name") or "").strip(),
            "nationality": "",  # not present in this mirror
            "overall":    overall,
            "potential":  int(row.get("potential") or overall),
            "position":   position,
            "preferred_foot": (row.get("preferred_foot") or "").strip().lower(),
            "weak_foot":  int(row.get("weak_foot") or 3),
            "build":      build,
            "attrs":      attrs,
        })

    # Final pass — sort by overall desc so the matcher can early-exit ties to the better-known pro
    out_players.sort(key=lambda p: (-p["overall"], -p["potential"]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({
            "_meta": {
                "source": SRC,
                "source_dataset": "Kaggle FIFA 22 — Stefano Leone (career-mode complete dataset)",
                "min_overall_filter": MIN_OVERALL,
                "rows_kept": len(out_players),
                "rows_skipped": skipped,
                "attribute_map": ATTR_MAP,
                "score_scale": "0-10 (FIFA 0-99 ÷ 9.9)",
                "license_note": (
                    "FIFA attribute ratings © EA Sports. Used here in a derived, "
                    "non-republished form for similarity matching only — not for "
                    "redistribution. Filtered to senior pros with overall >= "
                    f"{MIN_OVERALL}."
                ),
            },
            "players": out_players,
        }, f, separators=(",", ":"))

    out_size = os.path.getsize(OUT)
    print(f"✓ Wrote {OUT} — {len(out_players):,} players, {out_size:,} bytes "
          f"(skipped {skipped:,} rows below threshold or unmappable position)")


if __name__ == "__main__":
    main()
