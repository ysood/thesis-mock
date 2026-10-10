"""Source-bound legal and input passages for model selection, separate from embedding chunks."""

import hashlib
import json
import re

from pydantic import BaseModel

from app import knowledge as kb
from app.schema import FactRef

PASSAGE_VERSION = 'legal-quotes-v2'
FACT_PASSAGE_VERSION = 'input-passages-v1'


def input_passages(document):
    """Label exact scalar spans, keeping sentences whole so copying cannot drop negations.

    Empty/null/container values are not evidence passages. Booleans and numbers remain
    selectable. IDs bind text, offsets and the escaped JSON pointer to this input snapshot.
    """
    result = {}

    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                escaped = str(key).replace('~', '~0').replace('/', '~1')
                visit(child, path + '/' + escaped)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, path + '/' + str(index))
        elif value is not None:
            source = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            offset = 0
            for unit in re.split(r'(?<=[.!?])(?=\s+[A-Z])', source):
                text = unit.strip()
                start = offset + len(unit) - len(unit.lstrip())
                end = start + len(text)
                offset += len(unit)
                if not text:
                    continue
                key = f'{FACT_PASSAGE_VERSION}\0{path}\0{start}\0{end}\0{text}'
                fact_id = 'f_' + hashlib.sha256(key.encode()).hexdigest()[:20]
                result[fact_id] = {'fact_id': fact_id, 'path': path, 'start': start, 'end': end, 'text': text}

    visit(document, '')
    return result


def render_input(offered):
    lines, previous = [], None
    for p in offered.values():
        if p['path'] != previous:
            lines.append(p['path'])
            previous = p['path']
        lines.append(f"[{p['fact_id']}] {p['text']}")
    return '\n'.join(lines)


def bind_fact_references(value, offered):
    """Copy path/text as one pair from an offered ID, never from model-generated wording.

    Return fresh model objects. An unknown ID retains an empty path/quote so existing
    reference checks reject it without guessing a replacement or changing a conclusion.
    """
    if isinstance(value, FactRef):
        selected = offered.get(value.fact_id)
        return value.model_copy(update={'path': selected['path'] if selected else '',
                                        'quote': selected['text'] if selected else ''})
    if isinstance(value, BaseModel):
        return value.model_copy(update={name: bind_fact_references(getattr(value, name), offered)
                                        for name in type(value).model_fields})
    if isinstance(value, list):
        return [bind_fact_references(item, offered) for item in value]
    return value


def quote_units(source):
    """Keep retained paragraphs and numbered blocks whole, without a word cap.

    A colon-led numbered list stays with its introduction. Ambiguous/unmarked
    structure remains intact rather than guessing a hierarchy or cutting sentences.
    """
    for paragraph in re.split(r'(?<=\n)(?=\s*\n)', source):
        parts = [p for p in re.split(r'(?=^(?:\d+\.(?=\s)|\(\d+\)(?=\s)))',
                                    paragraph, flags=re.M) if p]
        if parts and parts[0].rstrip().endswith(':'):
            yield paragraph
        else:
            yield from parts


def provision_passages(provision_id):
    """Label exact structural source spans independently of embedding windows."""
    source = kb.provisions()[provision_id]['text']
    units = quote_units(source)
    passages, offset = [], 0
    for unit in units:
        text = unit.strip()
        start = offset + len(unit) - len(unit.lstrip())
        end = start + len(text)
        offset += len(unit)
        if not text:
            continue
        key = f'{PASSAGE_VERSION}\0{provision_id}\0{start}\0{end}\0{text}'
        quote_id = 'q_' + hashlib.sha256(key.encode()).hexdigest()[:20]
        passages.append({'quote_id': quote_id, 'provision_id': provision_id,
                         'start': start, 'end': end, 'text': text})
    return passages


def offered_passages(ids):
    return {p['quote_id']: p for pid in ids for p in provision_passages(pid)}


def render(passages):
    """Show every span once, labelled with the ID the specialist can select."""
    return '\n'.join(f"[{p['quote_id']}] {p['text']}" for p in passages)


def copy_quote(finding, offered):
    """Resolve only an offered ID from a cited provision. Never accept generated quote text."""
    result = {**finding, 'quote': ''}
    if 'routes' in finding:
        result['routes'] = [copy_quote(route, offered) for route in finding['routes']]
    quote_id = finding.get('quote_id', '')
    if not quote_id:
        return result
    passage = offered.get(quote_id)
    if passage is None:
        result['quote_selection_error'] = f'Quote ID was not shown to this agent: {quote_id}.'
    elif passage['provision_id'] not in {
            p for citation in finding['citations'] for p in kb.resolve(citation, kb.provisions())}:
        result['quote_selection_error'] = 'Quote ID belongs to a provision absent from this finding\'s citations.'
    else:
        result['quote'] = passage['text']
    return result
