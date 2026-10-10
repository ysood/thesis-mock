"""Request boundaries and recorded failure shapes; all model/retrieval calls are offline."""

import unittest

from app import knowledge as kb, passages
from app.requests import RequestError, prepare_request
from app.schema import NationalLawRequest, SourceRequest, SupervisorAction
from tests import test_v9

fake_model = test_v9.fake_model


class RequestTests(unittest.TestCase):
    def test_run912_bracketed_retrieval_ids_are_normalised_without_mutating_reply(self):
        request = SourceRequest(question_ids=['[gdpr_specialist:local1]'], query='Find the statutory definition.')
        actual = prepare_request(request, actor='local_law_IE', regime='IE', questions=['gdpr_specialist:local1'])
        self.assertEqual(actual.question_ids, ['gdpr_specialist:local1'])
        self.assertEqual(request.question_ids, ['[gdpr_specialist:local1]'])

    def test_supervisor_uses_same_normalisation_for_current_ids(self):
        request = SupervisorAction(action='delegate', target='[GDPR_SPECIALIST]',
                                   question_ids=['[gdpr.lawful_basis]'], finding_ids=['[gdpr_specialist:r1.a:f3]'],
                                   instruction=' Review the basis. ', provision_ids=['[GDPR Art. 6(1)(b)]'])
        actual = prepare_request(request, actor='supervisor', regime='GDPR', questions=['gdpr.lawful_basis'],
                                 targets=['gdpr_specialist'], finding_ids=['gdpr_specialist:r1.a:f3'])
        self.assertEqual(actual.target, 'gdpr_specialist')
        self.assertEqual(actual.question_ids, ['gdpr.lawful_basis'])
        self.assertEqual(actual.finding_ids, ['gdpr_specialist:r1.a:f3'])
        self.assertEqual(actual.provision_ids, ['GDPR Art. 6'])
        self.assertEqual(actual.instruction, 'Review the basis.')

    def test_unknown_ambiguous_and_child_ids_are_not_guessed(self):
        for question, assigned in [('unknown', ['gdpr.lawful_basis']),
                                   ('applicability', ['gdpr.applicability', 'hipaa.applicability']),
                                   ('gdpr_specialist:local1', ['gdpr.special_category_condition'])]:
            with self.subTest(question=question), self.assertRaises(RequestError):
                prepare_request(SourceRequest(question_ids=[question], query='Review'),
                                actor='gdpr_specialist', regime='GDPR', questions=assigned)

    def test_empty_request_wrong_regime_and_stale_finding_are_rejected(self):
        with self.assertRaises(RequestError):
            prepare_request(SourceRequest(question_ids=['gdpr.lawful_basis'], query=' '),
                            actor='gdpr_specialist', regime='GDPR', questions=['gdpr.lawful_basis'])
        with self.assertRaises(RequestError):
            prepare_request(SourceRequest(question_ids=['gdpr.lawful_basis'], query='', provision_ids=['IE DPA 2018 s. 52']),
                            actor='gdpr_specialist', regime='GDPR', questions=['gdpr.lawful_basis'])
        with self.assertRaises(RequestError):
            prepare_request(SupervisorAction(action='delegate', target='gdpr_specialist', instruction='Review',
                                            question_ids=['gdpr.lawful_basis'], finding_ids=['gdpr_specialist:r1.a:f3']),
                            actor='supervisor', regime='GDPR', questions=['gdpr.lawful_basis'],
                            targets=['gdpr_specialist'], finding_ids=['gdpr_specialist:r2.a:f3'])

    def test_national_request_normalises_parent_and_preserves_revisit_scope(self):
        old = {'question_id': 'gdpr_specialist:local1', 'country': 'IE',
               'requirement': 'gdpr.special_category_condition'}
        request = NationalLawRequest(country='ie', requirement='[gdpr.special_category_condition]', question='Clarify the definition.',
                                     gdpr_provisions=['[GDPR Art. 9]'], revisit_question_id='[gdpr_specialist:local1]')
        args = dict(actor='gdpr_specialist', regime='GDPR', questions=['gdpr.special_category_condition'], national=[old])
        actual = prepare_request(request, **args)
        self.assertEqual(actual.country, 'IE')
        self.assertEqual(actual.revisit_question_id, old['question_id'])
        self.assertEqual(actual.gdpr_provisions, ['GDPR Art. 9'])
        with self.assertRaises(RequestError):
            prepare_request(request.model_copy(update={'country': 'FR'}), **args)
        with self.assertRaises(RequestError):
            prepare_request(request.model_copy(update={'revisit_question_id': 'gdpr_specialist:local2'}), **args)
        with self.assertRaises(RequestError):
            prepare_request(request.model_copy(update={'gdpr_provisions': ['IE DPA 2018 s. 52']}), **args)


class RequestRuntimeTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_child_retrieval_gets_past_brackets_and_parent_gets_reassessment(self):
        calls, added = [], []
        def fake(agent, schema, system, user):
            calls.append(agent)
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and calls.count(agent) == 1:
                answer.national_law_requests = [NationalLawRequest(
                    country='IE', requirement='[gdpr.special_category_condition]', question='Identify the Irish treatment route.',
                    gdpr_provisions=['GDPR Art. 9'])]
            if agent == 'local_law_IE':
                self.assertIn(passages.render(passages.provision_passages('IE HIA 2014 s. 2 [health practitioner]')), user)
                self.assertIn(passages.render(passages.provision_passages('IE MPA 2007 s. 2 [registered medical practitioner]')), user)
                if calls.count(agent) == 1:
                    pid = next(p for p, law in kb.provisions().items() if law['regime'] == 'IE' and f'[{p}]' not in user)
                    added.append(pid)
                    answer.source_requests = [SourceRequest(question_ids=['[gdpr_specialist:local1]'],
                                                            query='', provision_ids=[pid])]
                else:
                    self.assertIn(f'[{added[0]}]', user)
            return answer
        result, events = self.run_fake(fake, search_results=[('IE DPA 2018 s. 52', 0.1)])
        self.assertEqual(calls.count('local_law_IE'), 2)
        self.assertEqual(calls.count('gdpr_specialist'), 2)
        self.assertTrue(result['case_record']['checks']['complete'])
        self.assertTrue(all(f['status'] == 'insufficient_information' for f in result['findings']))
        self.assertTrue(any(e['kind'] == 'request_validated' and e['changes']
                            and e['request_type'] == 'SourceRequest' for e in events))

    def test_one_invalid_retrieval_does_not_drop_a_valid_sibling_or_hide_the_error(self):
        calls = 0
        def fake(agent, schema, system, user):
            nonlocal calls
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                calls += 1
                if calls == 1:
                    pid = next(p for p, law in kb.provisions().items() if law['regime'] == 'GDPR' and f'[{p}]' not in user)
                    answer.source_requests = [SourceRequest(question_ids=['invented'], query='Find law.'),
                                              SourceRequest(question_ids=['[gdpr.accountability]'], query='', provision_ids=[pid])]
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(calls, 2)
        self.assertTrue(any('invented' in issue for issue in result['case_record']['checks']['issues']))
        self.assertTrue(any(e['kind'] == 'request_rejected' for e in events))

    def test_already_available_sources_do_not_trigger_another_model_call(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                answer.source_requests = [SourceRequest(question_ids=['gdpr.lawful_basis'], query='', provision_ids=['GDPR Art. 6'])]
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)
        self.assertTrue(result['case_record']['checks']['complete'])
        added = next(e for e in events if e['kind'] == 'sources_added')
        self.assertEqual(added['ids'], [])
        self.assertIn('GDPR Art. 6', added['already_available'])

    def test_invalid_national_request_stays_visible_after_valid_child_review(self):
        calls = 0
        def fake(agent, schema, system, user):
            nonlocal calls
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                calls += 1
                if calls == 1:
                    answer.national_law_requests = [
                        NationalLawRequest(country='IE', requirement='invented', question='Find Irish law.'),
                        NationalLawRequest(country='IE', requirement='gdpr.special_category_condition',
                                           question='Identify the treatment route.', gdpr_provisions=['GDPR Art. 9'])]
            return answer
        result, events = self.run_fake(fake)
        self.assertTrue(any(e['kind'] == 'llm_request' and e['agent'] == 'local_law_IE' for e in events))
        self.assertTrue(any('invented' in issue for issue in result['case_record']['checks']['issues']))

    def test_processed_pending_question_does_not_remain_in_next_review(self):
        gdpr_calls, supervisor_calls = 0, 0
        def request(topic):
            return NationalLawRequest(country='IE', requirement='gdpr.special_category_condition',
                                      question='Clarify '+topic, gdpr_provisions=['GDPR Art. 9'])
        def fake(agent, schema, system, user):
            nonlocal gdpr_calls, supervisor_calls
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                gdpr_calls += 1
                if gdpr_calls == 1:
                    answer.national_law_requests = [request('Article 9(2)(h) healthcare basis')]
                if gdpr_calls in (2, 3):
                    answer.national_law_requests = [request('Article 9(4) additional conditions')]
            if schema is SupervisorAction:
                supervisor_calls += 1
                if supervisor_calls == 1:
                    return SupervisorAction(action='delegate', target='[gdpr_specialist]',
                                            question_ids=['[gdpr.special_category_condition]'], instruction='Resolve the pending question.')
            return answer
        result, _ = self.run_fake(fake)
        branch = result['case_record']['specialists']['gdpr_specialist']
        self.assertEqual(gdpr_calls, 4)
        self.assertEqual(len(branch['national_questions']), 2)
        self.assertEqual(branch['pending_national_requests'], [])
        self.assertTrue(result['case_record']['checks']['complete'])


