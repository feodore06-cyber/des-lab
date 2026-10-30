# -*- coding: utf-8 -*-
"""Find papers for a topic, and rank them so the closest ones come first.

Source: OpenAlex (open catalogue, no API key, ~250M works). Nothing here needs a paid plan, and the
ranking is ours: search relevance, how often the paper is cited, and how recent it is.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.openalex.org/works"
AGENT = "biomat-lab/1.0 (research workbench; contact via app)"
TIMEOUT = 20


class PaperError(RuntimeError):
    """Raised when the catalogue cannot be reached, with a message that can be shown as-is."""


def _fetch(params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{API}?{query}",
                                     headers={"User-Agent": AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise PaperError(f"the catalogue answered {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PaperError("the catalogue could not be reached") from exc
    except json.JSONDecodeError as exc:
        raise PaperError("the catalogue sent something unreadable") from exc


def _abstract(work: dict) -> str:
    """OpenAlex stores abstracts as an inverted index; rebuild the sentences."""
    index = work.get("abstract_inverted_index") or {}
    if not index:
        return ""
    positions = {}
    for word, places in index.items():
        for place in places:
            positions[place] = word
    return " ".join(positions[place] for place in sorted(positions))[:900]


def _venue(work: dict) -> str:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    return source.get("display_name") or ""


def _authors(work: dict) -> str:
    names = []
    for authorship in (work.get("authorships") or [])[:3]:
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            names.append(name)
    if len(work.get("authorships") or []) > 3:
        names.append("et al.")
    return ", ".join(names)


# a book chapter or a dissertation is rarely what somebody means by "the paper I want"
KIND_WEIGHT = {"article": 1.0, "review": 1.1, "preprint": 0.85,
               "book-chapter": 0.6, "book": 0.6, "dissertation": 0.55, "dataset": 0.4}


def score(work: dict, position: int) -> float:
    """Relevance, then how often it is cited, then freshness - weighted so a well-cited journal
    article outranks a one-citation book chapter that merely repeats the query words."""
    cites = float(work.get("cited_by_count") or 0)
    year = work.get("publication_year") or 0
    relevance = 1.0 / (1.0 + position)          # the catalogue already ranked these
    reputation = math.log1p(cites) / 3.0        # citations count, with diminishing returns
    freshness = max(0, (year - 2015)) / 50.0
    has_abstract = 0.15 if work.get("abstract_inverted_index") else 0.0
    kind = KIND_WEIGHT.get(str(work.get("type") or "").lower(), 0.85)
    return round(kind * (relevance * 2.0 + reputation + freshness + has_abstract), 4)


def search(query: str, limit: int = 12, since: int | None = None,
           min_citations: int = 0, sort: str = "relevant") -> list[dict]:
    """Return ranked papers for ``query``."""
    clean = " ".join(str(query or "").split())
    if not clean:
        return []
    params = {"search": clean, "per-page": max(1, min(int(limit), 50)),
              "sort": "relevance_score:desc", "mailto": "biomat-lab@example.com"}
    if since:
        params["filter"] = f"from_publication_date:{int(since)}-01-01"
    payload = _fetch(params)

    papers = []
    for position, work in enumerate(payload.get("results") or []):
        cites = int(work.get("cited_by_count") or 0)
        if cites < min_citations:
            continue
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        papers.append({
            "title": (work.get("title") or "untitled").strip(),
            "year": work.get("publication_year") or "",
            "venue": _venue(work),
            "authors": _authors(work),
            "citations": cites,
            "doi": doi,
            "url": work.get("doi") or work.get("id") or "",
            "abstract": _abstract(work),
            "score": score(work, position),
        })

    if sort == "cited":
        papers.sort(key=lambda paper: paper["citations"], reverse=True)
    elif sort == "newest":
        papers.sort(key=lambda paper: paper["year"] or 0, reverse=True)
    else:
        papers.sort(key=lambda paper: paper["score"], reverse=True)
    return papers[: int(limit)]


def summarise(query: str, papers: list[dict]) -> str:
    """A one-line statement of what the ranking is based on, shown above the table."""
    if not papers:
        return ""
    years = [paper["year"] for paper in papers if paper["year"]]
    span = f"{min(years)}-{max(years)}" if years else "no dates"
    return f"{len(papers)} papers for “{query}” ({span}), ranked by relevance, citations and recency."

def by_doi(doi: str) -> dict | None:
    """Fetch one work by DOI; used to prefill the comparison from the paper the user picked."""
    clean = str(doi or "").strip().replace("https://doi.org/", "")
    if not clean:
        return None
    payload = _fetch({"filter": f"doi:{clean}", "per-page": 1,
                      "mailto": "biomat-lab@example.com"})
    results = payload.get("results") or []
    if not results:
        return None
    work = results[0]
    return {"title": (work.get("title") or "").strip(), "year": work.get("publication_year"),
            "abstract": _abstract(work), "doi": (work.get("doi") or "").replace(
                "https://doi.org/", "")}
