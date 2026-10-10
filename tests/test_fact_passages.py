"""Input passage provenance and runtime wiring, without model calls or legal outcome assertions."""

import json
import unittest
from copy import deepcopy

from app import passages
from app.review import quoted_fact, read_pointer
from app.schema import (FactRef, Finding, Claim, IntakeReview, NationalLawRequest,
                        SupervisorAction, SupervisorPlan)
from tests import test_v9


class InputPassageTests(unittest.TestCase):
    def setUp(self):
        self.request = test_v9.load('24_ie_research_to_ny_analytics_mixed_evidence.json')
        self.offered = passages.input_passages(self.request)

    def test_scalar_spans_preserve_text_types_and_escaped_pointers(self):
        document = {'a/b': {'x~y': [False, 0, None, '', 'unknown', 'First sentence. Second sentence.']}}
        offered = passages.input_passages(document)
        self.assertEqual([p['text'] for p in offered.values()],
                         ['false', '0', 'unknown', 'First sentence.', 'Second sentence.'])
        for p in offered.values():
            value = read_pointer(document, p['path'])
            source = value if isinstance(value, str) else json.dumps(value)
            self.assertEqual(source[p['start']:p['end']], p['text'])
            self.assertTrue(quoted_fact({'fact_id': p['fact_id'], 'path': p['path'], 'quote': p['text']}, document))

    def test_run24_dpia_sentence_keeps_the_negated_list_whole(self):
        p = next(p for p in self.offered.values() if p['path'] == '/evidence/3/summary'
                 and 'automated decisions with significant individual effects' in p['text'])
        self.assertEqual(p['text'], 'It records no children, biometric identification, clinical monitoring of public '
                         'areas or automated decisions with significant individual effects.')
        selected = FactRef(fact_id=p['fact_id'], path='/evidence/8/summary',
                           quote='no automated decisions with significant individual effects')
        bound = passages.bind_fact_references(selected, self.offered)
        self.assertEqual(bound.path, '/evidence/3/summary')
        self.assertEqual(bound.quote, p['text'])
        self.assertTrue(quoted_fact(bound.model_dump(), self.request))
        self.assertEqual(selected.quote, 'no automated decisions with significant individual effects')

    def test_ids_are_stable_and_bound_to_location_and_content(self):
        original = passages.input_passages({'a': 'Same text.', 'b': 'Same text.'})
        self.assertEqual(original, passages.input_passages({'a': 'Same text.', 'b': 'Same text.'}))
        self.assertEqual(len(original), 2)
        changed = passages.input_passages({'a': 'Changed text.', 'b': 'Same text.'})
        self.assertEqual(len(set(original) & set(changed)), 1)

    def test_unknown_id_is_not_repaired_by_generated_text_or_a_valid_pointer(self):
        selected = FactRef(fact_id='f_not_offered', path='/organisations/0/country', quote='IE')
        bound = passages.bind_fact_references(selected, self.offered)
        self.assertEqual((bound.path, bound.quote), ('', ''))
        self.assertFalse(quoted_fact(bound.model_dump(), self.request))

    def test_saved_pair_rejects_tampering_and_an_id_from_another_snapshot(self):
        p = next(p for p in self.offered.values() if p['path'] == '/organisations/0/country')
        ref = passages.bind_fact_references(FactRef(fact_id=p['fact_id']), self.offered).model_dump()
        for replacement in ({'quote': ref['quote'] + ' '}, {'path': '/transfer/locations/stored_in/0'}):
            self.assertFalse(quoted_fact({**ref, **replacement}, self.request))
        changed = deepcopy(self.request)
        changed['organisations'][0]['country'] = 'DE'
        self.assertFalse(quoted_fact(ref, changed))

    def test_response_schemas_offer_only_a_selection_not_generated_text_or_paths(self):
        for schema in (Finding, SupervisorPlan, SupervisorAction):
            for name, definition in schema.model_json_schema()['$defs'].items():
                if name in ('FactRef', 'RequestQuote'):
                    self.assertEqual(set(definition['properties']), {'fact_id'})
                    self.assertEqual(definition['required'], ['fact_id'])


