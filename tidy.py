"""Put a project's variables in a sensible order and point out what looks duplicated."""

import ai
import columnmap
import research

ORDER = {"metadata": 0, "independent": 1, "controlled": 2, "covariate": 3,
         "dependent": 4, "derived": 5}


def tidy(items: list) -> dict:
    """Return the variables in reading order, with the changes that were made and the clashes.

    Order: identifiers, then the conditions you set, then anything else, then the results.
    Nothing is merged or deleted here - duplicates are only reported.
    """
    prepared = []
    for item in items or []:
        # the same lowercase rule as everywhere else: Temperature_C and temperature_c are one name
        name = research.normalise_name(item.get("name"))
        if not name:
            continue
        proposal = columnmap.suggest(name)
        role = item.get("role") or proposal["role"] or "independent"
        prepared.append({
            **item,
            "name": name,
            "unit": item.get("unit") or proposal["unit"],
            "data_type": item.get("data_type") or proposal["data_type"],
            "role": role,
        })

    ordered = sorted(prepared, key=lambda entry: (ORDER.get(entry["role"], 3),
                                                  str(entry["name"])))
    changes = []
    by_name = {str(item.get("name")): item for item in items or []}
    for entry in ordered:
        before = by_name.get(entry["name"], {})
        if str(before.get("name") or "") != entry["name"]:
            changes.append({"variable": entry["name"], "field": "name",
                            "from": before.get("name"), "to": entry["name"]})
        if before.get("role") and before.get("role") != entry["role"]:
            changes.append({"variable": entry["name"], "field": "role",
                            "from": before.get("role"), "to": entry["role"]})
        if not before.get("unit") and entry.get("unit"):
            changes.append({"variable": entry["name"], "field": "unit",
                            "from": "", "to": entry["unit"]})

    # the same concept twice (time_min vs reaction_time_h) is worth a human decision
    by_concept = {}
    for entry in ordered:
        concept = columnmap.suggest(entry["name"])["name"].split("_")[0]
        by_concept.setdefault(concept, []).append(entry["name"])
    duplicates = {concept: names for concept, names in by_concept.items() if len(names) > 1}

    return {"items": ordered, "changes": changes, "duplicates": duplicates}


def move(items: list, name: str, step: int) -> list:
    """Move one variable up or down without dragging; order is whatever the list says."""
    names = [str(item.get("name")) for item in items or []]
    if name not in names:
        return list(items or [])
    index = names.index(name)
    target = index + step
    if target < 0 or target >= len(names):
        return list(items or [])
    moved = list(items)
    moved[index], moved[target] = moved[target], moved[index]
    for position, entry in enumerate(moved):
        entry["position"] = position
    return moved


def ai_tidy(project: str, items: list, language: str = "en") -> dict:
    """Local rules always run; the model is asked for roles and units when it is available."""
    base = tidy(items)
    if not ai.available():
        return base
    proposals = columnmap.ai_suggest([entry["name"] for entry in base["items"]], [], language)
    by_name = {item["name"]: item for item in proposals}
    refined = []
    for entry in base["items"]:
        found = by_name.get(entry["name"]) or {}
        refined.append({**entry,
                        "unit": found.get("unit") or entry.get("unit"),
                        "data_type": found.get("data_type") or entry.get("data_type"),
                        "role": found.get("role") or entry.get("role")})
    return {**base, "items": refined}
