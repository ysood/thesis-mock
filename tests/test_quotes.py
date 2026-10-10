"""Fact quotes may skip words with an ellipsis; every kept piece must still be exact and in order."""

import unittest

from app import knowledge as kb
from app.review import quote_pieces, quoted_fact

TEXT = ('Named accounts with MFA for every clinician and staff member, role-based access, '
        'encryption in transit and at rest, access logs reviewed monthly by the practice manager.')
DOC = {'evidence': [{'summary': TEXT}], 'organisations': [{'country': 'IE'}]}
PATH = '/evidence/0/summary'


def ok(quote, path=PATH):
    return quoted_fact({'path': path, 'quote': quote}, DOC)


class QuoteTests(unittest.TestCase):
    def test_contiguous_quotes_still_pass(self):
        self.assertTrue(ok('role-based access, encryption in transit'))
        self.assertTrue(ok('IE', '/organisations/0/country'))

    def test_run196_ellipsis_excerpt_passes(self):
        self.assertTrue(ok('Named accounts with MFA ... role-based access, encryption in transit and at rest'))
        self.assertTrue(ok('Named accounts with MFA … access logs reviewed monthly'))

    def test_pieces_must_be_exact_ordered_and_non_overlapping(self):
        self.assertFalse(ok('encryption in transit and at rest … Named accounts with MFA'))
        self.assertFalse(ok('Named accounts with MFA … encryption in transit and in storage'))
        self.assertFalse(ok('access logs … access logs'))
        self.assertFalse(ok('…'))
        self.assertFalse(ok(''))

    def test_pieces_cannot_join_fields(self):
        self.assertFalse(ok('Named accounts with MFA … IE'))
        self.assertFalse(ok('Named accounts … ie'))  # not inside 'reviewed'
        self.assertTrue(ok('Named accounts … reviewed monthly'))

    def test_quote_pieces(self):
        self.assertEqual(quote_pieces('A b … c d... e'), ['a b', 'c d', 'e'])


class CorpusSpacingTests(unittest.TestCase):
    """run0111: the scraped IE DPA s. 54 text reads 'section 42\\n,'; a correct quote 'section 42,' failed."""

    def test_line_break_before_punctuation_is_ignored(self):
        text = kb.normalise_text(kb.provisions()['IE DPA 2018 s. 54']['text'])
        self.assertIn(kb.normalise_text('Subject to compliance with section 42, the processing of special '
                                        'categories of personal data is lawful'), text)
        self.assertEqual(kb.normalise_text('see ( a ) and b ,c'), 'see (a) and b,c')

    def test_skipped_text_still_fails(self):
        text = kb.normalise_text(kb.provisions()['IE DPA 2018 s. 54']['text'])
        self.assertNotIn(kb.normalise_text('necessary and proportionate for— (b) scientific'), text)


if __name__ == '__main__':
    unittest.main()