def selections_only(value):
    """Simulate JSON produced using only the fields offered in the response schema."""
    if isinstance(value, dict):
        if 'fact_id' in value:
            return {'fact_id': value['fact_id']}
        return {key: selections_only(child) for key, child in value.items()}
    if isinstance(value, list):
        return [selections_only(child) for child in value]
    return value


class InputPassageRuntimeTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_supervisor_national_and_targeted_reviews_copy_only_shown_input_passages(self):
        given = test_v9.load('24_ie_research_to_ny_analytics_mixed_evidence.json')
        before = deepcopy(given)
        p = next(p for p in passages.input_passages(given).values() if p['path'] == '/evidence/3/summary'
                 and 'automated decisions with significant individual effects' in p['text'])
        reviews = 0
        agents = []

        def fake(agent, schema, system, user):
            nonlocal reviews
            agents.append(agent)
            self.assertIn(f"[{p['fact_id']}] {p['text']}", user)
            self.assertIn(p['path'], user)
            answer = test_v9.fake_model(agent, schema, system, user)
            if schema is SupervisorPlan:
                answer.intake = IntakeReview(
                    claims=[Claim(statement='The declaration excludes automated significant decisions.', kind='fact',
                                  source={'fact_id': p['fact_id']})], contradictions=[], missing_information=[])
            if agent in ('gdpr_specialist', 'local_law_IE'):
                for finding in answer.findings:
                    finding.facts = [FactRef(fact_id=p['fact_id'])]
                if agent == 'gdpr_specialist' and agents.count(agent) == 1:
                    answer.national_law_requests = [NationalLawRequest(
                        country='IE', requirement='gdpr.special_category_condition',
                        question='Synthetic Irish research question.', gdpr_provisions=['GDPR Art. 9'])]
            if schema is SupervisorAction:
                reviews += 1
                if reviews == 1:
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            question_ids=['gdpr.dpia'], instruction='Synthetic targeted review.')
                answer.intake = IntakeReview(
                    claims=[Claim(statement='The declaration excludes automated significant decisions.', kind='fact',
                                  source={'fact_id': p['fact_id']})], contradictions=[], missing_information=[])
            return schema.model_validate(selections_only(answer.model_dump()))

        result, events = self.run_fake(fake, given)
        self.assertEqual(given, before)
        self.assertIn('local_law_IE', agents)
        self.assertEqual(agents.count('gdpr_specialist'), 3)
        self.assertTrue(result['case_record']['checks']['complete'])
        ref = result['case_record']['supervisor']['intake']['claims'][0]['source']
        self.assertEqual((ref['fact_id'], ref['path'], ref['quote']), (p['fact_id'], p['path'], p['text']))
        for f in result['findings']:
            if f['agent'] in ('gdpr_specialist', 'local_law_IE'):
                self.assertEqual(f['facts'], [ref])
                self.assertTrue(f['verified'])
                self.assertEqual(f['status'], 'insufficient_information')
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 8)

    def test_unknown_selection_preserves_status_and_blocks_a_favourable_finish(self):
        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent in ('gdpr_specialist', 'hipaa_specialist'):
                pid = 'GDPR Art. 3' if agent == 'gdpr_specialist' else '45 CFR 160.102'
                for f in answer.findings:
                    f.status, f.citations, f.quote_id = 'not_applicable', [pid], test_v9.legal_quote_id(pid)
            if agent == 'gdpr_specialist':
                answer.findings[0].facts = [FactRef(fact_id='f_not_offered')]
            if schema is SupervisorAction:
                answer.decision = 'proceed'
            return answer
        result, _ = self.run_fake(fake)
        f = next(f for f in result['findings'] if f['agent'] == 'gdpr_specialist')
        self.assertEqual(f['status'], 'not_applicable')
        self.assertFalse(f['verified'])
        self.assertIn('f_not_offered', f['verification_notes'][0])
        self.assertEqual(result['decision'], 'needs_review')


if __name__ == '__main__':
    unittest.main()
