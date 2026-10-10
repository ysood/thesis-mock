"""Orchestration: plan -> specialists -> delegation -> supervisor review loop -> verify -> decide -> brief.

Python owns the flow, budgets and checks; agents own every legal judgement. Python never
changes a status: it verifies references and derives the decision from verified statuses.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor

from engine import agents, brief, corpus, facts, llm, tools
from engine.llm import emit
from engine.schema import Case

MAX_REVIEWS = 3


class Run:
    def __init__(self, case):
        self.case = Case.model_validate(case).model_dump()
        self.offered = facts.passages(self.case)
        self.records = {cid: tools.new_record() for cid in corpus.manifests()}
        self.answers = {}         # corpus -> latest SpecialistAnswer
        self.received = {}        # corpus -> answers others gave it (dicts)
        self.extra = {}           # ref -> requirement reported by a delegate/peer (dict)
        self.questions = {}       # ref -> peer question state
        self.log = []             # delegation/routing actions, for the trace

    # -------------------------------------------------------------- steps

    def assess(self, cid, **kwargs):
        emit('stage', f'{cid}_specialist', status='running')
        result = agents.assess(cid, self.case, self.offered, self.records[cid],
                               answers=self.received.get(cid, []), **kwargs)
        emit('stage', f'{cid}_specialist', status='done' if result else 'failed')
        if result:
            self.answers[cid] = result
            self.collect_questions(cid)
        return result

    def collect_questions(self, cid):
        # One question per asker, requirement and jurisdiction: a reassessment that rephrases it is not new.
        known = {(q['from'], q['requirement_id'], q['jurisdiction']) for q in self.questions.values()}
        for q in self.answers[cid].peer_questions:
            if (cid, q.requirement_id, q.jurisdiction) not in known:
                known.add((cid, q.requirement_id, q.jurisdiction))
                ref = f"{cid}:q{sum(x['from'] == cid for x in self.questions.values()) + 1}"
                self.questions[ref] = {'ref': ref, 'from': cid, 'status': 'open', 'answer': None, **q.model_dump()}

    def ask_corpus(self, target, asked_by, items, kind, instruction=''):
        """Put questions (or a supervisor revision) to a corpus specialist; file its answers with each
        asker and keep its extra requirements. A revision replaces the target's earlier extras."""
        prior = [r for r in self.extra.values() if r['corpus'] == target] if instruction else []
        already = [r['title'] for r in self.extra.values() if r['corpus'] == target and not instruction]
        if target in self.answers:
            already += [r.title for r in self.answers[target].requirements]
        name = ', '.join(corpus.manifests()[a]['name'] for a in asked_by)
        for asker in asked_by:
            emit('edge', 'pipeline', source=asker, target=target, relation=kind)
        emit('stage', f'{target}_specialist', status='running')
        result = agents.answer_questions(target, name, items, self.case, self.offered, self.records[target], already,
                                         prior=[{k: r[k] for k in ('id', 'title', 'kind', 'status', 'reasoning')}
                                                for r in prior], instruction=instruction)
        emit('stage', f'{target}_specialist', status='done' if result else 'failed')
        self.log.append({'to': target, 'asked_by': asked_by, 'kind': kind, 'questions': items,
                         'instruction': instruction, 'ok': bool(result)})
        if not result:
            return None
        for r in prior:
            self.extra.pop(r['ref'], None)
        by_id = {i['question_id']: i for i in items}
        for answer in result.answers:
            item = by_id.get(answer.question_id)
            if item:
                self.received.setdefault(item['asker'], []).append({'from': target, 'question': item['question'],
                                                                    **answer.model_dump()})
        for r in result.additional_requirements:
            ref = f'{target}:{r.id}'
            self.extra[ref] = {**r.model_dump(), 'corpus': target, 'ref': ref, 'source': f'reported to {name}'}
        return result

    def delegate(self, cid):
        a = self.answers.get(cid)
        if not a or not a.delegations:
            return
        for child in corpus.children(cid):
            mine = [d for d in a.delegations if d.corpus == child]
            if mine:
                items = [{'question_id': f'{cid}>{child}:d{i}', 'asker': cid, 'requirement_id': d.requirement_id,
                          'question': d.question, 'referring_provisions': d.referring_provisions}
                         for i, d in enumerate(mine, 1)]
                self.ask_corpus(child, [cid], items, 'delegation')
        rejected = [d.corpus for d in a.delegations if d.corpus not in corpus.children(cid)]
        if rejected:
            self.log.append({'rejected_delegations': rejected, 'from': cid})
        self.assess(cid, prior=a)

    def route(self, review):
        """Apply a review: answer routed questions, then reassess askers and revision targets."""
        groups, askers = {}, set()
        for r in review.routings:
            q = self.questions.get(r.question_ref)
            if not q or q['status'] != 'open' or r.to_corpus not in corpus.manifests() or r.to_corpus == q['from']:
                self.log.append({'rejected_routing': r.model_dump()})
                continue
            groups.setdefault(r.to_corpus, []).append({'question_id': q['ref'], 'asker': q['from'],
                                                       'requirement_id': q['requirement_id'], 'question': r.question})
        for target, items in groups.items():
            result = self.ask_corpus(target, sorted({i['asker'] for i in items}), items, 'routing')
            for item in items:
                q = self.questions[item['question_id']]
                q.update(status='answered' if result else 'failed', routed_to=target,
                         answer=next((a.answer for a in (result.answers if result else [])
                                      if a.question_id == q['ref']), None))
                askers.add(q['from'])
        targets, lower = {}, {}
        for r in review.revisions:
            parent = corpus.manifests().get(r.corpus, {}).get('parent')
            if r.corpus in self.answers:
                targets[r.corpus] = (targets.get(r.corpus, '') + '\n' + r.instruction).strip()
            elif parent in self.answers:  # a lower-level corpus: revise its report, then its parent reassesses
                lower[r.corpus] = (lower.get(r.corpus, '') + '\n' + r.instruction).strip()
            else:
                self.log.append({'rejected_revision': r.model_dump()})
        for child, instruction in lower.items():
            parent = corpus.manifests()[child]['parent']
            self.ask_corpus(child, [parent], [], 'revision', instruction=instruction)
            askers.add(parent)
        for cid in sorted(askers | set(targets)):
            self.assess(cid, prior=self.answers[cid], instruction=targets.get(cid, ''))
        return bool(groups or targets or lower)

    # -------------------------------------------------------------- views and checks

    def findings(self):
        found = {}
        for cid, a in self.answers.items():
            for r in a.requirements:
                ref = f'{cid}:{r.id}'
                found[ref] = {**r.model_dump(), 'corpus': cid, 'ref': ref, 'source': 'assessment'}
        for ref, r in self.extra.items():
            found.setdefault(ref, r)
        return [verify(f, self.records[f['corpus']], {e['id'] for e in self.case['evidence']}) for f in found.values()]

    def view(self):
        return {'specialists': {cid: {'applies': a.applies, 'applicability': a.applicability_reasoning,
                                      'coverage_note': a.coverage_note} for cid, a in self.answers.items()},
                'requirements': [{k: f[k] for k in ('ref', 'title', 'kind', 'status', 'reasoning', 'citations',
                                                    'routes', 'open_dependency', 'required_actions', 'issues', 'source')}
                                 for f in self.findings()],
                'open_questions': [q for q in self.questions.values() if q['status'] == 'open'],
                'answered_questions': [q for q in self.questions.values() if q['status'] != 'open'],
                'delegations': self.log}


