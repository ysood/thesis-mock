"""Single-input intake contracts and reference facts, without legacy conversion."""

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from app import agents
from app.case import fact_document, new_case
from app.schema import AssessmentInput, load_request

SCENARIOS = Path(__file__).resolve().parents[1] / 'scenarios'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def given():
    return json.loads((FIXTURES / '18_ie_hospital_to_us_teleradiology_two_layer.json').read_text())['request']


class IntakeTests(unittest.TestCase):
    def test_one_shape_preserves_facts_without_legal_labels_or_synthetic_evidence(self):
        supplied = given()
        supplied['evidence'][0]['attested_by'] = 'Alice Example, hospital privacy officer'
        request = load_request(supplied)
        self.assertEqual(request, supplied)
        self.assertNotIn('attestations', request)
        self.assertNotIn('gdpr_role', request['organisations'][0])
        self.assertNotIn('gdpr_status', request['transfer']['data'])
        self.assertEqual(request['evidence'][0]['attested_by'], 'Alice Example, hospital privacy officer')
        request['evidence'][0]['summary'] = 'Changed working value'
        self.assertNotEqual(request, supplied)

    def test_identifiability_stays_supplied_and_is_never_mapped(self):
        for label in ('identified', 'coded', 'anonymous', 'unknown'):
            with self.subTest(label=label):
                supplied = given()
                supplied['transfer']['data']['identifiability'] = label
                data = load_request(supplied)['transfer']['data']
                self.assertEqual(data['identifiability'], label)
                self.assertNotIn('gdpr_status', data)
                self.assertNotIn('hipaa_status', data)

    def test_sender_reference_works_when_organisations_are_reordered(self):
        supplied = given()
        supplied['organisations'].reverse()
        request = load_request(supplied)
        facts = agents.derive_facts(request)
        self.assertEqual(facts['sender_country'], 'IE')
        self.assertEqual(facts['recipient_country'], 'US')
        self.assertEqual(request['organisations'], supplied['organisations'])

    def test_storage_and_access_remain_distinct_and_both_reach_reference_facts(self):
        supplied = given()
        supplied['organisations'][1]['country'] = 'IE'
        supplied['transfer']['locations'] = {'stored_in': ['IE'], 'accessed_from': ['US']}
        request = load_request(supplied)
        self.assertEqual(request['transfer']['locations'], supplied['transfer']['locations'])
        self.assertNotIn('access_or_storage_countries', request)
        facts = agents.derive_facts(request)
        self.assertEqual(set(facts['countries']), {'IE', 'US'})
        self.assertTrue(facts['data_moves_from_eea_to_non_eea_country'])
        request['transfer']['locations']['accessed_from'] = ['IE']
        self.assertFalse(agents.derive_facts(request)['data_moves_from_eea_to_non_eea_country'])
        request['transfer']['locations'] = {'stored_in': ['US'], 'accessed_from': []}
        self.assertTrue(agents.derive_facts(request)['data_moves_from_eea_to_non_eea_country'])

    def test_omissions_and_explicit_unknowns_survive_case_creation(self):
        supplied = given()
        supplied['transfer']['data'] = {'description': 'Unknown identifying fields', 'identifiability': 'unknown'}
        supplied['transfer'].pop('locations', None)
        supplied.pop('evidence', None)
        request = load_request(supplied)
        case = new_case(request, agents.derive_facts(request))
        self.assertEqual(case['input']['transfer']['data'], supplied['transfer']['data'])
        self.assertNotIn('locations', case['input']['transfer'])
        self.assertNotIn('evidence', case['input'])
        self.assertEqual(set(fact_document(case)), {'organisations', 'transfer', 'reference_facts'})

    def test_additional_organisations_remain_structured(self):
        supplied = given()
        supplied['organisations'].append({'id': 'cloud', 'name': 'Example Cloud', 'country': 'DE',
                                          'kind': 'cloud_provider'})
        self.assertEqual(load_request(supplied)['organisations'][-1], supplied['organisations'][-1])

    def test_all_current_examples_and_minimal_input_validate(self):
        for file in SCENARIOS.glob('*.json'):
            with self.subTest(file=file.name):
                request = json.loads(file.read_text())['request']
                self.assertEqual(load_request(request), request)
        minimum = {'organisations': [{'id': 'a', 'name': 'A', 'country': 'ie'},
                                     {'id': 'b', 'name': 'B', 'country': 'us'}],
                   'transfer': {'title': 'Minimal', 'sender': 'a', 'recipient': 'b',
                                'data': {'description': 'Records'}, 'purpose': 'other'}}
        request = load_request(minimum)
        self.assertEqual(request['organisations'][0]['country'], 'IE')
        self.assertFalse(agents.derive_facts(request)['countries']['US']['eea_member'])

    def test_old_input_and_old_transfer_names_are_rejected(self):
        old = {'title': 'Old request', 'sender': {'country': 'IE'}, 'recipient': {'country': 'US'}}
        with self.assertRaises(ValidationError):
            load_request(old)
        supplied = given()
        supplied['transfer']['from'] = supplied['transfer'].pop('sender')
        supplied['transfer']['to'] = supplied['transfer'].pop('recipient')
        with self.assertRaises(ValidationError):
            load_request(supplied)


class ValidationTests(unittest.TestCase):
    def test_references_must_name_known_organisations(self):
        for key in ('sender', 'recipient', 'between'):
            with self.subTest(key=key):
                supplied = given()
                if key == 'between':
                    supplied['evidence'][0]['between'] = ['missing']
                else:
                    supplied['transfer'][key] = 'missing'
                with self.assertRaises(ValidationError):
                    AssessmentInput.model_validate(supplied)

    def test_ids_are_unique_and_the_parties_differ(self):
        supplied = given()
        supplied['evidence'][1]['id'] = supplied['evidence'][0]['id']
        with self.assertRaises(ValidationError):
            load_request(supplied)
        supplied = given()
        supplied['organisations'][1]['id'] = supplied['organisations'][0]['id']
        with self.assertRaises(ValidationError):
            load_request(supplied)
        supplied = given()
        supplied['transfer']['recipient'] = supplied['transfer']['sender']
        with self.assertRaises(ValidationError):
            load_request(supplied)
