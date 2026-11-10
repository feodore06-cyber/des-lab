"""Export a project so that an outside reader can interpret every column."""

import json


def payload(project: str, variables: list, runs: list, extra: dict | None = None) -> dict:
    """Records plus the definition of every variable they use."""
    definitions = []
    for item in variables or []:
        definitions.append({
            "name": item.get("name"),
            "display_name": item.get("display_name") or item.get("name"),
            "unit": item.get("unit") or "",
            "dtype": item.get("dtype") or "",
            "role": item.get("role") or "",
            "priority": item.get("priority") or "",
            "definition": item.get("definition") or "",
            "synonyms": list(item.get("synonyms") or []),
            "method": item.get("method") or "",
            "formula": item.get("formula") or "",
        })
    used = set()
    for row in runs or []:
        used.update(row.keys())
    body = {
        "project": project,
        "schema_version": 1,
        "variables": definitions,
        "columns_present": sorted(used),
        "runs": runs or [],
    }
    if extra:
        body.update(extra)
    return body


def to_json(body: dict) -> str:
    return json.dumps(body, ensure_ascii=False, indent=2, default=str)


def describe(body: dict) -> str:
    """How complete the export is, in one line."""
    defined = {item["name"] for item in body.get("variables") or []}
    present = set(body.get("columns_present") or [])
    undocumented = sorted(present - defined - {"sample_id", "recorded_at", "project", "_owner"})
    if not undocumented:
        return "Every exported column has a definition."
    return ("These exported columns have no definition yet: " + ", ".join(undocumented))