def verify(f, record, evidence_ids):
    """Reference checks only: facts were supplied, cited law was read, quotes were shown and belong to it."""
    issues = [f"unknown fact {x['fact_id']}" for x in f['facts'] if not x['quote']]
    issues += [f'unknown evidence {e}' for e in f['evidence_ids'] if e not in evidence_ids]

    def check(item, label, quote_required):
        resolved = []
        for c in item['citations']:
            pid = corpus.resolve(c)
            if pid is None:
                issues.append(f'{label} cites unknown provision {c}')
            elif pid not in record['read']:
                issues.append(f'{label} cites {pid}, which this agent did not read')
            else:
                resolved.append(pid)
        item['resolved_citations'], item['quote'] = resolved, ''
        qid = item.get('quote_id', '')
        if qid:
            text = record['passages'].get(qid)
            if text is None:
                issues.append(f'{label} quote {qid} was not shown to this agent')
            elif qid.rsplit('#', 1)[0] not in resolved:
                issues.append(f'{label} quote {qid} is not from a cited provision')
            else:
                item['quote'] = text
        elif quote_required:
            issues.append(f'{label} has no quote')

    check(f, 'requirement', f['status'] in ('met', 'unmet'))
    for route in f['routes']:
        check(route, f"route '{route['name'][:40]}'", True)
    if f['status'] in ('met', 'unmet') and not f['citations']:
        issues.append('a decided requirement cites no law')
    return {**f, 'issues': issues, 'verified': not issues}


