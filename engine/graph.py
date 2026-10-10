"""Optional graph support: the generated normative graph as hints on kg_node and read_provision.

KG_GRAPH=runtime (default) gives agents only the citation graph built from the prose (corpus.py).
KG_GRAPH=generated also attaches, to every provision an agent inspects or reads, what the generated
graph in kg/generated_graph.json holds about it: the requirements, routes, conditions and exceptions
built from it, effects of other corpora's provisions on it (fills an opening, adds a condition,
restricts a route...), and interactions with other jurisdictions' law.

The graph was generated offline from the same corpora (sandbox/kg_mockgen, LLM-proposed, guardrail-
checked, then human-reviewed; see kg/README.md). It is a map, not law: hints are never citable and
are labelled so. Detail of a corpus's own nodes is shown only for provisions in the agent's scope;
for provisions elsewhere, only the cross-corpus pointers. No legal content is written here.
"""

import json
import os
from collections import defaultdict
from functools import lru_cache

from engine import corpus

MODE = os.environ.get('KG_GRAPH', 'runtime')  # 'runtime' | 'generated'
PATH = corpus.ROOT / 'kg' / 'generated_graph.json'
MAX_CONDITIONS = 8
NOTE = ('Hints from a pre-built map of the law (generated offline, reviewed). Not law and not citable: '
        'read the provisions to confirm, and decide from the text.')

PROMPT = (' GRAPH: kg_node and read_provision also return graph_hints for each provision: the requirement, '
          'its routes (alternatives), conditions and exceptions built from it, effects of other corpora\'s provisions '
          'on it, and interactions with other jurisdictions\' law. Use them to check you have not missed a route, '
          'an exception, a cumulative condition or another law\'s effect. They are not law and not citable.')


def enabled():
    return MODE == 'generated' and PATH.exists()


@lru_cache
def load():
    return json.loads(PATH.read_text())


def _provisions(sources):
    return {s['provision'] for s in sources}


@lru_cache
def _index():
    g = load()
    conds = {c['id']: c for c in g['conditions']}
    by_prov, node_provs, owner = defaultdict(list), {}, {}
    for q in g['requirements']:
        provs = _provisions(q['sources'])
        node_provs[q['id']] = provs
        for p in provs:
            by_prov[p].append(('requirement', q['id']))
        for r in (q['routes'] or {}).get('items', []):
            node_provs[r['id']] = _provisions(r['sources'])
            owner[r['id']] = q
            for p in node_provs[r['id']]:
                by_prov[p].append(('route', r['id']))
    for c in g['conditions']:
        node_provs[c['id']] = _provisions(c['sources'])
        for p in node_provs[c['id']]:
            by_prov[p].append(('condition', c['id']))
    reqs = {q['id']: q for q in g['requirements']}
    return conds, reqs, owner, by_prov, node_provs


def _conditions(node, conds, depth=0):
    out = []
    for field, label in (('scoped_by', 'only if'), ('requires', 'requires')):
        for cid in node.get(field, []):
            c = conds.get(cid)
            if c:
                out.append(f'{label}: {c["statement"]}')
                if depth == 0:
                    out += [f'  {line}' for line in _conditions(c, conds, 1)]
    for e in node.get('excepted_by', []):
        c = conds.get(e['node'])
        out.append(f'except where: {c["statement"] if c else e["node"]} ("{e["source"]["quote"]}")')
    return out


def _route(r, conds):
    return {'route': r['label'], 'statement': r['statement'], 'conditions': _conditions(r, conds)}


def _requirement(q, conds):
    out = {'requirement': q['title'], 'class': q['cls'], 'statement': q['statement'], 'conditions': _conditions(q, conds)}
    if q['routes']:
        out['routes_any_one_suffices'] = [_route(r, conds) for r in q['routes']['items']]
    return out


def about(pid, scope):
    """Graph hints for one provision, or None when the graph is off or says nothing about it."""
    if not enabled():
        return None
    g = load()
    conds, reqs, owner, by_prov, node_provs = _index()
    corpus_of = corpus.provisions()[pid]['corpus']
    hints = {}
    if corpus_of in scope:
        shown, nodes = set(), []
        for kind, nid in by_prov.get(pid, []):
            if kind == 'requirement' and nid not in shown:
                nodes.append(_requirement(reqs[nid], conds))
                shown |= {nid, *[r['id'] for r in (reqs[nid]['routes'] or {}).get('items', [])]}
        for kind, nid in by_prov.get(pid, []):
            if kind == 'route' and nid not in shown:
                q = owner[nid]
                route = next(r for r in q['routes']['items'] if r['id'] == nid)
                nodes.append({'route_of': q['title'], **_route(route, conds)})
                shown.add(nid)
        loose = [conds[nid]['statement'] for kind, nid in by_prov.get(pid, []) if kind == 'condition']
        if nodes:
            hints['built_from_this_provision'] = nodes
        elif loose:
            hints['conditions_quoting_this_provision'] = loose[:MAX_CONDITIONS]
    effects = []
    for l in g['links']:
        target_provs = node_provs.get(l['target_node'], set())
        if pid in target_provs and l['source_provision'] != pid:
            effects.append({'relation': l['relation'], 'by': l['source_provision'],
                            'jurisdiction': corpus.manifests()[l['source_corpus']]['name'],
                            'effect': l['statement'], 'when': l['when']})
        elif l['source_provision'] == pid:
            on = sorted(target_provs)
            effects.append({'relation': l['relation'], 'on': on, 'effect': l['statement'], 'when': l['when']})
    if effects:
        hints['cross_corpus_effects'] = effects
    inter = []
    for x in g['interactions']:
        for here, there in (('a', 'b'), ('b', 'a')):
            mine = x[here]['provision'] == pid or pid in node_provs.get(x[here]['node'], set())
            if mine:
                other = x[there]['provision']
                inter.append({'relation': x['relation'], 'with': other,
                              'jurisdiction': corpus.manifests()[corpus.provisions()[other]['corpus']]['name'],
                              'effect': x['statement'], 'when': x['when']})
                break
    if inter:
        hints['other_jurisdictions'] = inter
    return {'note': NOTE, **hints} if hints else None
