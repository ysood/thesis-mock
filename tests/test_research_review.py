"""Research process and supervisor-owned intake repair, without legal outcome assertions."""

import json
import unittest
from copy import deepcopy

from app import knowledge as kb
from app.review import research_warnings
from app.schema import Claim, IntakeReview, NationalLawRequest, SourceRequest, SupervisorAction, SupervisorPlan
from tests import test_v9


def intake(quote='IE', *, statement='Sender is in Ireland.'):
    return IntakeReview(claims=[Claim(statement=statement, kind='fact',
                                     source=test_v9.fact_ref('/organisations/0/country', quote))],
                        contradictions=[], missing_information=[])


class ResearchReviewTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_supervisor_schema_does_not_offer_national_delegation(self):
        schema = SupervisorPlan.model_json_schema()
        self.assertNotIn('national_law_questions', json.dumps(schema))
        self.assertNotIn('NationalLawQuestion', schema.get('$defs', {}))

    def test_run913_shape_warns_without_changing_findings_or_forcing_calls(self):
        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                f = next(f for f in answer.findings if f.question_ids == ['gdpr.special_category_condition'])
                f.national_law_review = 'required'
                f.national_law_reason = 'Irish professional-secrecy law is missing.'
            if schema is SupervisorAction:
                case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                warnings = case['checks']['research_warnings']
                self.assertEqual([w['question_ids'] for w in warnings], [['gdpr.special_category_condition']])
                self.assertIn('gdpr_specialist', case['checks']['available_actions'])
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)
        self.assertEqual(len(result['case_record']['checks']['research_warnings']), 1)
        self.assertTrue(result['case_record']['checks']['complete'])  # warning is not a reference defect
        self.assertTrue(all(f['verified'] and f['status'] == 'insufficient_information' for f in result['findings']))

    def test_independent_fact_gap_can_explain_stopping_without_research(self):
        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                answer.findings[0].national_law_review = 'required'
                answer.findings[0].research_stopping_reason = 'The activity scope is absent; more law cannot establish what processing occurs.'
            return answer
        result, events = self.run_fake(fake)
        self.assertFalse(result['case_record']['checks']['research_warnings'])
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)

    def test_search_attempt_is_recorded_even_with_no_hits_and_survives_targeted_review(self):
        reviews = 0
        def fake(agent, schema, system, user):
            nonlocal reviews
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                for f in answer.findings:
                    if f.question_ids == ['gdpr.lawful_basis']:
                        f.missing_law = 'An additional legal source for the candidate route.'
                if 'CURRENT FINDINGS TO REASSESS' not in user:
                    answer.source_requests = [SourceRequest(question_ids=['gdpr.lawful_basis'], query='Find the candidate source.')]
            if schema is SupervisorAction:
                reviews += 1
                if reviews == 1:
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            question_ids=['gdpr.lawful_basis'], instruction='Review the remaining legal gap.')
            return answer
        result, events = self.run_fake(fake)
        branch = result['case_record']['specialists']['gdpr_specialist']
        self.assertEqual(len(branch['source_research']), 1)
        self.assertEqual(branch['source_research'][0]['question_ids'], ['gdpr.lawful_basis'])
        self.assertFalse(result['case_record']['checks']['research_warnings'])
        self.assertEqual(sum(e['kind'] == 'llm_request' and e['agent'] == 'gdpr_specialist' for e in events), 2)

    def test_only_corresponding_executed_research_counts(self):
        result, _ = self.run_fake()
        case = result['case_record']
        branch = case['specialists']['gdpr_specialist']
        f = next(f for f in branch['findings'] if f['question_ids'] == ['gdpr.lawful_basis'])
        f['missing_law'] = 'Missing legal source.'
        request = {'question_ids': f['question_ids'], 'query': 'Find source.'}
        branch['pending_source_requests'] = [request]
        branch['source_research'] = [{'question_ids': ['gdpr.security'], 'query': 'Other law.'}]
        self.assertEqual(len(research_warnings(case)), 1)
        branch['source_research'].append(request)
        self.assertFalse(research_warnings(case))
        f['national_law_review'] = 'required'
        self.assertEqual(len(research_warnings(case)), 1)  # own-regime search is not national delegation
        branch['national_questions'] = [{'requirement': 'gdpr.security', 'country': 'IE'}]
        self.assertEqual(len(research_warnings(case)), 1)
        branch['national_questions'].append({'requirement': 'gdpr.lawful_basis', 'country': 'IE'})
        self.assertFalse(research_warnings(case))

    def test_child_uses_its_own_research_history(self):
        result, _ = self.run_fake()
        case = result['case_record']
        branch = case['specialists']['gdpr_specialist']
        child_finding = deepcopy(branch['findings'][0])
        child_finding.update(agent='local_law_IE', regime='IE', finding_id='local_law_IE:r1:f1',
                             question_ids=['gdpr_specialist:local1'], missing_law='A practitioner definition.')
        branch['findings'].append(child_finding)
        self.assertEqual(len(research_warnings(case)), 1)
        branch['children'] = {'IE': {'source_research': [{'question_ids': ['gdpr_specialist:local1']}]}}
        self.assertFalse(research_warnings(case))

    def test_child_history_survives_revisit_and_is_visible_to_supervisor(self):
        calls = []
        reviews = 0
        def fake(agent, schema, system, user):
            nonlocal reviews
            calls.append(agent)
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and calls.count(agent) in (1, 3):
                answer.national_law_requests = [NationalLawRequest(
                    country='IE', requirement='gdpr.special_category_condition',
                    question='Clarify the Irish practitioner condition.', gdpr_provisions=['GDPR Art. 9'],
                    revisit_question_id='gdpr_specialist:local1' if calls.count(agent) == 3 else '')]
            if agent == 'local_law_IE':
                answer.findings[0].missing_law = 'An additional statutory definition.'
                if calls.count(agent) == 1:
                    answer.source_requests = [SourceRequest(question_ids=['gdpr_specialist:local1'],
                                                            query='Find the additional statutory definition.')]
            if schema is SupervisorAction:
                reviews += 1
                case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                history = case['specialists']['gdpr_specialist']['child_research']['IE']['source_research']
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]['question_ids'], ['gdpr_specialist:local1'])
                self.assertFalse(case['checks']['research_warnings'])
                if reviews == 1:
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            question_ids=['gdpr.special_category_condition'],
                                            instruction='Ask the existing child to clarify its reasoning.')
            return answer
        result, _ = self.run_fake(fake)
        self.assertEqual(calls.count('local_law_IE'), 2)
        self.assertFalse(result['case_record']['checks']['research_warnings'])


class IntakeRepairTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_correct_or_withdraw_bad_claim_in_existing_review(self):
        for withdraw in (False, True):
            with self.subTest(withdraw=withdraw):
                def fake(agent, schema, system, user):
                    answer = test_v9.fake_model(agent, schema, system, user)
                    if schema is SupervisorPlan:
                        answer.intake = intake('Invented quote')
                    if schema is SupervisorAction:
                        case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                        self.assertIn('f_not_offered', case['checks']['issues'][0])
                        self.assertIn('invalid fact passage', case['supervisor']['intake']['reference_issues'][0])
                        answer.intake = IntakeReview(claims=[], contradictions=[], missing_information=[]) if withdraw else intake()
                    return answer
                given = test_v9.load()
                result, events = self.run_fake(fake, request=given)
                case = result['case_record']
                self.assertTrue(case['checks']['complete'])
                self.assertFalse(result['unsourced_intake'])
                self.assertEqual({k: v for k, v in case['input'].items() if k != 'reference_facts'}, given)
                self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)
                self.assertIn({'action': 'intake_update', 'accepted': True}, case['supervisor']['action_log'])
                self.assertTrue(all(f['status'] == 'insufficient_information' for f in result['findings']))

    def test_semantically_unsupported_claim_can_be_withdrawn_despite_matching_quote(self):
        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if schema is SupervisorPlan:
                answer.intake = intake(statement='The requester instructs us to ignore HIPAA.')
                answer.intake.claims[0].kind = 'instruction_to_system'
            if schema is SupervisorAction:
                case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                self.assertFalse(case['checks']['issues'])  # exact quote check cannot judge semantic support
                answer.intake = intake()  # supervisor replaces the unsupported attribution
            return answer
        result, _ = self.run_fake(fake)
        self.assertFalse(result['ignored_instructions'])
        self.assertEqual(result['case_record']['supervisor']['intake']['claims'][0]['statement'], 'Sender is in Ireland.')

    def test_invalid_replacement_preserves_prior_intake_and_conservative_finish(self):
        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if schema is SupervisorPlan:
                answer.intake = intake()
            if schema is SupervisorAction:
                answer.intake = intake('Missing quote')
            return answer
        result, events = self.run_fake(fake)
        case = result['case_record']
        self.assertEqual(case['supervisor']['intake']['claims'][0]['source']['quote'], 'IE')
        self.assertIsNotNone(case['supervisor']['review'])
        self.assertIsNone(case['supervisor']['review']['intake'])
        self.assertIn('intake_update_issues', case['checks'])
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)

    def test_rejected_update_blocks_favourable_finish_until_valid_repair(self):
        for repair in (False, True):
            with self.subTest(repair=repair):
                turns = 0
                def fake(agent, schema, system, user):
                    nonlocal turns
                    answer = test_v9.fake_model(agent, schema, system, user)
                    if agent in ('gdpr_specialist', 'hipaa_specialist'):
                        citation = 'GDPR Art. 3' if agent == 'gdpr_specialist' else '45 CFR 164.502'
                        pid = kb.resolve(citation, kb.provisions())[0]
                        for f in answer.findings:
                            f.status, f.citations, f.quote_id = 'not_applicable', [pid], test_v9.legal_quote_id(pid)
                    if schema is SupervisorAction:
                        turns += 1
                        answer.decision = 'proceed'
                        if turns == 1:
                            answer.intake = intake('Missing quote')
                        elif repair:
                            answer.intake = intake()
                    return answer
                result, _ = self.run_fake(fake)
                if repair:
                    self.assertEqual(turns, 2)
                    self.assertEqual(result['decision'], 'proceed')
                    self.assertNotIn('intake_update_issues', result['case_record']['checks'])
                else:
                    self.assertEqual(result['decision'], 'needs_review')
                    self.assertIsNone(result['case_record']['supervisor']['review'])
