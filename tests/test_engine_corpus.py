"""Corpus registry: structure comes from corpora/ manifests and the law's own cross-references."""

import unittest

from engine import corpus as c


class RegistryTests(unittest.TestCase):
    def test_corpora_and_levels_come_from_manifests(self):
        self.assertEqual(list(c.manifests()), ['region_a', 'region_b', 'subregion_a1'])
        self.assertEqual(c.top_level(), ['region_a', 'region_b'])
        self.assertEqual(c.children('region_a'), ['subregion_a1'])
        self.assertEqual(c.jurisdictions()['A1']['member_of'], 'A')

    def test_every_provision_belongs_to_a_declared_instrument(self):
        prefixes = {i['prefix'] for m in c.manifests().values() for i in m['instruments']}
        self.assertTrue(all(p['instrument'] in prefixes for p in c.provisions().values()))
        self.assertTrue(all(p['text'] for p in c.provisions().values()))


class CitationGraphTests(unittest.TestCase):
    def test_own_instrument_ranges_and_capitalised_units(self):
        self.assertEqual(c.citations()['A-REG 16'], ['A-REG 17', 'A-REG 18', 'A-REG 19'])
        self.assertEqual(c.citations()['B-HRA 3'], ['B-HRA 4', 'B-HRA 5', 'B-HRA 6', 'B-HRA 7', 'B-HRA 8', 'B-HRA 9'])

    def test_regional_law_points_up_to_the_parent_instrument(self):
        # 'Article 7(2), ... of that Regulation' in an Act whose own unit is 'section'
        self.assertEqual(c.citations()['A1-HIA 1'], ['A-REG 7', 'A-REG 8', 'A-REG 12', 'A-REG 21'])
        self.assertEqual(c.citations()['A1-HIA 7'], ['A-REG 8', 'A-REG 19'])
        self.assertEqual(c.cited_by('A-REG 8'), ['A-REG 21', 'A1-HIA 1', 'A1-HIA 4', 'A1-HIA 6', 'A1-HIA 7'])

    def test_cross_instrument_reference_within_one_corpus_and_annexes(self):
        self.assertEqual(c.citations()['B-RAA 2'], ['B-HRA 2'])
        self.assertEqual(c.citations()['A-REG 17'], ['A-REG Annex II'])

    def test_resolve_strips_subdivisions_and_brackets(self):
        self.assertEqual(c.resolve('[A-REG 8(2)(c)]'), 'A-REG 8')
        self.assertIsNone(c.resolve('A-REG 99'))


class SearchAndPassageTests(unittest.TestCase):
    def test_search_is_scoped_to_given_corpora(self):
        hits = c.search('impact assessment hosting patient record system', ['region_b'])
        self.assertTrue(all(c.provisions()[pid]['corpus'] == 'region_b' for pid, _, _ in hits))
        top = [pid for pid, _, _ in c.search('impact assessment hosting patient record system', ['region_a', 'subregion_a1'], k=3)]
        self.assertIn('A1-HIA 8', top)

    def test_passages_are_lines_bound_to_ids(self):
        passages = c.passages('A1-HIA 6')
        self.assertTrue(passages['A1-HIA 6#L3'].startswith('(b) the records are encrypted'))


if __name__ == '__main__':
    unittest.main()
