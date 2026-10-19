# -*- coding: utf-8 -*-
"""Account store, hashing and per-user record files."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[auth.DATA_DIR_ENV] = self.tmp.name

    def tearDown(self):
        os.environ.pop(auth.DATA_DIR_ENV, None)
        self.tmp.cleanup()

    def test_seed_creates_both_teammates(self):
        users = auth.ensure_store()
        self.assertEqual(set(users), {"Thena", "Chuanyu"})
        self.assertTrue(auth.verify("Thena", auth.DEFAULT_PASSWORD))
        self.assertTrue(auth.verify("Chuanyu", auth.DEFAULT_PASSWORD))

    def test_passwords_are_salted_hashes_not_plaintext(self):
        auth.ensure_store()
        raw = (Path(self.tmp.name) / "users.json").read_text(encoding="utf-8")
        self.assertNotIn(auth.DEFAULT_PASSWORD, raw, "the password must never be stored in plain text")
        users = auth.load_users()
        self.assertNotEqual(users["Thena"]["salt"], users["Chuanyu"]["salt"])
        self.assertNotEqual(users["Thena"]["hash"], users["Chuanyu"]["hash"])

    def test_accounts_can_be_seeded_from_secrets(self):
        """A hosted deployment can seed its own accounts instead of the documented defaults."""
        import streamlit as st

        original = st.secrets
        try:
            st.secrets = {"accounts": {"Wei": "deploy-secret", "Thena": "another-secret"}}
            users = auth.ensure_store()
            self.assertEqual(set(users), {"Wei", "Thena"})
            self.assertTrue(auth.verify("Wei", "deploy-secret"))
            self.assertFalse(auth.verify("Wei", auth.DEFAULT_PASSWORD))
        finally:
            st.secrets = original

    def test_hosted_without_secrets_never_seeds_the_default_password(self):
        os.environ[auth.HOSTED_ENV] = "1"
        try:
            self.assertEqual(auth.ensure_store(), {}, "a hosted site must not create demo accounts")
            self.assertEqual(auth.load_users(), {})
            self.assertFalse(auth.verify("Chuanyu", auth.DEFAULT_PASSWORD))
        finally:
            os.environ.pop(auth.HOSTED_ENV, None)

    def test_wrong_password_and_unknown_user(self):
        auth.ensure_store()
        self.assertFalse(auth.verify("Thena", "wrong"))
        self.assertFalse(auth.verify("the_na", auth.DEFAULT_PASSWORD))
        self.assertFalse(auth.verify("Nobody", auth.DEFAULT_PASSWORD))
        self.assertFalse(auth.verify("", ""))

    def test_add_user_change_password(self):
        auth.ensure_store()
        auth.add_user("Wei", "second-password")
        self.assertTrue(auth.verify("Wei", "second-password"))
        auth.change_password("Wei", "third-password")
        self.assertFalse(auth.verify("Wei", "second-password"))
        self.assertTrue(auth.verify("Wei", "third-password"))

    def test_add_user_validation(self):
        auth.ensure_store()
        with self.assertRaises(ValueError):
            auth.add_user("Thena", "another-password")
        with self.assertRaises(ValueError):
            auth.add_user("bad name", "another-password")
        with self.assertRaises(ValueError):
            auth.add_user("Shorty", "123")

    def test_record_folders_are_separate_and_sanitised(self):
        the = auth.user_dir("Thena")
        chu = auth.user_dir("Chuanyu")
        self.assertNotEqual(the, chu)
        self.assertTrue(the.is_dir() and chu.is_dir())
        for bad in ("../evil", "a/b", "", "Thena/../../x"):
            with self.assertRaises(ValueError):
                auth.user_dir(bad)

    def test_save_load_results_append_and_replace(self):
        rows = pd.DataFrame({"formulation": ["ChCl-GA 1:2"], "lignin_yield_pct": [1.94]})
        auth.save_results("Chuanyu", rows, append=False)
        self.assertEqual(len(auth.load_results("Chuanyu")), 1)
        auth.save_results("Chuanyu", rows, append=True)
        self.assertEqual(len(auth.load_results("Chuanyu")), 2)
        auth.save_results("Chuanyu", rows, append=False)
        self.assertEqual(len(auth.load_results("Chuanyu")), 1)
        self.assertIsNone(auth.load_results("Thena"), "other teammates must not see these rows")

    def test_save_recipe_uses_user_folder(self):
        frame = pd.DataFrame({"name": ["ChCl"], "weigh_g": [4.95]})
        path = auth.save_recipe("Thena", frame)
        self.assertTrue(path.exists())
        self.assertEqual(path.parent.parent, auth.user_dir("Thena"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
