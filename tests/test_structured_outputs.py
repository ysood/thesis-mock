"""Strict output schemas and actual SDK payloads. All invocations are offline."""

import unittest
from copy import deepcopy
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app import agents, knowledge as kb, llm, passages, supervisor, traversal
from app.schema import (Assessment, FactRef, GdprAssessment, NationalLawRequest,
                        SupervisorAction, SupervisorPlan)
from tests import test_traversal, test_v9
from tests.test_traversal import Answer, Scripted, call


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


class StrictSchemaTests(unittest.TestCase):
    def test_described_source_references_are_inlined_without_losing_instructions(self):
        for schema in (SupervisorPlan, SupervisorAction):
            with self.subTest(schema=schema.__name__):
                original = deepcopy(schema.model_json_schema())
                original_source = original['$defs']['Claim']['properties']['source']
                self.assertIn('$ref', original_source)  # The shape rejected in the live run.
                shape = llm.response_format(schema, ['f_supplied'])['json_schema']['schema']
                source = shape['$defs']['Claim']['properties']['source']
                self.assertNotIn('$ref', source)
                self.assertEqual(source['description'], original_source['description'])
                self.assertEqual(source['type'], 'object')
                self.assertEqual(source['required'], ['fact_id'])
                self.assertFalse(source['additionalProperties'])
                self.assertEqual(source['properties']['fact_id']['enum'], ['f_supplied'])
                self.assertEqual(schema.model_json_schema(), original)

    def test_existing_schemas_are_adapted_without_changing_saved_shapes(self):
        for schema in (SupervisorPlan, SupervisorAction, Assessment, GdprAssessment):
            with self.subTest(schema=schema.__name__):
                original = deepcopy(schema.model_json_schema())
                fmt = llm.response_format(schema, ['f_first', 'f_second', 'f_first'], ['q_shown'])
                shape = fmt['json_schema']['schema']
                self.assertTrue(fmt['json_schema']['strict'])
                self.assertEqual(shape['type'], 'object')
                fact_fields = []
                for node in nodes(shape):
                    self.assertNotIn('default', node)
                    if node.get('type') == 'object':
                        self.assertFalse(node['additionalProperties'])
                        self.assertEqual(node['required'], list(node['properties']))
                        if 'fact_id' in node['properties']:
                            fact_fields.append(node['properties'])
                self.assertTrue(fact_fields)
                self.assertTrue(all(list(fields) == ['fact_id'] for fields in fact_fields))
                self.assertTrue(all(fields['fact_id']['enum'] == ['f_first', 'f_second'] for fields in fact_fields))
                self.assertEqual(schema.model_json_schema(), original)

    def test_nullable_updates_and_status_enums_retain_their_meaning(self):
        shape = llm.response_format(SupervisorAction, ['f_source'])['json_schema']['schema']
        self.assertIn({'type': 'null'}, shape['properties']['interpretation']['anyOf'])
        self.assertIn({'type': 'null'}, shape['properties']['reconciliation']['anyOf'])
        self.assertEqual(shape['properties']['action']['enum'], ['delegate', 'finish'])
        routes = llm.response_format(GdprAssessment, ['f_source'], ['q_shown'])['json_schema']['schema']['$defs']['LegalRoute']
        self.assertEqual(routes['properties']['status']['enum'],
                         ['supported', 'ruled_out', 'unresolved', 'not_investigated'])
        self.assertNotIn('not_satisfied', routes['properties']['status']['enum'])

    def test_fact_catalogue_is_required_and_isolated_between_calls(self):
        with self.assertRaisesRegex(ValueError, 'needs supplied fact_ids'):
            llm.response_format(SupervisorPlan)
        first = llm.response_format(FactRef, ['f_case_one'])
        second = llm.response_format(FactRef, ['f_case_two'])
        self.assertEqual(first['json_schema']['schema']['properties']['fact_id']['enum'], ['f_case_one'])
        self.assertEqual(second['json_schema']['schema']['properties']['fact_id']['enum'], ['f_case_two'])
        self.assertNotIn('enum', FactRef.model_json_schema()['properties']['fact_id'])

    def test_native_chat_and_responses_payloads_include_strict_constraints(self):
        tools, _ = traversal.toolset('offline', 'GDPR')
        for schema in (SupervisorPlan, SupervisorAction, Assessment, GdprAssessment):
            for responses in (False, True):
                with self.subTest(schema=schema.__name__, responses=responses):
                    chat = ChatOpenAI(model='gpt-4o', api_key='sk-offline', use_responses_api=responses)
                    fmt = llm.response_format(schema, ['f_supplied'], ['q_supplied'])
                    bound = chat.bind_tools(tools, response_format=fmt) if responses else chat.bind(response_format=fmt)
                    # Build the actual SDK request locally. No invoke() or network call.
                    payload = chat._get_request_payload([HumanMessage('offline')], **bound.kwargs)
                    sent = payload['text']['format'] if responses else payload['response_format']['json_schema']
                    self.assertTrue(sent['strict'])
                    for node in nodes(sent['schema']):
                        if '$ref' in node:
                            self.assertEqual(set(node), {'$ref'})
                    self.assertEqual(sent['schema']['$defs']['FactRef']['properties']['fact_id']['enum'], ['f_supplied'])
                    if schema in (Assessment, GdprAssessment):
                        self.assertEqual(sent['schema']['$defs']['LegalQuoteId']['enum'], ['q_supplied'])
                    if responses:
                        self.assertTrue(payload['tools'])
                        self.assertNotIn('response_format', payload)

    def test_quote_selection_excludes_run25_typo_and_keeps_empty_findings_only(self):
        valid = 'q_0ec791661eb4ebd7adc4'
        typo = 'q_0ec791661eb4b7d7adc4'
        for schema in (Assessment, GdprAssessment):
            with self.subTest(schema=schema.__name__):
                original = deepcopy(schema.model_json_schema())
                shape = llm.response_format(schema, ['f_source'], [valid, valid])['json_schema']['schema']
                self.assertEqual(shape['$defs']['LegalQuoteId']['enum'], [valid])
                self.assertNotIn(typo, shape['$defs']['LegalQuoteId']['enum'])
                ref = {'$ref': '#/$defs/LegalQuoteId'}
                finding = shape['$defs']['Finding']['properties']['quote_id']
                route = shape['$defs']['LegalRoute']['properties']['quote_id']
                self.assertEqual(finding['anyOf'], [ref, {'type': 'string', 'enum': ['']}])
                self.assertEqual(route['anyOf'], [ref])
                self.assertEqual(route['description'], original['$defs']['LegalRoute']['properties']['quote_id']['description'])
                self.assertEqual(schema.model_json_schema(), original)
        with self.assertRaisesRegex(ValueError, 'needs supplied quote_ids'):
            llm.response_format(Assessment, ['f_source'])
        other = llm.response_format(Assessment, ['f_source'], ['q_other'])
        self.assertEqual(other['json_schema']['schema']['$defs']['LegalQuoteId']['enum'], ['q_other'])


