"""Session 123 tests — TASK A (extract_json robustness + retry structure) and TASK B (pinned Top-3 cards grep + live render).

Testing strategy:
- Directly import extract_json and stress-test 13 scenarios (10 valid, 3 invalid).
- Verify call_gemini_with_video retry structure via source inspection (no live Gemini call).
- Verify ReportPage.jsx contains the pinned Top-3 cards + Zap/Target imports (grep).
- Regression: existing iter52 (21 cases) and e2e_full_audit (10 cases) suites remain green (run separately).
"""

import os
import re
import sys
import json
import pytest

BACKEND_DIR = "/app/backend"
sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
# TASK A H1 — extract_json stress tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def extract_json():
    # Import lazily to avoid the full FastAPI app startup cost — server.py has
    # module-level side effects but is safe under `python -c "import server"`.
    from server import extract_json as _fn
    return _fn


class TestExtractJsonHappyPath:
    """10 valid inputs — must ALL parse into a dict"""

    def test_simple_object(self, extract_json):
        d = extract_json('{"a": 1, "b": "x"}')
        assert d == {"a": 1, "b": "x"}

    def test_fenced_json(self, extract_json):
        d = extract_json('```json\n{"k": 42}\n```')
        assert d == {"k": 42}

    def test_fenced_no_language(self, extract_json):
        d = extract_json('```\n{"k": 42}\n```')
        assert d == {"k": 42}

    def test_prose_prefix(self, extract_json):
        d = extract_json('Here is the JSON:\n{"score": 88}')
        assert d == {"score": 88}

    def test_prose_suffix(self, extract_json):
        d = extract_json('{"score": 88}\n\nHope this helps!')
        assert d == {"score": 88}

    def test_trailing_comma(self, extract_json):
        d = extract_json('{"a": 1, "b": 2,}')
        assert d == {"a": 1, "b": 2}

    def test_smart_quotes(self, extract_json):
        # Smart quotes around keys and values (as Gemini sometimes emits)
        d = extract_json('{\u201ckey\u201d: \u201cvalue\u201d}')
        assert d == {"key": "value"}

    def test_prose_around_fence(self, extract_json):
        d = extract_json('Sure! Here is the JSON:\n```json\n{"x": 1}\n```\nLet me know if you want changes.')
        assert d == {"x": 1}

    def test_nested_braces_deep(self, extract_json):
        payload = '{"outer": {"inner": {"deep": [1,2,{"leaf": true}]}}}'
        d = extract_json(f'Prose before {payload} and prose after.')
        assert d == {"outer": {"inner": {"deep": [1, 2, {"leaf": True}]}}}

    def test_two_fences_take_larger(self, extract_json):
        text = (
            'Example only:\n```json\n{"a":1}\n```\n\n'
            'And here is the real one:\n```json\n{"real": true, "score": 99, "items": [1,2,3]}\n```'
        )
        d = extract_json(text)
        # Should choose the LARGER fence
        assert d.get("real") is True
        assert d.get("score") == 99


class TestExtractJsonReject:
    """3 invalid inputs — must raise ValueError with categorized prefix"""

    def test_empty_response_rejected(self, extract_json):
        with pytest.raises(ValueError) as exc:
            extract_json("   ")
        assert "EMPTY_RESPONSE" in str(exc.value)

    def test_no_json_rejected(self, extract_json):
        with pytest.raises(ValueError) as exc:
            extract_json("Sorry, I cannot provide that.")
        assert "NO_JSON_FOUND" in str(exc.value)

    def test_list_not_dict_rejected(self, extract_json):
        # A bare JSON array — extract_json requires a dict.
        # The balanced-brace walker still finds the inner object if any, so
        # supply a list that contains no top-level {} — pure array.
        with pytest.raises(ValueError) as exc:
            extract_json("[1, 2, 3]")
        # Either NO_JSON_FOUND (no braces) or PARSED_NOT_DICT if walker were to slice — either is fine
        msg = str(exc.value)
        assert ("NO_JSON_FOUND" in msg) or ("PARSED_NOT_DICT" in msg) or ("ALL_CANDIDATES_FAILED" in msg)


class TestExtractJsonExtras:
    """Extra edge cases the fix explicitly claims to handle"""

    def test_zero_width_and_bom(self, extract_json):
        # BOM + zero-width chars around and inside the JSON
        text = '\ufeff\u200b{"a": 1}\u200b'
        d = extract_json(text)
        assert d == {"a": 1}

    def test_string_with_braces_inside(self, extract_json):
        # Balanced-brace scanner must NOT confuse braces inside string literals
        text = '{"quote": "he said \\"hello { world }\\" today"}'
        d = extract_json(text)
        assert d["quote"] == 'he said "hello { world }" today'


# ---------------------------------------------------------------------------
# TASK A H2 — retry-once structure
# ---------------------------------------------------------------------------

