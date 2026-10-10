"""The one place that talks to the language model, plus the event trace.

Every agent calls ask(). OpenAI calls enforce the existing Pydantic response
shape through strict JSON Schema, with fact and quote IDs restricted to supplied
passages. Other providers keep prompt-based JSON. Python still validates
answers and checks sources downstream. Every request and reply is traced.
"""

import json
import os
import re
import time
from copy import deepcopy
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

# Set by tests to replace the real model: fake(agent, schema, system, user) -> object
FAKE_MODEL = None


def emit(kind, agent, **data):
    """Send a trace event to whoever is streaming the graph (UI or CLI)."""
    event = {"time": round(time.time(), 3), "kind": kind, "agent": agent, **data}
    try:
        from langgraph.config import get_stream_writer
        get_stream_writer()(event)
    except Exception:
        pass  # called outside a running graph: nothing is listening
    return event


# Which configured model to use: "luna" (MODEL, the default) or "haiku" (HAIKU_MODEL). The UI sets this.
CHOICE = "luna"


def model_name():
    return os.environ.get("HAIKU_MODEL") if CHOICE == "haiku" else os.environ.get("MODEL")


def model():
    return _model(model_name())


def tool_model():
    """The model for tool-using calls. OpenAI reasoning models only accept function tools together
    with reasoning_effort on the Responses API, so tool loops use it from first call to last."""
    return _model(model_name(), responses=True)


@lru_cache
def _model(name, responses=False):
    from langchain.chat_models import init_chat_model

    if not name:
        raise RuntimeError("Set MODEL in .env, e.g. MODEL=openai:gpt-5.6-luna")
    options = {"max_tokens": int(os.environ.get("MAX_TOKENS", "16000"))}
    if os.environ.get("TEMPERATURE"):  # reasoning models reject sampling parameters
        options["temperature"] = float(os.environ["TEMPERATURE"])
    if name.startswith("openai:"):  # favour accuracy over speed by default
        options["reasoning_effort"] = os.environ.get("REASONING_EFFORT", "high")
        if responses:
            options["use_responses_api"] = True
    return init_chat_model(name, **options)


def reply_text(message):
    return str(message.text)  # in LangChain 1.x .text is a string property


def parse_json(text):
    """The first JSON object in a reply, tolerating ```json fences, surrounding prose or trailing text.

    run2201: a Responses API reply had text after the object ("Extra data"), which json.loads rejects.
    """
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object in reply.")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def inline_ref(node, shape):
    """Replace a $ref that has sibling keys with the referenced definition, keeping the siblings.

    OpenAI rejects siblings on a $ref (Pydantic adds field descriptions).
    """
    ref = node['$ref']
    if not ref.startswith('#/'):
        raise ValueError(f'Unsupported schema reference: {ref}')
    resolved = shape
    for part in ref[2:].split('/'):
        resolved = resolved[part.replace('~1', '/').replace('~0', '~')]
    expanded = {**deepcopy(resolved), **node}
    expanded.pop('$ref')
    node.clear()
    node.update(expanded)


def quote_choice(field):
    """A quote_id field restricted to the shared LegalQuoteId enum; findings may also leave it empty."""
    selection = [{'$ref': '#/$defs/LegalQuoteId'}]
    if not field.get('minLength', 0):  # Findings may omit a quote; routes may not.
        selection.append({'type': 'string', 'enum': ['']})
    return {**{k: v for k, v in field.items() if k in ('title', 'description')}, 'anyOf': selection}


def response_format(schema, fact_ids=(), quote_ids=()):
    """Adapt a fresh response schema for OpenAI strict output, without changing saved models.

    All object fields are required; nullable fields retain their existing null union.
    Unused non-nullable fields are returned as empty lists/strings. A factual reference
    must select from this call's real input IDs, not generate a new string.
    Quote choices are shared by findings/routes to avoid duplicating large enums.
    """
    shape = schema.model_json_schema()
    choices = list(dict.fromkeys(fact_ids or ()))
    quotes = list(dict.fromkeys(quote_ids or ()))
    has_quotes = False

    def adapt(node):
        nonlocal has_quotes
        if isinstance(node, list):
            for child in node:
                adapt(child)
        elif isinstance(node, dict):
            node.pop('default', None)
            if '$ref' in node and len(node) > 1:
                inline_ref(node, shape)
            if node.get('type') == 'object':
                fields = node.get('properties', {})
                node['required'] = list(fields)
                node['additionalProperties'] = False
                if 'fact_id' in fields:
                    if not choices:
                        raise ValueError('A response containing factual references needs supplied fact_ids.')
                    fields['fact_id']['enum'] = choices
                if 'quote_id' in fields:
                    if not quotes:
                        raise ValueError('A response containing legal references needs supplied quote_ids.')
                    fields['quote_id'] = quote_choice(fields['quote_id'])
                    has_quotes = True
            for child in node.values():
                adapt(child)

    adapt(shape)
    if has_quotes:
        shape.setdefault('$defs', {})['LegalQuoteId'] = {'type': 'string', 'enum': quotes}
    return {'type': 'json_schema', 'json_schema': {'name': schema.__name__, 'strict': True, 'schema': shape}}


