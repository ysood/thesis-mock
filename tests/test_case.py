"""One input snapshot, isolated from caller and model views."""

import unittest

from app.case import evidence_by_id, fact_document, new_case


class CaseContractTests(unittest.TestCase):
    def test_input_and_views_are_independent_snapshots(self):
        request = {'organisations': [], 'transfer': {'additional_info': 'Existing activity'},
                   'evidence': [{'id': 'E1', 'between': ['clinic'], 'summary': 'Only clinic',
                                 'attested_by': 'Alice Example'}]}
        reference = {'countries': {'IE': {'eea_member': True}}}
        case = new_case(request, reference)
        request['evidence'][0]['between'].append('hospital')
        request['transfer']['additional_info'] = 'changed'
        reference['countries']['IE']['eea_member'] = False
        view = fact_document(case)
        view['evidence'][0]['summary'] = 'changed'
        self.assertEqual(case['input']['transfer']['additional_info'], 'Existing activity')
        self.assertTrue(case['input']['reference_facts']['countries']['IE']['eea_member'])
        evidence = evidence_by_id(case)
        self.assertEqual(evidence['E1']['between'], ['clinic'])
        self.assertEqual(evidence['E1']['summary'], 'Only clinic')
        self.assertEqual(evidence['E1']['attested_by'], 'Alice Example')
        evidence['E1']['between'].append('another')
        self.assertEqual(evidence_by_id(case)['E1']['between'], ['clinic'])
        self.assertEqual(fact_document(case), case['input'])
        self.assertNotIn('submitted', case['input'])
        self.assertNotIn('request', case['input'])

    def test_empty_assessment_sections_do_not_infer_any_findings(self):
        case = new_case({'organisations': [], 'transfer': {}, 'evidence': []}, {})
        self.assertEqual(case['version'], 'v15')
        self.assertEqual(evidence_by_id(case), {})
        self.assertEqual(case['specialists'], {})
        self.assertEqual(case['checks'], {})
        self.assertIsNone(case['supervisor']['review'])
