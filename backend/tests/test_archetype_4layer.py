"""
Iteration 9 — 4-Layer Intelligence Stack validation.

Verifies:
  - Layer 1 (catalog): every position has the new `profile` and `academy_bio` schema.
  - Layer 2 (multi-dimensional ranker): the matcher returns a `lenses` block
    with Style / Build / Role / Career-path twins.
  - Layer 3 (Gemini narrative): the report serialization attaches a non-empty
    narrative when an archetype is found.
  - Layer 4 (UI contract): the API still ships the legacy archetype fields
    (id, name, club, league, tier, match_strength, alternatives) so the
    frontend rendering does not regress.
"""
import os
import json
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://scout-ai-pro-1.preview.emergentagent.com"
).rstrip("/")
PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"

ARCHETYPES_PATH = "/app/backend/data/archetypes.json"
EIGHT_POSITIONS = [
    "goalkeeper", "centre back", "full back", "defensive midfielder",
    "central midfielder", "attacking midfielder", "winger", "striker",
]
LENS_KEYS = ["style", "build", "role", "path"]
FIFA_LENS_KEYS = ["style", "build", "role", "path", "fifa"]


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="session")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def lukas_report(headers):
    rs = requests.get(f"{BASE_URL}/api/reports/mine", headers=headers, timeout=20)
    assert rs.status_code == 200
    reports = rs.json()
    paid = [r for r in reports if r.get("is_paid") or r.get("manually_unlocked")]
    assert paid, "no unlocked report found for premium user"
    rid = paid[0]["id"]
    # First fetch may take a few seconds for the Gemini narrative — retry once.
    r = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Layer 1: catalog schema sanity ----------

def test_layer1_every_position_has_profile_schema():
    with open(ARCHETYPES_PATH, "r") as f:
        catalog = json.load(f)
    for pos in EIGHT_POSITIONS:
        archs = catalog.get(pos)
        assert isinstance(archs, list) and archs, f"position '{pos}' missing in catalog"
        for arch in archs:
            prof = arch.get("profile") or {}
            assert prof.get("build"), f"archetype {arch['id']} ({pos}) missing profile.build"
            assert prof.get("role"),  f"archetype {arch['id']} ({pos}) missing profile.role"
            # foot and path are nice-to-have but recommended
            assert "foot" in prof,    f"archetype {arch['id']} ({pos}) missing profile.foot"


def test_layer1_attacking_midfielders_have_academy_bio():
    """The AM position MUST have bios across the 4 critical age brackets."""
    with open(ARCHETYPES_PATH, "r") as f:
        catalog = json.load(f)
    ams = catalog.get("attacking midfielder") or []
    assert ams
    required_brackets = ["11-12", "13-14", "15-17", "18-21"]
    for am in ams:
        bio = am.get("academy_bio") or {}
        for br in required_brackets:
            assert bio.get(br) and len(bio[br]) > 40, (
                f"archetype {am['id']} missing or thin academy_bio[{br}]"
            )


# ---------- Layer 2: 4-Lens matcher ----------

def test_layer2_lukas_returns_lenses_block(lukas_report):
    arch = lukas_report.get("archetype")
    assert isinstance(arch, dict) and arch.get("id"), "archetype missing or developing"
    lenses = arch.get("lenses")
    assert isinstance(lenses, dict)
    for k in LENS_KEYS:
        assert k in lenses, f"lens key '{k}' missing"
        assert lenses[k].get("name"), f"lens '{k}' has no archetype name"
        assert lenses[k].get("lens_label"), f"lens '{k}' has no label"
        assert isinstance(lenses[k].get("score"), (int, float))
        # Iteration-9 fix: the lens score is advertised as `/10` on the UI,
        # so the backend MUST clip it to [0, 10].
        assert 0.0 <= lenses[k]["score"] <= 10.0, (
            f"lens '{k}' score {lenses[k]['score']} violates 0-10 contract"
        )


