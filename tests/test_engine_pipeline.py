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
        if schema is SupervisorReview:
            reviews.append(user)
            if len(reviews) == 1:
                return SupervisorReview(action='route_or_revise', summary='Route the access question.', routings=[
                    Routing(question_ref='region_a:q1', to_corpus='region_b', question='Can Region B authorities compel access?')])
            return SupervisorReview(action='finish', summary='Done.', conflicts=[
                Conflict(description='Deletion vs retention.', requirement_refs=['region_a:agent_contract', 'region_b:host_retention'],
                         resolvable=True, resolution='Return instead of delete.')])
        if schema is DelegateAnswer and agent == 'subregion_a1_specialist':
            return DelegateAnswer(answers=[Answer(question_id='region_a>subregion_a1:d1', answer='A1-HIA 4 supplies the condition.',
                                                  citations=['A1-HIA 4'], quote_id='A1-HIA 4#L1')],
                                  additional_requirements=[Requirement(
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
        # plan, 2 specialists, subregion_a1 delegate, region_a reassess, review, region_b answer, region_a reassess, review
        self.assertEqual(len(self.calls), 9, self.calls)


class RevisionAndQuestionTests(unittest.TestCase):
    def setUp(self):
        self.seen = []

        def model(agent, schema, system, user):
            self.seen.append((agent, schema.__name__, user))
            if schema is DelegateAnswer:
                return DelegateAnswer(answers=[], additional_requirements=[Requirement(
                    id='impact_assessment_list', title='National impact assessment list', kind='gate', status='unmet',
                    reasoning='Hosting abroad needs one.', citations=['A1-HIA 8'], quote_id='A1-HIA 8#L1')])
            return SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c')

        llm.FAKE_MODEL, tools.ENABLED = model, False

    def tearDown(self):
        llm.FAKE_MODEL, tools.ENABLED = None, True

    def test_supervisor_revision_reaches_a_lower_level_corpus(self):
        state = pipeline.Run(CASE)
        state.answers['region_a'] = SpecialistAnswer(applies=True, applicability_reasoning='r', coverage_note='c')
        state.extra['subregion_a1:old'] = {'id': 'old', 'title': 'Old', 'kind': 'gate', 'status': 'met', 'reasoning': 'r',
                                      'corpus': 'subregion_a1', 'ref': 'subregion_a1:old'}
        review = SupervisorReview(action='route_or_revise', summary='s',
                                  revisions=[Revision(corpus='subregion_a1', instruction='Assess A1-HIA 8.')])
        self.assertTrue(state.route(review))
        self.assertEqual(list(state.extra), ['subregion_a1:impact_assessment_list'])  # replaced, not appended
        self.assertEqual([(a, s) for a, s, _ in self.seen],
                         [('subregion_a1_specialist', 'DelegateAnswer'), ('region_a_specialist', 'SpecialistAnswer')])
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

    def test_delegates_are_pointed_to_linked_provisions_from_the_graph(self):
        from engine import agents
        linked = agents.linked_provisions('subregion_a1', [{'question': 'Is there a list under A-REG 12#L5?',
                                                       'referring_provisions': []}])
        self.assertIn('A1-HIA 8 (Section 8 - Impact assessment list) cites A-REG 12', linked)


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
