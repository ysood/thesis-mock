"""Offline end-to-end run of the corpus-driven engine with a scripted model (no paid calls).

Tools are switched off so each agent's whole corpus is its reading (and citable), which lets the
script cite real provisions. The script checks mechanics, not legal quality.
"""

import json
import re
import unittest
from pathlib import Path

from engine import corpus, llm, pipeline, tools
from engine.schema import (Answer, Case, Conflict, CorpusApplicability, DelegateAnswer, Delegation, Engagement,
                           Blocker, Correction, FactRef, PeerQuestion, PlannedRoute, Requirement, Route, Routing,
                           SingleAssessment, SingleRequirement, SpecialistAnswer, SpecialistPatch, SupervisorConclusion,
                           SupervisorPlan, SupervisorSynthesis)

CASE = json.loads((Path(__file__).resolve().parent.parent / 'cases' / '01_a1_gp_to_region_b_host' / 'case.json').read_text())


def fact(user):
    return [FactRef(fact_id=re.search(r'\[(f_[0-9a-f]{12})\]', user).group(1))]


def scripted(calls):
    reviews = []

    def model(agent, schema, system, user):
        calls.append((agent, schema.__name__))
        if schema is SupervisorPlan:
            return SupervisorPlan(understanding='GP practice to Region B host.', engagements=[
                Engagement(corpus='region_a', engaged=True, reason='Sender in Subregion A1.', facts=fact(user)),
                Engagement(corpus='region_b', engaged=True, reason='Host in Region B.', facts=fact(user))])
        if schema is SupervisorSynthesis:
            reviews.append(user)
            return SupervisorSynthesis(outcome='undetermined', reasoning='Waiting on Region B access law.',
                                       summary='Route the access question.', routings=[
                    Routing(question_ref='region_a:q1', to_corpus='region_b', question='Can Region B authorities compel access?')])
        if schema is SupervisorConclusion:
            reviews.append(user)
            return SupervisorConclusion(outcome='not_satisfiable_together', reasoning='The route is ruled out.',
                                        summary='Done.', conflicts=[
                Conflict(description='Deletion vs retention.', kind='incompatible_law',
                         requirement_refs=['region_a:transfer_route', 'region_b:host_retention'],
                         resolvable=True, resolution='Return instead of delete.', quote_ids=['B-HRA 9#L1'])])
        if schema is DelegateAnswer and agent == 'subregion_a1_specialist':
            return DelegateAnswer(answers=[Answer(question_id='region_a>subregion_a1:d1', answer='A1-HIA 4 supplies the condition.',
                                                  citations=['A1-HIA 4'], quote_id='A1-HIA 4#L1')],
                                  requirements=[Requirement(
                                      id='national_transfer_conditions', title='Subregion A1 outward transfer conditions', kind='gate',
                                      status='unmet', reasoning='Keys are held in Region B.', facts=fact(user),
                                      citations=['A1-HIA 6'], quote_id='A1-HIA 6#L3')])
        if schema is DelegateAnswer:
            return DelegateAnswer(answers=[Answer(question_id='region_a:q1', answer='Yes, secretly, without a court.',
                                                  citations=['B-RAA 3'], quote_id='B-RAA 3#L1')])
        if agent == 'region_b_specialist':
            return SpecialistAnswer(applies=True, applicability_reasoning='Northgate is a data host.', coverage_note='Read all.',
                                    requirements=[Requirement(id='host_retention', title='Retention by data hosts', kind='duty',
                                                              status='unmet', reasoning='Agreement deletes in 30 days.',
                                                              citations=['B-HRA 9'], quote_id='B-HRA 9#L1',
                                                              required_actions=['Return records and keep no copy.'])])
        answered = '"from": "region_b"' in user
        if schema is SpecialistPatch:
            route = Route(name='Approved clauses (Art 18)', status='ruled_out' if answered else 'unresolved',
                          reasoning='Depends on Region B access law.', citations=['A-REG 18'], quote_id='A-REG 18#L2')
            return SpecialistPatch(impact='Answers affect the transfer route only.', changed_requirements=[Requirement(
                id='transfer_route', title='Outward transfer route', kind='gate',
                status='unmet' if answered else 'undetermined', reasoning='See routes.', facts=fact(user),
                citations=['A-REG 18'], quote_id='A-REG 18#L1', routes=[route],
                open_dependency='' if answered else 'Region B access law',
                required_actions=['Hold keys in Region A.'] if answered else [])],
                peer_questions=[] if answered else [PeerQuestion(jurisdiction='B', requirement_id='transfer_route',
                                                                 question='Can Region B authorities compel access?',
                                                                 why='A-REG 18(2)')])
        route = Route(name='Approved clauses (Art 18)', status='ruled_out' if answered else 'unresolved',
                      reasoning='Depends on Region B access law.', citations=['A-REG 18'], quote_id='A-REG 18#L2')
        return SpecialistAnswer(
            applies=True, applicability_reasoning='Custodian established in Subregion A1.', coverage_note='Read the TOC.',
            requirements=[Requirement(id='transfer_route', title='Outward transfer route', kind='gate',
                                      status='unmet' if answered else 'undetermined', reasoning='See routes.',
                                      facts=fact(user), citations=['A-REG 18'], quote_id='A-REG 18#L1', routes=[route],
                                      open_dependency='' if answered else 'Region B access law',
                                      required_actions=['Hold keys in Region A.'] if answered else [])],
            delegations=[] if '"from": "subregion_a1"' in user else [Delegation(
                corpus='subregion_a1', requirement_id='sensitive_condition', question='Which national condition applies?',
                referring_provisions=['A-REG 8'])],
            peer_questions=[PeerQuestion(jurisdiction='B', requirement_id='transfer_route',
                                         question='Can Region B authorities compel access?', why='A-REG 18(2)')])
    return model


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        llm.FAKE_MODEL, tools.ENABLED = scripted(self.calls), False

    def tearDown(self):
        llm.FAKE_MODEL, tools.ENABLED = None, True

    def test_delegation_routing_and_refusal(self):
        result, events = pipeline.run(CASE)
        refs = {f['ref']: f for f in result['findings']}
        self.assertEqual(set(refs), {'region_a:transfer_route', 'subregion_a1:national_transfer_conditions', 'region_b:host_retention'})
        self.assertTrue(all(f['verified'] for f in refs.values()), [f['issues'] for f in refs.values()])
        self.assertEqual(refs['region_a:transfer_route']['status'], 'unmet')  # reassessed after Region B answered
        self.assertEqual(result['questions'][0]['status'], 'answered')
        self.assertEqual(result['questions'][0]['routed_to'], 'region_b')
        self.assertEqual(result['decision'], 'do_not_proceed')
        self.assertIn('subregion_a1:national_transfer_conditions', ' '.join(result['reasons']))
        self.assertEqual(refs['region_a:transfer_route']['quote'][:20], '1. In the absence of')
        self.assertTrue(result['brief']['conflicts'][0]['resolvable'])
        # plan, 2 specialists, subregion_a1 delegate, region_a reassess, synthesis, region_b answer, region_a reassess,
        # conclusion
        self.assertEqual(len(self.calls), 9, self.calls)
        self.assertEqual([s for a, s in self.calls if a == 'supervisor'][1:], ['SupervisorSynthesis', 'SupervisorConclusion'])
        self.assertEqual(result['conclusion_issues'], ['the conclusion that the requirements cannot be satisfied '
                                                       'together cites no passage'])
        self.assertEqual(result['brief']['conclusion']['outcome'], 'not_satisfiable_together')