class StrictCallTests(unittest.TestCase):
    def ask(self, model, schema=Answer, *, tools=None, budget=0, fact_ids=(), provider='openai:offline'):
        events = []
        with (patch.object(llm, 'FAKE_MODEL', None),
              patch.object(llm, 'model_name', return_value=provider),
              patch.object(llm, 'model', return_value=model),
              patch.object(llm, 'tool_model', return_value=model),
              patch.object(llm, 'emit', lambda kind, agent, **data: events.append((kind, data)))):
            result = llm.ask('offline', 'test', schema, 'system', 'user',
                             tools=tools, budget=budget, fact_ids=fact_ids)
        return result, events

    def test_plain_call_sends_fact_choices_and_logs_the_mode(self):
        model = Scripted([AIMessage(content='{"fact_id":"f_selected"}')])
        result, events = self.ask(model, FactRef, fact_ids=['f_selected'])
        self.assertEqual(result.fact_id, 'f_selected')
        self.assertEqual(len(model.calls), 1)
        fmt = model.calls[0]['options']['response_format']
        self.assertEqual(fmt['json_schema']['schema']['properties']['fact_id']['enum'], ['f_selected'])
        self.assertEqual(events[0][1]['output_format'], 'json_schema_strict')
        self.assertEqual(events[0][1]['fact_choices'], 1)
        self.assertNotIn('"properties"', model.calls[0]['messages'][0].content)  # Schema is an API parameter.

    def test_tool_loop_retains_format_after_budget_is_spent(self):
        reads = []

        def read(provision_id: str) -> dict:
            """Read synthetic data."""
            reads.append(provision_id)
            return {'text': 'Synthetic source.'}

        model = Scripted([
            AIMessage(content='', tool_calls=[call('read', {'provision_id': 'p1'}, 'one')]),
            AIMessage(content='{"answer":"done"}')])
        result, _ = self.ask(model, tools=[read], budget=1)
        self.assertEqual(result.answer, 'done')
        self.assertEqual(reads, ['p1'])
        self.assertEqual([c['bound'] for c in model.calls], [True, False])
        self.assertTrue(all(c['options']['response_format']['json_schema']['strict'] for c in model.calls))
        self.assertEqual(model.calls[1]['messages'][-1].tool_call_id, 'one')

    def test_refusals_and_incomplete_responses_are_not_retried_or_accepted(self):
        replies = [
            AIMessage(content='', additional_kwargs={'refusal': 'Declined.'}),
            AIMessage(content=[{'type': 'refusal', 'refusal': 'Declined.'}]),
            AIMessage(content='{"answer":"partial"}', response_metadata={'status': 'incomplete'}),
            AIMessage(content='{"answer":"partial"}', response_metadata={'finish_reason': 'length'}),
        ]
        for reply in replies:
            with self.subTest(reply=reply.content, metadata=reply.response_metadata):
                model = Scripted([reply])
                result, events = self.ask(model)
                self.assertIsNone(result)
                self.assertEqual(len(model.calls), 1)
                self.assertFalse(any(kind == 'llm_retry' for kind, _ in events))
                self.assertFalse(events[-1][1]['ok'])

    def test_openai_has_no_silent_prompt_fallback_on_an_api_error(self):
        model = Scripted([])
        with patch.object(model, 'respond', side_effect=RuntimeError('Unsupported strict schema')) as invoke:
            result, events = self.ask(model)
        self.assertIsNone(result)
        self.assertEqual(invoke.call_count, 1)
        self.assertIn('Unsupported strict schema', events[-1][1]['error'])

    def test_missing_catalogue_fails_before_invocation(self):
        model = Scripted([])
        result, events = self.ask(model, FactRef)
        self.assertIsNone(result)
        self.assertFalse(model.calls)
        self.assertIn('needs supplied fact_ids', events[-1][1]['error'])

    def test_strict_json_rejects_trailing_text_and_keeps_bounded_retry(self):
        model = Scripted([AIMessage(content='{"answer":"bad"} extra'), AIMessage(content='{"answer":"good"}')])
        result, events = self.ask(model)
        self.assertEqual(result.answer, 'good')
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(sum(kind == 'llm_retry' for kind, _ in events), 1)
        self.assertTrue(all(c['options']['response_format']['json_schema']['strict'] for c in model.calls))

    def test_other_providers_keep_prompt_json_without_openai_parameters(self):
        model = Scripted([AIMessage(content='```json\n{"answer":"legacy"}\n```')])
        result, events = self.ask(model, provider='anthropic:offline')
        self.assertEqual(result.answer, 'legacy')
        self.assertFalse(model.calls[0]['options'])
        self.assertIn('"properties"', model.calls[0]['messages'][0].content)
        self.assertEqual(events[0][1]['output_format'], 'prompt_json')


