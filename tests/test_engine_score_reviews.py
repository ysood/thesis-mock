"""Evidence-linked score corrections preserve raw matches and fail closed when stale."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from engine import score


KEY = {'decision': 'do_not_proceed', 'engaged': {},
       'requirements': [{'id': 'retention', 'provisions': ['B-HRA 9'], 'expect': ['not_applicable']}],
       'routes': [], 'conflicts': [], 'questions': [], 'must_not': []}
RESULT = {'decision': 'do_not_proceed', 'plan': None, 'reviews': [], 'questions': [],
          'findings': [{'ref': 'region_b:scope', 'status': 'not_applicable', 'kind': 'gate',
                        'resolved_citations': ['B-HRA 2', 'B-HRA 3'], 'verified': True, 'routes': [],
                        'reasoning': 'The recipient stores its own care record, not records on behalf of another person. '
                                     'It is not a data host and Section 9 does not apply.'}]}


def ledger():
    return {'version': 1, 'key_sha256': score.fingerprint(KEY), 'reviewer': 'offline test',
            'criterion': 'Correct selected concept, regardless of output location.',
            'runs': [{'result_sha256': score.fingerprint(RESULT), 'label': 'copied answer',
                      'raw_outcomes_sha256': score.fingerprint(score.outcomes(score.score(RESULT, KEY))),
                      'reviewed_checks': ['decision', 'requirement:retention'],
                      'overrides': [{'check': 'requirement:retention', 'expected_raw': False,
                                     'passed': True, 'reason': 'Explicit scope conclusion uses definitions.',
                                     'evidence': [{'pointer': '/findings/0/reasoning',
                                                   'quote': 'It is not a data host and Section 9 does not apply.'}]}]}]}


class ReviewTests(unittest.TestCase):
    def test_raw_and_reviewed_outcomes_stay_separate(self):
        card = score.score(RESULT, KEY, ledger())
        self.assertFalse(card['requirements'][0]['ok'])
        self.assertTrue(card['reviewed']['requirements'][0]['ok'])
        self.assertEqual(card['summary']['requirements_correct'], '0/1')
        self.assertEqual(card['reviewed']['summary']['requirements_correct'], '1/1')
        self.assertEqual(card['review_metadata']['raw_passed'], 1)
        self.assertEqual(card['review_metadata']['reviewed_passed'], 2)
        self.assertEqual(RESULT['findings'][0]['resolved_citations'], ['B-HRA 2', 'B-HRA 3'])

    def test_canonical_json_and_copied_filenames_use_same_review(self):
        reordered = json.loads(json.dumps(RESULT, sort_keys=True, indent=4))
        self.assertEqual(score.score(reordered, KEY, ledger())['review_status'], 'reviewed')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'key.json'
            path.write_text(json.dumps(KEY))
            (path.parent / 'score_reviews.json').write_text(json.dumps(ledger()))
            card = score.score_file(reordered, path)
            self.assertTrue(card['reviewed']['requirements'][0]['ok'])

    def test_changed_answer_or_key_does_not_inherit_review(self):
        changed = deepcopy(RESULT)
        changed['findings'][0]['reasoning'] = 'The recipient is a data host.'
        self.assertEqual(score.score(changed, KEY, ledger())['review_status'], 'not_reviewed')
        key = deepcopy(KEY)
        key['requirements'][0]['expect'] = ['met']
        self.assertEqual(score.score(RESULT, key, ledger())['review_status'], 'different_key')

    def test_evidence_errors_and_wrong_raw_expectation_are_rejected(self):
        for field, value in (('pointer', '/findings/9/reasoning'), ('quote', 'No such statement.')):
            review = ledger()
            review['runs'][0]['overrides'][0]['evidence'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                score.score(RESULT, KEY, review)
        review = ledger()
        review['runs'][0]['overrides'][0]['expected_raw'] = True
        with self.assertRaisesRegex(ValueError, 'raw expectation'):
            score.score(RESULT, KEY, review)

    def test_unknown_duplicate_or_partial_review_is_rejected(self):
        for kind in ('unknown', 'duplicate', 'partial', 'duplicate_run', 'nonboolean', 'missing_evidence'):
            review = ledger()
            entry = review['runs'][0]
            if kind == 'unknown': entry['overrides'][0]['check'] = 'requirement:unlisted'
            if kind == 'duplicate': entry['overrides'].append(deepcopy(entry['overrides'][0]))
            if kind == 'partial': entry['reviewed_checks'] = ['decision']
            if kind == 'duplicate_run': review['runs'].append(deepcopy(entry))
            if kind == 'nonboolean': entry['overrides'][0]['passed'] = 'true'
            if kind == 'missing_evidence': entry['overrides'][0]['evidence'] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                score.score(RESULT, KEY, review)

    def test_review_can_remove_a_false_pass(self):
        key = deepcopy(KEY)
        key['requirements'][0]['provisions'] = ['B-HRA 2', 'B-HRA 3']
        review = ledger()
        review['key_sha256'] = score.fingerprint(key)
        correction = review['runs'][0]['overrides'][0]
        correction.update(expected_raw=True, passed=False, reason='A matching status lacks the required assessment.')
        review['runs'][0]['raw_outcomes_sha256'] = score.fingerprint(score.outcomes(score.score(RESULT, key)))
        card = score.score(RESULT, key, review)
        self.assertTrue(card['requirements'][0]['ok'])
        self.assertFalse(card['reviewed']['requirements'][0]['ok'])

    def test_unrelated_or_empty_answer_gets_no_automatic_credit(self):
        unrelated = deepcopy(RESULT)
        unrelated['findings'][0]['reasoning'] = 'Some unrelated rule is satisfied.'
        self.assertFalse(score.score(unrelated, KEY, ledger())['requirements'][0]['ok'])
        empty = {**RESULT, 'decision': 'needs_review', 'findings': []}
        card = score.score(empty, KEY, ledger())
        self.assertEqual(sum(score.outcomes(card).values()), 0)
        self.assertNotIn('reviewed', card)

    def test_scorer_drift_is_rejected_even_without_overrides(self):
        review = ledger()
        review['runs'][0]['overrides'] = []
        changed = {**score.check_requirement(RESULT['findings'], KEY['requirements'][0]), 'ok': True}
        with patch.object(score, 'check_requirement', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'raw outcomes differ'):
                score.score(RESULT, KEY, review)

    def test_noncanonical_array_indices_and_bad_escapes_are_rejected(self):
        for pointer in ('/findings/-1/reasoning', '/findings/+0/reasoning',
                        '/findings/00/reasoning', '/findings/0/reasoning~2'):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                score.pointer_value(RESULT, pointer)


if __name__ == '__main__':
    unittest.main()