if __name__ == '__main__':
    unittest.main()


class ChildCitationTests(unittest.TestCase):
    """run113/193/212: GDPR cited Irish law that only its national child had been given."""
    run_fake = test_v9.RuntimeTests.run_fake

    def test_gdpr_can_read_and_cite_law_its_child_cited(self):
        pid = 'IE DPA 2018 s. 52'
        quote_id = test_v9.legal_quote_id(pid)
        calls, prompts = [], []

        def fake(agent, schema, system, user):
            calls.append(agent)
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and calls.count(agent) == 1:
                answer.national_law_requests = [NationalLawRequest(
                    country='IE', requirement='gdpr.special_category_condition', question='Identify the Irish treatment route.',
                    gdpr_provisions=['GDPR Art. 9'])]
            elif agent == 'local_law_IE':
                self.assertIn(f'[{pid}]', user)
                answer.findings[0].citations, answer.findings[0].quote_id = [pid], quote_id
            elif agent == 'gdpr_specialist':
                prompts.append(user)
                for f in answer.findings:
                    if f.question_ids == ['gdpr.special_category_condition']:
                        f.citations, f.quote_id = [pid], quote_id
            return answer

        result, _ = self.run_fake(fake, search_results=[('IE DPA 2018 s. 52', 0.1)])
        self.assertEqual(calls.count('gdpr_specialist'), 2)
        self.assertIn(f'[{pid}]', prompts[0])  # GDPR now reads the text it relies on
        art9 = next(f for f in result['findings'] if f['agent'] == 'gdpr_specialist'
                    and f['question_ids'] == ['gdpr.special_category_condition'])
        self.assertIn(pid, art9['resolved_citations'])
        self.assertFalse([n for n in art9['verification_notes'] if 'not supplied' in n])


class NationalQuestionSelectionTests(unittest.TestCase):
    """National questions are selected by the specialist, never inserted as companions."""
    run_fake = test_v9.RuntimeTests.run_fake

    def test_research_route_question_does_not_force_art9_4_review(self):
        child_prompts, calls = [], []

        def fake(agent, schema, system, user):
            calls.append(agent)
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and calls.count(agent) == 1:
                answer.national_law_requests = [NationalLawRequest(
                    country='IE', requirement='gdpr.special_category_condition', question='Does Irish law supply a research basis?',
                    gdpr_provisions=['GDPR Art. 9'])]
            if agent == 'local_law_IE':
                child_prompts.append(user)
            return answer

        result, events = self.run_fake(fake)
        questions = result['case_record']['specialists']['gdpr_specialist']['national_questions']
        self.assertEqual([q['question'] for q in questions],
                         ['Does Irish law supply a research basis?'])
        self.assertEqual(len(child_prompts), 1)
        self.assertFalse(any(e['kind'] == 'coverage_added' for e in events))
        self.assertEqual(calls.count('local_law_IE'), 1)

    def test_specialist_can_still_choose_art9_4_review(self):
        calls = []

        def fake(agent, schema, system, user):
            calls.append(agent)
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and calls.count(agent) == 1:
                answer.national_law_requests = [NationalLawRequest(
                    country='IE', requirement='gdpr.special_category_condition', question='Which additional conditions apply?',
                    gdpr_provisions=['GDPR Art. 9'])]
            if agent == 'local_law_IE':
                self.assertIn('[IE S.I. 314/2018 Reg. 3]', user)
            return answer

        result, events = self.run_fake(fake, search_results=[('IE S.I. 314/2018 Reg. 3', 0.1)])
        questions = result['case_record']['specialists']['gdpr_specialist']['national_questions']
        self.assertEqual([q['question'] for q in questions], ['Which additional conditions apply?'])
        self.assertTrue(result['case_record']['checks']['complete'])
        self.assertFalse(any(e['kind'] == 'coverage_added' for e in events))
