"""Validate explicit family identity declarations before paid upload work."""
import re

_NUMBER_CLAIM = re.compile(
    r"\b(?:(?:shirt|jersey|trøje)\s*(?:(?:number|nummer|nr\.?)\s*)?"
    r"|(?:number|nummer|nr\.?)\s*)[:#]?\s*(\d{1,3})\b", re.I)


def jersey_declaration_conflict(jersey_number, description):
    """Return only an unambiguous contradiction, never infer visual identity.

    Age, scores and other unlabelled numbers are ignored. Multiple distinct
    number claims in free text are ambiguous and must not be auto-resolved.
    Neither input is silently replaced with a model's jersey-number reading.
    """
    field = str(jersey_number or "").strip()
    if not re.fullmatch(r"\d{1,3}", field) or not isinstance(description, str):
        return None
    claims = {str(int(m.group(1))) for m in _NUMBER_CLAIM.finditer(description)}
    if len(claims) != 1:
        return None
    stated = str(int(field))
    described = next(iter(claims))
    return {"field_number": stated, "description_number": described} if stated != described else None
