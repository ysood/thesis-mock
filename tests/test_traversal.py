"""KG traversal tools and the bounded tool loop. Offline: a scripted chat model, no paid calls."""

import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

from app import agents, knowledge as kb, llm, passages, requirements as rq, traversal
from app.case import new_case
from app.review import check_finding
from app.schema import load_request

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / 'tests' / 'fixtures' / '19_ie_gp_practice_to_de_cloud_ehr_two_layer.json'


class Scripted:
    """Replays AIMessages; records each invocation's messages and whether tools were bound."""

    def __init__(self, replies):
        self.replies, self.calls = iter(replies), []

    def bind_tools(self, tools, **options):
        outer = self

        class Bound:
            def invoke(self, messages):
                return outer.respond(messages, bound=True, options=options)
        return Bound()

    def bind(self, **options):
        outer = self

        class Bound:
            def invoke(self, messages):
                return outer.respond(messages, bound=False, options=options)
        return Bound()

    def invoke(self, messages):
        return self.respond(messages, bound=False)

    def respond(self, messages, bound, options=None):
        self.calls.append({'messages': list(messages), 'bound': bound, 'options': options or {}})
        return next(self.replies)


def call(name, args, cid):
    return {'name': name, 'args': args, 'id': cid, 'type': 'tool_call'}


class Answer(BaseModel):
    answer: str


