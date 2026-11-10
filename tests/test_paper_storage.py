import os
import tempfile
import unittest

import auth
import literature as lit


class PaperStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DESLAB_DATA_DIR"] = self.tmp.name
        os.environ["DESLAB_STORAGE"] = "file"
        auth.ensure_store()

    def tearDown(self):
        os.environ.pop("DESLAB_DATA_DIR", None)
        self.tmp.cleanup()

    def test_a_paper_keeps_its_values_and_their_sources(self):
        values = [lit.make_value("lignin_recovery_pct", "58.3 %", "%", page=5,
                                 section="Results")]
        paper_id = auth.save_paper("Chuanyu", "10.0000/x", "Synthetic paper", 2024, values)
        stored = auth.papers_of("Chuanyu")[0]
        self.assertEqual(stored["id"], paper_id)
        self.assertEqual(stored["values"][0]["page"], 5)
        self.assertEqual(stored["values"][0]["normalized"], 58.3)

    def test_reviewing_a_paper_updates_the_stored_status(self):
        values = [lit.make_value("lignin_mg", "388", "mg", page=3)]
        paper_id = auth.save_paper("Chuanyu", "", "Paper", 2024, values)
        accepted = lit.verify(auth.papers_of("Chuanyu")[0]["values"], "lignin_mg")
        auth.review_paper("Chuanyu", paper_id, accepted)
        self.assertEqual(auth.papers_of("Chuanyu")[0]["values"][0]["status"], lit.VERIFIED)

    def test_papers_are_private_to_their_owner(self):
        auth.save_paper("Chuanyu", "", "Mine", 2024, [])
        self.assertEqual(auth.papers_of("Thena"), [])


if __name__ == "__main__":
    unittest.main()