class TestRetryStructure:
    @pytest.fixture(scope="class")
    def source(self):
        with open(os.path.join(BACKEND_DIR, "server.py"), "r", encoding="utf-8") as f:
            return f.read()

    def test_retry_chat_variable_exists(self, source):
        assert "retry_chat = LlmChat(" in source

    def test_retry_session_id_suffix(self, source):
        assert '-retry"' in source or "-retry'" in source

    def test_strict_prompt_prepend(self, source):
        assert "strict_prompt" in source
        assert "previous response could not be parsed" in source.lower()

    def test_502_on_double_fail(self, source):
        # HTTPException with 502 status code appears after retry catch
        assert re.search(r"status_code\s*=\s*502", source), "Expected HTTPException(status_code=502) after retry fail"

    def test_no_generic_500_invalid_format(self, source):
        # The old generic 500 with "AI analysis returned invalid format" must NOT
        # be raised anymore from the retry/parse path.
        assert 'AI analysis returned invalid format' not in source, \
            "The old generic 500 error message should be removed"

    def test_first_err_captured_and_logged(self, source):
        assert "first_err" in source
        # We log the first failure BEFORE retrying
        assert re.search(r"parse failed", source, re.IGNORECASE)

    def test_retry_logs_success(self, source):
        assert "parsed on RETRY" in source or "on RETRY" in source


# ---------------------------------------------------------------------------
# TASK A H3 — categorized error prefixes present in extract_json
# ---------------------------------------------------------------------------

class TestCategorizedPrefixes:
    @pytest.fixture(scope="class")
    def source(self):
        with open(os.path.join(BACKEND_DIR, "server.py"), "r", encoding="utf-8") as f:
            return f.read()

    def test_empty_response_prefix(self, source):
        assert "EMPTY_RESPONSE" in source

    def test_no_json_found_prefix(self, source):
        assert "NO_JSON_FOUND" in source

    def test_all_candidates_failed_prefix(self, source):
        assert "ALL_CANDIDATES_FAILED" in source

    def test_parsed_not_dict_prefix(self, source):
        assert "PARSED_NOT_DICT" in source


# ---------------------------------------------------------------------------
# TASK B — pinned Top-3 cards (I1, I2, I3) via grep
# ---------------------------------------------------------------------------

REPORT_PAGE = "/app/frontend/src/pages/ReportPage.jsx"


class TestPinnedTop3Cards:
    @pytest.fixture(scope="class")
    def src(self):
        with open(REPORT_PAGE, "r", encoding="utf-8") as f:
            return f.read()

    def test_zap_and_target_imported(self, src):
        # I2 — Zap + Target must appear in the lucide-react import block
        import_block = re.search(r"from ['\"]lucide-react['\"]", src)
        assert import_block, "lucide-react import not found"
        # Zap + Target present anywhere in top imports
        header = src[: import_block.end() + 10]
        # Zap/Target could be on prev lines
        top = src[: import_block.end()]
        assert "Zap" in top and "Target" in top, "Zap or Target missing from lucide-react imports"

    def test_pinned_grid_testid(self, src):
        assert 'data-testid="report-pinned-top3-cards"' in src

    def test_strengths_card_testid(self, src):
        assert 'data-testid="report-pinned-strengths"' in src

    def test_focus_card_testid(self, src):
        assert 'data-testid="report-pinned-focus"' in src

    def test_border_colors(self, src):
        assert "border-l-emerald-400" in src
        assert "border-l-amber-400" in src

    def test_labels_danish(self, src):
        assert "Top 3 Styrker" in src
        assert "Top 3 Fokusområder" in src

    def test_slice_top3(self, src):
        # Both cards slice(0,3)
        matches = re.findall(r"\.slice\(0,\s*3\)", src)
        assert len(matches) >= 2, f"Expected at least 2 .slice(0,3) calls, found {len(matches)}"

    def test_fallback_areas_of_concern(self, src):
        # The focus card falls back to areas_of_concern
        assert "areas_of_concern" in src
        assert "development_priorities" in src

    def test_empty_state_messages(self, src):
        # I3 — italic empty-state copy
        assert "Ingen styrker registreret endnu" in src
        assert "Ingen fokusområder registreret endnu" in src

    def test_pinned_cards_above_radar(self, src):
        # I1 — the pinned cards fragment must appear BEFORE <PerformanceRadarHero
        idx_pinned = src.find('data-testid="report-pinned-top3-cards"')
        idx_radar = src.find("<PerformanceRadarHero")
        assert idx_pinned != -1 and idx_radar != -1
        assert idx_pinned < idx_radar, "Pinned Top-3 cards must render ABOVE the radar hero"


# ---------------------------------------------------------------------------
# Regression sanity — required text still present (Session 116-122)
# ---------------------------------------------------------------------------

class TestSession122Regressions:
    @pytest.fixture(scope="class")
    def src(self):
        with open(os.path.join(BACKEND_DIR, "server.py"), "r", encoding="utf-8") as f:
            return f.read()

    def test_r2_flush_before_ready_comment(self, src):
        assert "BEFORE marking the report" in src

    def test_gate_skipped_paid(self, src):
        assert src.count("gate_skipped_paid") >= 1

    def test_litellm_extra_params_timeout(self, src):
        assert "extra_params" in src and "timeout" in src

    def test_no_chef_or_cooking(self):
        # Grep for chef/Cooking across backend excluding tests
        import subprocess
        r = subprocess.run(
            ["grep", "-rE", r"\bchef\b|Cooking", "/app/backend", "--include=*.py",
             "--exclude-dir=tests", "--exclude-dir=__pycache__", "--exclude-dir=venv"],
            capture_output=True, text=True,
        )
        # 0 hits => stdout empty
        assert r.stdout.strip() == "", f"Unexpected chef/Cooking hits:\n{r.stdout}"
