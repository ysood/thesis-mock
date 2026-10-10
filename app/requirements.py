"""Fixed coverage catalogue and direct display of specialist-owned requirement statuses."""

import hashlib
import json
from functools import lru_cache

from app.case import evidence_by_id
from app.knowledge import ROOT, provisions, resolve
from app.schema import PlanQuestion

FROM_FINDING = {'not_satisfied': 'unmet', 'insufficient_information': 'undetermined',
                'satisfied_if_verified': 'met', 'not_applicable': 'not_applicable'}


@lru_cache
def catalogue():
    return json.loads((ROOT / 'reference' / 'requirements.json').read_text())


def items(regime):
    return [r for r in catalogue()['requirements'] if r['regime'] == regime]


def applicability_key(regime):
    return items(regime)[0]['key']


def source_ids(question_id):
    """Starting provisions for a fixed review question, not graph predicates."""
    item = next(item for item in catalogue()['requirements'] if item['key'] == question_id)
    allowed = [pid for pid, law in provisions().items() if law['regime'] == item['regime']]
    chosen = []
    for anchor in item['anchors']:
        hits = resolve(anchor, allowed)
        if not hits:
            raise ValueError(f'No {item["regime"]} source matches checklist anchor {anchor}.')
        chosen += [pid for pid in hits if pid not in chosen]
    return chosen


def plan_questions(regime, plan=None):
    return [PlanQuestion(question_id=i['key'], question=i['question'], search_query='', provision_ids=i['anchors'],
                         requirement_class=i['class'], class_reason=i['class_reason']) for i in items(regime)]


def checklist_text(questions, evidence=True):
    typical = {i['key']: i['evidence'] for i in catalogue()['requirements']} if evidence else {}
    return '\n'.join(f"- [{q.question_id}] ({getattr(q, 'requirement_class', 'delegated')}) {q.question}"
                     + (f" Typical evidence: {', '.join(typical[q.question_id])}." if q.question_id in typical else '')
                     for q in questions)


def request_id(key, evidence):
    digest = hashlib.sha1(evidence['description'].strip().lower().encode()).hexdigest()[:6]
    return f"{key}/{evidence['evidence_type']}/{digest}"


def build_records(case, findings):
    records = []
    evidence = evidence_by_id(case)
    for branch in case['specialists'].values():
        main = [f for f in branch['findings'] if f['agent'] in ('gdpr_specialist', 'hipaa_specialist')]
        regime = 'GDPR' if any(f['agent'] == 'gdpr_specialist' for f in main) else 'HIPAA'
        # Failed branches still retain their full assigned checklist for the report.
        if not main:
            regime = branch['coverage'][0]['regime']
        for item in items(regime):
            members = [f for f in findings if item['key'] in f.get('question_ids', [])]
            finding = members[0] if len(members) == 1 else None
            requests = [{**e, 'request_id': request_id(item['key'], e)} for e in (finding or {}).get('evidence_requests', [])]
            records.append({'key': item['key'], 'title': item['title'], 'regime': regime, 'class': item['class'],
                            'class_reason': item['class_reason'], 'question_ids': [item['key']],
                            'status': FROM_FINDING[finding['status']] if finding else 'undetermined',
                            'evidence': requests, 'evidence_status': 'outstanding' if requests else 'none',
                            'supporting_evidence': [evidence[i] for i in (finding or {}).get('evidence_ids', []) if i in evidence],
                            'finding_ids': [f['finding_id'] for f in members],
                            'obligation_scope': (finding or {}).get('obligation_scope', 'transfer'),
                            'actions': (finding or {}).get('required_actions', []) + (finding or {}).get('missing_information', []),
                            'note': '' if finding else 'No unique specialist answer; see coverage checks.'})
    return records


def is_gate(record):
    return record['class'] == 'gate'


def evidence_template(records, inputs):
    """A fill-in template in the current evidence schema; it is not evidence yet."""
    transfer = inputs['transfer']
    parties = {'sender': [transfer['sender']], 'recipient': [transfer['recipient']],
               'both': [transfer['sender'], transfer['recipient']]}
    return [{'id': e['request_id'], 'kind': e['evidence_type'], 'title': e['description'], 'between': parties[e['from_party']],
             'summary': '', 'attested_by': ''} for r in records if is_gate(r) for e in r['evidence']]


def outcome(records):
    lines = []
    for regime in dict.fromkeys(r['regime'] for r in records):
        mine = [r for r in records if r['regime'] == regime]
        parts = [f"{s} ({sum(r['status'] == s for r in mine)})"
                 for s in ('met', 'unmet', 'undetermined', 'not_applicable')]
        lines.append(f"{regime}: " + '; '.join(parts))
    return lines