def test_layer2_legacy_fields_still_present(lukas_report):
    """The frontend still uses these top-level fields — must not regress."""
    arch = lukas_report["archetype"]
    for field in ("id", "name", "club", "league", "tier", "match_strength", "alternatives"):
        assert field in arch, f"legacy archetype field '{field}' missing"
    assert isinstance(arch["alternatives"], list)


def test_layer2_inferred_profile_is_attached(lukas_report):
    arch = lukas_report["archetype"]
    # _infer_build is purely deterministic and must always produce a value
    assert arch.get("inferred_build") in (
        "small_technical", "compact_balanced", "athletic_runner", "tall_powerful"
    )
    # role inference may be None for sparse positions, but for an unlocked
    # premium AM report it should resolve.
    pos = (lukas_report.get("player_details") or {}).get("position", "")
    if "midfielder" in pos.lower():
        assert arch.get("inferred_role"), "inferred_role missing on midfielder report"


# ---------- Layer 3: Gemini narrative ----------

def test_layer3_narrative_attached(lukas_report, headers):
    arch = lukas_report["archetype"]
    if arch.get("developing"):
        pytest.skip("developing archetype, narrative is skipped by design")
    # The narrative is generated asynchronously on first paid fetch — it
    # may still be missing on the very first call. Re-fetch once.
    if not arch.get("narrative"):
        time.sleep(4)
        r = requests.get(
            f"{BASE_URL}/api/reports/{lukas_report['id']}", headers=headers, timeout=120,
        )
        assert r.status_code == 200
        arch = (r.json() or {}).get("archetype") or {}
    assert isinstance(arch.get("narrative"), str), "no narrative produced"
    narrative = arch["narrative"]
    # Soft length sanity (50-70 words target → allow 20-200 words)
    word_count = len(narrative.split())
    assert 20 <= word_count <= 200, f"narrative length unreasonable: {word_count} words"


def test_layer3_narrative_is_cached(lukas_report, headers):
    """Two fetches in a row should return the same narrative — proving caching."""
    rid = lukas_report["id"]
    r1 = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=120).json()
    r2 = requests.get(f"{BASE_URL}/api/reports/{rid}", headers=headers, timeout=30).json()
    n1 = (r1.get("archetype") or {}).get("narrative")
    n2 = (r2.get("archetype") or {}).get("narrative")
    if not n1 or not n2:
        pytest.skip("narrative still generating — cache test not applicable")
    assert n1 == n2


# ---------- Layer 4: UI contract ----------

def test_layer4_age_bracket_and_bio_chunk(lukas_report):
    arch = lukas_report["archetype"]
    if arch.get("developing"):
        pytest.skip("developing — bio chunk not applicable")
    # bracket should match the player's age
    age = int((lukas_report.get("player_details") or {}).get("age") or 0)
    bracket = arch.get("age_bracket_used")
    assert bracket in ("8-10", "11-12", "13-14", "15-17", "18-21"), f"bad bracket: {bracket}"
    # bio chunk must be a verbatim string from the catalog (no Gemini hallucination here)
    assert arch.get("academy_bio_chunk"), "bio chunk missing"
    with open(ARCHETYPES_PATH, "r") as f:
        catalog = json.load(f)
    position = (lukas_report["player_details"]["position"] or "").lower().strip()
    # match the catalog position (alias-tolerant)
    arch_list = catalog.get(position) or catalog.get(position.replace(" midfielder", "")) or []
    if not arch_list:
        # try fuzzy match
        for k in catalog:
            if k != "_meta" and position.split()[0] in k:
                arch_list = catalog[k]
                break
    catalog_entry = next((a for a in arch_list if a.get("id") == arch["id"]), None)
    assert catalog_entry, f"archetype {arch['id']} not found in catalog for position '{position}'"
    expected_bio = (catalog_entry.get("academy_bio") or {}).get(bracket)
    assert arch["academy_bio_chunk"] == expected_bio, "bio chunk does not match catalog"


