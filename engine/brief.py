"""Reviewer brief: known / required / missing / routes / conflicts. Copies verified findings; infers nothing."""


def blocking(f):
    return f['kind'] == 'gate' and f['status'] in ('unmet', 'undetermined')


def build(findings, questions, final_review, offered):
    known = {}
    for f in findings:
        for x in f['facts']:
            if x['quote']:
                entry = known.setdefault(x['fact_id'], {'fact_id': x['fact_id'], 'path': x['path'],
                                                        'text': x['quote'], 'used_by': []})
                if f['ref'] not in entry['used_by']:
                    entry['used_by'].append(f['ref'])

    required = [{'ref': f['ref'], 'title': f['title'], 'kind': f['kind'], 'status': f['status'],
                 'blocking': blocking(f), 'citations': f['resolved_citations'], 'quote': f['quote'],
                 'verified': f['verified'], 'source': f['source']} for f in findings]
    required.sort(key=lambda r: (not r['blocking'], r['kind'] != 'gate', r['ref']))

    missing = []
    for f in findings:
        def add(kind, text):
            missing.append({'kind': kind, 'requirement': f['ref'], 'blocking': blocking(f), 'description': text})
        for text in f['missing_facts']:
            add('fact', text)
        for text in f['missing_evidence']:
            add('evidence', text)
        if f['open_dependency']:
            add('other_law', f['open_dependency'])
        for text in f['confirmations']:
            add('confirm', text)
        for text in f['issues']:
            add('reference_defect', text)
    missing += [{'kind': 'open_question', 'requirement': f"{q['from']}:{q['requirement_id']}", 'blocking': True,
                 'description': q['question']} for q in questions.values() if q['status'] != 'answered']
    missing += [{'kind': 'review', 'requirement': '', 'blocking': True, 'description': u}
                for u in (final_review.unresolved if final_review else ['Supervisor review did not complete.'])]
    missing.sort(key=lambda m: not m['blocking'])

    routes = [{'requirement': f['ref'], 'status': f['status'], 'blocking': blocking(f),
               'routes': [{k: r[k] for k in ('name', 'status', 'reasoning', 'resolved_citations', 'quote')}
                          for r in f['routes']],
               'to_close': f['required_actions']}
              for f in findings if f['status'] != 'not_applicable' and (f['routes'] or f['required_actions'])]
    routes.sort(key=lambda r: not r['blocking'])

    conflicts = [c.model_dump() for c in final_review.conflicts] if final_review else []
    return {'known': list(known.values()), 'required': required, 'missing': missing, 'routes': routes,
            'conflicts': conflicts}
