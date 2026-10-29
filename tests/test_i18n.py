# -*- coding: utf-8 -*-
"""Every t("key") used in the source must exist in both languages.

A missing key silently renders as the raw key (the sign-up form once showed "signup.display"), so this
scan fails the build instead of relying on someone noticing.
"""
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import i18n  # noqa: E402

SOURCES = ("Hello.py", "auth.py", "views.py", "feedback.py", "chem.py", "store.py", "lab_core.py")
PATTERN = re.compile(r"""\bt\(\s*["']([A-Za-z0-9_.]+)["']""")
# keys are sometimes built at runtime ("cmp." + code + ".claim"): a trailing dot marks that prefix
DYNAMIC = ("cmp.", "cmp.tag_", "res.q_", "guide.")


def is_dynamic(key: str) -> bool:
    return key.endswith(".") or key.endswith("_") or key in DYNAMIC


def used_keys() -> dict:
    found = {}
    for name in SOURCES:
        path = ROOT / name
        if not path.exists():
            continue
        for match in PATTERN.finditer(path.read_text(encoding="utf-8")):
            key = match.group(1)
            if is_dynamic(key):
                continue  # a prefix assembled at runtime, checked by the tests that use it
            found.setdefault(key, set()).add(name)
    return found


class TranslationCoverageTests(unittest.TestCase):
    def test_every_key_used_in_the_code_has_both_languages(self):
        keys = used_keys()
        self.assertGreater(len(keys), 100, "the scan should find the interface strings")
        missing_en = sorted(k for k in keys if k not in i18n.EN)
        missing_zh = sorted(k for k in keys if k not in i18n.ZH)
        self.assertEqual(missing_en, [], f"missing from the English table: {missing_en}")
        self.assertEqual(missing_zh, [], f"missing from the Chinese table: {missing_zh}")

    def test_the_chinese_table_covers_every_english_key(self):
        only_zh = sorted(set(i18n.ZH) - set(i18n.EN))
        self.assertEqual(only_zh, [], f"translated but not in English: {only_zh}")

    def test_no_translation_is_empty(self):
        for table_name, table in (("EN", i18n.EN), ("ZH", i18n.ZH)):
            empty = [key for key, value in table.items() if not str(value).strip()]
            self.assertEqual(empty, [], f"empty values in {table_name}: {empty}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
