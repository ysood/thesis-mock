"""Fixed checklist integrity. Runtime ownership is tested in test_v9.py."""

import unittest
from typing import get_args

from app import requirements as rq, knowledge as kb
from app.schema import EvidenceType, Plan

class CatalogueTests(unittest.TestCase):
    def test_catalogue_is_well_formed(self):
        items = rq.catalogue()["requirements"]
        keys = [i["key"] for i in items]
        self.assertEqual(len(keys), len(set(keys)))
        allowed = set(get_args(EvidenceType))
        self.assertEqual(set(rq.catalogue()["evidence_types"]), allowed)
        for item in items:
            self.assertIn(item["class"], ("gate", "advisory"))
            self.assertTrue(item["class_reason"].strip())
            self.assertTrue(set(item["evidence"]) <= allowed, item["key"])
            for anchor in item["anchors"]:
                self.assertTrue(kb.resolve(anchor, kb.provisions()), f"{item['key']}: {anchor}")
        for regime in ("GDPR", "HIPAA"):
            self.assertTrue(rq.applicability_key(regime).endswith(".applicability"))

    def test_the_checklist_is_fixed_and_in_order(self):
        questions = rq.plan_questions("GDPR", Plan(applicability=""))
        catalogue_keys = [i["key"] for i in rq.items("GDPR")]
        self.assertEqual([q.question_id for q in questions], catalogue_keys)  # no case-specific extras
        # Checklist sources are pinned by the knowledge graph, so the plan carries no search terms for them.
        self.assertTrue(all(q.search_query == "" for q in questions[:len(catalogue_keys)]))