class CallerCatalogueTests(unittest.TestCase):
    run_fake = test_v9.RuntimeTests.run_fake

    def test_every_phase_supplies_the_same_real_catalogue_without_extra_calls(self):
        calls, reviews = [], []
        original = llm.ask

        def capture(agent, purpose, schema, system, user, **options):
            catalogue = options['fact_ids']
            expected = set(passages.input_passages(case_input))
            self.assertEqual(set(catalogue), expected)
            quotes = options.get('quote_ids', ())
            fmt = llm.response_format(schema, catalogue, quotes)
            if schema in (Assessment, GdprAssessment):
                self.assertTrue(quotes)
                self.assertEqual(set(fmt['json_schema']['schema']['$defs']['LegalQuoteId']['enum']), set(quotes))
                for q, passage in quotes.items():
                    self.assertIn(f"[{q}] {passage['text']}", user)
            for node in nodes(fmt['json_schema']['schema']):
                if 'fact_id' in node.get('properties', {}):
                    self.assertEqual(set(node['properties']['fact_id']['enum']), expected)
            calls.append((agent, schema))
            return original(agent, purpose, schema, system, user, **options)

        def fake(agent, schema, system, user):
            answer = test_v9.fake_model(agent, schema, system, user)
            if agent == 'gdpr_specialist' and sum(a == agent for a, _ in calls) == 1:
                answer.national_law_requests = [NationalLawRequest(
                    country='IE', requirement='gdpr.special_category_condition',
                    question='Synthetic Irish dependency.', gdpr_provisions=['GDPR Art. 9'])]
            if schema is SupervisorAction:
                reviews.append(True)
                if len(reviews) == 1:
                    return SupervisorAction(action='delegate', target='gdpr_specialist',
                                            question_ids=['gdpr.lawful_basis'], instruction='Synthetic focused revision.')
            return answer

        given = test_v9.load()
        from app.case import fact_document, new_case
        case_input = fact_document(new_case(given, agents.derive_facts(given)))
        with (patch.object(agents, 'ask', side_effect=capture), patch.object(supervisor, 'ask', side_effect=capture)):
            result, events = self.run_fake(fake, given)
        self.assertEqual(len(calls), 8)  # Existing initial, national and targeted-review phases.
        self.assertEqual(sum(e['kind'] == 'llm_request' for e in events), 8)
        self.assertIn(('local_law_IE', Assessment), calls)
        self.assertIn(('supervisor', SupervisorPlan), calls)
        self.assertIn(('supervisor', SupervisorAction), calls)
        self.assertEqual(result['decision'], 'needs_review')
        self.assertTrue(all(f['status'] == 'insufficient_information' for f in result['findings']))


