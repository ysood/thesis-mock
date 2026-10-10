"""The evidence-presence, closed-world and as-described policies are fixed prompt rules, not status calculators."""

import unittest

from app import agents, supervisor


class EvidencePolicyPromptTests(unittest.TestCase):
    def test_presence_policy(self):
        rules, system = agents.common_rules(), supervisor.system_prompt()
        self.assertIn('Evidence-presence policy', rules)
        self.assertIn('in confirmations, never in missing_information', rules)
        self.assertIn('Evidence-presence policy', system)
        self.assertNotIn("A document's kind or title cannot establish", system)
        self.assertNotIn('{evidence', rules + system)


class ClosedWorldPolicyTests(unittest.TestCase):
    def test_rule_in_specialists_and_supervisor(self):
        rules, system = agents.common_rules(), supervisor.system_prompt()
        self.assertIn('11. Corpus policy (closed world)', rules)
        self.assertIn('confirm none applies outside it', rules)
        self.assertIn('enabling rule still needs a supplied source', rules)
        self.assertIn('Corpus policy (closed world)', system)
        self.assertLess(rules.index('11. Corpus policy'), rules.index('For each fact reference'))


class AsDescribedPolicyTests(unittest.TestCase):
    def test_rule_in_specialists_and_supervisor(self):
        rules, system = agents.common_rules(), supervisor.system_prompt()
        self.assertIn('12. Assessment as described', rules)
        self.assertIn('not_satisfied as described', rules)
        self.assertIn('Missing documentary evidence for a stated fact is still not failure', rules)
        self.assertIn('Assessment as described', system)
        self.assertIn('do_not_proceed then follows', system)
        self.assertLess(rules.index('11. Corpus policy'), rules.index('12. Assessment as described'))


if __name__ == '__main__':
    unittest.main()
