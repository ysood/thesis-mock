"""Corpus registry: structure comes from corpora/ manifests and the law's own cross-references."""

import unittest

from engine import corpus as c


class RegistryTests(unittest.TestCase):
    def test_corpora_and_levels_come_from_manifests(self):
        self.assertEqual(list(c.manifests()), ['aster', 'corvel', 'valdora'])
        self.assertEqual(c.top_level(), ['aster', 'corvel'])
        self.assertEqual(c.children('aster'), ['valdora'])
        self.assertEqual(c.jurisdictions()['XV']['member_of'], 'XU')

    def test_every_provision_belongs_to_a_declared_instrument(self):
        prefixes = {i['prefix'] for m in c.manifests().values() for i in m['instruments']}
        self.assertTrue(all(p['instrument'] in prefixes for p in c.provisions().values()))
        self.assertTrue(all(p['text'] for p in c.provisions().values()))


class CitationGraphTests(unittest.TestCase):
    def test_own_instrument_ranges_and_capitalised_units(self):
        self.assertEqual(c.citations()['APIR 16'], ['APIR 17', 'APIR 18', 'APIR 19'])
        self.assertEqual(c.citations()['CHRA 3'], ['CHRA 4', 'CHRA 5', 'CHRA 6', 'CHRA 7', 'CHRA 8', 'CHRA 9'])

    def test_regional_law_points_up_to_the_parent_instrument(self):
        # 'Article 7(2), ... of that Regulation' in an Act whose own unit is 'section'
        self.assertEqual(c.citations()['VHIA 1'], ['APIR 7', 'APIR 8', 'APIR 12', 'APIR 21'])
        self.assertEqual(c.citations()['VHIA 7'], ['APIR 8', 'APIR 19'])
        self.assertEqual(c.cited_by('APIR 8'), ['APIR 21', 'VHIA 1', 'VHIA 4', 'VHIA 6', 'VHIA 7'])

    def test_cross_instrument_reference_within_one_corpus_and_annexes(self):
        self.assertEqual(c.citations()['CRAA 2'], ['CHRA 2'])
        self.assertEqual(c.citations()['APIR 17'], ['APIR Annex II'])

    def test_resolve_strips_subdivisions_and_brackets(self):
        self.assertEqual(c.resolve('[APIR 8(2)(c)]'), 'APIR 8')
        self.assertIsNone(c.resolve('APIR 99'))


class SearchAndPassageTests(unittest.TestCase):
    def test_search_is_scoped_to_given_corpora(self):
        hits = c.search('impact assessment hosting patient record system', ['corvel'])
        self.assertTrue(all(c.provisions()[pid]['corpus'] == 'corvel' for pid, _, _ in hits))
        top = [pid for pid, _, _ in c.search('impact assessment hosting patient record system', ['aster', 'valdora'], k=3)]
        self.assertIn('VHIA 8', top)

    def test_passages_are_lines_bound_to_ids(self):
        passages = c.passages('VHIA 6')
        self.assertTrue(passages['VHIA 6#L3'].startswith('(b) the records are encrypted'))


if __name__ == '__main__':
    unittest.main()
