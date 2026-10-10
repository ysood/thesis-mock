"""Reviewer brief: regroups checked findings without inferring statuses, gaps or routes."""

import unittest

from app import brief


def record(key, status, cls='gate', scope='transfer', finding_ids=None, evidence=()):
    return {'key': key, 'title': key, 'regime': 'GDPR', 'class': cls, 'obligation_scope': scope, 'status': status,
            'finding_ids': [f'gdpr_specialist:{key}'] if finding_ids is None else finding_ids,
            'evidence': list(evidence), 'note': ''}


def finding(key, **fields):
    return {'finding_id': f'gdpr_specialist:{key}', 'question_ids': [key], 'verified': True,
            'resolved_citations': ['GDPR Art. 46'], 'quote': 'text', **fields}


ROUTE = {'name': 'SCCs', 'status': 'unresolved', 'reasoning': 'Not yet signed.', 'resolved_citations': ['GDPR Art. 46']}
EVIDENCE = {'evidence_type': 'executed_agreement', 'description': 'Signed SCCs', 'from_party': 'both',
            'request_id': 'gdpr.transfer_mechanism/executed_agreement/abc123'}


class BriefTests(unittest.TestCase):
    def test_blocking_gaps_and_routes_come_first(self):
        records = [record('gdpr.security', 'undetermined', cls='advisory'),
                   record('gdpr.transfer_mechanism', 'undetermined', evidence=[EVIDENCE])]
        findings = [finding('gdpr.security', confirmations=['Confirm encryption at rest.']),
                    finding('gdpr.transfer_mechanism', missing_information=['Who signs the SCCs'],
                            routes=[ROUTE], required_actions=['Execute SCCs module 2'])]
        b = brief.build(records, findings, [])
        self.assertEqual([(m['kind'], m['blocking']) for m in b['missing']],
                         [('fact', True), ('evidence', True), ('confirm', False)])
        self.assertEqual(b['missing'][1]['request_id'], EVIDENCE['request_id'])
        self.assertEqual(b['routes'][0]['requirement'], 'gdpr.transfer_mechanism')
        self.assertEqual(b['routes'][0]['to_close'], ['Execute SCCs module 2'])
        self.assertEqual([r['blocking'] for r in b['required']], [False, True])

    def test_activity_scope_and_met_gates_do_not_block(self):
        records = [record('gdpr.dpia', 'undetermined', scope='activity'), record('gdpr.lawful_basis', 'met')]
        b = brief.build(records, [finding('gdpr.dpia'), finding('gdpr.lawful_basis')], [])
        self.assertFalse(any(r['blocking'] for r in b['required']))

    def test_review_gaps_are_kept_with_their_blocking_flag(self):
        b = brief.build([], [], [{'blocking': True, 'source': 'supervisor', 'description': 'Conflict unresolved'}])
        self.assertEqual(b['missing'], [{'kind': 'review', 'requirement': '', 'blocking': True,
                                         'description': 'supervisor: Conflict unresolved'}])

    def test_no_unique_finding_gives_no_citations_or_routes(self):
        records = [record('gdpr.transfer_mechanism', 'undetermined', finding_ids=['a', 'b'])]
        b = brief.build(records, [finding('gdpr.transfer_mechanism', routes=[ROUTE])], [])
        self.assertEqual(b['required'][0]['citations'], [])
        self.assertFalse(b['required'][0]['verified'])
        self.assertEqual(b['routes'], [])

    def test_not_applicable_requirements_have_no_routes(self):
        b = brief.build([record('gdpr.research_safeguards', 'not_applicable')],
                        [finding('gdpr.research_safeguards', routes=[ROUTE])], [])
        self.assertEqual(b['routes'], [])

    def test_known_facts_are_deduplicated_and_skip_unresolved_selections(self):
        fact = {'fact_id': 'f_1', 'path': '/transfer/purpose', 'quote': 'treatment'}
        findings = [finding('gdpr.lawful_basis', facts=[fact, {'fact_id': 'f_bad', 'path': '', 'quote': ''}]),
                    finding('gdpr.data_minimisation', facts=[fact])]
        b = brief.build([], findings, [])
        self.assertEqual(b['known'], [{'fact_id': 'f_1', 'path': '/transfer/purpose', 'text': 'treatment',
                                       'used_by': ['gdpr.lawful_basis', 'gdpr.data_minimisation']}])


if __name__ == '__main__':
    unittest.main()
