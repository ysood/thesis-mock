"""HIPAA routing rubric wiring and the routing-only probe. Offline; no legal ground truth asserted."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app import knowledge as kb, llm, supervisor
from app.schema import IntakeReview, Plan, RegimeExclusion, SupervisorPlan, load_request
from tests import test_v9

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / 'tests' / 'fixtures' / '19_ie_gp_practice_to_de_cloud_ehr_two_layer.json'


def planner(hipaa_plan=None, exclusions=()):
    seen = {}

    def fake(agent, schema, system, user):
        seen.update(system=system, user=user)
        return SupervisorPlan(intake=IntakeReview(claims=[], contradictions=[], missing_information=[]),
                              interpretation=[], exclusions=list(exclusions),
                              gdpr_plan=Plan(applicability='GDPR on supplied facts.'), hipaa_plan=hipaa_plan)
    return fake, seen


def plan(fake):
    request = json.loads(SCENARIO.read_text())['request']
    with patch.object(llm, 'FAKE_MODEL', fake), patch.object(llm, 'model', side_effect=AssertionError('Paid call')):
        return supervisor.plan_case({'request': load_request(request)})


class RoutingRubricTests(unittest.TestCase):
    def test_rubric_reaches_setup_call_and_old_line_is_gone(self):
        fake, seen = planner(hipaa_plan=Plan(applicability='x'))
        plan(fake)
        self.assertIn('ROUTING RUBRICS:\n# HIPAA routing rubric', seen['user'])
        self.assertIn('[45 CFR 160.103 [Transaction]]', seen['user'])  # rubric citations are supplied sources
        self.assertNotIn('Country facts and corpus availability', seen['system'])

    def test_rubric_citations_are_corpus_provisions(self):
        ids = supervisor.rubric_sources()
        self.assertIn('45 CFR 160.102', ids)
        self.assertTrue(set(ids) <= set(kb.provisions()))

    def test_hipaa_routed_without_fact_is_flagged_not_blocked(self):
        case, setup, _ = plan(planner(hipaa_plan=Plan(applicability='Possibly.'))[0])
        self.assertIsNotNone(setup.hipaa_plan)  # routing kept as proposed
        self.assertEqual(case['checks']['routing_warnings'],
                         ['HIPAA routed without a cited nexus fact under its routing rubric.'])

    def test_hipaa_routed_with_fact_has_no_warning(self):
        fact = test_v9.fact_ref('/organisations/0/country', 'IE')
        case, _, _ = plan(planner(hipaa_plan=Plan(applicability='Yes.', facts=[fact]))[0])
        self.assertEqual(case['checks']['routing_warnings'], [])
        self.assertFalse([i for i in case['checks']['setup_issues'] if i.startswith('HIPAA plan')])

    def test_bad_plan_fact_is_a_reference_issue(self):
        fact = test_v9.fact_ref('/organisations/0/country', 'US')
        case, _, _ = plan(planner(hipaa_plan=Plan(applicability='Yes.', facts=[fact]))[0])
        self.assertIn('HIPAA plan: Fact passage reference is unknown or does not match its bound path/text: f_not_offered.',
                      case['checks']['setup_issues'])

    def test_exclusion_is_not_flagged(self):
        exclusion = RegimeExclusion(regime='HIPAA', reasoning='No rubric signal.',
                                    facts=[test_v9.fact_ref('/organisations/0/country', 'IE')], citations=['45 CFR 160.102'])
        case, setup, _ = plan(planner(exclusions=[exclusion])[0])
        self.assertIsNone(setup.hipaa_plan)
        self.assertEqual(case['checks']['routing_warnings'], [])
        self.assertFalse([i for i in case['checks']['setup_issues'] if 'HIPAA' in i])


class ProbeScriptTests(unittest.TestCase):
    def test_probe_cases_append_text(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('probe', ROOT / 'scripts' / 'probe_routing.py')
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        cases = probe.cases(ROOT / 'tests' / 'fixtures' / 'hipaa_routing_probes.json')
        self.assertEqual(len(cases), 11)
        billing = next(c for c in cases if 'bills US insurers' in c['name'])
        self.assertIn('US health insurers', billing['request']['organisations'][0]['description'])
        base = json.loads(SCENARIO.read_text())['request']
        self.assertNotIn('US health insurers', base['organisations'][0]['description'])  # source untouched
        for c in cases:
            load_request(c['request'])  # every probe stays a valid request


if __name__ == '__main__':
    unittest.main()
