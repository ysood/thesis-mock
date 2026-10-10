"""Route records and source handoff, with synthetic judgments and paid calls blocked."""

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from pydantic import ValidationError

from app import agents, knowledge as kb, llm, passages, requirements as rq, supervisor, traversal
from app.case import new_case
from app.review import check_finding, established_refusals, finish_issues
from app.schema import (Conflict, Finding, GdprAssessment, LegalRoute, NationalLawRequest,
                        Reconciliation, SupervisorAction)
from tests import test_v9


def route(pid='GDPR Art. 6', *, status='unresolved', quote_id=None,
          name='Recipient processing: synthetic alternative', reasoning='The decisive case fact is unanswered.'):
    return LegalRoute(name=name, status=status, reasoning=reasoning, citations=[pid],
                      quote_id=quote_id or test_v9.legal_quote_id(pid))


def finding(routes=(), *, status='insufficient_information'):
    return Finding(question_ids=['gdpr.lawful_basis'], issue='Synthetic route-review question',
                   status=status, reasoning='Scripted output, not a conclusion about legal correctness.',
                   route_coverage='The synthetic alternatives are recorded separately for recipient processing.',
                   routes=list(routes), citations=['GDPR Art. 6'], quote_id=test_v9.legal_quote_id('GDPR Art. 6'),
                   facts=[test_v9.fact_ref('/organisations/0/country', 'IE')])


class RouteIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.case = new_case(test_v9.load(), {})
        self.questions = [q for q in rq.plan_questions('GDPR') if q.question_id == 'gdpr.lawful_basis']

    def assess(self, value, *, sources=('GDPR Art. 6',), reads=None):
        answer = GdprAssessment(regime_applies='unclear', applicability_reasoning='Synthetic fixture.',
                                findings=[value])
        with (patch.object(llm, 'FAKE_MODEL', lambda *args: answer),
              patch.object(llm, 'model', side_effect=AssertionError('Paid call forbidden')),
              patch.object(llm, 'tool_model', side_effect=AssertionError('Paid call forbidden')),
              patch.object(kb, 'vector_store', return_value=None),
              patch.object(traversal, 'ENABLED', reads is not None),
              patch.object(traversal, 'toolset', return_value=(None, reads or {'read': [], 'passages': {}}))):
            return agents.assess(self.case, 'GDPR', 'gdpr_specialist', self.questions, list(sources))['findings'][0]

    def test_coverage_is_required_but_simple_duties_need_no_route_list(self):
        value = finding().model_dump()
        self.assertEqual(value['routes'], [])
        for missing in (True, False):
            candidate = deepcopy(value)
            if missing:
                candidate.pop('route_coverage')
            else:
                candidate['route_coverage'] = ''
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                Finding.model_validate(candidate)
        fields = LegalRoute.model_json_schema()['properties']
        self.assertIn('quote_id', fields)
        self.assertNotIn('quote', fields)

    def test_route_quote_is_copied_exactly_and_its_source_is_checked(self):
        value = self.assess(finding([route()], status='satisfied_if_verified'))
        selected = passages.provision_passages('GDPR Art. 6')[0]
        self.assertEqual(value['routes'][0]['quote'], selected['text'])
        checked = check_finding(value, self.case)
        self.assertTrue(checked['verified'])
        self.assertEqual(checked['routes'][0]['resolved_citations'], ['GDPR Art. 6'])
        self.assertIn('GDPR Art. 6', checked['resolved_citations'])
        self.assertEqual(checked['status'], 'satisfied_if_verified')

    def test_deferred_fallback_keeps_its_status_and_exact_source(self):
        value = self.assess(finding([
            route(status='supported', name='Sender processing: synthetic established route',
                  reasoning='The supplied predicates support this synthetic route.'),
            route(status='not_investigated', name='Sender processing: optional synthetic fallback',
                  reasoning='The established route suffices for this same activity; fallback feasibility was not assessed.')
        ], status='satisfied_if_verified'))
        checked = check_finding(value, self.case)
        self.assertTrue(checked['verified'])
        self.assertEqual([r['status'] for r in checked['routes']], ['supported', 'not_investigated'])
        self.assertEqual(checked['routes'][1]['quote'], passages.provision_passages('GDPR Art. 6')[0]['text'])
        self.assertEqual(checked['status'], 'satisfied_if_verified')
        self.assertEqual(LegalRoute.model_validate({k: v for k, v in value['routes'][1].items()
                                                   if k in LegalRoute.model_fields}).status, 'not_investigated')

    def test_deferred_fallback_still_needs_a_shown_source(self):
        value = self.assess(finding([
            route(status='supported'),
            route(status='not_investigated', quote_id='q_not_offered',
                  reasoning='An established synthetic route makes the optional fallback unnecessary.')
        ], status='satisfied_if_verified'))
        checked = check_finding(value, self.case)
        self.assertFalse(checked['verified'])
        self.assertTrue(any("Route '" in note and 'Quote ID was not shown' in note
                            for note in checked['verification_notes']))
        self.assertEqual(checked['routes'][1]['status'], 'not_investigated')
        self.assertEqual(checked['status'], 'satisfied_if_verified')

    def test_unknown_or_uncited_route_quote_is_a_defect_without_rewriting_parent(self):
        for selected in (route(quote_id='q_not_offered'),
                         route('GDPR Art. 5', quote_id=test_v9.legal_quote_id('GDPR Art. 6'))):
            with self.subTest(route=selected.model_dump()):
                value = self.assess(finding([selected], status='satisfied_if_verified'),
                                    sources=('GDPR Art. 6', 'GDPR Art. 5'))
                self.assertEqual(value['routes'][0]['quote'], '')
                self.assertTrue(value['routes'][0]['quote_selection_error'])
                checked = check_finding(value, self.case)
                self.assertFalse(checked['verified'])
                self.assertEqual(checked['status'], 'satisfied_if_verified')
                self.assertEqual(checked['routes'][0]['status'], 'unresolved')

    def test_read_parent_does_not_authorize_an_unshown_route_passage(self):
        pid = 'GDPR Art. 9'
        selected = passages.provision_passages(pid)
        self.assertGreater(len(selected), 1)
        # Simulate a tool page that exposes only its first complete labelled passage.
        reads = {'read': [pid], 'passages': {selected[0]['quote_id']: selected[0]}}
        value = self.assess(finding([route(pid, quote_id=selected[-1]['quote_id'])]), reads=reads)
        self.assertIn(pid, value['allowed'])
        self.assertEqual(value['routes'][0]['quote'], '')
        self.assertTrue(value['routes'][0]['quote_selection_error'])
        self.assertFalse(check_finding(value, self.case)['verified'])
        self.assertEqual(value['status'], 'insufficient_information')

    def test_saved_route_quote_cannot_be_tampered_with(self):
        value = self.assess(finding([route()]))
        value['routes'][0]['quote'] += ' '
        checked = check_finding(value, self.case)
        self.assertFalse(checked['verified'])
        self.assertEqual(checked['status'], 'insufficient_information')

    def test_targeted_revision_keeps_route_only_law(self):
        extra = 'GDPR Art. 80'
        self.assertNotIn(extra, rq.source_ids('gdpr.lawful_basis'))
        prior = finding([route(extra)]).model_dump()
        prior['citations'] = []
        selected = agents.source_view('GDPR', self.questions, ['GDPR Art. 6', extra], [prior], [])
        self.assertIn(extra, selected)

    def test_child_route_only_law_is_handed_back_to_gdpr(self):
        pid = next(pid for pid, law in kb.provisions().items() if law['regime'] == 'IE')
        value = finding([route(pid)]).model_dump()
        offered = passages.offered_passages(['GDPR Art. 6', pid])
        value = passages.copy_quote(value, offered)
        value.update(finding_id='local_law_IE:r1:f1', agent='local_law_IE', regime='IE',
                     question_ids=['gdpr_specialist:local1'], allowed=['GDPR Art. 6', pid])
        checked = check_finding(value, self.case)
        self.assertTrue(checked['verified'])
        self.assertIn(pid, checked['resolved_citations'])
        self.assertIn(pid, agents.child_cited({'IE': {'findings': [agents.finding_view(checked)]}}))


class RouteRuntimeTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_deferred_fallback_survives_review_without_resolving_mandatory_gaps(self):
        for mandatory_gap in (False, True):
            with self.subTest(mandatory_gap=mandatory_gap):
                reviewed = []

                def fake(agent, schema, system, user):
                    answer = test_v9.fake_model(agent, schema, system, user)
                    if agent == 'gdpr_specialist':
                        value = next(f for f in answer.findings if f.question_ids == ['gdpr.lawful_basis'])
                        value.status = 'insufficient_information' if mandatory_gap else 'satisfied_if_verified'
                        value.citations, value.quote_id = ['GDPR Art. 6'], test_v9.legal_quote_id('GDPR Art. 6')
                        value.routes = [
                            route(status='supported', name='Sender activity: synthetic established route',
                                  reasoning='The synthetic route-specific predicates are supported.'),
                            route(status='not_investigated', name='Sender activity: optional synthetic fallback',
                                  reasoning='The established route suffices; the fallback cannot settle a separate mandatory duty.')
                        ]
                        value.route_coverage = 'Fallback feasibility was not assessed; mandatory duties remain separate.'
                        if mandatory_gap:
                            value.missing_law = 'A separate mandatory safeguard remains unresolved.'
                            value.research_stopping_reason = 'The required safeguard source is unavailable in this synthetic fixture.'
                    if schema is SupervisorAction:
                        legal, record = user.split('\n\nCASE RECORD:\n', 1)
                        case = json.loads(record)
                        value = next(f for b in case['specialists'].values() for f in b['findings']
                                     if f['question_ids'] == ['gdpr.lawful_basis'])
                        self.assertIn('[GDPR Art. 6]', legal)
                        self.assertEqual([r['status'] for r in value['routes']], ['supported', 'not_investigated'])
                        self.assertEqual(value['routes'][1]['quote'], passages.provision_passages('GDPR Art. 6')[0]['text'])
                        self.assertEqual(bool(value.get('missing_law')), mandatory_gap)
                        reviewed.append(value['finding_id'])
                    return answer

                result, events = self.run_fake(fake)
                value = next(f for f in result['findings'] if f['question_ids'] == ['gdpr.lawful_basis'])
                self.assertTrue(value['verified'])
                self.assertEqual(value['status'], 'insufficient_information' if mandatory_gap else 'satisfied_if_verified')
                self.assertEqual(value['routes'][1]['status'], 'not_investigated')
                self.assertEqual(len(reviewed), 1)
                self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)
                self.assertEqual(result['decision'], 'needs_review')  # Other fixture findings remain unresolved.

    def test_supervisor_reads_route_only_law_in_the_existing_review(self):
        pid = 'GDPR Art. 80'
        self.assertNotIn(pid, supervisor.initial_sources())
        starting = kb.include_supporting_sources([p for regime in ('GDPR', 'HIPAA')
                                                  for q in rq.plan_questions(regime)
                                                  for p in rq.source_ids(q.question_id)])
        self.assertNotIn(pid, starting)
        reviewed = []
        original_gather, original_toolset = agents.gather_sources, traversal.toolset

        def gather(agent, regime, questions):
            sources = original_gather(agent, regime, questions)
            return sources + [pid] if agent == 'gdpr_specialist' else sources

        def toolset(agent, regime):
            if agent == 'gdpr_specialist':
                # An unpinned pool addition is opened before its labelled quote can be used.
                return None, {'read': [pid], 'passages': passages.offered_passages([pid])}
            return original_toolset(agent, regime)

        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                value = next(f for f in answer.findings if f.question_ids == ['gdpr.lawful_basis'])
                value.routes = [route(pid)]
                value.route_coverage = 'Recipient processing has one unresolved synthetic route in the read source.'
                self.assertEqual(value.citations, [])  # The law appears only inside its route.
            if schema is SupervisorAction:
                legal, record = user.split('\n\nCASE RECORD:\n', 1)
                self.assertIn(f'[{pid}]', legal)
                case = json.loads(record)
                value = next(f for b in case['specialists'].values() for f in b['findings']
                             if f['question_ids'] == ['gdpr.lawful_basis'])
                self.assertEqual(value['routes'][0]['status'], 'unresolved')
                self.assertIn(pid, value['resolved_citations'])
                reviewed.append(value['finding_id'])
            return answer

        with (patch.object(agents, 'gather_sources', side_effect=gather),
              patch.object(traversal, 'ENABLED', True),
              patch.object(traversal, 'toolset', side_effect=toolset)):
            result, events = self.run_fake(fake)
        self.assertEqual(len(reviewed), 1)
        self.assertTrue(result['case_record']['checks']['complete'])
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)
        self.assertEqual(result['decision'], 'needs_review')

    def test_supervisor_can_review_uncited_starting_law_and_request_missing_routes(self):
        reviews, specialist_calls = [], []

        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                value = next(f for f in answer.findings if f.question_ids == ['gdpr.lawful_basis'])
                value.citations, value.quote_id = ['GDPR Art. 5'], test_v9.legal_quote_id('GDPR Art. 5')
                specialist_calls.append(value.question_ids)
                if len(specialist_calls) == 1:
                    value.route_coverage = 'This synthetic answer claims a single duty and records no alternatives.'
                    value.routes = []
                else:
                    self.assertIn('Review the alternatives in the starting law.', user)
                    value.route_coverage = 'The previously omitted recipient alternative is now recorded and unresolved.'
                    value.routes = [route(name='Recipient processing: previously omitted alternative')]
            if schema is SupervisorAction:
                legal, record = user.split('\n\nCASE RECORD:\n', 1)
                self.assertIn('[GDPR Art. 6]', legal)
                case = json.loads(record)
                value = next(f for b in case['specialists'].values() for f in b['findings']
                             if f['question_ids'] == ['gdpr.lawful_basis'])
                reviews.append(value)
                if len(reviews) == 1:
                    self.assertFalse(value.get('routes'))
                    self.assertEqual(value['resolved_citations'], ['GDPR Art. 5'])
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            question_ids=['gdpr.lawful_basis'], finding_ids=[value['finding_id']],
                                            instruction='Review the alternatives in the starting law.')
                self.assertEqual(value['routes'][0]['status'], 'unresolved')
                self.assertIn('GDPR Art. 6', value['resolved_citations'])
            return answer

        result, _ = self.run_fake(fake)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(len(specialist_calls), 2)
        self.assertTrue(result['case_record']['checks']['complete'])
        self.assertEqual(result['decision'], 'needs_review')
        self.assertTrue(any(a['action'] == 'delegate' and a.get('accepted')
                            for a in result['case_record']['supervisor']['action_log']))

    def test_simple_duty_records_do_not_add_a_mandatory_model_phase(self):
        result, events = self.run_fake()
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 4)
        self.assertTrue(result['case_record']['checks']['complete'])
        self.assertTrue(all(f['route_coverage'] and not f.get('routes') for f in result['findings']))

    def test_national_failure_stays_scoped_while_an_alternative_is_unresolved(self):
        seen_parent = []

        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist':
                value = next(f for f in answer.findings if f.question_ids == ['gdpr.lawful_basis'])
                delegated = json.loads(user.split('DELEGATED NATIONAL QUESTIONS:\n', 1)[1].split('\n\n', 1)[0])
                value.route_coverage = 'Two synthetic recipient routes remain separate; common duties still require review.'
                value.routes = [route(name='Recipient processing: alternative A'),
                                route(name='Recipient processing: alternative B',
                                      status='ruled_out' if delegated else 'unresolved',
                                      reasoning='The national answer rules out only alternative B.' if delegated
                                      else 'The national-law dependency is unanswered.')]
                if not delegated:
                    answer.national_law_requests = [NationalLawRequest(
                        country='IE', requirement='gdpr.lawful_basis',
                        question='Synthetic national-law question concerning alternative B only.',
                        gdpr_provisions=['GDPR Art. 6'])]
            if agent == 'local_law_IE':
                value = answer.findings[0]
                value.status = 'not_satisfied'
                value.citations = ['GDPR Art. 6']
                value.quote_id = test_v9.legal_quote_id('GDPR Art. 6')
                value.route_coverage = 'The delegated question addresses only recipient alternative B.'
                value.reasoning = 'Synthetic adverse branch answer, without deciding the parent requirement.'
            if schema is SupervisorAction:
                case = json.loads(user.split('CASE RECORD:\n', 1)[1])
                values = [f for b in case['specialists'].values() for f in b['findings']]
                parent = next(f for f in values if f['question_ids'] == ['gdpr.lawful_basis'])
                child = next(f for f in values if f['agent'] == 'local_law_IE')
                self.assertEqual(child['status'], 'not_satisfied')
                self.assertEqual(parent['status'], 'insufficient_information')
                self.assertEqual([r['status'] for r in parent['routes']], ['unresolved', 'ruled_out'])
                self.assertFalse(established_refusals(values))
                seen_parent.append(parent)
            return answer

        result, _ = self.run_fake(fake)
        self.assertEqual(len(seen_parent), 1)
        self.assertEqual(result['decision'], 'needs_review')
        self.assertTrue(result['case_record']['checks']['complete'])


