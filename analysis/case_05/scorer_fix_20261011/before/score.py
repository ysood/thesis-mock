"""Score a run against its case's answer key.

Agents name their own requirements, so ids change between runs. Findings are matched to key items
by the provisions they cite: the best candidate is the finding whose citations are most focused on
the key's provisions. The scorer reads saved results only; it never calls a model.
"""

import json
import re

from engine import corpus

# Runs saved before the 10 Oct rename use the old corpus names and provision prefixes.
LEGACY = [('APIR ', 'A-REG '), ('VHIA ', 'A1-HIA '), ('CHRA ', 'B-HRA '), ('CRAA ', 'B-RAA '),
          ('"aster', '"region_a'), ('aster:', 'region_a:'), ('aster>', 'region_a>'), ('aster_', 'region_a_'),
          ('"corvel', '"region_b'), ('corvel:', 'region_b:'), ('corvel_', 'region_b_'),
          ('"valdora', '"subregion_a1'), ('valdora:', 'subregion_a1:'), ('valdora_', 'subregion_a1_'),
          ('01_valdora_gp_to_corvel_host', '01_a1_gp_to_region_b_host')]
OPEN = ('unmet', 'undetermined')
RELEVANT = 0.5  # a finding is about the key item when at least half its substantive citations are listed provisions


def modernise(result):
    text = json.dumps(result)
    if 'APIR ' not in text and '"aster' not in text:
        return result
    for old, new in LEGACY:
        text = text.replace(old, new)
    return json.loads(text)


def cites(item):
    return set(item.get('resolved_citations') or [])


def supporting(pid):
    """Definitions and interpretation provisions support many findings; they do not say what a finding is about."""
    p = corpus.provisions().get(pid)
    return bool(p) and bool(re.search(r'Definitions|Interpretation', p['title']))


def substantive(item):
    core = {p for p in cites(item) if not supporting(p)}
    return core or cites(item)


def scored_candidates(findings, provisions):
    """[(focus, finding)] for findings citing any listed provision, most focused first."""
    wanted, found = set(provisions), []
    for f in findings:
        overlap = substantive(f) & wanted
        if overlap:
            found.append((len(overlap) / len(substantive(f)), f))
    return sorted(found, key=lambda pair: -pair[0])


def candidates(findings, provisions):
    return [f for _, f in scored_candidates(findings, provisions)]


def relevant(findings, provisions):
    """Candidates that are about these provisions; at least the best one."""
    scored = scored_candidates(findings, provisions)
    return [f for focus, f in scored if focus >= RELEVANT] or [f for _, f in scored[:1]]


def matching_routes(findings, item):
    hints = [h.lower() for h in item.get('name_hint', [])]
    return [(f, r) for f in findings for r in f['routes']
            if cites(r) & set(item['provisions']) and (not hints or any(h in r['name'].lower() for h in hints))]


def check_requirement(findings, item):
    """Found if some finding cites the provisions; correct if a finding about them has the expected status.
    Other findings about the same provisions that disagree are reported, not hidden."""
    found = relevant(findings, item['provisions'])
    row = {'id': item['id'], 'expect': item['expect'], 'found': bool(found),
           'best': found[0]['ref'] if found else None, 'status': found[0]['status'] if found else None,
           'about': [f['ref'] for f in found]}
    if item.get('all_candidates'):
        found = candidates(findings, item['provisions'])
        row['ok'] = bool(found) and all(f['status'] in item['expect'] for f in found)
        row['status'] = ', '.join(sorted({f['status'] for f in found}))
    else:
        right = [f for f in found if f['status'] in item['expect']]
        row['ok'] = bool(right)
        if right:
            row['best'], row['status'] = right[0]['ref'], right[0]['status']
        disagree = [f"{f['ref']} ({f['status']})" for f in found
                    if f['status'] not in item['expect'] and f['status'] != 'not_applicable']
        if right and disagree:
            row['disagreeing'] = disagree
    missing = [p for p in item.get('must_cite', []) if not any(p in cites(f) for f in findings)]
    if missing:
        row['ok'], row['missing_citation'] = False, missing
    return row


def check_route(findings, item):
    routes = matching_routes(findings, item)
    statuses = [r['status'] for _, r in routes]
    ok = bool(routes) and (all(s in item['expect'] for s in statuses) if item.get('all_routes')
                           else any(s in item['expect'] for s in statuses))
    return {'id': item['id'], 'expect': item['expect'], 'found': bool(routes), 'statuses': statuses, 'ok': ok,
            'where': sorted({f['ref'] for f, _ in routes})}


