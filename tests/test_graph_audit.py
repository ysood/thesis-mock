"""Source-status notices from the 2026-10-05 audit. No model or network calls.

The audit's legal counterexamples exercised the v5-v8 rule evaluator, removed in v13; they remain on branch v12.
"""
import unittest

from app import agents, knowledge as kb


class StatusNoticeTests(unittest.TestCase):
    def test_status_notice_reaches_affected_hipaa_sources(self):
        text = agents.sources_text(['45 CFR 164.502(a)'])
        self.assertTrue(text.startswith('LEGAL STATUS NOTICE'))
        self.assertIn('vacated most', text)
        self.assertIn('164.509', text)
        self.assertEqual(kb.source_status_notes(['GDPR Art. 9']), [])


if __name__ == '__main__':
    unittest.main()
