"""Provision-only graph and fixed checklist starting sources. Offline checks."""

import unittest
from unittest.mock import patch

from app import agents, knowledge as kb, requirements as rq, traversal
from app.schema import GdprAssessment, NationalLawRequest, Plan


class ProvisionGraphTests(unittest.TestCase):
    def test_every_link_connects_existing_source_provisions(self):
        provisions = kb.provisions()
        graph = kb.graph()
        for relation in ('cites', 'amends', 'definitions'):
            for source, targets in graph[relation].items():
                self.assertIn(source, provisions)
                self.assertTrue(set(targets) <= set(provisions))
        self.assertEqual(traversal.describe_node('GDPR Art. 9')['edges']['cites'], ['GDPR Art. 89'])

    def test_source_links_are_navigation_not_legal_predicates_or_read_text(self):
        node = traversal.describe_node('GDPR Art. 9')
        self.assertNotIn('statement', node)
        self.assertNotIn('text', node)
        self.assertTrue(set(node['edges']) <= {'cites', 'amends', 'definitions'})
        self.assertIn('error', traversal.describe_node('gdpr.special_category_condition'))

    def test_model_schema_has_no_authored_conditions_or_national_opening_ids(self):
        schema = GdprAssessment.model_json_schema()
        self.assertNotIn('ConditionAnswer', schema.get('$defs', {}))
        self.assertNotIn('opening', NationalLawRequest.model_fields)

    def test_every_checklist_item_has_initial_sources_in_its_own_regime(self):
        for item in rq.catalogue()['requirements']:
            with self.subTest(question=item['key']):
                ids = rq.source_ids(item['key'])
                self.assertTrue(ids)
                self.assertTrue(all(kb.provisions()[pid]['regime'] == item['regime'] for pid in ids))


class PinnedSourcesTests(unittest.TestCase):
    """Integration step 1: checklist items read their graph bundle instead of a fresh search."""

    def gather(self, plan, regime="GDPR", search=None):
        events = []
        with patch.object(kb, "search", side_effect=search or (lambda query, regime, k=6: [])) as searched, \
                patch.object(agents, "emit", side_effect=lambda kind, agent, **data: events.append({"kind": kind, **data})):
            sources = agents.gather_sources(f"{regime.lower()}_specialist", regime, rq.plan_questions(regime, plan))
        return sources, searched, events

    def pinned(self, regime):
        return list(dict.fromkeys(pid for item in rq.items(regime) for pid in rq.source_ids(item["key"])))

    def test_checklist_sources_are_exactly_the_starting_provisions(self):
        for regime in ("GDPR", "HIPAA"):
            with self.subTest(regime=regime):
                sources, searched, events = self.gather(Plan(applicability="Applies."), regime)
                self.assertEqual(sources, kb.include_supporting_sources(self.pinned(regime)))
                self.assertFalse(searched.called)
                self.assertEqual([e["requirement"] for e in events if e["kind"] == "bundle"],
                                 [item["key"] for item in rq.items(regime)])

    def test_the_plan_cannot_change_checklist_sources(self):
        first, _, _ = self.gather(Plan(applicability="Pseudonymised genomic research data."))
        second, _, _ = self.gather(Plan(applicability="Anonymous statistics, probably out of scope."))
        self.assertEqual(first, second)

    def test_sources_are_only_the_pinned_bundles(self):
        def hit(query, regime, k=6):
            return [("GDPR Art. 33", 0.1)]
        sources, searched, _ = self.gather(Plan(applicability=""), search=hit)
        self.assertEqual(searched.call_count, 0)  # no extra questions, so nothing is searched
        self.assertEqual(sources[:len(self.pinned("GDPR"))], self.pinned("GDPR"))
        self.assertNotIn("GDPR Art. 33", sources)

if __name__ == '__main__':
    unittest.main()
