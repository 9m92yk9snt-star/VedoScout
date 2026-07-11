"""
identity_verify.py — Layer A of the player-identity guarantee.

After the full report is generated, every evidence frame extracted at a
Gemini-claimed timestamp is cross-checked by a DIFFERENT model family
(OpenAI gpt-4o-mini vision via the Emergent LLM key): "is the tapped player
from the reference crops clearly visible in this frame?". Frames that fail
are re-windowed or dropped so the report never displays the wrong player.

Purely additive and best-effort — any error returns None (inconclusive) and
the pipeline behaves exactly as before this layer existed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logger = logging.getLogger(__name__)

VERIFY_PROVIDER = "openai"
VERIFY_MODEL = "gpt-4o"  # calibrated: 4o-mini misses small players; 4o is reliable
MAX_REF_CROPS = 3
MAX_PROFILE_CROPS = 5
MAX_PROFILE_WIDE = 3


def _b64(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


async def verify_frame_identity(
    api_key: str,
    session_id: str,
    ref_crop_paths: list[str],
    frame_path: str,
    jersey_name: str = "unclear",
    shorts_name: str = "unclear",
) -> bool | None:
    """Return True (tapped player visible), False (not visible / another
    same-kit player), or None (inconclusive / any error — do not overrule)."""
    try:
        refs = [
            ImageContent(image_base64=_b64(p))
            for p in ref_crop_paths[:MAX_REF_CROPS]
            if p and Path(p).exists()
        ]
        if not refs or not Path(frame_path).exists():
            return None
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=(
                "You verify football player identity across images. "
                "Respond with STRICT JSON only — no prose, no markdown."
            ),
        ).with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        prompt = (
            f"The first {len(refs)} image(s) are reference crops of ONE specific youth football player. "
            "First, identify the player's distinctive features from the reference crops yourself "
            "(kit colours, headwear, sleeves, socks, build). An automated kit-colour read said "
            f"'{jersey_name} jersey, {shorts_name} shorts' but it MAY BE INACCURATE — trust the images.\n"
            "NOTE: the player may be PARTIALLY HIDDEN in a reference crop (behind another player, only part "
            "of the body visible) — the player at the CENTRE of each crop is the target, not necessarily the "
            "most visible person in it.\n"
            "The LAST image is a frame from the match video.\n"
            "Question: is that SAME individual player visible anywhere in the frame, even if small or "
            "partially occluded behind other players? A partial but plausible presence counts as visible. "
            "Do not confuse them with teammates in an identical kit — check build, hair, socks, boots.\n"
            'Respond ONLY with JSON: {"match": true|false, "confidence": "high"|"medium"|"low", '
            '"why": "<one short sentence>"}'
        )
        msg = UserMessage(text=prompt, file_contents=[*refs, ImageContent(image_base64=_b64(frame_path))])
        resp = await asyncio.wait_for(chat.send_message(msg), timeout=60)
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json.loads(text[start:end + 1])
        match = bool(data.get("match"))
        conf = str(data.get("confidence", "")).lower()
        logger.info(f"[identity] {session_id}: match={match} conf={conf} why={str(data.get('why'))[:120]}")
        # Conservative policy: only a HIGH-confidence rejection drops a frame;
        # a LOW-confidence approval never counts as verified.
        if match:
            return True if conf in ("high", "medium") else None
        return False if conf == "high" else None
    except Exception as e:
        logger.warning(f"identity verify inconclusive ({session_id}): {e}")
        return None


def _extract_json(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


async def build_identity_profile(
    api_key: str,
    session_id: str,
    crop_paths: list[str],
    wide_crop_paths: list[str],
) -> dict | None:
    """Layer B (pre-analysis) — GPT-vision examines the user's tap crops BEFORE
    Gemini runs and returns a verified description of the tapped player plus,
    for each wide crop, whether the TARGET is the one carrying the ball at that
    tap moment. Best-effort: any error returns None and the pipeline proceeds
    exactly as before."""
    try:
        tights = [
            ImageContent(image_base64=_b64(p))
            for p in crop_paths[:MAX_PROFILE_CROPS]
            if p and Path(p).exists()
        ]
        if not tights:
            return None
        wides = [
            ImageContent(image_base64=_b64(p))
            for p in wide_crop_paths[:MAX_PROFILE_WIDE]
            if p and Path(p).exists()
        ]
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=(
                "You verify football player identity across images. "
                "Respond with STRICT JSON only — no prose, no markdown."
            ),
        ).with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        prompt = (
            f"The first {len(tights)} image(s) are TIGHT crops of ONE specific youth football player. "
            "The user tapped precisely on THEIR player at different moments of a match video — the target "
            "is the player at the CENTRE of each crop. They may be partially hidden (behind an opponent or "
            "teammate, only part of the body visible) — never assume the biggest or clearest figure is the target.\n"
            + (
                f"The last {len(wides)} image(s) are WIDE context crops taken at the same tap moments — the "
                "target is at the CENTRE of each wide crop, surrounded by other players.\n"
                if wides else ""
            )
            + "\nTasks:\n"
            "1. Confirm all tight crops show the SAME individual (kit, build, hair, socks, boots).\n"
            "2. Write a precise physical description that distinguishes the target from teammates in an "
            "IDENTICAL kit (build, hair colour/style, sock height, boot colour, shirt number if visible).\n"
            "3. For each WIDE crop, state whether the TARGET (the centre player) is the one in possession of "
            "the ball at that instant, or whether the ball is with a DIFFERENT player.\n\n"
            'Respond ONLY with JSON: {"same_player": true|false, "confidence": "high"|"medium"|"low", '
            '"description": "<2-3 sentences>", '
            '"wide_ball_status": [{"idx": 1, "target_has_ball": "yes"|"no"|"unclear", "note": "<short>"}], '
            '"confusion_risk": "<one short sentence about nearby players who could be confused with the target, or \'none\'>"}'
        )
        msg = UserMessage(text=prompt, file_contents=[*tights, *wides])
        resp = await asyncio.wait_for(chat.send_message(msg), timeout=90)
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        data = _extract_json(text)
        if not data or "description" not in data:
            return None
        logger.info(
            f"[identity-profile] {session_id}: same_player={data.get('same_player')} "
            f"conf={data.get('confidence')} desc={str(data.get('description'))[:120]}"
        )
        return data
    except Exception as e:
        logger.warning(f"identity profile inconclusive ({session_id}): {e}")
        return None


def identity_profile_block(profile: dict | None) -> str:
    """Prompt block injected into BOTH the preview and full-report Gemini prompts
    when a pre-analysis identity profile exists."""
    if not profile or not profile.get("description"):
        return ""
    rows = []
    for w in (profile.get("wide_ball_status") or []):
        if not isinstance(w, dict):
            continue
        status = str(w.get("target_has_ball", "unclear")).lower()
        label = (
            "HAS the ball" if status == "yes"
            else "does NOT have the ball (the ball is with a DIFFERENT player)" if status == "no"
            else "ball possession unclear"
        )
        note = str(w.get("note") or "").strip()
        rows.append(f"  • Tap moment {w.get('idx', '?')} — target {label}{f' — {note}' if note else ''}")
    confusion = str(profile.get("confusion_risk") or "").strip()
    return (
        "\n\n🔒 CROSS-MODEL IDENTITY VERIFICATION (an INDEPENDENT vision system examined the user's tap "
        "crops BEFORE this analysis)\n"
        f"VERIFIED TARGET DESCRIPTION: {profile.get('description')}\n"
        + (f"CONFUSION RISK: {confusion}\n" if confusion and confusion.lower() != "none" else "")
        + (("BALL STATUS AT THE USER'S TAP MOMENTS:\n" + "\n".join(rows) + "\n") if rows else "")
        + "HARD RULES:\n"
        "- If the target does NOT have the ball at a tap moment, ANY on-ball action happening then "
        "(dribbling, carrying, beating players, passing) belongs to a DIFFERENT player — NEVER credit "
        "it to the target.\n"
        "- The eye-catching ball-carrier is often NOT the target. The target may be making off-ball runs, "
        "arriving to receive a pass, or finishing a move a teammate started.\n"
        "- Re-identify the target against the VERIFIED TARGET DESCRIPTION before writing every sentence."
    )


async def verify_preview_summary(
    api_key: str,
    session_id: str,
    crop_paths: list[str],
    wide_crop_paths: list[str],
    summary_text: str,
) -> bool | None:
    """Layer B (post-analysis) — cross-model check that the generated preview
    describes the TAPPED player and not another player (e.g. the ball-carrier).
    Returns True (describes target), False (high-confidence mismatch), or None
    (inconclusive — never overrule)."""
    try:
        summary_text = (summary_text or "").strip()
        if not summary_text:
            return None
        tights = [
            ImageContent(image_base64=_b64(p))
            for p in crop_paths[:MAX_PROFILE_CROPS]
            if p and Path(p).exists()
        ]
        if not tights:
            return None
        wides = [
            ImageContent(image_base64=_b64(p))
            for p in wide_crop_paths[:MAX_PROFILE_WIDE]
            if p and Path(p).exists()
        ]
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=(
                "You verify football player identity across images. "
                "Respond with STRICT JSON only — no prose, no markdown."
            ),
        ).with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        prompt = (
            f"The first {len(tights)} image(s) are TIGHT crops of the TARGET player — the user tapped "
            "precisely on THEIR player; the target is at the CENTRE of each crop and may be partially hidden.\n"
            + (
                f"The last {len(wides)} image(s) are WIDE context crops at the same tap moments — the target "
                "is at the CENTRE, other players around.\n"
                if wides else ""
            )
            + "\nBelow is a scouting summary generated from the FULL VIDEO for this target:\n---\n"
            f"{summary_text[:1200]}\n---\n"
            "IMPORTANT: you only see still crops from a few tap moments — the summary was written from the "
            "WHOLE video. Actions it describes (shots, dribbles, finishes) may well happen at moments NOT "
            "covered by these stills. NEVER reject just because the described action is not visible in the crops.\n"
            "Question: do the crops contain POSITIVE evidence that this summary describes a DIFFERENT player "
            "than the target? Examples of positive evidence: the summary is a story about carrying/dribbling "
            "the ball through midfield while the wide crops clearly show ANOTHER player carrying the ball as "
            "the target stands elsewhere off the ball; or the summary describes a goalkeeper while the target "
            "is an outfield player; or kit/appearance details in the summary contradict the target.\n"
            "If there is no such positive contradiction, answer describes_target=true.\n"
            'Respond ONLY with JSON: {"describes_target": true|false, "confidence": "high"|"medium"|"low", '
            '"why": "<one short sentence>"}'
        )
        msg = UserMessage(text=prompt, file_contents=[*tights, *wides])
        resp = await asyncio.wait_for(chat.send_message(msg), timeout=90)
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        data = _extract_json(text)
        if not data:
            return None
        ok = bool(data.get("describes_target"))
        conf = str(data.get("confidence", "")).lower()
        logger.info(
            f"[preview-identity] {session_id}: describes_target={ok} conf={conf} "
            f"why={str(data.get('why'))[:140]}"
        )
        # Conservative policy (same as verify_frame_identity): only a
        # HIGH-confidence rejection triggers the corrective retry.
        if ok:
            return True if conf in ("high", "medium") else None
        return False if conf == "high" else None
    except Exception as e:
        logger.warning(f"preview identity verify inconclusive ({session_id}): {e}")
        return None