class RouteDecisionTests(unittest.TestCase):
    def setUp(self):
        self.case = new_case(test_v9.load(), {})

    def checked(self, identifier, question, status, *, agent='gdpr_specialist',
                regime='GDPR', citation='GDPR Art. 6'):
        value = finding(status=status).model_dump()
        value.update(finding_id=identifier, question_ids=[question], agent=agent, regime=regime,
                     citations=[citation], quote_id=test_v9.legal_quote_id(citation), allowed=[citation])
        value = passages.copy_quote(value, passages.offered_passages([citation]))
        checked = check_finding(value, self.case)
        self.assertTrue(checked['verified'])
        return checked

    def action(self, values, conflicts=()):
        return SupervisorAction(action='finish', decision='do_not_proceed',
                                accepted_finding_ids=[f['finding_id'] for f in values],
                                reasons=['Synthetic decision consistency test.'],
                                reconciliation=Reconciliation(conflicts=list(conflicts), summary='Synthetic fixture.'))

    def test_failed_child_and_unresolved_parent_cannot_establish_refusal(self):
        parent = self.checked('parent', 'gdpr.lawful_basis', 'insufficient_information')
        child = self.checked('child', 'gdpr_specialist:local1', 'not_satisfied',
                             agent='local_law_IE', regime='IE')
        values = [parent, child]
        self.assertFalse(established_refusals(values))
        defects = finish_issues(self.action(values), values, [], ['GDPR Art. 6'])
        self.assertTrue(any('failed alternative or national-law branch' in note for note in defects))

    def test_verified_unmet_parent_gate_can_establish_refusal(self):
        applies = self.checked('applicability', 'gdpr.applicability', 'satisfied_if_verified',
                               citation='GDPR Art. 3')
        parent = self.checked('parent', 'gdpr.lawful_basis', 'not_satisfied')
        values = [applies, parent]
        self.assertEqual([f['finding_id'] for f in established_refusals(values)], ['parent'])
        self.assertEqual(finish_issues(self.action(values), values, [], ['GDPR Art. 3', 'GDPR Art. 6']), [])

    def test_sourced_incompatibility_between_verified_main_transfer_findings_can_refuse(self):
        gdpr = self.checked('gdpr', 'gdpr.lawful_basis', 'satisfied_if_verified')
        hipaa = self.checked('hipaa', 'hipaa.disclosure_permission', 'satisfied_if_verified',
                             agent='hipaa_specialist', regime='HIPAA', citation='45 CFR 164.502(a)')
        values = [gdpr, hipaa]
        conflict = Conflict(kind='incompatibility', finding_ids=['gdpr', 'hipaa'],
                            shared_scope='The same synthetic actor, disclosure, data and time.',
                            description='Scripted incompatible obligations, not an assertion about these laws.',
                            regimes=['GDPR', 'HIPAA'], citations=['GDPR Art. 6', '45 CFR 164.502(a)'],
                            how_to_satisfy_both='The scripted obligations cannot both be fulfilled.')
        cited = ['GDPR Art. 6', '45 CFR 164.502(a)']
        self.assertEqual(finish_issues(self.action(values, [conflict]), values, [], cited), [])
        conflict.citations = ['not.a.shown.provision']
        defects = finish_issues(self.action(values, [conflict]), values, [], cited)
        self.assertTrue(any('sources absent from this review' in note for note in defects))

    def test_incompatibility_with_a_child_unverified_or_unresolved_main_finding_cannot_bypass_guard(self):
        parent = self.checked('parent', 'gdpr.lawful_basis', 'satisfied_if_verified')
        child = self.checked('child', 'gdpr_specialist:local1', 'not_satisfied',
                             agent='local_law_IE', regime='IE')
        conflict = Conflict(kind='incompatibility', finding_ids=['parent', 'child'],
                            shared_scope='The same synthetic scope.', description='Scripted claimed conflict.',
                            regimes=['GDPR', 'IE'], citations=['GDPR Art. 6'], how_to_satisfy_both='Unresolved.')
        for kind in ('child', 'unverified_main', 'unresolved_main'):
            other = deepcopy(child)
            if kind != 'child':
                other.update(agent='hipaa_specialist', regime='HIPAA')
            if kind == 'unverified_main':
                other['verified'] = False
            elif kind == 'unresolved_main':
                other['status'] = 'insufficient_information'
            values = [parent, other]
            with self.subTest(kind=kind):
                defects = finish_issues(self.action(values, [conflict]), values, [], ['GDPR Art. 6'])
                self.assertTrue(any('verified main transfer findings' in note for note in defects))


if __name__ == '__main__':
    unittest.main()
