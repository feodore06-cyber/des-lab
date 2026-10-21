# -*- coding: utf-8 -*-
"""Live chemical lookup through the public PubChem REST API.

No API key is needed. Every function here is safe to call when the machine is offline: network
problems raise :class:`ChemError`, which the page turns into a readable message.

Data source: PubChem (NCBI/NLM). Values are informational - always check against your own reagent
documentation before using them in a formulation.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest"
HEADERS = {"User-Agent": "DES-Lab/1.0 (laboratory notebook; contact: lab)"}
TIMEOUT = 15
PROPERTIES = ("Title,MolecularFormula,MolecularWeight,IUPACName,SMILES,"
              "HBondDonorCount,HBondAcceptorCount,XLogP,TPSA")
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

# Common DES components: let people type the Chinese name they know.
ALIASES = {
    "氯化胆碱": "choline chloride",
    "胆碱": "choline",
    "乙醛酸": "glyoxylic acid",
    "乳酸": "lactic acid",
    "柠檬酸": "citric acid",
    "枸橼酸": "citric acid",
    "草酸": "oxalic acid",
    "丙二酸": "malonic acid",
    "苹果酸": "malic acid",
    "琥珀酸": "succinic acid",
    "对甲苯磺酸": "p-toluenesulfonic acid",
    "甲苯磺酸": "p-toluenesulfonic acid",
    "乙酰丙酸": "levulinic acid",
    "甜菜碱": "betaine",
    "尿素": "urea",
    "乙二醇": "ethylene glycol",
    "丙三醇": "glycerol",
    "甘油": "glycerol",
    "木糖醇": "xylitol",
    "山梨醇": "sorbitol",
    "蔗糖": "sucrose",
    "葡萄糖": "glucose",
    "果糖": "fructose",
    "苯酚": "phenol",
    "甲醛": "formaldehyde",
    "甲酸": "formic acid",
    "乙酸": "acetic acid",
    "乙醇": "ethanol",
    "甲醇": "methanol",
    "水": "water",
    "氢氧化钠": "sodium hydroxide",
    "氯化钠": "sodium chloride",
    "γ-戊内酯": "gamma-valerolactone",
    "戊内酯": "gamma-valerolactone",
    "聚乙烯醇": "polyvinyl alcohol",
}


class ChemError(RuntimeError):
    """Network or API problem while talking to PubChem."""


def _get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ChemError("not found") from exc
        raise ChemError(f"PubChem returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ChemError("offline") from exc
    except json.JSONDecodeError as exc:
        raise ChemError("PubChem returned an unreadable answer") from exc


def translate_term(term: str) -> str:
    """Map a Chinese name to the English one PubChem indexes, otherwise return it unchanged."""
    cleaned = (term or "").strip()
    return ALIASES.get(cleaned, cleaned)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def suggest(term: str, limit: int = 8) -> list[str]:
    """Autocomplete names for a search box."""
    query = translate_term(term)
    if not query:
        return []
    url = f"{BASE}/autocomplete/compound/{urllib.parse.quote(query)}/json?limit={limit}"
    try:
        payload = _get_json(url)
    except ChemError:
        return []
    return list(payload.get("dictionary_terms", {}).get("compound", []))[:limit]


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def find_cids(term: str) -> list[int]:
    """Resolve a name, a CAS number or a formula to candidate CIDs."""
    query = translate_term(term)
    if not query:
        return []
    for kind in ("name", "cid"):
        try:
            payload = _get_json(f"{BASE}/pug/compound/{kind}/{urllib.parse.quote(query)}/cids/JSON")
        except ChemError as exc:
            if str(exc) == "not found":
                continue
            raise
        return list(payload.get("IdentifierList", {}).get("CID", []))
    return []


def _cas_from_synonyms(cid: int) -> str | None:
    try:
        payload = _get_json(f"{BASE}/pug/compound/cid/{cid}/synonyms/JSON")
    except ChemError:
        return None
    entries = payload.get("InformationList", {}).get("Information", [])
    for entry in entries:
        for synonym in entry.get("Synonym", []):
            if CAS_RE.match(synonym.strip()):
                return synonym.strip()
    return None


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def compound(cid: int) -> dict:
    """Full record for one CID, including a CAS number when PubChem lists one."""
    url = f"{BASE}/pug/compound/cid/{cid}/property/{PROPERTIES}/JSON"
    payload = _get_json(url)
    rows = payload.get("PropertyTable", {}).get("Properties", [])
    if not rows:
        raise ChemError("empty record")
    row = rows[0]

    def number(key):
        value = row.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "cid": int(row.get("CID", cid)),
        "name": row.get("Title") or f"CID {cid}",
        "formula": row.get("MolecularFormula") or "",
        "mw": number("MolecularWeight"),
        "iupac": row.get("IUPACName") or "",
        "smiles": row.get("SMILES") or "",
        "hbd": number("HBondDonorCount"),
        "hba": number("HBondAcceptorCount"),
        "xlogp": number("XLogP"),
        "tpsa": number("TPSA"),
        "cas": _cas_from_synonyms(cid),
        "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
    }


def search(term: str) -> tuple[list[str], dict | None]:
    """Return (suggestions, record) for a typed term.

    ``record`` is filled when the term resolves to exactly one compound, so a plain "glyoxylic acid"
    needs one round trip instead of a pick list.
    """
    cids = find_cids(term)
    if len(cids) == 1:
        return suggest(term), compound(cids[0])
    return suggest(term), None


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def molar_mass(term: str) -> float | None:
    """Convenience helper: a molar mass straight from a name."""
    cids = find_cids(term)
    if not cids:
        return None
    return compound(cids[0]).get("mw")