class RevisionAndQuestionTests(unittest.TestCase):
    def setUp(self):
        self.seen = []

        def model(agent, schema, system, user):
            self.seen.append((agent, schema.__name__, user))
            if schema is DelegateAnswer:
                return DelegateAnswer(answers=[], requirements=[Requirement(
                    id='impact_assessment_list', title='National impact assessment list', kind='gate', status='unmet',
                    reasoning='Hosting abroad needs one.', citations=['A1-HIA 8'], quote_id='A1-HIA 8#L1')])
            if schema is SpecialistPatch:
                return SpecialistPatch(impact='No change.')
            return SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c')

        llm.FAKE_MODEL, tools.ENABLED = model, False

    def tearDown(self):
        llm.FAKE_MODEL, tools.ENABLED = None, True

    def test_supervisor_revision_reaches_a_lower_level_corpus(self):
        state = pipeline.Run(CASE)
        state.answers['region_a'] = SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c')
        state.extra['subregion_a1:old'] = {'id': 'old', 'title': 'Old', 'kind': 'gate', 'status': 'met', 'reasoning': 'r',
                                      'corpus': 'subregion_a1', 'ref': 'subregion_a1:old'}
        review = SupervisorSynthesis(outcome='undetermined', reasoning='r', summary='s', corrections=[
            Correction(corpus='subregion_a1', requirement_ids=['old'], kind='missed_provision',
                       instruction='Assess A1-HIA 8.')])
        self.assertTrue(state.route(review, {}))
        self.assertEqual(list(state.extra), ['subregion_a1:impact_assessment_list'])  # replaced, not appended
        self.assertEqual([(a, s) for a, s, _ in self.seen],
                         [('subregion_a1_specialist', 'DelegateAnswer'), ('region_a_specialist', 'SpecialistPatch')])
        self.assertIn('YOUR PRIOR REPORT', self.seen[0][2])
        self.assertIn('Assess A1-HIA 8.', self.seen[0][2])

    def test_rephrased_peer_question_is_not_asked_twice(self):
        state = pipeline.Run(CASE)
        ask = lambda text: SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c', peer_questions=[
            PeerQuestion(jurisdiction='B', requirement_id='transfer_route', question=text, why='w')])
        state.answers['region_a'] = ask('Can Region B compel access?')
        state.collect_questions('region_a')
        state.answers['region_a'] = ask('Under Region B law, may authorities compel access?')
        state.collect_questions('region_a')
        self.assertEqual(list(state.questions), ['region_a:q1'])

    def test_lower_level_report_is_complete_and_replaces_the_earlier_one(self):
        state = pipeline.Run(CASE)
        state.extra['subregion_a1:old'] = {'id': 'old', 'title': 'Old', 'kind': 'gate', 'status': 'met', 'reasoning': 'r',
                                           'corpus': 'subregion_a1', 'ref': 'subregion_a1:old'}
        state.ask_corpus('subregion_a1', ['region_a'], [{'question_id': 'd1', 'asker': 'region_a', 'requirement_id': 'x',
                                                        'question': 'Is there a national list?'}], 'delegation')
        self.assertEqual(list(state.extra), ['subregion_a1:impact_assessment_list'])
        self.assertIn('YOUR PRIOR REPORT', self.seen[-1][2])  # a routed question, not only a revision, shows it
        self.assertIn('"Old"', self.seen[-1][2])
        from engine import agents
        self.assertIn('whether or not a question asked about it', agents.delegate_system('subregion_a1', 'Region A'))
        self.assertIn('ALREADY REPORTED', agents.delegate_system('region_b', 'Region A'))

    def test_answers_carry_the_law_they_rely_on_and_flag_unsupported_citations(self):
        def model(agent, schema, system, user):
            return DelegateAnswer(answers=[Answer(question_id='region_a:q1', answer='They cannot compel decryption.',
                                                  citations=['B-RAA 5', 'A-REG 18', 'B-RAA 99'], quote_id='B-RAA 5#L1')])
        llm.FAKE_MODEL = model
        state = pipeline.Run(CASE)
        state.ask_corpus('region_b', ['region_a'], [{'question_id': 'region_a:q1', 'asker': 'region_a',
                                                     'requirement_id': 'x', 'question': 'Can B compel decryption?'}], 'routing')
        received = state.received['region_a'][0]
        self.assertEqual(received['law'][0], {'quote': corpus.passages('B-RAA 5')['B-RAA 5#L1']})
        self.assertEqual(received['law'][1]['provision'], 'B-RAA 5')
        self.assertIn(corpus.passages('B-RAA 5')['B-RAA 5#L1'], received['law'][1]['text'])
        self.assertEqual(received['issues'], ['cites A-REG 18, which is not a provision of region_b',
                                              'cites B-RAA 99, which is not a provision of region_b'])
        self.assertNotIn('B-RAA 5', state.records['region_a']['read'])  # carried, not citable by the asker

    def test_a_top_level_answer_sees_its_current_findings_not_just_titles(self):
        state = pipeline.Run(CASE)
        route = Route(name='Approved clauses', status='ruled_out', reasoning='B can compel production.',
                      citations=['A-REG 18'], quote_id='A-REG 18#L1')
        state.answers['region_a'] = SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c',
                                                     requirements=[Requirement(id='outward_transfer', title='Transfer',
                                                                               kind='gate', status='unmet', reasoning='r',
                                                                               routes=[route])])
        state.ask_corpus('region_a', ['region_b'], [{'question_id': 'region_b:q1', 'asker': 'region_b',
                                                     'requirement_id': 'x', 'question': 'Does Article 18 allow it?'}], 'routing')
        user = self.seen[-1][2]
        self.assertIn('"status": "ruled_out"', user.split('ALREADY REPORTED')[1])
        from engine import agents
        self.assertIn('must agree with that assessment', agents.delegate_system('region_a', 'Region B'))

    def test_supervisor_owns_the_combination_not_the_findings(self):
        from engine import agents
        self.assertIn('You own the combined conclusion', agents.SYNTHESIS_RULES)
        self.assertIn('never tell a specialist what status to give', agents.FOLLOW_UPS)
        self.assertIn('Never ask to fold requirements of different corpora together', agents.FOLLOW_UPS)
        self.assertIn('keep your finding if your law supports it', agents.NOT_A_CONCLUSION)

    def test_corrections_must_be_specific_and_carry_their_passages(self):
        state = pipeline.Run(CASE)
        state.answers['region_a'] = SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c',
                                                     requirements=[Requirement(id='transfer_route', title='t', kind='gate',
                                                                               status='unmet', reasoning='r')])
        refs, shown = {'region_a:transfer_route'}, {'A-REG 18#L2': 'Approved clauses may be used.'}
        fix = lambda **k: state.correction(Correction(corpus='region_a', instruction='Check the clauses route.',
                                                      **k), refs, shown)
        text = fix(requirement_ids=['region_a:transfer_route'], kind='contradiction', quote_ids=['A-REG 18#L2'])
        self.assertIn('contradiction in transfer_route', text)
        self.assertIn('[A-REG 18#L2] Approved clauses may be used.', text)
        self.assertIsNone(fix(requirement_ids=['transfer_route'], kind='contradiction'))           # no passage
        self.assertIsNone(fix(requirement_ids=['transfer_route'], kind='stale_answer', quote_ids=['A-REG 9#L1']))
        self.assertIsNone(fix(requirement_ids=['other'], kind='stale_answer'))                     # unknown requirement
        self.assertEqual(len([e for e in state.log if 'rejected_correction' in e]), 3)

    def test_conclusion_checks_and_combined_decision(self):
        gate = lambda ref, status='met': {'ref': ref, 'title': ref, 'kind': 'gate', 'status': status, 'verified': True,
                                          'issues': [], 'missing_evidence': [], 'required_actions': [],
                                          'confirmations': [], 'routes': [{'name': 'Clauses'}]}
        findings = [gate('region_a:route'), gate('region_b:host')]
        shown = {'A-REG 18#L2': 'text'}
        ok = SupervisorConclusion(outcome='satisfiable_with_changes', reasoning='r', summary='s', quote_ids=['A-REG 18#L2'],
                                  route_plan=[PlannedRoute(requirement_ref='region_a:route', route='Clauses'),
                                              PlannedRoute(requirement_ref='region_b:host', route='met')])
        self.assertEqual(pipeline.check_conclusion(ok, findings, shown), [])
        self.assertEqual(pipeline.decide(findings, {}, ok)[0], 'proceed_subject_to_conditions')
        bad = ok.model_copy(update={'quote_ids': ['B-RAA 5#L1'], 'route_plan': ok.route_plan[:1]})
        self.assertEqual(pipeline.check_conclusion(bad, findings, shown),
                         ['conclusion cites passage B-RAA 5#L1, which it was not shown',
                          'route plan leaves out gate region_b:host'])
        refuse = ok.model_copy(update={'outcome': 'not_satisfiable_together', 'route_plan': []})
        self.assertEqual(pipeline.decide(findings, {}, refuse, [])[0], 'do_not_proceed')
        self.assertEqual(pipeline.decide(findings, {}, refuse, ['defect'])[0], 'needs_review')  # unverified: no refusal
        open_ = ok.model_copy(update={'outcome': 'undetermined'})
        self.assertEqual(pipeline.decide(findings, {}, open_)[0], 'proceed')  # undetermined with no blocker: a note
        self.assertIn('not blocking', pipeline.supervisor_items(open_, findings)[1][0])
        real = Blocker(requirement_ref='region_a:route', gap='Whether the clauses are signed.', why_not_a_confirmation='')
        self.assertEqual(pipeline.decide(findings, {}, open_.model_copy(update={'blockers': [real]}))[0], 'needs_review')

    def test_blockers_must_name_a_gate_and_beat_its_confirmations(self):
        f = lambda ref, kind='gate', conf=(): {'ref': ref, 'title': ref, 'kind': kind, 'status': 'met', 'verified': True,
                                               'issues': [], 'missing_evidence': [], 'required_actions': [],
                                               'confirmations': list(conf), 'routes': []}
        findings = [f('region_a:minimisation', 'duty'), f('region_a:route', conf=['Confirm accuracy.'])]
        final = SupervisorConclusion(outcome='undetermined', reasoning='r', summary='s', blockers=[
            Blocker(requirement_ref='region_a:minimisation', gap='Accuracy not certified.', why_not_a_confirmation=''),
            Blocker(requirement_ref='region_a:route', gap='Accuracy not certified.', why_not_a_confirmation='')])
        holds, notes = pipeline.supervisor_items(final, findings)
        self.assertEqual(holds, [])
        self.assertEqual(len(notes), 3)  # two demoted blockers + the unsupported undetermined outcome
        self.assertEqual(pipeline.decide(findings, {}, final)[0], 'proceed_subject_to_conditions')

    def test_open_question_on_a_met_requirement_does_not_block(self):
        findings = [{'ref': 'region_a:route', 'kind': 'gate', 'status': 'met', 'verified': True}]
        q = {'from': 'region_a', 'requirement_id': 'route'}
        self.assertFalse(pipeline.blocking_question(q, findings))
        self.assertTrue(pipeline.blocking_question({**q, 'requirement_id': 'other'}, findings))
        self.assertTrue(pipeline.blocking_question(q, [{**findings[0], 'status': 'undetermined'}]))

    def test_supervisor_gets_the_specialists_evidence_policy(self):
        from engine import agents
        self.assertIn(agents.EVIDENCE, agents.RULES)
        self.assertIn(agents.EVIDENCE, agents.SYNTHESIS_RULES.format(evidence=agents.EVIDENCE, follow_ups=''))

    def test_tool_budget_lets_any_agent_read_its_whole_scope(self):
        self.assertEqual(tools.budget(['region_a']), max(tools.MAX_TOOL_CALLS, 34))
        self.assertEqual(tools.budget(['subregion_a1']), max(tools.MAX_TOOL_CALLS, 11))
        self.assertEqual(tools.budget(['region_a', 'region_b', 'subregion_a1']), max(3 * tools.MAX_TOOL_CALLS, 64))

    def test_coverage_warnings_list_unread_law_linked_from_relied_on_law(self):
        state = pipeline.Run(CASE)
        state.records['region_a']['read'] = ['A-REG 16', 'A-REG 18']
        state.answers['region_a'] = SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c',
                                                     requirements=[Requirement(id='t', title='t', kind='gate', status='unmet',
                                                                               reasoning='r', citations=['A-REG 16'])])
        self.assertEqual([w['unread'] for w in state.coverage('region_a')], ['A-REG 17', 'A-REG 19'])
        self.assertIn('region_a', state.view()['coverage_warnings'])
        state.assess('region_a', prior=state.answers['region_a'])
        self.assertIn('COVERAGE WARNINGS', self.seen[-1][2])
        self.assertIn('A-REG 17', self.seen[-1][2])

    def test_renamed_requirement_does_not_reopen_a_question_but_a_new_one_is_asked(self):
        state = pipeline.Run(CASE)
        ask = lambda rid, text: SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c', peer_questions=[
            PeerQuestion(jurisdiction='B', requirement_id=rid, question=text, why='w')])
        state.answers['region_a'] = ask('clauses_assessment', 'For Article 18(2), what Region B law lets authorities '
                                                               'require disclosure from Northgate?')
        state.collect_questions('region_a')
        state.answers['region_a'] = ask('legal_environment', 'For Article 18(2), what Region B law lets public '
                                                              'authorities require disclosure from Northgate Cloud?')
        state.collect_questions('region_a')
        state.answers['region_a'] = ask('retention', 'Must a Region B data host keep health records for a fixed period?')
        state.collect_questions('region_a')
        self.assertEqual(list(state.questions), ['region_a:q1', 'region_a:q2'])
        self.assertIn('retention', state.questions['region_a:q2']['requirement_id'])

    def test_already_asked_questions_are_shown_to_the_asker(self):
        state = pipeline.Run(CASE)
        state.questions['region_a:q1'] = {'ref': 'region_a:q1', 'from': 'region_a', 'jurisdiction': 'B',
                                          'requirement_id': 'x', 'question': 'Can B compel access?', 'why': 'w',
                                          'status': 'answered', 'answer': 'Yes.'}
        state.assess('region_a')
        self.assertIn('QUESTIONS YOU HAVE ALREADY ASKED', self.seen[-1][2])
        self.assertIn('Can B compel access?', self.seen[-1][2])

    def test_patch_replaces_adds_and_withdraws_by_id_and_keeps_the_rest(self):
        req = lambda rid, status: Requirement(id=rid, title=rid, kind='gate', status=status, reasoning='r')
        prior = SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='old',
                                 requirements=[req('a', 'met'), req('b', 'undetermined'), req('c', 'met')])
        patch = SpecialistPatch(impact='b resolved; c withdrawn; d new.', changed_requirements=[req('b', 'unmet'), req('d', 'met')],
                                removed_requirement_ids=['c'])
        merged = pipeline.merge(prior, patch)
        self.assertEqual([(r.id, r.status) for r in merged.requirements], [('a', 'met'), ('b', 'unmet'), ('d', 'met')])
        self.assertEqual(merged.coverage_note, 'old')

    def test_available_is_a_route_forward_status(self):
        route = Route(name='Return records and keep no copy', status='available', reasoning='B-HRA 9(2).',
                      citations=['B-HRA 9'], quote_id='B-HRA 9#L2')
        self.assertEqual(route.status, 'available')

    def test_delegates_are_pointed_to_linked_provisions_from_the_graph(self):
        from engine import agents
        linked = agents.linked_provisions('subregion_a1', [{'question': 'Is there a list under A-REG 12#L5?',
                                                       'referring_provisions': []}])
        self.assertIn('A1-HIA 8 (Section 8 - Impact assessment list) cites A-REG 12', linked)


