"""Offline ownership regressions, not assertions of legal correctness."""

import json
import re
import threading
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app import knowledge as kb, llm, passages
from app.case import fact_document
from app.graph import run
from app.review import coverage, quoted_fact
from app.schema import (Assessment, Classification, Finding, IntakeReview, Plan,
                        Reconciliation, SupervisorAction, SupervisorPlan)

ROOT = Path(__file__).resolve().parents[1]


def load(name='18_ie_hospital_to_us_teleradiology_two_layer.json'):
    return json.loads((ROOT / 'tests' / 'fixtures' / name).read_text())['request']


def legal_quote_id(pid):
    return passages.provision_passages(pid)[0]['quote_id']


def fact_ref(path, quote, document=None):
    """Scripted selection of a shown input passage, or an intentionally invalid ID."""
    offered = passages.input_passages(load() if document is None else document)
    selected = next((p for p in offered.values() if p['path'] == path and quote in p['text']), None)
    return ({'fact_id': selected['fact_id'], 'path': path, 'quote': selected['text']} if selected else
            {'fact_id': 'f_not_offered', 'path': path, 'quote': quote})


def fake_model(agent, schema, system, user):
    """A conservative scripted fixture: never labels the scenario legally compliant."""
    if schema is SupervisorAction:
        case = json.loads(user.split('CASE RECORD:\n', 1)[1])
        ids = [f['finding_id'] for b in case['specialists'].values() for f in b['findings']]
        return SupervisorAction(action='finish', accepted_finding_ids=ids, decision='needs_review',
                                reasons=['Scripted findings are unresolved; no legal ground truth is asserted.'],
                                reconciliation=Reconciliation(conflicts=[], summary='Offline fixture only.'))
    input_text = re.search(r'CASE INPUT[^\n]*:\n(.*)', user, re.S).group(1)
    inputs, _ = json.JSONDecoder().raw_decode(input_text)
    sender_index = next(i for i, o in enumerate(inputs['organisations']) if o['id'] == inputs['transfer']['sender'])
    sender_country = inputs['organisations'][sender_index]['country']
    sender_path = f'/organisations/{sender_index}/country'
    if schema is SupervisorPlan:
        return SupervisorPlan(intake=IntakeReview(claims=[], contradictions=[], missing_information=[]),
                              interpretation=[Classification(subject='Sender activity', classification='Activity scope',
                                                             value='unknown', reasoning='Fixture does not infer legal correctness.',
                                                             facts=[fact_ref(sender_path, sender_country, inputs)],
                                                             citations=['GDPR Art. 3'])],
                              gdpr_plan=Plan(applicability='Review GDPR on supplied facts.'),
                              hipaa_plan=Plan(applicability='Review HIPAA on supplied facts.'))
    ids = re.findall(r'^- \[([^]]+)\]', user.split('ASSIGNED QUESTIONS:\n', 1)[1].split('\n\n', 1)[0], re.M)
    return schema(regime_applies='unclear', applicability_reasoning='Offline fixture.',
                  findings=[Finding(question_ids=[q], issue=q, status='insufficient_information',
                                    reasoning='A decisive predicate has not been established in this scripted fixture.',
                                    route_coverage='Scripted fixture leaves route coverage unresolved; no legal conclusion is asserted.',
                                    citations=[], facts=[fact_ref(sender_path, sender_country, inputs)]) for q in ids])


