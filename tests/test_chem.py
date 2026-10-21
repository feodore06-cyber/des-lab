# -*- coding: utf-8 -*-
"""PubChem client: parsing, aliases and error handling (network is stubbed out)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chem  # noqa: E402


class ChemTests(unittest.TestCase):
    def setUp(self):
        chem.find_cids.clear()
        chem.compound.clear()
        chem.suggest.clear()
        self.original = chem._get_json
        self.calls = []

    def tearDown(self):
        chem._get_json = self.original
        chem.find_cids.clear()
        chem.compound.clear()
        chem.suggest.clear()

    def fake(self, mapping):
        def _get(url):
            self.calls.append(url)
            for fragment, payload in mapping.items():
                if fragment in url:
                    if isinstance(payload, Exception):
                        raise payload
                    return payload
            raise chem.ChemError("not found")
        return _get

    def test_chinese_aliases(self):
        self.assertEqual(chem.translate_term("氯化胆碱"), "choline chloride")
        self.assertEqual(chem.translate_term("乙醛酸"), "glyoxylic acid")
        self.assertEqual(chem.translate_term("  urea  "), "urea")
        self.assertEqual(chem.translate_term("UnknownStuff"), "UnknownStuff")

    def test_find_cids_by_name(self):
        chem._get_json = self.fake({"/name/glyoxylic%20acid/cids": {"IdentifierList": {"CID": [760]}}})
        self.assertEqual(chem.find_cids("glyoxylic acid"), [760])

    def test_find_cids_falls_back_to_cid_lookup_for_a_cas_number(self):
        def router(url):
            self.calls.append(url)
            if "/name/50-99-7/" in url:
                raise chem.ChemError("not found")
            if "/cid/50-99-7/" in url:
                return {"IdentifierList": {"CID": [5793]}}
            raise chem.ChemError("not found")
        chem._get_json = router
        self.assertEqual(chem.find_cids("50-99-7"), [5793])
        self.assertTrue(any("/name/" in url for url in self.calls), "should try the name endpoint first")

    def test_compound_parsing_and_cas_from_synonyms(self):
        properties = {"PropertyTable": {"Properties": [{
            "CID": 6209, "Title": "Choline Chloride", "MolecularFormula": "C5H14ClNO",
            "MolecularWeight": "139.62", "IUPACName": "2-hydroxyethyl(trimethyl)azanium;chloride",
            "SMILES": "C[N+](C)(C)CCO.[Cl-]", "HBondDonorCount": 1, "HBondAcceptorCount": 2,
            "XLogP": -5.9, "TPSA": 20.2}]}}
        synonyms = {"InformationList": {"Information": [{"Synonym": ["CC", "67-48-1", "Choline chloride"]}]}}
        chem._get_json = self.fake({
            "/property/": properties,
            "/synonyms/": synonyms,
        })
        record = chem.compound(6209)
        self.assertEqual(record["name"], "Choline Chloride")
        self.assertAlmostEqual(record["mw"], 139.62)
        self.assertEqual(record["formula"], "C5H14ClNO")
        self.assertEqual(record["cas"], "67-48-1")
        self.assertEqual(record["hbd"], 1)
        self.assertAlmostEqual(record["xlogp"], -5.9)
        self.assertIn("pubchem.ncbi.nlm.nih.gov/compound/6209", record["url"])

    def test_offline_raises_chem_error(self):
        def boom(url):
            raise chem.ChemError("offline")
        chem._get_json = boom
        with self.assertRaises(chem.ChemError):
            chem.find_cids("water")
        self.assertEqual(chem.suggest("water"), [], "suggestions degrade quietly when offline")

    def test_unknown_term_returns_no_cids(self):
        chem._get_json = self.fake({})
        self.assertEqual(chem.find_cids("not-a-real-chemical-xyz"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