def scripted(replies):
    model = Scripted(replies)
    return model, patch.object(llm, 'tool_model', return_value=model)


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tools, self.record = traversal.toolset('hipaa_specialist', 'HIPAA')
        self.by_name = {t.__name__: t for t in self.tools}

    def test_kg_node_shows_typed_edges(self):
        node = traversal.describe_node('GDPR Art. 9')
        self.assertEqual(node['type'], 'provision')
        self.assertEqual(node['edges']['cites'], ['GDPR Art. 89'])
        self.assertIn('error', traversal.describe_node('no.such.node'))
        self.assertIn('not graph nodes', traversal.describe_node('gdpr_specialist:local1')['error'])
        self.assertIn('error', traversal.describe_node('gdpr.dpia'))

    def test_delegation_schema_uses_provisions_without_graph_openings(self):
        from app.schema import NationalLawQuestion, NationalLawRequest
        self.assertNotIn('opening', NationalLawQuestion.model_fields)
        self.assertNotIn('opening', NationalLawRequest.model_fields)
        self.assertIn('gdpr_provisions', NationalLawRequest.model_fields)

    def test_prompt_states_search_scope(self):
        gdpr, ie = traversal.prompt('GDPR', 8), traversal.prompt('IE', 8)
        self.assertIn('cover only GDPR law', gdpr)
        self.assertIn('national_law_requests', gdpr)
        self.assertIn('cover only IE law', ie)
        self.assertNotIn('national_law_requests', ie)
        self.assertIn('question IDs are not graph nodes', ie)

    def test_read_provision_records_reads_within_regime_only(self):
        self.assertIn('error', self.by_name['read_provision']('GDPR Art. 35'))
        result = self.by_name['read_provision']('45 CFR 160.102')
        self.assertEqual(result['provisions'][0]['id'], '45 CFR 160.102')
        self.assertEqual(self.record['read'], ['45 CFR 160.102'])
        self.assertTrue(all(link['id'] in kb.provisions()
                            for link in result['provisions'][0]['kg_links']['items']))

    def test_continuation_preserves_quote_ids_and_only_offers_shown_passages(self):
        tools, record = traversal.toolset('gdpr_specialist', 'GDPR')
        read = next(t for t in tools if t.__name__ == 'read_provision')
        pid = 'GDPR Art. 9'
        expected = passages.provision_passages(pid)
        with patch.object(traversal, 'MAX_TEXT', len(expected[0]['text'])):
            first = read(pid)
            self.assertTrue(first['truncated'])
            self.assertEqual(first['next_start'], 1)
            self.assertEqual(list(record['passages']), [expected[0]['quote_id']])
            quote = {'quote_id': expected[1]['quote_id'], 'citations': [pid]}
            self.assertIn('quote_selection_error', passages.copy_quote(quote, record['passages']))
            start = first['next_start']
            while start is not None:
                page = read(pid, start=start)
                for item in page['provisions']:
                    self.assertTrue(item['text'])
                if page['next_start'] is not None:
                    self.assertGreater(page['next_start'], start)
                start = page['next_start']
        self.assertEqual(record['passages'], {p['quote_id']: p for p in expected})
        copied = passages.copy_quote(quote, record['passages'])
        self.assertEqual(copied['quote'], expected[1]['text'])
        self.assertNotIn('quote_selection_error', copied)
        self.assertFalse(page['truncated'])
        self.assertEqual(record['read'], [pid])

    def test_continuation_covers_every_chunk_of_a_resolved_section(self):
        query = '45 CFR 164.514'
        ids = kb.resolve(query, kb.provisions())
        first = passages.provision_passages(ids[0])
        with patch.object(traversal, 'MAX_TEXT', sum(len(p['text']) for p in first)):
            page = self.by_name['read_provision'](query)
        self.assertEqual([p['id'] for p in page['provisions']], [ids[0]])
        self.assertFalse(page['provisions'][0]['truncated'])  # this chunk is complete
        self.assertTrue(page['truncated'])  # the section still has later chunks
        start = page['next_start']
        while start is not None:
            page = self.by_name['read_provision'](query, start=start)
            if page['next_start'] is not None:
                self.assertGreater(page['next_start'], start)
            start = page['next_start']
        self.assertEqual(self.record['read'], ids)
        self.assertEqual(self.record['passages'], passages.offered_passages(ids))
        self.assertFalse(page['truncated'])

    def test_oversized_passage_is_shown_whole_and_continuation_advances(self):
        pid = '45 CFR 160.102'
        provisions = deepcopy(kb.provisions())
        provisions[pid]['text'] = 'x' * (traversal.MAX_TEXT + 1) + '\n\n' + ' '.join(['word'] * 50)
        with patch.object(kb, 'provisions', return_value=provisions):
            expected = passages.provision_passages(pid)
            self.assertGreater(len(expected[0]['text']), traversal.MAX_TEXT)
            page = self.by_name['read_provision'](pid)
            self.assertEqual(page['provisions'][0]['text'], passages.render(expected[:1]))
            self.assertEqual(page['next_start'], 1)
            self.assertEqual(list(self.record['passages']), [expected[0]['quote_id']])
            final = self.by_name['read_provision'](pid, start=page['next_start'])
        self.assertIsNone(final['next_start'])
        self.assertFalse(final['truncated'])
        self.assertEqual(self.record['passages'], {p['quote_id']: p for p in expected})

    def test_invalid_continuation_is_reported_without_offering_sources(self):
        for start in (-1, 100000, '1', True):
            result = self.by_name['read_provision']('45 CFR 160.102', start=start)
            self.assertIn('error', result)
        self.assertEqual(self.record['read'], [])
        self.assertEqual(self.record['passages'], {})

    def test_opened_provision_exposes_reverse_graph_links_and_cross_references(self):
        tools, record = traversal.toolset('gdpr_specialist', 'GDPR')
        read = next(t for t in tools if t.__name__ == 'read_provision')
        result = read('GDPR Art. 9')['provisions'][0]
        links = {link['id']: link for link in result['kg_links']['items']}
        self.assertEqual(links['GDPR Art. 35']['relation'], 'cites')
        self.assertEqual(links['GDPR Art. 35']['direction'], 'incoming')
        self.assertEqual(links['GDPR Art. 89']['relation'], 'cites')
        self.assertFalse(any('text' in link for link in links.values()))
        self.assertEqual(record['read'], ['GDPR Art. 9'])  # linked text has not been read

    def test_link_payload_is_bounded_and_omitted_links_remain_inspectable(self):
        links = traversal.provision_links('GDPR Art. 9')
        self.assertEqual(len(links['items']), traversal.MAX_GRAPH_LINKS)
        self.assertTrue(links['truncated'])
        self.assertGreater(links['total'], len(links['items']))
        self.assertTrue(all(len(link['label']) <= traversal.MAX_LINK_LABEL for link in links['items']))
        node = traversal.describe_node('GDPR Art. 9')
        all_ids = {target for edges in (node['edges'], node['incoming_edges'])
                   for targets in edges.values() for target in targets}
        expected = kb.graph()['cited_by']['GDPR Art. 9']
        self.assertTrue(expected <= all_ids)
        self.assertIn('GDPR Art. 89', all_ids)
        self.assertFalse(any(node_id.startswith(('gdpr.', 'hipaa.', 'ie.')) for node_id in all_ids))

    def test_unmodelled_provision_can_still_expose_textual_links(self):
        node = traversal.describe_node('IE DPA 2018 s. 54')
        links = traversal.provision_links('IE DPA 2018 s. 54')
        self.assertEqual(node['edges']['cites'], ['IE DPA 2018 s. 42'])
        self.assertEqual(links['items'][0]['id'], 'IE DPA 2018 s. 42')

    def test_search_returns_ids_not_text(self):
        with patch.object(kb, 'search', return_value=[('45 CFR 160.102', 0.2)]):
            result = self.by_name['search_law']('who is covered')
        self.assertEqual(result['results'][0]['id'], '45 CFR 160.102')
        self.assertNotIn('text', result['results'][0])
        self.assertNotIn('kg_links', result['results'][0])
        self.assertEqual(self.record['read'], [])  # searching is not reading


