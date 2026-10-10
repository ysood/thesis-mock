"""Decision consistency rules: refusal precedence and proceed-with-conditions. Status consistency only."""

import unittest

from app.review import established_refusals, final_decision


def finding(qid, status, agent='gdpr_specialist', regime='GDPR', verified=True, scope='transfer'):
    return {'finding_id': f'{agent}:{qid}', 'agent': agent, 'regime': regime, 'question_ids': [qid],
            'status': status, 'verified': verified, 'obligation_scope': scope}


APPLIES = finding('gdpr.applicability', 'satisfied_if_verified')
UNMET_TRANSFER = finding('gdpr.transfer_mechanism', 'not_satisfied')


class RefusalTests(unittest.TestCase):
    def test_verified_unmet_transfer_gate_refuses_despite_other_issues(self):  # run0009
        checked = [APPLIES, UNMET_TRANSFER, finding('gdpr.lawful_basis', 'insufficient_information'),
                   finding('hipaa.required_agreements', 'insufficient_information', 'hipaa_specialist', 'HIPAA', False)]
        decision, notes = final_decision('needs_review', ['hipaa quote defect'], checked, [], False)
        self.assertEqual(decision, 'do_not_proceed')
        self.assertIn('gdpr_specialist:gdpr.transfer_mechanism', notes[0])

    def test_no_refusal_without_applicability_unverified_finding_child_or_activity_scope(self):
        self.assertEqual(established_refusals([finding('gdpr.applicability', 'insufficient_information'), UNMET_TRANSFER]), [])
        self.assertEqual(established_refusals([APPLIES, finding('gdpr.transfer_mechanism', 'not_satisfied', verified=False)]), [])
        self.assertEqual(established_refusals([APPLIES, finding('gdpr_specialist:local1', 'not_satisfied', 'local_law_IE', 'IE')]), [])
        self.assertEqual(established_refusals([APPLIES, finding('gdpr.dpia', 'not_satisfied', scope='activity')]), [])
        self.assertEqual(established_refusals([APPLIES, finding('gdpr.security', 'not_satisfied')]), [])  # advisory

    def test_applicability_not_met_is_not_a_refusal(self):
        self.assertEqual(established_refusals([finding('gdpr.applicability', 'not_satisfied')]), [])

    def test_other_regime_applicability_does_not_count(self):
        hipaa_applies = finding('hipaa.applicability', 'satisfied_if_verified', 'hipaa_specialist', 'HIPAA')
        self.assertEqual(established_refusals([hipaa_applies, UNMET_TRANSFER]), [])


class ConditionTests(unittest.TestCase):
    def test_proceed_with_conditions_is_relabelled(self):  # run214
        self.assertEqual(final_decision('proceed', [], [APPLIES], ['Confirm X.'], False)[0], 'proceed_subject_to_conditions')
        self.assertEqual(final_decision('proceed', [], [APPLIES], [], True)[0], 'proceed_subject_to_conditions')
        self.assertEqual(final_decision('proceed', [], [APPLIES], [], False), ('proceed', []))

    def test_issues_still_hold_non_refusals(self):
        self.assertEqual(final_decision('proceed_subject_to_conditions', ['defect'], [APPLIES], [], False)[0], 'needs_review')
        self.assertEqual(final_decision('do_not_proceed', [], [APPLIES, UNMET_TRANSFER], [], False), ('do_not_proceed', []))


if __name__ == '__main__':
    unittest.main()
