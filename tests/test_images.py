# -*- coding: utf-8 -*-
"""Pictures attached to a run: scoping, categories, limits."""
import io
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database
os.environ["DESLAB_MAIL_DISABLE"] = "1"  # tests must never send mail

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import auth  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
       b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
       b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


class ImageRuleTests(unittest.TestCase):
    """The rules are enforced before anything is written, so file mode can test them."""

    def test_there_are_many_categories_to_choose_from(self):
        self.assertGreaterEqual(len(auth.IMAGE_CATEGORIES), 15)
        for wanted in ("SEM", "TEM", "Optical microscope", "XRD pattern", "Sample photo (macro)"):
            self.assertIn(wanted, auth.IMAGE_CATEGORIES)

    def test_a_file_that_is_not_an_image_is_refused(self):
        with self.assertRaises(ValueError):
            auth.add_image("Chuanyu", "EXP-01", "SEM", "", "notes.pdf", "application/pdf", b"%PDF")

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(ValueError):
            auth.add_image("Chuanyu", "EXP-01", "SEM", "", "empty.png", "image/png", b"")

    def test_an_oversized_picture_is_refused(self):
        too_big = b"x" * (auth.IMAGE_LIMIT_BYTES + 1)
        with self.assertRaises(ValueError):
            auth.add_image("Chuanyu", "EXP-01", "SEM", "", "big.jpg", "image/jpeg", too_big)

    def test_without_a_database_it_says_so_rather_than_pretending(self):
        with self.assertRaises(ValueError):
            auth.add_image("Chuanyu", "EXP-01", "SEM", "", "ok.png", "image/png", PNG)

    def test_reading_pictures_without_a_database_is_empty_not_an_error(self):
        self.assertEqual(auth.images_of("Chuanyu"), [])
        self.assertEqual(auth.image_counts("Chuanyu"), {})
        self.assertIsNone(auth.image_content("Chuanyu", 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
