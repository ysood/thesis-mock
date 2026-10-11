"""Unguarded baseline: one prompted-JSON call; reference problems are recorded, not rejected."""

import json
import unittest
from pathlib import Path

from engine import llm, pipeline
from engine.schema import BaselineAssessment

CASE = json.loads((Path(__file__).resolve().parent.parent / 'cases' / '05_a1_genetic_second_opinion_in_b' / 'case.json').read_text())


def answer(system_seen):
    def model(agent, schema, system, user):
        system_seen.append((schema, system, user))
        return BaselineAssessment.model_validate({
            'understanding': 'u', 'coverage_note': 'c', 'decision': 'proceed', 'decision_reasoning': 'consent suffices',
            'applicability': [{'corpus': 'region_a', 'applies': True, 'reasoning': 'r'}],
            'requirements': [{
                'corpus': 'region_a', 'id': 'transfer', 'title': 'Transfer route', 'kind': 'gate', 'status': 'unmet',
                'reasoning': 'r', 'citations': ['A-REG 19(1)(a)', 'A-REG 99'], 'quote_id': 'A-REG 19#L2',
                'facts': [{'fact_id': 'f_made_up'}],
                'routes': [{'name': 'Explicit consent', 'status': 'supported', 'reasoning': 'r',
                            'citations': ['A-REG 19'], 'quote_id': 'none'}]}]})
    return model


class BaselineTests(unittest.TestCase):
    def run_level(self, level):
        seen = []
        llm.FAKE_MODEL, pipeline.MODE, pipeline.BASELINE = answer(seen), 'baseline', level
        try:
            result, _ = pipeline.run(CASE)
        finally:
            llm.FAKE_MODEL, pipeline.MODE, pipeline.BASELINE = None, 'multi', 'raw'
        return result, seen

    def test_raw_records_problems_and_keeps_three_decisions(self):
        result, seen = self.run_level('raw')
        self.assertIs(seen[0][0], BaselineAssessment)
        self.assertNotIn('FULL TEXT', seen[0][2])
        self.assertNotIn('only law', seen[0][1])  # no corpus-only rule
        self.assertEqual(result['decision'], 'proceed')  # the model's own decision is the headline
        self.assertEqual(result['decision_from_gates']['decision'], 'do_not_proceed')  # an unmet gate
        self.assertEqual(result['decision_guarded']['decision'], 'needs_review')  # unread law fails verification
        audit = result['audit']
        self.assertEqual(audit['citations_unknown'], ['A-REG 99'])
        self.assertEqual(audit['citations_not_shown'], ['A-REG 19'])
        self.assertEqual(audit['quote_ids_not_shown'], ['A-REG 19#L2'])
        self.assertEqual(audit['fact_ids_unknown'], ['f_made_up'])
        self.assertEqual(result['findings'][0]['resolved_citations'], ['A-REG 19'])  # scored on existing provisions

    def test_corpus_level_puts_the_full_text_in_the_prompt(self):
        result, seen = self.run_level('corpus')
        self.assertIn('FULL TEXT', seen[0][2])
        self.assertEqual(result['audit']['citations_not_shown'], [])
        self.assertEqual(result['audit']['quote_ids_not_shown'], [])
