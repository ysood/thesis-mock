"""Reviewer brief: regroup checked findings as known / required / missing / routes.

Pure presentation over the verified case. It copies specialist-owned fields and
requirement records; it never infers a status, a gap or a route of its own.
"""

from app.requirements import is_gate

OPEN = ('unmet', 'undetermined')


def unique_finding(record, by_id):
    """The record's single answering finding, or None when coverage failed."""
    ids = record['finding_ids']
    return by_id.get(ids[0]) if len(ids) == 1 else None


def blocking(record):
    return is_gate(record) and record['obligation_scope'] == 'transfer' and record['status'] in OPEN


def known(findings):
    facts = {}
    for f in findings:
        for fact in f.get('facts', []):
            if not fact.get('path') or not fact.get('quote'):
                continue  # unresolved fact selections stay in the case record's checks
            entry = facts.setdefault(fact['fact_id'], {'fact_id': fact['fact_id'], 'path': fact['path'],
                                                       'text': fact['quote'], 'used_by': []})
            entry['used_by'] += [q for q in f['question_ids'] if q not in entry['used_by']]
    return list(facts.values())


def required(records, by_id):
    rows = []
    for r in records:
        f = unique_finding(r, by_id)
        rows.append({'key': r['key'], 'title': r['title'], 'regime': r['regime'], 'class': r['class'],
                     'scope': r['obligation_scope'], 'status': r['status'], 'blocking': blocking(r),
                     'citations': (f or {}).get('resolved_citations', []), 'quote': (f or {}).get('quote', ''),
                     'verified': bool(f and f.get('verified')), 'note': r['note']})
    return rows


def missing(records, by_id, gaps):
    items = [{'kind': 'review', 'requirement': '', 'blocking': g['blocking'],
              'description': f"{g['source']}: {g['description']}"} for g in gaps]
    for r in records:
        f = unique_finding(r, by_id) or {}
        block = blocking(r)

        def add(kind, description, **extra):
            items.append({'kind': kind, 'requirement': r['key'], 'blocking': block, 'description': description, **extra})

        for text in f.get('missing_information', []):
            add('fact', text)
        for e in r['evidence']:
            add('evidence', e['description'], evidence_type=e['evidence_type'], from_party=e['from_party'],
                request_id=e['request_id'])
        if f.get('missing_law'):
            add('law', f['missing_law'], stopping_reason=f.get('research_stopping_reason', ''))
        for text in f.get('confirmations', []):
            add('confirm', text)
    return sorted(items, key=lambda i: not i['blocking'])


def routes(records, by_id):
    rows = []
    for r in records:
        f = unique_finding(r, by_id)
        if not f or r['status'] == 'not_applicable':
            continue
        if not (f.get('routes') or f.get('required_actions') or f.get('unmet_fact_paths')):
            continue
        rows.append({'requirement': r['key'], 'status': r['status'], 'blocking': blocking(r),
                     'coverage': f.get('route_coverage', ''),
                     'routes': [{'name': x['name'], 'status': x['status'], 'reasoning': x['reasoning'],
                                 'citations': x.get('resolved_citations', []), 'quote': x.get('quote', '')}
                                for x in f.get('routes', [])],
                     'to_close': f.get('required_actions', []), 'failing_facts': f.get('unmet_fact_paths', [])})
    return sorted(rows, key=lambda row: not row['blocking'])


def build(records, findings, gaps):
    by_id = {f['finding_id']: f for f in findings}
    return {'known': known(findings), 'required': required(records, by_id),
            'missing': missing(records, by_id, gaps), 'routes': routes(records, by_id)}