def decide(findings, questions, final_review):
    gates = [f for f in findings if f['kind'] == 'gate']
    refusals = [f for f in gates if f['status'] == 'unmet' and f['verified']]
    if refusals:
        return 'do_not_proceed', [f"{f['ref']} ({f['title']}) is unmet as described." for f in refusals]
    holds = [f"{f['ref']}: reference defects ({'; '.join(f['issues'][:2])})" for f in findings if not f['verified']]
    holds += [f"{f['ref']} ({f['title']}) is undetermined." for f in gates if f['status'] == 'undetermined']
    holds += [f"Open question {q['ref']}: {q['question']}" for q in questions.values() if q['status'] != 'answered']
    if final_review:
        holds += [f'Unresolved conflict: {c.description}' for c in final_review.conflicts if not c.resolvable]
        holds += [f'Supervisor: {u}' for u in final_review.unresolved]
    else:
        holds.append('Supervisor review did not complete.')
    if holds:
        return 'needs_review', holds
    conditional = any(f[k] for f in gates for k in ('missing_evidence', 'required_actions', 'confirmations'))
    return ('proceed_subject_to_conditions', ['Gates are met; conditions remain.']) if conditional else \
        ('proceed', ['Every gate is met on the supplied facts.'])


def supervise(call, *args):
    emit('stage', 'supervisor', status='running')
    result = call(*args)
    emit('stage', 'supervisor', status='idle' if result else 'failed')
    return result


def run(case, on_event=None):
    started, events = time.time(), []

    def listen(event):
        events.append(event)
        if on_event:
            on_event(event)

    llm.LISTENER = listen
    try:
        state = Run(case)
        plan = supervise(agents.plan, state.case, state.offered)
        reviews = []
        if plan:
            engaged = [e.corpus for e in plan.engagements if e.engaged and e.corpus in corpus.top_level()]
            emit('plan', 'supervisor', engaged=engaged)
            focus = {e.corpus: e.focus for e in plan.engagements}
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda c: state.assess(c, focus=focus.get(c, '')), engaged))
            for cid in engaged:
                state.delegate(cid)
            for _ in range(MAX_REVIEWS):
                review = supervise(agents.review, state.case, state.offered, state.view())
                reviews.append({'review': review, 'stale': False})
                if review is None or review.action == 'finish' or not state.route(review):
                    break
                reviews[-1]['stale'] = True
            if reviews and reviews[-1]['stale']:  # budget spent after changes: one last look, no actions taken
                reviews.append({'review': supervise(agents.review, state.case, state.offered, state.view()), 'stale': False})
        emit('stage', 'verification', status='running')
        final = reviews[-1]['review'] if reviews else None
        findings = state.findings()
        decision, reasons = decide(findings, state.questions, final)
        result = {'decision': decision, 'reasons': reasons, 'seconds': round(time.time() - started, 1),
                  'plan': plan.model_dump() if plan else None,
                  'specialists': {c: a.model_dump() for c, a in state.answers.items()},
                  'findings': findings, 'questions': list(state.questions.values()), 'delegations': state.log,
                  'reviews': [r['review'].model_dump() if r['review'] else None for r in reviews],
                  'read': {c: r['read'] for c, r in state.records.items() if r['read']},
                  'case': state.case}
        result['brief'] = brief.build(findings, state.questions, final, state.offered)
        emit('decision', 'verification', decision=decision, reasons=reasons)
        emit('stage', 'verification', status='done')
        return result, events
    finally:
        llm.LISTENER = None


def save(result, events, name, folder=corpus.ROOT / 'runs' / 'mock'):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}_{name}.json"
    path.write_text(json.dumps({'model': llm.model_name(), 'tools': tools.ENABLED, 'result': result, 'events': events},
                               indent=1, default=str))
    return path
