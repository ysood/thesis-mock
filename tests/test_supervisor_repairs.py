"""Supervisor review policy and bounded self-repair, without legal ground-truth claims."""

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from app import requirements as rq
from app.review import finish_issues
from app.schema import RegimeExclusion, Reconciliation, SupervisorAction, SupervisorPlan
from tests import test_v9


def exclusion(*, citation='45 CFR 160.102', quote='IE', regime='HIPAA'):
    return RegimeExclusion(regime=regime, reasoning='Synthetic routing fixture, not a legal conclusion.',
                           facts=[test_v9.fact_ref('/organisations/0/country', quote)], citations=[citation])


def fixture(agent, schema, system, user, *, conclusive=False):
    answer = test_v9.fake_model(agent, schema, system, user)
    if schema is SupervisorPlan:
        answer.hipaa_plan = None
        answer.exclusions = [exclusion()]
    if conclusive and agent == 'gdpr_specialist':
        for finding in answer.findings:
            finding.status = 'not_applicable'
            finding.citations = ['GDPR Art. 3']
            finding.quote_id = test_v9.legal_quote_id('GDPR Art. 3')
            finding.route_coverage = 'Synthetic applicability exclusion; no legal correctness is asserted.'
    return answer


class SupervisorRepairTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_malformed_exclusion_is_repaired_in_same_finish_without_rerouting(self):
        given = test_v9.load()
        before = deepcopy(given)
        def fake(agent, schema, system, user):
            answer = fixture(agent, schema, system, user, conclusive=True)
            if schema is SupervisorPlan:
                answer.exclusions = [exclusion(citation='[45 CFR 160.102](a)')]
            if schema is SupervisorAction:
                case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                self.assertTrue(any('[45 CFR 160.102](a)' in issue for issue in case['checks']['issues']))
                answer.exclusions = [exclusion()]
                answer.decision = 'proceed'
            return answer
        result, events = self.run_fake(fake, given)
        case = result['case_record']
        self.assertEqual(result['decision'], 'proceed')
        self.assertTrue(case['checks']['complete'])
        self.assertFalse(case['checks']['setup_issues'])
        self.assertEqual(case['supervisor']['exclusions'], [exclusion().model_dump()])
        self.assertIn({'action': 'exclusions_update', 'accepted': True}, case['supervisor']['action_log'])
        self.assertFalse(result['routing']['hipaa'])
        self.assertEqual(len(result['findings']), 10)
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 3)
        self.assertFalse(any(e['kind'] == 'llm_request' and e['agent'] == 'hipaa_specialist' for e in events))
        self.assertEqual(given, before)
        self.assertEqual({key: value for key, value in case['input'].items() if key != 'reference_facts'}, before)

    def test_invalid_or_rerouting_replacements_preserve_prior_exclusion_and_conservative_finish(self):
        updates = {
            'citation': [exclusion(citation='invented.provision')],
            'fact': [exclusion(quote='Unstated country')],
            'duplicate': [exclusion(), exclusion()],
            'added_regime': [exclusion(), exclusion(regime='GDPR', citation='GDPR Art. 3')],
            'removed_regime': [],
        }
        for name, update in updates.items():
            with self.subTest(update=name):
                def fake(agent, schema, system, user):
                    answer = fixture(agent, schema, system, user)
                    if schema is SupervisorAction:
                        answer.exclusions = update
                    return answer
                result, events = self.run_fake(fake)
                case = result['case_record']
                self.assertEqual(case['supervisor']['exclusions'], [exclusion().model_dump()])
                self.assertTrue(case['checks']['exclusion_update_issues'])
                self.assertTrue(any('exclusion' in issue.lower() for issue in case['checks']['issues']))
                self.assertEqual(case['supervisor']['review']['decision'], 'needs_review')
                self.assertIsNone(case['supervisor']['review']['exclusions'])
                self.assertFalse(case['checks'].get('runtime_issues'))
                self.assertFalse(result['routing']['hipaa'])
                self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 3)
                self.assertFalse(any(e['kind'] == 'llm_request' and e['agent'] == 'hipaa_specialist' for e in events))

    def test_rejected_update_blocks_proceed_until_valid_repair(self):
        for repair in (False, True):
            with self.subTest(repair=repair):
                turns = 0
                def fake(agent, schema, system, user):
                    nonlocal turns
                    answer = fixture(agent, schema, system, user, conclusive=True)
                    if schema is SupervisorAction:
                        turns += 1
                        answer.decision = 'proceed'
                        answer.exclusions = [exclusion() if repair and turns > 1 else exclusion(quote='Missing fact')]
                    return answer
                result, _ = self.run_fake(fake)
                case = result['case_record']
                self.assertEqual(case['supervisor']['exclusions'], [exclusion().model_dump()])
                if repair:
                    self.assertEqual(turns, 2)
                    self.assertEqual(result['decision'], 'proceed')
                    self.assertNotIn('exclusion_update_issues', case['checks'])
                    self.assertTrue(case['checks']['complete'])
                else:
                    self.assertEqual(result['decision'], 'needs_review')
                    self.assertIsNone(case['supervisor']['review'])
                    self.assertTrue(case['checks']['exclusion_update_issues'])

    def test_rejected_optional_update_does_not_lose_established_gate_refusal(self):
        def fake(agent, schema, system, user):
            answer = fixture(agent, schema, system, user, conclusive=True)
            if agent == 'gdpr_specialist':
                for finding in answer.findings:
                    if finding.question_ids == ['gdpr.applicability']:
                        finding.status = 'satisfied_if_verified'
                    elif finding.question_ids == ['gdpr.lawful_basis']:
                        finding.status = 'not_satisfied'
                        finding.citations = ['GDPR Art. 6']
                        finding.quote_id = test_v9.legal_quote_id('GDPR Art. 6')
            if schema is SupervisorAction:
                answer.decision = 'do_not_proceed'
                answer.exclusions = [exclusion(citation='invented.provision')]
            return answer
        result, events = self.run_fake(fake)
        case = result['case_record']
        self.assertEqual(result['decision'], 'do_not_proceed')
        self.assertEqual(case['supervisor']['review']['decision'], 'do_not_proceed')
        self.assertIsNone(case['supervisor']['review']['exclusions'])
        self.assertTrue(case['checks']['exclusion_update_issues'])
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 3)

    def test_policy_survives_rejection_and_specialist_budget_exhaustion(self):
        expected = {item['key']: {key: item[key] for key in ('class', 'class_reason')}
                    for item in rq.items('GDPR')}
        turns = 0
        def fake(agent, schema, system, user):
            nonlocal turns
            answer = fixture(agent, schema, system, user)
            if schema is SupervisorAction:
                turns += 1
                case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                self.assertEqual(case['checks']['requirement_policy'], expected)
                if turns > 1:
                    self.assertEqual(case['checks']['review_counts']['gdpr_specialist'], 2)
                    self.assertNotIn('gdpr_specialist', case['checks']['available_actions'])
                if turns in (1, 2):
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            question_ids=['gdpr.lawful_basis'], instruction='Synthetic targeted review.')
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(turns, 3)
        self.assertIsNotNone(result['case_record']['supervisor']['review'])
        self.assertEqual(sum(e['kind'] == 'llm_request' and e['agent'] == 'gdpr_specialist' for e in events), 2)
        self.assertTrue(any(e['kind'] == 'supervisor_action' and 'budget is exhausted' in e.get('reason', '') for e in events))

    def test_refusal_feedback_uses_catalogue_class_without_hardcoded_question(self):
        key = 'gdpr.synthetic_advisory'
        catalogue = {'requirements': [
            {'key': 'gdpr.applicability', 'regime': 'GDPR', 'class': 'gate', 'class_reason': 'Synthetic applicability.'},
            {'key': key, 'regime': 'GDPR', 'class': 'advisory', 'class_reason': 'Synthetic ongoing duty.'},
        ]}
        checked = [
            {'finding_id': 'applies', 'question_ids': ['gdpr.applicability'], 'agent': 'gdpr_specialist',
             'regime': 'GDPR', 'verified': True, 'status': 'satisfied_if_verified', 'obligation_scope': 'transfer'},
            {'finding_id': 'advice', 'question_ids': [key], 'agent': 'gdpr_specialist',
             'regime': 'GDPR', 'verified': True, 'status': 'not_satisfied', 'obligation_scope': 'transfer'},
        ]
        action = SupervisorAction(action='finish', decision='do_not_proceed', accepted_finding_ids=['applies', 'advice'],
                                  reasons=['Synthetic refusal.'], reconciliation=Reconciliation(conflicts=[], summary='Fixture.'))
        with patch.object(rq, 'catalogue', return_value=catalogue):
            defects = finish_issues(action, checked, [], [])
        self.assertTrue(any(key in note and 'advisory' in note for note in defects))


if __name__ == '__main__':
    unittest.main()
