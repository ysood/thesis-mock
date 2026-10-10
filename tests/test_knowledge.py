"""Structural graph checks against stored text; no external lookup required."""

import unittest
from app import knowledge as kb


class KnowledgeGraphTests(unittest.TestCase):
    def test_article_range_expands_and_paragraph_numbers_stay_attached(self):
        self.assertEqual(kb.article_references("Articles 12 to 22"), {str(n) for n in range(12, 23)})
        self.assertEqual(kb.article_references("Articles 6(1)(e) and 9(2)(j)"), {"6(1)(e)", "9(2)(j)"})
        self.assertTrue({f"GDPR Art. {n}" for n in range(12, 23)} <= kb.graph()["cites"]["GDPR Art. 23"])

    def test_amendment_points_to_principal_instrument(self):
        links = kb.graph()["cites"]["IE S.I. 18/2021 Reg. 4"]
        self.assertIn("IE S.I. 314/2018 Reg. 3", links)
        self.assertNotIn("IE S.I. 18/2021 Reg. 3", links)

    def test_retrieving_original_or_amendment_brings_whole_family(self):
        expected = {"IE S.I. 314/2018 Reg. 6", "IE S.I. 188/2019 Reg. 2",
                    "IE S.I. 18/2021 Reg. 8", "IE S.I. 18/2021 Reg. 9"}
        for pid in expected:
            with self.subTest(pid=pid):
                self.assertEqual(set(kb.include_amendments([pid])), expected)

    def test_curated_links_reference_existing_text(self):
        for link in kb.legal_relationships()["amendments"]:
            self.assertIn(link["source"], kb.provisions())
            self.assertIn(link["target"], kb.provisions())
        for source in kb.legal_relationships()["inserted_provisions"].values():
            self.assertIn(source, kb.provisions())

    def test_irish_definition_chain_reaches_sources_without_vector_search(self):
        expected = {'IE DPA 2018 s. 52', 'IE HIA 2014 s. 2 [health practitioner]',
                    'IE MPA 2007 s. 2 [registered medical practitioner]', 'IE MPA 2007 s. 2 [register]'}
        self.assertEqual(set(kb.include_supporting_sources(['IE DPA 2018 s. 52'])), expected)
        self.assertTrue(expected <= set(kb.include_supporting_sources(['IE DPA 2018 s. 52'])))
        self.assertIn('IE HIA 2014 s. 2 [health practitioner]', kb.graph()['cites']['IE DPA 2018 s. 52'])
        self.assertIn('subject to section 56A', kb.provisions()['IE MPA 2007 s. 2 [registered medical practitioner]']['text'])
        # Foreign section references must not become accidental DPA links.
        self.assertNotIn('IE DPA 2018 s. 2', kb.graph()['cites']['IE HIA 2014 s. 2 [health practitioner]'])


if __name__ == "__main__":
    unittest.main()
