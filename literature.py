"""Literature values with provenance: what was extracted, from where, and who confirmed it."""

import re

EXTRACTED = "extracted_awaiting_review"
VERIFIED = "verified"
CORRECTED = "corrected_by_user"
NOT_REPORTED = "not_reported"
FAILED = "extraction_failed"

STATUSES = (EXTRACTED, VERIFIED, CORRECTED, NOT_REPORTED, FAILED)

_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def normalise(raw) -> float | None:
    """The number hidden in a cell such as "58.3 % of Klason lignin"."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = _NUMBER.search(str(raw).replace(",", "."))
    return float(match.group(0)) if match else None


def make_value(variable: str, original, unit: str, page=None, section="", confidence="",
               note="") -> dict:
    """Build one extracted value. A value with no number is recorded as not reported."""
    number = normalise(original)
    status = EXTRACTED if number is not None else NOT_REPORTED
    return {
        "variable": str(variable),
        "original": "" if original is None else str(original),
        "normalized": number,
        "unit": str(unit or ""),
        "page": page,
        "section": str(section or ""),
        "confidence": str(confidence or ""),
        "status": status,
        "note": str(note or ""),
    }


def has_provenance(value: dict) -> bool:
    """A value is only trustworthy when the reader can find it in the paper."""
    return bool(value.get("page") or str(value.get("section") or "").strip())


def can_be_compared(value: dict) -> bool:
    """Only a number that the researcher has accepted may be compared."""
    return value.get("status") in (VERIFIED, CORRECTED) and value.get("normalized") is not None


def review(values: list) -> dict:
    """Counts per status, so a screen can say how much still needs checking."""
    counts = {status: 0 for status in STATUSES}
    for value in values or []:
        status = value.get("status")
        if status in counts:
            counts[status] += 1
    counts["total"] = len(values or [])
    counts["without_source"] = sum(1 for value in (values or [])
                                   if not has_provenance(value))
    return counts


def verify(values: list, variable: str, corrected=None) -> list:
    """Accept an extracted value, or replace it with the value the researcher read."""
    out = []
    for value in values or []:
        if value.get("variable") != variable:
            out.append(value)
            continue
        if corrected is None:
            out.append({**value, "status": VERIFIED})
        else:
            number = normalise(corrected)
            out.append({**value, "normalized": number,
                        "status": CORRECTED if number is not None else NOT_REPORTED,
                        "note": f"user read {corrected}"})
    return out


def comparable_values(values: list) -> list:
    return [value for value in (values or []) if can_be_compared(value)]