class LoopTests(unittest.TestCase):
    def test_tool_results_return_to_model_then_json_is_parsed(self):
        tools, record = traversal.toolset('hipaa_specialist', 'HIPAA')
        model, patched = scripted([
            AIMessage(content='', tool_calls=[call('read_provision', {'provision_id': '45 CFR 160.102'}, 'c1')]),
            AIMessage(content='{"answer": "done"}')])
        with patched:
            result = llm.ask('hipaa_specialist', 'test', Answer, 'sys', 'user', tools=tools, budget=3)
        self.assertEqual(result.answer, 'done')
        second = model.calls[1]['messages']
        self.assertIsInstance(second[-1], ToolMessage)
        self.assertEqual(second[-1].tool_call_id, 'c1')
        self.assertIn('45 CFR 160.102', second[-1].content)
        self.assertEqual(record['read'], ['45 CFR 160.102'])

    def test_budget_answers_every_call_and_removes_tools(self):
        tools, record = traversal.toolset('hipaa_specialist', 'HIPAA')
        model, patched = scripted([
            AIMessage(content='', tool_calls=[call('read_provision', {'provision_id': '45 CFR 160.102'}, 'a'),
                                              call('read_provision', {'provision_id': '45 CFR 164.500'}, 'b')]),
            AIMessage(content='{"answer": "done"}')])
        with patched:
            result = llm.ask('hipaa_specialist', 'test', Answer, 'sys', 'user', tools=tools, budget=1)
        self.assertEqual(result.answer, 'done')
        replies = [m for m in model.calls[1]['messages'] if isinstance(m, ToolMessage)]
        self.assertEqual([m.tool_call_id for m in replies], ['a', 'b'])  # one result per call
        self.assertIn('budget exhausted', replies[1].content)
        self.assertFalse(model.calls[1]['bound'])  # the final turn cannot call tools
        self.assertEqual(record['read'], ['45 CFR 160.102'])

    def test_bad_tool_arguments_are_reported_not_raised(self):
        tools, _ = traversal.toolset('hipaa_specialist', 'HIPAA')
        model, patched = scripted([
            AIMessage(content='', tool_calls=[call('read_provision', {'wrong': 'x'}, 'c1'),
                                              call('no_such_tool', {}, 'c2')]),
            AIMessage(content='{"answer": "done"}')])
        with patched:
            self.assertEqual(llm.ask('a', 't', Answer, 's', 'u', tools=tools, budget=3).answer, 'done')
        contents = [m.content for m in model.calls[1]['messages'] if isinstance(m, ToolMessage)]
        self.assertIn('TypeError', contents[0])
        self.assertIn('Unknown tool', contents[1])


class ModelSelectionTests(unittest.TestCase):
    def test_tool_calls_use_the_responses_api_and_plain_calls_do_not(self):
        llm._model.cache_clear()
        with patch.dict('os.environ', {'MODEL': 'openai:gpt-4o', 'OPENAI_API_KEY': 'sk-test'}):
            self.assertTrue(llm.tool_model().use_responses_api)
            self.assertFalse(llm.model().use_responses_api)
            self.assertEqual(llm.tool_model().reasoning_effort, 'high')  # accuracy setting kept
        llm._model.cache_clear()


