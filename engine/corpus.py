"""Corpus registry: every jurisdiction, instrument and provision comes from corpora/, never from code.

A corpus is a folder with corpus.json (manifest) and markdown instruments whose provisions are
headed "## [ID] Title". The citation graph is read from the prose: "Article 8(3) of the Region A
Regulation", "section 4(2)", "Articles 16 to 19". Nothing here knows what the law says.
"""

import hashlib
import json
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPORA = ROOT / 'corpora'
CHROMA_DIR = ROOT / '.chroma-mock'
WINDOW_CHARS = 800  # MiniLM embeds at most 256 tokens; ~800 characters of statute stays under it
HEADING = re.compile(r'^## \[([^\]]+)\] (.+)$', re.M)
REFERENCE = re.compile(r'\b([Aa]rticles?|[Ss]ections?)\s+(\d+)((?:\([0-9a-z]+\))*)(?:\s+to\s+(\d+))?'
                       r'|\bAnnex\s+(I{1,3})\b')


@lru_cache
def registry():
    return json.loads((CORPORA / 'registry.json').read_text())


@lru_cache
def manifests():
    return {cid: json.loads((CORPORA / cid / 'corpus.json').read_text()) for cid in registry()['corpora']}


def jurisdictions():
    return {j['code']: j for j in registry()['jurisdictions']}


def top_level():
    """Corpora a supervisor can assign directly; regional corpora are reached by delegation."""
    return [cid for cid, m in manifests().items() if not m.get('parent')]


def children(corpus_id):
    return manifests()[corpus_id].get('children', [])


@lru_cache
def provisions():
    """All provisions keyed by ID, in corpus order."""
    found = {}
    for cid, manifest in manifests().items():
        for inst in manifest['instruments']:
            text = (CORPORA / cid / inst['file']).read_text()
            heads = list(HEADING.finditer(text))
            for i, head in enumerate(heads):
                end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
                found[head.group(1)] = {'id': head.group(1), 'title': head.group(2), 'corpus': cid,
                                        'instrument': inst['prefix'], 'text': text[head.end():end].strip()}
    return found


def instrument_aliases():
    """Alias -> instrument prefix, longest alias first so 'Region B Health Records Act' beats 'Health Records Act'."""
    pairs = [(alias, inst['prefix']) for m in manifests().values() for inst in m['instruments'] for alias in inst['aliases']]
    return sorted(pairs, key=lambda p: -len(p[0]))


def instrument_units():
    return {inst['prefix']: m['unit'].lower() for m in manifests().values() for inst in m['instruments']}


def _target_instrument(text, start, end, unit, own, last_other):
    """Which instrument a reference points to: an explicit 'of the <alias>', 'that Regulation/Act',
    the citing instrument when the unit word matches its own, otherwise the nearest earlier-named
    instrument that uses that unit word ('Article 7(2) ... of that Regulation' in an Act)."""
    tail = text[end:end + 80]
    match = re.match(r'\s+of\s+(?:the\s+)?', tail)
    rest = tail[match.end():] if match else ''
    if match and re.match(r'that\s+(Regulation|Act)\b', rest):
        return last_other
    if match and not re.match(r'this\s+(Regulation|Act)\b', rest):
        for alias, prefix in instrument_aliases():
            if rest.startswith(alias):
                return prefix
    units = instrument_units()
    if units[own] == unit:
        return own
    earlier = [(text.rfind(alias, 0, start), prefix) for alias, prefix in instrument_aliases()
               if units[prefix] == unit and text.rfind(alias, 0, start) >= 0]
    return max(earlier)[1] if earlier else last_other


