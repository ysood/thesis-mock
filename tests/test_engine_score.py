"""Scorer: matches findings to key items by cited provisions, not by requirement id."""

import unittest

from engine import score


def finding(ref, status, cites, kind='gate', routes=()):
    return {'ref': ref, 'status': status, 'kind': kind, 'resolved_citations': list(cites), 'verified': True,
            'routes': [{'name': n, 'status': s, 'resolved_citations': list(c)} for n, s, c in routes]}


KEY = {'decision': 'do_not_proceed', 'engaged': {'region_a': True},
       'requirements': [{'id': 'transfer', 'provisions': ['A-REG 16'], 'expect': ['unmet']},
                        {'id': 'impact', 'provisions': ['A-REG 12', 'A1-HIA 8'], 'expect': ['unmet'], 'must_cite': ['A1-HIA 8']},
                        {'id': 'agent', 'provisions': ['A-REG 9'], 'expect': ['met']}],
       'routes': [{'id': 'recognition', 'provisions': ['A-REG 17'], 'expect': ['ruled_out']},
                  {'id': 'legit', 'provisions': ['A-REG 6'], 'name_hint': ['legitimate'], 'expect': ['ruled_out']}],
       'conflicts': [{'id': 'retention', 'provisions': ['B-HRA 9'], 'resolvable': True}],
       'questions': [{'id': 'q', 'asker': 'region_a', 'answerer': 'region_b'}],
       'must_not': [{'id': 'recognition_relied_on', 'type': 'route', 'provisions': ['A-REG 17'], 'status': ['supported']},
                    {'id': 'consent_age', 'type': 'requirement', 'only_cites': ['A-REG 7', 'A-REG 4'],
                     'requires_any': ['A-REG 7'], 'status': ['met', 'unmet', 'undetermined']}]}


def result(findings, conflicts=(), questions=()):
    return {'decision': 'do_not_proceed', 'findings': findings, 'questions': list(questions),
            'plan': {'engagements': [{'corpus': 'region_a', 'engaged': True}]},
            'reviews': [{'conflicts': list(conflicts), 'unresolved': []}]}


class ScoreTests(unittest.TestCase):
    def test_matching_ignores_ids_and_definitions_and_uses_focus(self):
        findings = [finding('region_a:anything', 'unmet', ['A-REG 4', 'A-REG 16']),          # definitions ignored
                    finding('region_a:lawful', 'met', ['A-REG 6', 'A-REG 7', 'A-REG 9']),     # mentions A-REG 9 in passing
                    finding('region_a:agent', 'undetermined', ['A-REG 9'])]
        card = score.score(result(findings), KEY)
        rows = {r['id']: r for r in card['requirements']}
        self.assertTrue(rows['transfer']['ok'])
        self.assertEqual(rows['agent']['best'], 'region_a:agent')
        self.assertFalse(rows['agent']['ok'])  # the passing mention does not rescue it

    def test_must_cite_and_routes_and_traps(self):
        findings = [finding('region_a:impact', 'unmet', ['A-REG 12']),
                    finding('region_a:route', 'unmet', ['A-REG 16'], routes=[
                        ('Recognition', 'supported', ['A-REG 17']), ('Legitimate interests', 'ruled_out', ['A-REG 6'])]),
                    finding('region_a:defs', 'met', ['A-REG 4'])]                           # definitions alone: no trap
        card = score.score(result(findings), KEY)
        self.assertEqual({r['id']: r['ok'] for r in card['requirements']}['impact'], False)
        self.assertEqual({r['id']: r['ok'] for r in card['routes']}, {'recognition': False, 'legit': True})
        self.assertEqual({r['id']: r['violated'] for r in card['must_not']}, {'recognition_relied_on': True, 'consent_age': False})

    def test_conflicts_questions_and_unexplained_blockers(self):
        findings = [finding('region_b:retention', 'unmet', ['B-HRA 9'], kind='duty'),
                    finding('region_a:agent', 'met', ['A-REG 9']),
                    finding('region_a:recognition_route', 'unmet', ['A-REG 17'])]
        conflicts = [{'requirement_refs': ['region_a:agent', 'region_b:retention'], 'resolvable': True}]
        questions = [{'from': 'region_a', 'routed_to': 'region_b', 'status': 'answered'}]
        card = score.score(result(findings, conflicts, questions), KEY)
        self.assertTrue(card['conflicts'][0]['ok'])
        self.assertEqual(card['questions'][0]['times_asked'], 1)
        self.assertEqual(card['extra_blocking'], ['region_a:recognition_route (unmet)'])

    def test_legacy_runs_are_translated(self):
        legacy = result([finding('aster:route', 'unmet', ['APIR 16'])])
        self.assertTrue({r['id']: r['ok'] for r in score.score(legacy, KEY)['requirements']}['transfer'])
        self.assertEqual(score.case_name('20261010-154033_01_valdora_gp_to_corvel_host.json'), '01_a1_gp_to_region_b_host')


if __name__ == '__main__':
    unittest.main()