class QuoteToolTests(unittest.TestCase):
    setUp = test_traversal.AssessTests.setUp
    finding_json = test_traversal.AssessTests.finding_json
    run_assess = test_traversal.AssessTests.run_assess

    def test_quote_choices_grow_only_with_displayed_pages_through_budget_boundary(self):
        import json

        self.extra = next(pid for pid, provision in kb.provisions().items()
                          if provision['regime'] == 'HIPAA' and pid not in self.sources
                          and len(passages.provision_passages(pid)) > 2)
        selected = passages.provision_passages(self.extra)
        self.assertGreater(len(selected), 2)
        response = json.loads(self.finding_json())
        response['findings'][0]['quote_id'] = selected[1]['quote_id']
        with (patch.object(llm, 'FAKE_MODEL', None),
              patch.object(llm, 'model_name', return_value='openai:offline'),
              patch.object(traversal, 'MAX_TEXT', 1),
              patch.object(traversal, 'MAX_TOOL_CALLS', 2)):
            model, output = self.run_assess([
                AIMessage(content='', tool_calls=[call('read_provision', {'provision_id': self.extra}, 'one')]),
                AIMessage(content='', tool_calls=[call('read_provision', {'provision_id': self.extra, 'start': 1}, 'two')]),
                AIMessage(content=json.dumps(response))])
        choices = [set(c['options']['response_format']['json_schema']['schema']['$defs']['LegalQuoteId']['enum'])
                   for c in model.calls]
        self.assertNotIn(selected[0]['quote_id'], choices[0])
        self.assertEqual(choices[1] - choices[0], {selected[0]['quote_id']})
        self.assertEqual(choices[2] - choices[1], {selected[1]['quote_id']})
        self.assertNotIn(selected[2]['quote_id'], choices[2])
        self.assertEqual([c['bound'] for c in model.calls], [True, True, False])
        self.assertEqual(output['findings'][0]['quote'], selected[1]['text'])