# ---------- Layer 5: FIFA Data Twin (k-NN) ----------

def test_layer5_fifa_lens_returned_with_real_data(lukas_report):
    """The 5th lens (FIFA Data Twin) MUST be attached to a real archetype."""
    arch = lukas_report.get("archetype") or {}
    if arch.get("developing"):
        pytest.skip("developing archetype — FIFA lens not applicable")
    lenses = arch.get("lenses") or {}
    assert "fifa" in lenses, "FIFA k-NN lens missing from lenses block"
    fifa = lenses["fifa"]
    assert fifa.get("lens_label") == "FIFA data twin"
    assert fifa.get("name"), "FIFA lens has no pro name"
    assert fifa.get("club"), "FIFA lens has no club"
    assert isinstance(fifa.get("similarity_pct"), (int, float))
    # Hard cap test — similarity must NEVER exceed 92%
    assert 0.0 <= fifa["similarity_pct"] <= 92.0, (
        f"FIFA similarity {fifa['similarity_pct']} exceeds 92% credibility cap"
    )
    # Score is the 0-10 mirror, must be ≤ 9.2 (cap mirror)
    assert 0.0 <= fifa.get("score", 0) <= 9.2
    # nearest_attrs must be a list of 3 attribute names
    assert isinstance(fifa.get("nearest_attrs"), list)
    assert len(fifa["nearest_attrs"]) >= 1


def test_layer5_fifa_top5_neighbors_shipped(lukas_report):
    """The full top-5 neighbours block must be present for UI consumption."""
    arch = lukas_report.get("archetype") or {}
    if arch.get("developing"):
        pytest.skip("developing — FIFA panel not applicable")
    neighbors = arch.get("fifa_neighbors")
    assert isinstance(neighbors, list)
    assert 1 <= len(neighbors) <= 5
    for n in neighbors:
        assert n.get("name") and n.get("club"), f"incomplete neighbour: {n}"
        assert 0.0 <= n.get("similarity_pct", -1) <= 92.0
        assert isinstance(n.get("nearest_attrs"), list)
    # neighbors must be sorted by similarity desc
    sims = [n["similarity_pct"] for n in neighbors]
    assert sims == sorted(sims, reverse=True), "neighbors not sorted by similarity"


def test_layer5_fifa_meta_shipped(lukas_report):
    """The FIFA DB meta block must include source + size for the UI footnote."""
    arch = lukas_report.get("archetype") or {}
    if arch.get("developing"):
        pytest.skip("developing")
    meta = arch.get("fifa_db_meta") or {}
    assert meta.get("source"), "FIFA meta has no source"
    assert isinstance(meta.get("size"), int) and meta["size"] >= 1000


# ---------- Step 3: FBref-grade career_brief ----------

def test_step3_career_brief_on_modric_archetype(lukas_report):
    """Lukas's primary (Modric-type) must surface a career_brief string."""
    arch = lukas_report.get("archetype") or {}
    if arch.get("developing"):
        pytest.skip("developing")
    cb = arch.get("career_brief") or ""
    assert isinstance(cb, str) and len(cb) > 30, (
        f"career_brief missing or too short for primary archetype: {cb!r}"
    )
    # Spot-check: Modric brief should mention Croatia / Ballon d'Or
    assert "Croatia" in cb or "Modric" in cb or "Ballon" in cb


def test_step3_top_archetypes_have_career_brief():
    """At least 20 archetypes across the catalog should now have a career_brief."""
    with open(ARCHETYPES_PATH, "r") as f:
        catalog = json.load(f)
    enriched = 0
    for pos, archs in catalog.items():
        if pos.startswith("_") or not isinstance(archs, list):
            continue
        for a in archs:
            if isinstance(a.get("career_brief"), str) and len(a["career_brief"]) > 30:
                enriched += 1
    assert enriched >= 20, f"only {enriched} archetypes have career_brief — expected ≥20"