class AssessTests(unittest.TestCase):
    def setUp(self):
        raw = json.loads(SCENARIO.read_text())['request']
        request = load_request(raw)
        self.case = new_case(request, agents.derive_facts(request))
        self.questions = rq.plan_questions('HIPAA')[:1]
        self.sources = agents.gather_sources('hipaa_specialist', 'HIPAA', self.questions)
        self.extra = next(p for p, v in kb.provisions().items()
                          if v['regime'] == 'HIPAA' and p not in self.sources
                          and len(passages.provision_passages(p)) > 1)

    def finding_json(self):
        quote_id = passages.provision_passages(self.extra)[0]['quote_id']
        return json.dumps({'regime_applies': 'no', 'applicability_reasoning': 'Scripted.', 'findings': [{
            'question_ids': ['hipaa.applicability'], 'issue': 'HIPAA applicability', 'status': 'not_applicable',
            'reasoning': 'Scripted fixture; no legal claim.',
            'route_coverage': 'Scripted fixture checks source availability only.',
            'facts': [{'fact_id': next(p['fact_id'] for p in passages.input_passages(self.case['input']).values()
                                     if p['path'] == '/organisations/0/country')}],
            'citations': [self.extra], 'quote_id': quote_id}]})

    def run_assess(self, replies):
        model, patched = scripted(replies)
        with patched, patch.object(llm, 'model', return_value=model), patch.object(kb, 'vector_store', return_value=None):
            return model, agents.assess(self.case, 'HIPAA', 'hipaa_specialist', self.questions, self.sources)

    def test_provision_read_through_tools_is_citable(self):
        _, output = self.run_assess([
            AIMessage(content='', tool_calls=[call('read_provision', {'provision_id': self.extra}, 'c1')]),
            AIMessage(content=self.finding_json())])
        finding = output['findings'][0]
        self.assertIn(self.extra, finding['allowed'])
        self.assertIn(self.extra, output['extra_sources'])
        self.assertTrue(check_finding(finding, self.case)['verified'])

    def test_citing_unread_law_is_still_flagged(self):
        _, output = self.run_assess([AIMessage(content=self.finding_json())])
        checked = check_finding(output['findings'][0], self.case)
        self.assertFalse(checked['verified'])
        self.assertTrue(any('was not supplied' in n for n in checked['verification_notes']))

    def test_failed_assessment_keeps_sources_for_retry(self):
        _, output = self.run_assess([AIMessage(content='not json'), AIMessage(content='still not json')])
        self.assertEqual(output['findings'], [])
        self.assertEqual(output['sources'], self.sources)

    def test_prompt_and_switch(self):
        model, _ = self.run_assess([AIMessage(content=self.finding_json())])
        payload = model.calls[0]['messages'][1].content
        self.assertIn('TOOLS: LEGAL SOURCES are your starting reading.', payload)
        self.assertNotIn('KG GUIDANCE', payload)
        self.assertNotIn('hipaa.cond.', payload)
        self.assertTrue(model.calls[0]['bound'])
        with patch.object(traversal, 'ENABLED', False):
            model, _ = self.run_assess([AIMessage(content=self.finding_json())])
        self.assertNotIn('TOOLS:', model.calls[0]['messages'][1].content)
        self.assertFalse(model.calls[0]['bound'])


class RobustnessTests(unittest.TestCase):
    def test_trailing_text_after_json_is_ignored(self):
        self.assertEqual(llm.parse_json('{"answer": "a"}\n{"answer": "b"}'), {'answer': 'a'})  # run2201
        self.assertEqual(llm.parse_json('Here: {"answer": "x"} done'), {'answer': 'x'})
        self.assertEqual(llm.parse_json('```json\n{"answer": "y"}\n```'), {'answer': 'y'})
        with self.assertRaises(ValueError):
            llm.parse_json('no json here')

    def test_bad_json_retry_logs_raw_reply(self):
        events = []
        model, patched = scripted([AIMessage(content='not json'), AIMessage(content='{"answer": "ok"}')])
        with patch.object(llm, 'model', return_value=model), patch.object(llm, 'emit', lambda k, a, **d: events.append((k, d))):
            self.assertEqual(llm.ask('a', 't', Answer, 's', 'u').answer, 'ok')
        retry = next(d for k, d in events if k == 'llm_retry')
        self.assertEqual(retry['raw'], 'not json')

    def test_failed_specialist_keeps_its_sources(self):
        output = agents.failed_output('hipaa_specialist', 'HIPAA', ['hipaa.applicability'], 'failed', ['45 CFR 160.102'])
        self.assertEqual(output['sources'], ['45 CFR 160.102'])  # run2201: the retry had no law


if __name__ == '__main__':
    unittest.main()


class NationalProvisionTests(unittest.TestCase):
    def test_gdpr_node_lists_citing_national_provisions(self):
        from app.traversal import describe_node
        self.assertIn('IE MC Guide 2024 para. 25', describe_node('GDPR Art. 9')['national_provisions'])
        self.assertNotIn('national_provisions', describe_node('IE DPA 2018 s. 52'))