@lru_cache
def citations():
    """Provision ID -> sorted IDs it cites (other provisions only)."""
    ids = provisions()
    graph = {}
    for pid, p in ids.items():
        out, last_other = [], None
        for m in REFERENCE.finditer(p['text']):
            if m.group(5):
                targets = [f"{p['instrument']} Annex {m.group(5)}"]
            else:
                unit = m.group(1).lower().rstrip('s')
                prefix = _target_instrument(p['text'], m.start(), m.end(), unit, p['instrument'], last_other)
                if prefix is None:
                    continue
                if prefix != p['instrument']:
                    last_other = prefix
                first, last = int(m.group(2)), int(m.group(4) or m.group(2))
                targets = [f'{prefix} {n}' for n in range(first, last + 1)]
            out += [t for t in targets if t in ids and t != pid and t not in out]
        graph[pid] = sorted(out, key=list(ids).index)
    return graph


def cited_by(pid):
    return [src for src, targets in citations().items() if pid in targets]


def resolve(ref):
    """'A-REG 8(2)(c)', '[A-REG 8]' or a quote ID 'A-REG 8#L3' -> 'A-REG 8' when it exists, else None."""
    ref = ref.strip().strip('[]').split('#')[0].strip()
    if ref in provisions():
        return ref
    base = re.sub(r'(\([0-9a-z]+\))+$', '', ref)
    return base if base in provisions() else None


def search(query, corpus_ids, k=6):
    """Semantic search (Chroma + MiniLM) within the given corpora: [(id, title, distance)]."""
    if not corpus_ids:
        return []
    where = {'corpus': corpus_ids[0]} if len(corpus_ids) == 1 else {'corpus': {'$in': list(corpus_ids)}}
    best = {}
    for doc, distance in vector_store().similarity_search_with_score(query, k=k * 3, filter=where):
        pid = doc.metadata['provision']
        best[pid] = min(distance, best.get(pid, distance))
    ranked = sorted(best.items(), key=lambda kv: kv[1])[:k]
    return [(pid, provisions()[pid]['title'], round(d, 3)) for pid, d in ranked]


def windows():
    """Embedding chunks: whole passages packed up to WINDOW_CHARS, each prefixed by ID and title."""
    for pid, p in provisions().items():
        heading, chunk, n = f"{pid} {p['title']}\n", '', 0
        for line in passages(pid).values():
            if chunk and len(chunk) + len(line) > WINDOW_CHARS:
                yield {'id': f'{pid}#{n}', 'provision': pid, 'corpus': p['corpus'], 'text': heading + chunk}
                chunk, n = '', n + 1
            chunk += line + '\n'
        yield {'id': f'{pid}#{n}', 'provision': pid, 'corpus': p['corpus'], 'text': heading + chunk}


_store, _store_lock = None, threading.Lock()


def vector_store():
    """Chroma collection over every corpus, rebuilt when the corpus text changes."""
    global _store
    with _store_lock:
        if _store is None:
            from langchain_chroma import Chroma
            store = Chroma(collection_name='mock_laws', persist_directory=str(CHROMA_DIR))
            chunks = list(windows())
            fingerprint = hashlib.sha256(json.dumps(chunks, sort_keys=True).encode()).hexdigest()
            metadata = store._collection.metadata or {}
            if store._collection.count() != len(chunks) or metadata.get('fingerprint') != fingerprint:
                store.reset_collection()
                store.add_texts(texts=[c['text'] for c in chunks], ids=[c['id'] for c in chunks],
                                metadatas=[{'provision': c['provision'], 'corpus': c['corpus']} for c in chunks])
                store._collection.modify(metadata={**metadata, 'fingerprint': fingerprint})
            _store = store
        return _store


def passages(pid):
    """Quotable units: each non-empty line of a provision, ID "<provision>#L<line>" bound to its text.
    The L-number is a line label, never a paragraph number."""
    lines = [line.strip() for line in provisions()[pid]['text'].splitlines() if line.strip()]
    return {f'{pid}#L{i}': line for i, line in enumerate(lines, 1)}


def table_of_contents(corpus_ids):
    return [{'id': pid, 'title': p['title']} for pid, p in provisions().items() if p['corpus'] in corpus_ids]