def check_conflict(findings, conflicts, item):
    by_ref = {f['ref']: f for f in findings}
    hits = [c for c in conflicts
            if set(item['provisions']) & set().union(*[cites(by_ref[r]) for r in c['requirement_refs'] if r in by_ref])]
    return {'id': item['id'], 'found': bool(hits), 'ok': any(c['resolvable'] == item['resolvable'] for c in hits),
            'resolvable': [c['resolvable'] for c in hits]}


def check_question(questions, item):
    asked = [q for q in questions if q['from'] == item['asker'] and q.get('routed_to') == item['answerer']]
    return {'id': item['id'], 'ok': any(q['status'] == 'answered' for q in asked), 'times_asked': len(asked)}


def check_must_not(findings, item):
    if item['type'] == 'route':
        hits = [f"{f['ref']}: {r['name']} ({r['status']})" for f, r in matching_routes(findings, item)
                if r['status'] in item['status']]
    else:
        allowed, needed = set(item['only_cites']), set(item.get('requires_any', item['only_cites']))
        hits = [f"{f['ref']} ({f['status']})" for f in findings
                if cites(f) and cites(f) <= allowed and cites(f) & needed and f['status'] in item['status']]
    return {'id': item['id'], 'violated': bool(hits), 'hits': hits}


def score(result, key):
    result = modernise(result)
    findings = result['findings']
    final = next((r for r in reversed(result.get('reviews') or []) if r), None)
    plan = result.get('plan') or {'engagements': []}
    engaged = {e['corpus']: e['engaged'] for e in plan['engagements']}
    requirements = [check_requirement(findings, i) for i in key['requirements']]
    explained = {ref for row in requirements for ref in row['about']}
    for item in key['requirements']:  # every candidate of an all-candidates item is explained too
        if item.get('all_candidates'):
            explained |= {f['ref'] for f in candidates(findings, item['provisions'])}
    card = {
        'decision': {'expect': key['decision'], 'got': result['decision'],  # one decision, or a list of acceptable ones
                     'ok': result['decision'] in (key['decision'] if isinstance(key['decision'], list) else [key['decision']])},
        'engaged': {'expect': key['engaged'], 'got': engaged,
                    'ok': all(engaged.get(c) == v for c, v in key['engaged'].items())},
        'requirements': requirements,
        'routes': [check_route(findings, i) for i in key.get('routes', [])],
        'conflicts': [check_conflict(findings, final['conflicts'] if final else [], i) for i in key.get('conflicts', [])],
        'questions': [check_question(result.get('questions', []), i) for i in key.get('questions', [])],
        'must_not': [check_must_not(findings, i) for i in key.get('must_not', [])],
        'extra_blocking': [f"{f['ref']} ({f['status']})" for f in findings
                           if f['kind'] == 'gate' and f['status'] in OPEN and f['ref'] not in explained],
        'verified': f"{sum(f['verified'] for f in findings)}/{len(findings)}",
    }
    card['summary'] = summary(card)
    return card


def summary(card):
    count = lambda rows: f"{sum(r['ok'] for r in rows)}/{len(rows)}"
    return {'decision': card['decision']['ok'], 'engaged': card['engaged']['ok'],
            'requirements_found': f"{sum(r['found'] for r in card['requirements'])}/{len(card['requirements'])}",
            'requirements_correct': count(card['requirements']), 'routes_correct': count(card['routes']),
            'conflicts_found': count(card['conflicts']), 'questions_answered': count(card['questions']),
            'traps_violated': sum(r['violated'] for r in card['must_not']),
            'extra_blocking': len(card['extra_blocking']), 'verified': card['verified']}


def cost(events):
    calls = [e for e in events if e['kind'] == 'llm_response']
    out = sum((e.get('usage') or {}).get('output_tokens') or 0 for e in calls)
    span = round(events[-1]['time'] - events[0]['time']) if events else 0
    return {'seconds': span, 'model_calls': len(calls), 'tool_calls': sum(e['kind'] == 'tool_call' for e in events),
            'output_tokens': out}


def case_name(run_path_name):
    """'20261010-164950_01_a1_gp_to_region_b_host.json' -> '01_a1_gp_to_region_b_host' (legacy names mapped)."""
    name = re.sub(r'^\d{8}-\d{6}_', '', run_path_name).rsplit('.', 1)[0]
    return dict((o, n) for o, n in LEGACY if o.startswith('01_')).get(name, name)
