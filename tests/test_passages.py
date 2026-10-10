"""Source-bound legal quotes, with model and vector calls blocked."""

import json
import unittest
from unittest.mock import patch

from app import knowledge as kb, passages, traversal
from app.review import check_finding
from app.schema import Finding
from tests import test_traversal, test_v9
from langchain_core.messages import AIMessage


class PassageTests(unittest.TestCase):
    def test_entire_corpus_has_unique_exact_spans_without_lost_words(self):
        seen = set()
        for pid, provision in kb.provisions().items():
            selected = passages.provision_passages(pid)
            previous = 0
            for p in selected:
                self.assertNotIn(p['quote_id'], seen)
                seen.add(p['quote_id'])
                self.assertEqual(p['text'], provision['text'][p['start']:p['end']])
                self.assertFalse(provision['text'][previous:p['start']].strip())
                previous = p['end']
            self.assertFalse(provision['text'][previous:].strip())
            self.assertEqual(' '.join(p['text'] for p in selected).split(), provision['text'].split())

    def test_minimum_necessary_rule_and_complete_exception_list_are_separate(self):
        pid = '45 CFR 164.502(b)'
        selected = passages.provision_passages(pid)
        rule, exceptions = kb.provisions()[pid]['text'].split('\n(2)', 1)
        self.assertEqual([p['text'] for p in selected], [rule, '(2)' + exceptions])
        self.assertGreater(len(selected[0]['text'].split()), 40)
        self.assertIn('does not apply', selected[1]['text'])
        self.assertIn('health care provider for treatment;', selected[1]['text'])
        self.assertIn('(vi)', selected[1]['text'])

    def test_gdpr_scope_and_prohibition_do_not_spill_into_exception_paragraphs(self):
        for pid in ['GDPR Art. 2', 'GDPR Art. 9']:
            with self.subTest(pid=pid):
                selected = passages.provision_passages(pid)
                self.assertEqual(len(selected), 4)
                self.assertTrue(all(p['text'].startswith(f'{i}. ')
                                    for i, p in enumerate(selected, 1)))
                self.assertNotIn('\n2.', selected[0]['text'])
                self.assertIn('(a)', selected[1]['text'])

    def test_numbered_list_keeps_its_intro_and_wrapped_prose_stays_whole(self):
        source = 'Applies to:\n(1) The first recipient.\n(2) The second recipient.\n\n'
        source += 'A complete sentence with a soft\nline break and no numbered structure.'
        parts = list(passages.quote_units(source))
        self.assertEqual(''.join(parts), source)
        nonempty = [p.strip() for p in parts if p.strip()]
        self.assertEqual(len(nonempty), 2)
        self.assertIn('(2) The second recipient.', nonempty[0])
        self.assertIn('soft\nline break', nonempty[1])

    def test_id_is_stable_and_changes_when_provision_or_text_changes(self):
        law = {'a': {'text': 'Exact original sentence.'}, 'b': {'text': 'Exact original sentence.'}}
        with patch.object(kb, 'provisions', return_value=law):
            original = passages.provision_passages('a')[0]['quote_id']
            self.assertEqual(original, passages.provision_passages('a')[0]['quote_id'])
            self.assertNotEqual(original, passages.provision_passages('b')[0]['quote_id'])
            law['a']['text'] = 'Changed source sentence.'
            self.assertNotEqual(original, passages.provision_passages('a')[0]['quote_id'])

    def test_schema_selects_an_id_instead_of_generating_legal_quote_text(self):
        fields = Finding.model_json_schema()['properties']
        self.assertIn('quote_id', fields)
        self.assertNotIn('quote', fields)
        fact_fields = Finding.model_json_schema()['$defs']['FactRef']['properties']
        self.assertEqual(set(fact_fields), {'fact_id'})

    def test_python_copies_source_even_if_generated_text_is_supplied(self):
        pid = 'GDPR Recital 26'
        p = next(p for p in passages.provision_passages(pid) if 'undergone pseudonymisation' in p['text'])
        finding = {'citations': [pid], 'quote_id': p['quote_id'], 'quote': 'Pseudonymised data'}
        copied = passages.copy_quote(finding, {p['quote_id']: p})
        self.assertEqual(copied['quote'], p['text'])
        self.assertIn('Personal data which have undergone pseudonymisation', copied['quote'])
        self.assertEqual(finding['quote'], 'Pseudonymised data')

    def test_hipaa_run229_quotes_keep_the_omitted_source_words(self):
        pid = '45 CFR 164.514(e)'
        selected = passages.provision_passages(pid)
        for phrase in ('paragraphs (e)(2) and (e)(3) of this section',
                       'under paragraph (e)(1) of this section only if'):
            p = next(p for p in selected if phrase in p['text'])
            copied = passages.copy_quote({'citations': [pid], 'quote_id': p['quote_id']}, {p['quote_id']: p})
            self.assertIn(phrase, copied['quote'])
            self.assertEqual(copied['quote'], p['text'])

    def test_unknown_id_and_uncited_provision_fail_without_substituting_text(self):
        pid = 'GDPR Art. 9'
        p = passages.provision_passages(pid)[0]
        offered = {p['quote_id']: p}
        for quote_id, citations in [('q_invented', [pid]), (p['quote_id'], ['GDPR Art. 6'])]:
            with self.subTest(quote_id=quote_id):
                copied = passages.copy_quote({'quote_id': quote_id, 'citations': citations}, offered)
                self.assertEqual(copied['quote'], '')
                self.assertTrue(copied['quote_selection_error'])

    def test_source_quote_recheck_rejects_tampered_saved_text(self):
        pid = 'GDPR Art. 9'
        p = passages.provision_passages(pid)[0]
        finding = {'finding_id': 'fixture', 'question_ids': ['fixture'], 'agent': 'gdpr_specialist',
                   'regime': 'GDPR', 'status': 'insufficient_information', 'allowed': [pid],
                   'route_coverage': 'Fixture checks source integrity only.',
                   'citations': [pid], 'quote_id': p['quote_id'], 'quote': p['text']}
        case = {'input': {'organisations': [], 'transfer': {}, 'evidence': [], 'reference_facts': {}}, 'specialists': {}}
        self.assertTrue(check_finding(finding, case)['verified'])
        finding['quote'] = p['text'] + ' '  # Even normalization-equivalent rewriting is rejected.
        checked = check_finding(finding, case)
        self.assertFalse(checked['verified'])
        self.assertEqual(checked['status'], 'insufficient_information')

    def test_tool_truncation_registers_only_complete_visible_passages(self):
        pid = 'GDPR Art. 9'
        selected = passages.provision_passages(pid)
        tools, record = traversal.toolset('gdpr_specialist', 'GDPR')
        read = next(t for t in tools if t.__name__ == 'read_provision')
        with patch.object(traversal, 'MAX_TEXT', selected[0]['end'] + 1):
            result = read(pid)['provisions'][0]
        self.assertTrue(result['truncated'])
        self.assertEqual(record['read'], [pid])
        self.assertEqual(list(record['passages']), [selected[0]['quote_id']])
        self.assertIn(selected[0]['quote_id'], result['text'])
        self.assertNotIn(selected[1]['quote_id'], result['text'])
        copied = passages.copy_quote({'quote_id': selected[1]['quote_id'], 'citations': [pid]}, record['passages'])
        self.assertTrue(copied['quote_selection_error'])


class PassageRuntimeTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_initial_packs_copy_selected_quotes_with_tools_disabled(self):
        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent in ('gdpr_specialist', 'hipaa_specialist'):
                pid = 'GDPR Art. 3' if agent == 'gdpr_specialist' else '45 CFR 160.102'
                p = passages.provision_passages(pid)[0]
                self.assertIn(f"[{p['quote_id']}] {p['text']}", user)
                for f in answer.findings:
                    f.status, f.citations, f.quote_id = 'not_applicable', [pid], p['quote_id']
            return answer
        with patch.object(traversal, 'ENABLED', False):
            result, _ = self.run_fake(fake)
        self.assertTrue(all(f['verified'] for f in result['findings']))
        for f in result['findings']:
            self.assertEqual(f['quote'], passages.offered_passages(f['allowed'])[f['quote_id']]['text'])


class TruncatedQuoteRuntimeTests(unittest.TestCase):
    setUp = test_traversal.AssessTests.setUp
    finding_json = test_traversal.AssessTests.finding_json
    run_assess = test_traversal.AssessTests.run_assess

    def test_selecting_unshown_tail_is_flagged_even_after_reading_parent_provision(self):
        selected = passages.provision_passages(self.extra)
        self.assertGreater(len(selected), 1)
        response = json.loads(self.finding_json())
        response['findings'][0]['quote_id'] = selected[-1]['quote_id']
        with patch.object(traversal, 'MAX_TEXT', selected[0]['end']):
            _, output = self.run_assess([
                AIMessage(content='', tool_calls=[test_traversal.call('read_provision', {'provision_id': self.extra}, 'c1')]),
                AIMessage(content=json.dumps(response))])
        f = output['findings'][0]
        self.assertIn(self.extra, f['allowed'])
        self.assertEqual(f['quote'], '')
        self.assertFalse(check_finding(f, self.case)['verified'])
        self.assertEqual(f['status'], 'not_applicable')


if __name__ == '__main__':
    unittest.main()
