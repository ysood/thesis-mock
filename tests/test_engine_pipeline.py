"""Offline end-to-end run of the corpus-driven engine with a scripted model (no paid calls).

Tools are switched off so each agent's whole corpus is its reading (and citable), which lets the
script cite real provisions. The script checks mechanics, not legal quality.
"""

import json
import re
import unittest
from pathlib import Path

from engine import llm, pipeline, tools
from engine.schema import (Answer, Case, Conflict, DelegateAnswer, Delegation, Engagement, FactRef, PeerQuestion,
                           Requirement, Revision, Route, Routing, SpecialistAnswer, SupervisorPlan, SupervisorReview)

CASE = json.loads((Path(__file__).resolve().parent.parent / 'cases' / '01_valdora_gp_to_corvel_host' / 'case.json').read_text())


def fact(user):
    return [FactRef(fact_id=re.search(r'\[(f_[0-9a-f]{12})\]', user).group(1))]


def scripted(calls):
    reviews = []

    def model(agent, schema, system, user):
        calls.append((agent, schema.__name__))
        if schema is SupervisorPlan:
            return SupervisorPlan(understanding='GP practice to Corvel host.', engagements=[
                Engagement(corpus='aster', engaged=True, reason='Sender in Valdora.', facts=fact(user)),
                Engagement(corpus='corvel', engaged=True, reason='Host in Corvel.', facts=fact(user))])
        if schema is SupervisorReview:
            reviews.append(user)
            if len(reviews) == 1:
                return SupervisorReview(action='route_or_revise', summary='Route the access question.', routings=[
                    Routing(question_ref='aster:q1', to_corpus='corvel', question='Can Corvel authorities compel access?')])
            return SupervisorReview(action='finish', summary='Done.', conflicts=[
                Conflict(description='Deletion vs retention.', requirement_refs=['aster:agent_contract', 'corvel:host_retention'],
                         resolvable=True, resolution='Return instead of delete.')])
        if schema is DelegateAnswer and agent == 'valdora_specialist':
            return DelegateAnswer(answers=[Answer(question_id='aster>valdora:d1', answer='VHIA 4 supplies the condition.',
                                                  citations=['VHIA 4'], quote_id='VHIA 4#L1')],
                                  additional_requirements=[Requirement(
                                      id='national_transfer_conditions', title='Valdora outward transfer conditions', kind='gate',
                                      status='unmet', reasoning='Keys are held in Corvel.', facts=fact(user),
                                      citations=['VHIA 6'], quote_id='VHIA 6#L3')])
        if schema is DelegateAnswer:
            return DelegateAnswer(answers=[Answer(question_id='aster:q1', answer='Yes, secretly, without a court.',
                                                  citations=['CRAA 3'], quote_id='CRAA 3#L1')])
        if agent == 'corvel_specialist':
            return SpecialistAnswer(applies=True, applicability_reasoning='Northgate is a data host.', coverage_note='Read all.',
                                    requirements=[Requirement(id='host_retention', title='Retention by data hosts', kind='duty',
                                                              status='unmet', reasoning='Agreement deletes in 30 days.',
                                                              citations=['CHRA 9'], quote_id='CHRA 9#L1',
                                                              required_actions=['Return records and keep no copy.'])])
        answered = '"from": "corvel"' in user
        route = Route(name='Approved clauses (Art 18)', status='ruled_out' if answered else 'unresolved',
                      reasoning='Depends on Corvel access law.', citations=['APIR 18'], quote_id='APIR 18#L2')
        return SpecialistAnswer(
            applies=True, applicability_reasoning='Custodian established in Valdora.', coverage_note='Read the TOC.',
            requirements=[Requirement(id='transfer_route', title='Outward transfer route', kind='gate',
                                      status='unmet' if answered else 'undetermined', reasoning='See routes.',
                                      facts=fact(user), citations=['APIR 18'], quote_id='APIR 18#L1', routes=[route],
                                      open_dependency='' if answered else 'Corvel access law',
                                      required_actions=['Hold keys in the Union.'] if answered else [])],
            delegations=[] if '"from": "valdora"' in user else [Delegation(
                corpus='valdora', requirement_id='sensitive_condition', question='Which national condition applies?',
                referring_provisions=['APIR 8'])],
            peer_questions=[PeerQuestion(jurisdiction='XC', requirement_id='transfer_route',
                                         question='Can Corvel authorities compel access?', why='APIR 18(2)')])
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
        self.assertEqual(set(refs), {'aster:transfer_route', 'valdora:national_transfer_conditions', 'corvel:host_retention'})
        self.assertTrue(all(f['verified'] for f in refs.values()), [f['issues'] for f in refs.values()])
        self.assertEqual(refs['aster:transfer_route']['status'], 'unmet')  # reassessed after Corvel answered
        self.assertEqual(result['questions'][0]['status'], 'answered')
        self.assertEqual(result['questions'][0]['routed_to'], 'corvel')
        self.assertEqual(result['decision'], 'do_not_proceed')
        self.assertIn('valdora:national_transfer_conditions', ' '.join(result['reasons']))
        self.assertEqual(refs['aster:transfer_route']['quote'][:20], '1. In the absence of')
        self.assertTrue(result['brief']['conflicts'][0]['resolvable'])
        # plan, 2 specialists, valdora delegate, aster reassess, review, corvel answer, aster reassess, review
        self.assertEqual(len(self.calls), 9, self.calls)


