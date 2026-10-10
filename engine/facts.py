"""Input fact passages: stable IDs bound to exact input text (same scheme as app/passages.py)."""

import hashlib
import json
import re

from pydantic import BaseModel

from engine.schema import FactRef

VERSION = 'input-passages-v1'


def passages(document):
    """Label scalar input spans, one sentence each, so a selected fact cannot drop a negation."""
    result = {}

    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, path + '/' + str(key).replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f'{path}/{index}')
        elif value is not None and value != '':
            source = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            offset = 0
            for unit in re.split(r'(?<=[.!?])(?=\s+[A-Z])', source):
                text = unit.strip()
                offset += len(unit)
                if text:
                    fact_id = 'f_' + hashlib.sha256(f'{VERSION}\0{path}\0{text}'.encode()).hexdigest()[:12]
                    result[fact_id] = {'fact_id': fact_id, 'path': path, 'text': text}

    visit(document, '')
    return result


def render(offered):
    lines, previous = [], None
    for p in offered.values():
        if p['path'] != previous:
            lines.append(p['path'])
            previous = p['path']
        lines.append(f"  [{p['fact_id']}] {p['text']}")
    return '\n'.join(lines)


def bind(value, offered):
    """Copy path/text from the offered ID, never from model wording; unknown IDs stay empty."""
    if isinstance(value, FactRef):
        selected = offered.get(value.fact_id)
        return value.model_copy(update={'path': selected['path'] if selected else '',
                                        'quote': selected['text'] if selected else ''})
    if isinstance(value, BaseModel):
        return value.model_copy(update={n: bind(getattr(value, n), offered) for n in type(value).model_fields})
    if isinstance(value, list):
        return [bind(item, offered) for item in value]
    return value
