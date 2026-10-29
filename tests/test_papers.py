# -*- coding: utf-8 -*-
"""The paper finder: ranking, filters, and a graceful failure when the network is down."""
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database
os.environ["DESLAB_MAIL_DISABLE"] = "1"  # tests must never send mail

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import papers  # noqa: E402


def work(title, year, cites, kind="article", abstract=True, doi="https://doi.org/10.1/x"):
    return {
        "title": title, "publication_year": year, "cited_by_count": cites, "type": kind,
        "doi": doi,
        "primary_location": {"source": {"display_name": "Journal of Tests"}},
        "authorships": [{"author": {"display_name": "A. Author"}}],
        "abstract_inverted_index": ({"Lignin": [0], "yield": [1], "rises": [2]} if abstract else None),
    }


class RankingTests(unittest.TestCase):
    def test_a_well_cited_article_beats_a_one_citation_book_chapter(self):
        article = work("A cited article", 2022, 48)
        chapter = work("A book chapter", 2025, 1, kind="book-chapter")
        self.assertGreater(papers.score(article, 0), papers.score(chapter, 0))

    def test_relevance_still_matters_within_the_same_kind(self):
        first = work("The exact match", 2023, 10)
        tenth = work("Loosely related", 2023, 10)
        self.assertGreater(papers.score(first, 0), papers.score(tenth, 9))

    def test_an_abstract_is_rebuilt_from_the_inverted_index(self):
        self.assertEqual(papers._abstract(work("x", 2024, 0)), "Lignin yield rises")
        self.assertEqual(papers._abstract(work("x", 2024, 0, abstract=False)), "")


class SearchTests(unittest.TestCase):
    def payload(self):
        return {"results": [
            work("Low citation chapter", 2025, 0, kind="book-chapter"),
            work("Solid review", 2021, 300, kind="review"),
            work("Recent paper", 2024, 5),
        ]}

    def test_the_best_paper_comes_first(self):
        with mock.patch.object(papers, "_fetch", return_value=self.payload()):
            found = papers.search("deep eutectic solvent", limit=3)
        self.assertEqual(found[0]["title"], "Solid review")

    def test_the_minimum_citation_filter_is_applied(self):
        with mock.patch.object(papers, "_fetch", return_value=self.payload()):
            found = papers.search("des", limit=3, min_citations=100)
        self.assertEqual([paper["title"] for paper in found], ["Solid review"])

    def test_sorting_by_citations_and_by_year(self):
        with mock.patch.object(papers, "_fetch", return_value=self.payload()):
            cited = papers.search("des", limit=3, sort="cited")
            newest = papers.search("des", limit=3, sort="newest")
        self.assertEqual(cited[0]["title"], "Solid review")
        self.assertEqual(newest[0]["title"], "Low citation chapter")

    def test_an_empty_query_returns_nothing_without_calling_anything(self):
        with mock.patch.object(papers, "_fetch") as fetch:
            self.assertEqual(papers.search("   "), [])
        fetch.assert_not_called()

    def test_a_network_failure_is_a_readable_error(self):
        import urllib.error

        with mock.patch.object(papers.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(papers.PaperError) as caught:
                papers.search("lignin")
        self.assertIn("could not be reached", str(caught.exception))

    def test_the_summary_line_names_the_query_and_the_years(self):
        with mock.patch.object(papers, "_fetch", return_value=self.payload()):
            found = papers.search("des", limit=3)
        line = papers.summarise("des", found)
        self.assertIn("des", line)
        self.assertIn("2021", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