def response_problem(reply):
    """Refusals and incomplete API responses are execution failures, not malformed legal answers."""
    blocks = reply.content if isinstance(reply.content, list) else []
    if getattr(reply, 'additional_kwargs', {}).get('refusal') or any(
            isinstance(block, dict) and block.get('type') == 'refusal'
            for block in blocks):
        return 'Model refused the response; no assessment was accepted.'
    metadata = getattr(reply, 'response_metadata', {})
    if (metadata.get('status') in ('incomplete', 'failed', 'cancelled')
            or metadata.get('finish_reason') in ('length', 'max_tokens')):
        return 'Model response was incomplete or failed; no assessment was accepted.'
    return None


def run_tools(agent, reply, tools, used, budget):
    """Answer every tool call in a reply (the API requires one result per call). Returns (messages, used)."""
    from langchain_core.messages import ToolMessage

    by_name = {t.__name__: t for t in tools}
    results = []
    for call in reply.tool_calls:
        if used >= budget:
            content = {'error': 'Tool budget exhausted. Reply now with the JSON object.'}
        elif call['name'] not in by_name:
            content = {'error': f"Unknown tool {call['name']}."}
        else:
            used += 1
            try:
                content = by_name[call['name']](**call['args'])
            except Exception as exc:  # a bad argument is reported to the model, not raised
                content = {'error': f'{type(exc).__name__}: {exc}'[:500]}
        results.append(ToolMessage(json.dumps(content, ensure_ascii=False), tool_call_id=call['id']))
    return results, used


def ask(agent, purpose, schema, system, user, tools=None, budget=0, fact_ids=(), quote_ids=()):
    """Ask the model for an object of type `schema`. Returns None if it fails twice.

    Every call is stateless: agents receive what they need in the prompt, never a transcript.
    With tools, the model may call them (at most `budget` times) before giving its JSON reply;
    tool calls and results stay within this one call. quote_ids may be a shared
    passage dictionary that grows as tools display new law.
    """
    strict = (model_name() or '').startswith('openai:')
    emit("llm_request", agent, purpose=purpose, system=system, user=user,
         output_format='scripted' if FAKE_MODEL else 'json_schema_strict' if strict else 'prompt_json',
         response_schema=schema.__name__, fact_choices=len(fact_ids or ()),
         quote_choices=len(quote_ids or ()))

    if FAKE_MODEL:
        result = FAKE_MODEL(agent, schema, system, user)
        emit("llm_response", agent, purpose=purpose, ok=True, output=result.model_dump(), raw="(fake model)")
        return result

    from langchain_core.messages import HumanMessage, SystemMessage

    options = {}
    if strict:
        try:
            options['response_format'] = response_format(schema, fact_ids, quote_ids)
        except ValueError as exc:
            emit('llm_response', agent, purpose=purpose, ok=False, error=str(exc))
            return None
        instructions = ('\n\nReturn a single JSON object matching the API response schema. Return every field; '
                        'use empty lists/strings when unused and null only where allowed. '
                        'Select fact and quote IDs from the supplied choices.')
    else:
        instructions = ('\n\nReply with a single JSON object and nothing else. It must match this JSON schema:\n'
                        + json.dumps(schema.model_json_schema()))
    messages = [SystemMessage(system + instructions), HumanMessage(user)]
    error = None
    used = 0
    for attempt in (1, 2):
        started = time.time()
        reply, raw = None, ""
        try:
            chat = tool_model() if tools else model()
            def invoke(with_tools):
                if strict:  # Tool reads may have added selectable passages since the last invocation.
                    options['response_format'] = response_format(schema, fact_ids, quote_ids)
                bound = chat.bind_tools(tools, **options) if with_tools else chat.bind(**options) if options else chat
                return bound.invoke(messages)

            reply = invoke(bool(tools))
            while tools and getattr(reply, 'tool_calls', None):
                if error := response_problem(reply):
                    break
                results, used = run_tools(agent, reply, tools, used, budget)
                messages += [reply] + results
                # Once the budget is spent, ask without tools so the model must answer.
                reply = invoke(used < budget)
            raw = reply_text(reply)
            if error := response_problem(reply):
                break
            result = schema.model_validate(json.loads(raw) if strict else parse_json(raw))
            emit("llm_response", agent, purpose=purpose, ok=True, attempt=attempt,
                 seconds=round(time.time() - started, 1), output=result.model_dump(), raw=raw,
                 usage=getattr(reply, "usage_metadata", None), tool_calls=used)
            return result
        except (ValueError, ValidationError) as exc:  # bad JSON or wrong shape: retry once
            error = str(exc)[:1500]
            if reply is None:  # the call itself failed, not the reply
                break
            emit("llm_retry", agent, purpose=purpose, attempt=attempt, error=error, raw=raw[:6000])
            messages += [reply, HumanMessage(f"Your reply was not valid. Error:\n{error}\nReply again with only the JSON object.")]
        except Exception as exc:  # API error, missing key, etc.
            error = f"{type(exc).__name__}: {exc}"[:1500]
            break
    emit("llm_response", agent, purpose=purpose, ok=False, error=error, raw=raw)
    return None
