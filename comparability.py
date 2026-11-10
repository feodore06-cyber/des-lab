"""Decide whether two results may be compared at all, before any difference is calculated."""

DIRECTLY = "directly_comparable"
CAVEATS = "comparable_with_caveats"
NOT_COMPARABLE = "not_comparable"
INSUFFICIENT = "insufficient_information"

STATUS_ORDER = (DIRECTLY, CAVEATS, NOT_COMPARABLE, INSUFFICIENT)

# the classic trap: same number, different denominator
# most specific first: a recovery definition also mentions biomass, and must not be mistaken for
# a yield-on-biomass definition
DENOMINATOR_FAMILIES = {
    "recovery_on_lignin": ("klason", "lignin content", "lignin_content", "initial lignin"),
    "purity_on_total": ("total protein", "total mass"),
    "yield_on_biomass": ("biomass", "dry weight", "dry mass"),
}


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _definition(item: dict) -> str:
    return (_text(item.get("definition")) + " " + _text(item.get("formula"))).strip().lower()


def _denominator(definition: str) -> str:
    """Which denominator a definition names, when it names one."""
    for family, words in DENOMINATOR_FAMILIES.items():
        if any(word in definition for word in words):
            return family
    return ""


def _unit(item: dict) -> str:
    return _text(item.get("unit")).lower()


def check(mine: dict, theirs: dict, mine_item: dict | None = None,
          theirs_item: dict | None = None, replicates: int = 1) -> dict:
    """Return {status, reasons, blocking}.

    ``mine`` and ``theirs`` are the two records; ``mine_item``/``theirs_item`` are the variable
    definitions of the result being compared. A comparison is only allowed to proceed when the two
    numbers mean the same thing.
    """
    reasons = []
    blocking = []
    mine_item = mine_item or {}
    theirs_item = theirs_item or {}

    mine_definition = _definition(mine_item)
    theirs_definition = _definition(theirs_item)
    mine_unit, theirs_unit = _unit(mine_item), _unit(theirs_item)

    if mine_definition and theirs_definition:
        mine_den, theirs_den = _denominator(mine_definition), _denominator(theirs_definition)
        if mine_den and theirs_den and mine_den != theirs_den:
            blocking.append(
                f"the denominators differ: one is per {mine_den.replace('yield_on_', '').replace('recovery_on_', '').replace('_', ' ')}, "
                f"the other per {theirs_den.replace('yield_on_', '').replace('recovery_on_', '').replace('_', ' ')}")
        elif mine_den != theirs_den:
            reasons.append("one side names its denominator and the other does not")
    elif not mine_definition and not theirs_definition:
        return {"status": INSUFFICIENT,
                "reasons": ["neither side says what the number means (no definition, no formula)"],
                "blocking": []}
    elif not mine_definition or not theirs_definition:
        blocking.append("one side does not define what the number means")

    if mine_unit and theirs_unit and mine_unit != theirs_unit:
        blocking.append(f"the units differ ({mine_unit} vs {theirs_unit})")

    if mine_item.get("name") and theirs_item.get("name") \
            and mine_item["name"] != theirs_item["name"]:
        reasons.append(f"the variables are different ({mine_item['name']} vs "
                       f"{theirs_item['name']})")

    if str((mine or {}).get("feedstock") or "").strip().lower() != \
            str((theirs or {}).get("feedstock") or "").strip().lower() and \
            (mine or {}).get("feedstock") and (theirs or {}).get("feedstock"):
        reasons.append("the raw material is not the same")

    if blocking:
        return {"status": NOT_COMPARABLE, "reasons": blocking + reasons, "blocking": blocking}
    if reasons:
        return {"status": CAVEATS, "reasons": reasons, "blocking": []}
    if replicates < 2:
        return {"status": CAVEATS,
                "reasons": ["one run per condition, so the difference cannot be separated "
                            "from run-to-run noise"],
                "blocking": []}
    return {"status": DIRECTLY, "reasons": ["same definition, unit, material and method"],
            "blocking": []}


def conversion_note(mine_item: dict, theirs_item: dict) -> str:
    """What would have to change for these two numbers to become comparable."""
    mine_den = _denominator(_definition(mine_item))
    theirs_den = _denominator(_definition(theirs_item))
    if mine_den and theirs_den and mine_den != theirs_den:
        return (f"Convert both to the same basis first: divide by the same denominator "
                f"({mine_den.replace('_', ' ')} on one side, {theirs_den.replace('_', ' ')} "
                f"on the other).")
    return ""