class RuntimeTests(unittest.TestCase):
    def run_fake(self, fake=fake_model, request=None, *, search_results=()):
        # Block every paid/embedding path. Retrieval, when requested, is supplied by a local stub.
        with (patch.object(llm, 'FAKE_MODEL', fake),
              patch.object(llm, 'model', side_effect=AssertionError('Paid call forbidden')),
              patch.object(kb, 'vector_store', return_value=None), patch.object(kb, 'search', return_value=list(search_results))):
            return run(request or load())

    def test_two_supervisor_calls_and_unknowns_stay_unknown(self):
        result, events = self.run_fake()
        calls = [e for e in events if e['kind'] == 'llm_request']
        self.assertEqual(sum(e['agent'] == 'supervisor' for e in calls), 2)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(result['findings']), 16)
        self.assertTrue(all(f['status'] == 'insufficient_information' for f in result['findings']))
        self.assertTrue(all(r['status'] == 'undetermined' for r in result['requirements']))
        self.assertTrue(all(c['complete'] for c in result['coverage']))
        self.assertEqual(result['workflow'], 'supervisor-v15')
        self.assertEqual(result['decision'], 'needs_review')

    def test_original_input_scope_and_roles_do_not_change(self):
        given = load()
        before = deepcopy(given)
        result, _ = self.run_fake(request=given)
        case = result['case_record']
        self.assertEqual(given, before)
        self.assertEqual({k: v for k, v in case['input'].items() if k != 'reference_facts'}, before)
        self.assertNotIn('gdpr_role', case['input']['organisations'][0])
        self.assertEqual(case['input']['evidence'][0]['between'], before['evidence'][0]['between'])
        self.assertEqual(case['supervisor']['interpretation'][0]['value'], 'unknown')

    def test_reordered_organisations_and_attester_survive_every_prompt_and_report(self):
        given = load()
        given['organisations'].reverse()
        given['evidence'][0]['attested_by'] = 'Alice Example, privacy officer'
        seen = []
        def fake(agent, schema, system, user):
            if schema is SupervisorAction:
                inputs = json.loads(user.split('CASE RECORD:\n', 1)[1])['input']
            else:
                text = re.search(r'CASE INPUT[^\n]*:\n(.*)', user, re.S).group(1)
                inputs, _ = json.JSONDecoder().raw_decode(text)
            seen.append(inputs['evidence'][0]['attested_by'])
            self.assertEqual(inputs['transfer']['data']['identifiability'], given['transfer']['data']['identifiability'])
            self.assertEqual(inputs['transfer']['locations'], given['transfer']['locations'])
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                answer.findings[0].evidence_ids = [given['evidence'][0]['id']]
            return answer
        result, _ = self.run_fake(fake, given)
        self.assertEqual(seen, ['Alice Example, privacy officer'] * 4)
        self.assertTrue(result['case_record']['checks']['complete'])
        supported = result['requirements'][0]['supporting_evidence'][0]
        self.assertEqual(supported, given['evidence'][0])
        self.assertEqual(result['case_record']['input']['reference_facts']['sender_country'], 'IE')

    def test_all_prompt_phases_show_the_fact_checker_document(self):
        documents = []
        def fake(agent, schema, system, user):
            if schema is SupervisorAction:
                document = json.loads(user.split('CASE RECORD:\n', 1)[1])['input']
            else:
                text = re.search(r'CASE INPUT[^\n]*:\n(.*)', user, re.S).group(1)
                document, _ = json.JSONDecoder().raw_decode(text)
            documents.append(document)
            self.assertTrue(quoted_fact({'path': '/organisations/0/country', 'quote': 'IE'}, document))
            self.assertTrue(quoted_fact({'path': '/transfer/data/categories/0', 'quote': 'health'}, document))
            self.assertTrue(quoted_fact({'path': '/evidence/0/summary',
                                        'quote': document['evidence'][0]['summary'][:60]}, document))
            return fake_model(agent, schema, system, user)
        result, _ = self.run_fake(fake)
        self.assertEqual(len(documents), 4)
        self.assertTrue(all(d == fact_document(result['case_record']) for d in documents))
        self.assertNotIn('request', result['case_record']['input'])
        self.assertNotIn('submitted', result['case_record']['input'])

    def test_last_turn_finish_survives_rejected_optional_interpretation(self):
        turns = 0
        def fake(agent, schema, system, user):
            nonlocal turns
            answer = fake_model(agent, schema, system, user)
            if schema is SupervisorAction:
                turns += 1
                if turns == 1:
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            question_ids=['gdpr_specialist:local1'], instruction='Repair references.')
                if turns in (2, 3):
                    regime = 'gdpr' if turns == 2 else 'hipaa'
                    return SupervisorAction(action='delegate', target=f'{regime}_specialist',
                                            question_ids=[f'{regime}.applicability'], instruction='Review references.')
                answer.interpretation = [Classification(
                    subject='Data', classification='Data status', value='health', reasoning='Proposed update.',
                    facts=[fact_ref('/data/categories/0', 'health')], citations=['GDPR Art. 9'])]
            return answer
        result, events = self.run_fake(fake)
        case = result['case_record']
        self.assertEqual(turns, 4)
        self.assertIsNotNone(case['supervisor']['review'])
        self.assertEqual(case['supervisor']['review']['decision'], 'needs_review')
        self.assertIsNone(case['supervisor']['review']['interpretation'])
        self.assertEqual(case['supervisor']['interpretation'][0]['value'], 'unknown')
        self.assertTrue(any('f_not_offered' in i for i in case['checks']['issues']))
        self.assertFalse(case['checks'].get('runtime_issues'))
        self.assertTrue(all(f['status'] == 'insufficient_information' for f in result['findings']))
        self.assertTrue(any(e['kind'] == 'supervisor_action' and e.get('accepted')
                            and e.get('action') == 'finish' for e in events))
        rejected = [e['reason'] for e in events if e['kind'] == 'supervisor_action' and not e['accepted']]
        self.assertTrue(any('gdpr_specialist:local1' in reason and 'parent requirement' in reason for reason in rejected))

    def test_rejected_interpretation_blocks_proceed_until_corrected(self):
        for correct_later in (False, True):
            with self.subTest(correct_later=correct_later):
                turns = 0
                def fake(agent, schema, system, user):
                    nonlocal turns
                    answer = fake_model(agent, schema, system, user)
                    if agent in ('gdpr_specialist', 'hipaa_specialist'):
                        citation = 'GDPR Art. 3' if agent == 'gdpr_specialist' else '45 CFR 164.502'
                        pid = kb.resolve(citation, kb.provisions())[0]
                        for f in answer.findings:
                            f.status, f.citations, f.quote_id = 'not_applicable', [pid], legal_quote_id(pid)
                    if schema is SupervisorAction:
                        turns += 1
                        answer.decision = 'proceed'
                        path = '/organisations/0/country' if correct_later and turns > 1 else '/submitted/request/organisations/0/country'
                        answer.interpretation = [Classification(
                            subject='Sender', classification='Activity scope', value='fixture', reasoning='Offline fixture.',
                            facts=[fact_ref(path, 'IE')], citations=['GDPR Art. 3'])]
                    return answer
                result, events = self.run_fake(fake)
                case = result['case_record']
                self.assertEqual(len(result['findings']), 16)
                self.assertTrue(all(f['verified'] for f in result['findings']))
                self.assertTrue(any(e['kind'] == 'supervisor_action' and 'Unresolved checks' in e.get('reason', '')
                                    for e in events))
                if correct_later:
                    self.assertEqual(turns, 2)
                    self.assertEqual(case['supervisor']['review']['decision'], 'proceed')
                    self.assertNotIn('interpretation_update_issues', case['checks'])
                    self.assertIn({'action': 'interpretation_update', 'accepted': True},
                                  case['supervisor']['action_log'])
                    self.assertTrue(case['checks']['complete'])
                else:
                    self.assertIsNone(case['supervisor']['review'])
                    self.assertEqual(result['decision'], 'needs_review')

    def test_initial_specialists_execute_in_parallel(self):
        barrier = threading.Barrier(2, timeout=3)
        def fake(agent, schema, system, user):
            if agent in ('gdpr_specialist', 'hipaa_specialist'):
                barrier.wait()
            return fake_model(agent, schema, system, user)
        result, events = self.run_fake(fake)
        self.assertFalse(result['case_record']['checks']['issues'])
        requests = [e for e in events if e['kind'] == 'llm_request']
        self.assertEqual({e['agent'] for e in requests}, {'supervisor', 'gdpr_specialist', 'hipaa_specialist'})

    def test_unknown_quote_id_flags_finding_without_rewriting_status(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if agent == 'hipaa_specialist':
                answer.findings[0].status = 'satisfied_if_verified'
                answer.findings[0].citations = ['HIPAA 45 CFR 164.502']
                answer.findings[0].quote_id = 'q_not_offered'
            return answer
        result, _ = self.run_fake(fake)
        f = next(f for f in result['findings'] if f['question_ids'] == ['hipaa.applicability'])
        self.assertEqual(f['status'], 'satisfied_if_verified')
        self.assertFalse(f['verified'])
        self.assertEqual(result['decision'], 'needs_review')
        self.assertNotIn('original_status', f)

    def test_targeted_revision_keeps_unaffected_ids(self):
        turns, gdpr = [], []
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                gdpr.append([f.question_ids[0] for f in answer.findings])
            if schema is SupervisorAction:
                turns.append(answer)
                if len(turns) == 1:
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            instruction='Review Article 9 evidence scope.',
                                            question_ids=['gdpr.special_category_condition'])
            return answer
        result, _ = self.run_fake(fake)
        self.assertEqual(gdpr[1], ['gdpr.special_category_condition'])
        unchanged = next(f for f in result['findings'] if f['question_ids'] == ['gdpr.lawful_basis'])
        changed = next(f for f in result['findings'] if f['question_ids'] == ['gdpr.special_category_condition'])
        self.assertIn(':r1.a:', unchanged['finding_id'])
        self.assertIn(':r2.a:', changed['finding_id'])
        self.assertLess(len(changed['allowed']), len(unchanged['allowed']))
        self.assertTrue(result['case_record']['checks']['complete'])

    def test_omitted_revision_is_visible_and_keeps_previous_answer(self):
        turns = 0
        def fake(agent, schema, system, user):
            nonlocal turns
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and 'CURRENT FINDINGS TO REASSESS' in user:
                answer.findings = []
            if schema is SupervisorAction:
                turns += 1
                if turns == 1:
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            instruction='Review the evidence scope.', question_ids=['gdpr.lawful_basis'])
            return answer
        result, _ = self.run_fake(fake)
        self.assertEqual(len(result['findings']), 16)
        self.assertFalse(result['case_record']['checks']['complete'])
        self.assertTrue(any('Unanswered questions' in i for i in result['case_record']['checks']['issues']))

    def test_finish_cannot_accept_superseded_or_invented_findings(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if schema is SupervisorAction:
                answer.accepted_finding_ids.append('invented')
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(result['decision'], 'needs_review')
        self.assertIsNone(result['case_record']['supervisor']['review'])
        self.assertTrue(any(e['kind'] == 'supervisor_action' and not e['accepted'] for e in events))

    def test_assessment_schema_has_no_authored_graph_predicates(self):
        self.assertNotIn('condition_answers', Finding.model_fields)
        self.assertNotIn('ConditionAnswer', Assessment.model_json_schema().get('$defs', {}))

    def test_unknown_evidence_id_is_flagged(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                answer.findings[0].evidence_ids = ['nonexistent']
            return answer
        result, _ = self.run_fake(fake)
        self.assertTrue(any('Unknown evidence ID' in i for i in result['case_record']['checks']['issues']))


class DelegationAndRetrievalTests(unittest.TestCase):
    run_fake = RuntimeTests.run_fake
    def test_national_answer_requires_a_targeted_gdpr_reassessment(self):
        calls = []
        def fake(agent, schema, system, user):
            calls.append(agent)
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and calls.count(agent) == 1:
                from app.schema import NationalLawRequest
                answer.national_law_requests = [NationalLawRequest(
                    country='IE', requirement='gdpr.special_category_condition',
                    question='Does the supplied practitioner description establish the Irish healthcare condition?',
                    gdpr_provisions=['GDPR Art. 9'])]
            if agent == 'local_law_IE':
                self.assertIn(passages.render(passages.provision_passages('GDPR Art. 9')), user)
                # The child has reached a conclusion. It does not automatically change GDPR.
                pid = next(p for p, provision in kb.provisions().items()
                           if provision['regime'] == 'IE' and f'[{p}]' in user)
                answer.findings[0].status = 'satisfied_if_verified'
                answer.findings[0].citations = [pid]
                answer.findings[0].quote_id = legal_quote_id(pid)
            if agent == 'gdpr_specialist' and calls.count(agent) == 2:
                self.assertEqual([f.question_ids[0] for f in answer.findings], ['gdpr.special_category_condition'])
                self.assertIn('satisfied_if_verified', user.split('NATIONAL ANSWERS', 1)[1])
                # GDPR explicitly remains unresolved in this fixture despite a positive child.
                from app.schema import NationalDependency
                answer.findings[0].national_dependencies = [NationalDependency(country='IE', question_id='gdpr_specialist:local1')]
            if schema is SupervisorAction:
                case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                assignment = case['checks']['available_actions']['gdpr_specialist']
                self.assertNotIn('gdpr_specialist:local1', assignment['question_ids'])
                self.assertEqual(assignment['national_question_parents'],
                                 {'gdpr_specialist:local1': 'gdpr.special_category_condition'})
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(calls.count('gdpr_specialist'), 2)
        self.assertEqual(calls.count('local_law_IE'), 1)
        self.assertEqual(calls.count('supervisor'), 2)
        parent = next(f for f in result['findings'] if f['question_ids'] == ['gdpr.special_category_condition'])
        self.assertEqual(parent['status'], 'insufficient_information')
        self.assertTrue(parent['verified'])
        self.assertTrue(result['case_record']['checks']['complete'])
        self.assertIn(':r1.a:', next(f for f in result['findings'] if f['question_ids'] == ['gdpr.lawful_basis'])['finding_id'])

    def test_specialist_can_request_extra_law_then_revise_only_affected_question(self):
        calls = 0
        chosen = []
        def fake(agent, schema, system, user):
            nonlocal calls
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                calls += 1
                if calls == 1:
                    from app.schema import SourceRequest
                    pid = next(p for p, provision in kb.provisions().items()
                               if provision['regime'] == 'GDPR' and f'[{p}]' not in user)
                    chosen.append(pid)
                    answer.source_requests = [SourceRequest(question_ids=['gdpr.accountability'], query='', provision_ids=[pid])]
                else:
                    self.assertEqual([f.question_ids[0] for f in answer.findings], ['gdpr.accountability'])
                    self.assertIn(f'[{chosen[0]}]', user)
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(calls, 2)
        self.assertTrue(result['case_record']['checks']['complete'])
        self.assertTrue(any(e['kind'] == 'sources_added' and chosen[0] in e['ids'] for e in events))

    def test_favourable_finish_cannot_contradict_accepted_unknown_transfer_findings(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if schema is SupervisorAction:
                answer.decision = 'proceed'
            return answer
        result, events = self.run_fake(fake)
        self.assertEqual(result['decision'], 'needs_review')
        self.assertIsNone(result['case_record']['supervisor']['review'])
        self.assertTrue(any(e['kind'] == 'supervisor_action' and 'contradicts' in e.get('reason', '') for e in events))

    def test_foreign_or_duplicate_question_answers_are_visible_defects(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                answer.findings += [answer.findings[0].model_copy(deep=True)]
                answer.findings[-1].question_ids = ['hipaa.minimum_necessary']
            return answer
        result, _ = self.run_fake(fake)
        self.assertTrue(any('Unassigned questions' in issue for issue in result['case_record']['checks']['issues']))
        self.assertEqual(result['decision'], 'needs_review')

    def test_supervisor_can_revise_its_interpretation_without_changing_input(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if schema is SupervisorAction:
                answer.interpretation = [Classification(subject='Sender activity', classification='Activity scope',
                                                        value='existing', reasoning='A provisional interpretation only.',
                                                        facts=[fact_ref('/organisations/0/country', 'IE')],
                                                        citations=['GDPR Art. 3'])]
            return answer
        result, _ = self.run_fake(fake)
        self.assertEqual(result['case_record']['supervisor']['interpretation'][0]['value'], 'existing')
        self.assertNotIn('processing_activity', result['case_record']['input']['transfer'])

    def test_missing_child_corpus_stays_visible_to_parent(self):
        calls = 0
        def fake(agent, schema, system, user):
            nonlocal calls
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                calls += 1
                if calls == 1:
                    from app.schema import NationalLawRequest
                    answer.national_law_requests = [NationalLawRequest(country='FR', requirement='gdpr.lawful_basis',
                                                                      question='Which French law supplies this public task?',
                                                                      gdpr_provisions=['GDPR Art. 6'])]
                else:
                    self.assertIn('No local corpus', user)
            return answer
        result, _ = self.run_fake(fake)
        self.assertEqual(calls, 2)
        self.assertEqual(result['national_questions'][0]['country'], 'FR')
        self.assertEqual(next(f for f in result['findings'] if f['question_ids'] == ['gdpr.lawful_basis'])['status'], 'insufficient_information')


    def test_supervisor_exclusion_controls_initial_dispatch(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if schema is SupervisorPlan:
                from app.schema import RegimeExclusion
                from app.supervisor import initial_sources
                pid = next(p for p in initial_sources()
                           if kb.provisions()[p]['regime'] == 'HIPAA')
                answer.hipaa_plan = None
                answer.exclusions = [RegimeExclusion(regime='HIPAA', reasoning='Structural fixture exclusion, not a legal conclusion.',
                                                     facts=[fact_ref('/organisations/0/country', 'IE')], citations=[pid])]
            return answer
        result, events = self.run_fake(fake)
        self.assertFalse(result['routing']['hipaa'])
        self.assertEqual(len(result['findings']), 10)
        self.assertFalse(any(e['kind'] == 'llm_request' and e['agent'] == 'hipaa_specialist' for e in events))
        self.assertTrue(result['case_record']['checks']['complete'])

    def test_evidence_template_uses_the_current_schema_and_never_closes_by_kind(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                from app.schema import EvidenceRequest
                f = next(f for f in answer.findings if f.question_ids == ['gdpr.transfer_mechanism'])
                f.evidence_requests = [EvidenceRequest(evidence_type='certification_record',
                                                       description='Confirm the specific certification scope.', from_party='recipient')]
            return answer
        result, _ = self.run_fake(fake)
        record = next(r for r in result['requirements'] if r['key'] == 'gdpr.transfer_mechanism')
        self.assertEqual(record['evidence_status'], 'outstanding')
        self.assertFalse(record['supporting_evidence'])
        self.assertNotIn('attestation_template', result)
        template = result['evidence_template'][0]
        self.assertEqual(template['between'], [load()['transfer']['recipient']])
        from app.schema import AssessmentInput
        request = load()
        request['evidence'].append({**template, 'summary': 'Fixture answer with specific scope.'})
        AssessmentInput.model_validate(request)

    def test_reference_checks_do_not_change_conclusive_agent_statuses(self):
        def fake(agent, schema, system, user):
            answer = fake_model(agent, schema, system, user)
            if agent in ('gdpr_specialist', 'hipaa_specialist'):
                regime = 'GDPR' if agent == 'gdpr_specialist' else 'HIPAA'
                pid = next(p for p, provision in kb.provisions().items()
                           if provision['regime'] == regime and f'[{p}]' in user)
                for f in answer.findings:
                    f.status = 'not_applicable'
                    f.citations = [pid]
                    f.quote_id = legal_quote_id(pid)
            return answer
        result, _ = self.run_fake(fake)
        self.assertTrue(all(f['status'] == 'not_applicable' and f['verified'] for f in result['findings']))
        self.assertTrue(all(r['status'] == 'not_applicable' for r in result['requirements']))
        # Provenance-valid scripted conclusions are not a certification of legal correctness.


if __name__ == '__main__':
    unittest.main()