class SingleAgentTests(unittest.TestCase):
    def setUp(self):
        self.seen = []

        def model(agent, schema, system, user):
            self.seen.append((agent, schema.__name__, system))
            return SingleAssessment(
                understanding='GP practice to Region B host.', coverage_note='Read everything.',
                applicability=[CorpusApplicability(corpus=c, applies=True, reasoning='r')
                               for c in ('region_a', 'region_b', 'subregion_a1')],
                requirements=[SingleRequirement(corpus='subregion_a1', id='keys', title='Keys held in Region A',
                                                kind='gate', status='unmet', reasoning='Keys are held in Region B.',
                                                facts=fact(user), citations=['A1-HIA 6'], quote_id='A1-HIA 6#L3'),
                              SingleRequirement(corpus='region_b', id='retention', title='Retention', kind='duty',
                                                status='unmet', reasoning='r', citations=['B-HRA 9'],
                                                quote_id='B-HRA 9#L1')])

        llm.FAKE_MODEL, tools.ENABLED, pipeline.MODE = model, False, 'single'

    def tearDown(self):
        llm.FAKE_MODEL, tools.ENABLED, pipeline.MODE = None, True, 'multi'

    def test_one_call_over_every_corpus_with_the_same_checks_and_decision(self):
        result, _ = pipeline.run(CASE)
        self.assertEqual([(a, s) for a, s, _ in self.seen], [('single_agent', 'SingleAssessment')])
        self.assertNotIn('Report only requirements created by your own instruments', self.seen[0][2])
        refs = {f['ref']: f for f in result['findings']}
        self.assertEqual(set(refs), {'subregion_a1:keys', 'region_b:retention'})
        self.assertTrue(all(f['verified'] for f in refs.values()), [f['issues'] for f in refs.values()])
        self.assertEqual(result['decision'], 'do_not_proceed')
        self.assertEqual(result['plan']['engagements'][1], {'corpus': 'region_b', 'engaged': True, 'reason': 'r',
                                                            'focus': ''})

    def test_unknown_corpus_is_rejected(self):
        with self.assertRaises(ValueError):
            SingleRequirement(corpus='region_c', id='x', title='x', kind='gate', status='met', reasoning='r')


class VerificationTests(unittest.TestCase):
    def test_unread_law_and_unshown_quotes_are_defects(self):
        finding = Requirement(id='x', title='x', kind='gate', status='met', reasoning='r',
                              citations=['A-REG 18'], quote_id='A-REG 18#L1').model_dump()
        checked = pipeline.verify({**finding, 'corpus': 'region_a', 'ref': 'region_a:x'}, tools.new_record(), set())
        self.assertFalse(checked['verified'])
        self.assertIn('did not read', checked['issues'][0])

    def test_case_rejects_unknown_jurisdictions(self):
        bad = json.loads(json.dumps(CASE))
        bad['organisations'][0]['jurisdiction'] = 'IE'
        with self.assertRaises(ValueError):
            Case.model_validate(bad)


if __name__ == '__main__':
    unittest.main()