class RevisionAndQuestionTests(unittest.TestCase):
    def setUp(self):
        self.seen = []

        def model(agent, schema, system, user):
            self.seen.append((agent, schema.__name__, user))
            if schema is DelegateAnswer:
                return DelegateAnswer(answers=[], additional_requirements=[Requirement(
                    id='impact_assessment_list', title='National impact assessment list', kind='gate', status='unmet',
                    reasoning='Hosting abroad needs one.', citations=['VHIA 8'], quote_id='VHIA 8#L1')])
            return SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c')

        llm.FAKE_MODEL, tools.ENABLED = model, False

    def tearDown(self):
        llm.FAKE_MODEL, tools.ENABLED = None, True

    def test_supervisor_revision_reaches_a_lower_level_corpus(self):
        state = pipeline.Run(CASE)
        state.answers['aster'] = SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c')
        state.extra['valdora:old'] = {'id': 'old', 'title': 'Old', 'kind': 'gate', 'status': 'met', 'reasoning': 'r',
                                      'corpus': 'valdora', 'ref': 'valdora:old'}
        review = SupervisorReview(action='route_or_revise', summary='s',
                                  revisions=[Revision(corpus='valdora', instruction='Assess VHIA 8.')])
        self.assertTrue(state.route(review))
        self.assertEqual(list(state.extra), ['valdora:impact_assessment_list'])  # replaced, not appended
        self.assertEqual([(a, s) for a, s, _ in self.seen],
                         [('valdora_specialist', 'DelegateAnswer'), ('aster_specialist', 'SpecialistAnswer')])
        self.assertIn('YOUR PRIOR REPORT', self.seen[0][2])
        self.assertIn('Assess VHIA 8.', self.seen[0][2])

    def test_rephrased_peer_question_is_not_asked_twice(self):
        state = pipeline.Run(CASE)
        ask = lambda text: SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c', peer_questions=[
            PeerQuestion(jurisdiction='XC', requirement_id='transfer_route', question=text, why='w')])
        state.answers['aster'] = ask('Can Corvel compel access?')
        state.collect_questions('aster')
        state.answers['aster'] = ask('Under Corvel law, may authorities compel access?')
        state.collect_questions('aster')
        self.assertEqual(list(state.questions), ['aster:q1'])

    def test_delegates_are_pointed_to_linked_provisions_from_the_graph(self):
        from engine import agents
        linked = agents.linked_provisions('valdora', [{'question': 'Is there a list under APIR 12#L5?',
                                                       'referring_provisions': []}])
        self.assertIn('VHIA 8 (Section 8 - Impact assessment list) cites APIR 12', linked)


class VerificationTests(unittest.TestCase):
    def test_unread_law_and_unshown_quotes_are_defects(self):
        finding = Requirement(id='x', title='x', kind='gate', status='met', reasoning='r',
                              citations=['APIR 18'], quote_id='APIR 18#L1').model_dump()
        checked = pipeline.verify({**finding, 'corpus': 'aster', 'ref': 'aster:x'}, tools.new_record(), set())
        self.assertFalse(checked['verified'])
        self.assertIn('did not read', checked['issues'][0])

    def test_case_rejects_unknown_jurisdictions(self):
        bad = json.loads(json.dumps(CASE))
        bad['organisations'][0]['jurisdiction'] = 'IE'
        with self.assertRaises(ValueError):
            Case.model_validate(bad)


if __name__ == '__main__':
    unittest.main()
