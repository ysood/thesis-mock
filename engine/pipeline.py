"""Orchestration: plan -> specialists -> delegation -> supervisor review loop -> verify -> decide -> brief.

Python owns the flow, budgets and checks; agents own every legal judgement. Python never
changes a status: it verifies references and derives the decision from verified statuses.
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from engine import agents, brief, corpus, facts, llm, tools
from engine.llm import emit
from engine.schema import Case

MAX_REVIEWS = 3
MODE = os.environ.get('ARCHITECTURE', 'multi')  # 'single': one agent, one call (baseline for analyses)


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
        asked = [{k: q[k] for k in ('ref', 'jurisdiction', 'question', 'status', 'answer')}
                 for q in self.questions.values() if q['from'] == cid]
        if kwargs.get('prior') is not None:
            kwargs['coverage'] = self.coverage(cid)
        result = agents.assess(cid, self.case, self.offered, self.records[cid],
                               answers=self.received.get(cid, []), asked=asked, **kwargs)
        emit('stage', f'{cid}_specialist', status='done' if result else 'failed')
        if result and kwargs.get('prior') is not None:
            result = merge(kwargs['prior'], result)
        if result:
            self.answers[cid] = result
            self.collect_questions(cid)
            emit('coverage', 'pipeline', corpus=cid, unread=[w['unread'] for w in self.coverage(cid)])
        return result

    def coverage(self, cid):
        """Structural reading gaps from the citation graph: provisions of this corpus that are cited by law the
        agent relied on (its findings' and routes' citations) and that it has never read. Decides nothing."""
        read = set(self.records[cid]['read'])
        own = list(self.answers[cid].requirements) if cid in self.answers else []
        items = [r.model_dump() for r in own] + [r for r in self.extra.values() if r['corpus'] == cid]
        relied = {corpus.resolve(c) for item in items
                  for c in item.get('citations', []) + [x for rt in item.get('routes', []) for x in rt['citations']]}
        warnings, seen = [], set()
        for source in sorted(filter(None, relied & read)):
            for target in corpus.citations()[source]:
                if corpus.provisions()[target]['corpus'] == cid and target not in read and target not in seen:
                    seen.add(target)
                    warnings.append({'unread': target, 'title': corpus.provisions()[target]['title'],
                                     'cited_by': source})
        return warnings

    def collect_questions(self, cid):
        """Register new peer questions. A question that repeats one this asker already put to the same
        jurisdiction (same words mostly, even under a renamed requirement) is not asked again."""
        for q in self.answers[cid].peer_questions:
            earlier = [x['question'] for x in self.questions.values()
                       if x['from'] == cid and x['jurisdiction'] == q.jurisdiction]
            if any(repeats(q.question, e) for e in earlier):
                self.log.append({'repeated_question': q.question, 'from': cid})
                continue
            ref = f"{cid}:q{sum(x['from'] == cid for x in self.questions.values()) + 1}"
            self.questions[ref] = {'ref': ref, 'from': cid, 'status': 'open', 'answer': None, **q.model_dump()}

    def ask_corpus(self, target, asked_by, items, kind, instruction=''):
        """Put questions (or a supervisor revision) to a corpus specialist and file its answers with each asker.
        A lower-level corpus reports its complete set of requirements, which replaces its earlier report, so it is
        always shown that earlier report; a top-level corpus answering a peer question adds only requirements its
        own assessment lacks."""
        lower = bool(corpus.manifests()[target].get('parent'))
        mine = [r for r in self.extra.values() if r['corpus'] == target]
        prior = mine if lower or instruction else []
        current = mine + ([r.model_dump() for r in self.answers[target].requirements] if target in self.answers else [])
        already = [] if lower else [{'id': r['id'], 'title': r['title'], 'kind': r['kind'], 'status': r['status'],
                                     'reasoning': r['reasoning'],
                                     'routes': [{k: rt[k] for k in ('name', 'status', 'reasoning')} for rt in r['routes']]}
                                    for r in current]  # a top-level answer must agree with its current assessment
        name = ', '.join(corpus.manifests()[a]['name'] for a in asked_by)
        for asker in asked_by:
            emit('edge', 'pipeline', source=asker, target=target, relation=kind)
        emit('stage', f'{target}_specialist', status='running')
        result = agents.answer_questions(target, name, items, self.case, self.offered, self.records[target], already,
                                         prior=[{k: r[k] for k in ('id', 'title', 'kind', 'status', 'reasoning')}
                                                for r in prior], instruction=instruction,
                                         coverage=self.coverage(target) if instruction else ())
        emit('stage', f'{target}_specialist', status='done' if result else 'failed')
        self.log.append({'to': target, 'asked_by': asked_by, 'kind': kind, 'questions': items,
                         'instruction': instruction, 'ok': bool(result)})
        if not result:
            return None
        for r in (mine if lower or instruction else []):
            self.extra.pop(r['ref'], None)
        by_id = {i['question_id']: i for i in items}
        for answer in result.answers:
            item = by_id.get(answer.question_id)
            if item:
                law, issues = answer_law(answer.model_dump(), self.records[target], target)
                self.received.setdefault(item['asker'], []).append({'from': target, 'question': item['question'],
                                                                    **answer.model_dump(), 'law': law, 'issues': issues})
        for r in result.requirements:
            ref = f'{target}:{r.id}'
            self.extra[ref] = {**r.model_dump(), 'corpus': target, 'ref': ref, 'source': f'reported to {name}'}
        emit('coverage', 'pipeline', corpus=target, unread=[w['unread'] for w in self.coverage(target)])
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
                'coverage_warnings': {cid: w for cid in corpus.manifests() if (w := self.coverage(cid))},
                'open_questions': [q for q in self.questions.values() if q['status'] == 'open'],
                'answered_questions': [q for q in self.questions.values() if q['status'] != 'open'],
                'delegations': self.log}


def merge(prior, patch):
    """Apply a reassessment patch by requirement id: replace changed, append new, drop withdrawn."""
    changed = {r.id: r for r in patch.changed_requirements}
    replaced = [r.id for r in prior.requirements if r.id in changed]
    kept = [changed.pop(r.id, r) for r in prior.requirements if r.id not in patch.removed_requirement_ids]
    emit('patch', 'pipeline', replaced=replaced, added=list(changed), removed=patch.removed_requirement_ids,
         impact=patch.impact)
    return prior.model_copy(update={'requirements': kept + list(changed.values()),
                                    'coverage_note': patch.coverage_note or prior.coverage_note,
                                    'peer_questions': patch.peer_questions, 'delegations': []})


def repeats(a, b, threshold=0.6):
    """Word overlap relative to the shorter question; catches rephrasings, not new questions."""
    words = lambda t: set(re.findall(r'[a-z0-9]+', t.lower())) - {'the', 'a', 'an', 'of', 'to', 'in', 'for', 'and', 'or', 'is', 'does', 'what', 'which', 'under'}
    x, y = words(a), words(b)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= threshold


def answer_law(answer, record, cid):
    """The law an answer relies on, as the answering agent was shown it: cited provisions of its own corpus that it
    read, with the passages it saw, and the selected quote. The asker reasons from this text instead of the answer's
    summary alone; it cannot cite it, since only its own reading is citable. Unread or foreign citations are issues."""
    law, issues = [], []
    for c in answer['citations']:
        pid = corpus.resolve(c)
        if pid is None or corpus.provisions()[pid]['corpus'] != cid:
            issues.append(f'cites {c}, which is not a provision of {cid}')
        elif pid not in record['read']:
            issues.append(f'cites {pid}, which this agent did not read')
        elif pid not in [x['provision'] for x in law]:
            law.append({'provision': pid, 'title': corpus.provisions()[pid]['title'],
                        'text': '\n'.join(t for q, t in corpus.passages(pid).items() if q in record['passages'])})
    quote = record['passages'].get(answer['quote_id']) if answer['quote_id'] else None
    if answer['quote_id'] and (quote is None or answer['quote_id'].rsplit('#', 1)[0] not in [x['provision'] for x in law]):
        issues.append(f"quote {answer['quote_id']} was not shown to this agent from a cited provision")
    elif quote:
        law.insert(0, {'quote': quote})
    if not law:
        issues.append('cites no law it read')
    return law, issues


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
        if MODE == 'single':
            return run_single(case, started), events
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


def run_single(case, started):
    """Baseline: one agent, one call over every corpus. No plan, delegation, peer questions or review;
    the same reference checks, decision and brief. Its conflicts and unresolved stand in for the final review."""
    case = Case.model_validate(case).model_dump()
    offered = facts.passages(case)
    emit('stage', 'single_agent', status='running')
    answer, record = agents.single(case, offered)
    emit('stage', 'single_agent', status='done' if answer else 'failed')
    emit('stage', 'verification', status='running')
    evidence = {e['id'] for e in case['evidence']}
    findings = [verify({**r.model_dump(), 'ref': f'{r.corpus}:{r.id}', 'source': 'single agent'}, record, evidence)
                for r in (answer.requirements if answer else [])]
    decision, reasons = decide(findings, {}, answer)
    result = {'decision': decision, 'reasons': reasons, 'seconds': round(time.time() - started, 1), 'mode': 'single',
              'plan': {'understanding': answer.understanding,
                       'engagements': [{'corpus': a.corpus, 'engaged': a.applies, 'reason': a.reasoning, 'focus': ''}
                                       for a in answer.applicability]} if answer else None,
              'specialists': {a.corpus: {'applies': a.applies, 'applicability_reasoning': a.reasoning,
                                         'coverage_note': answer.coverage_note} for a in answer.applicability}
              if answer else {},
              'findings': findings, 'questions': [], 'delegations': [],
              'reviews': [{'action': 'single_agent (no review)', 'conflicts': [c.model_dump() for c in answer.conflicts],
                           'unresolved': answer.unresolved}] if answer else [],
              'read': {'single_agent': record['read']}, 'case': case}
    result['brief'] = brief.build(findings, {}, answer, offered)
    emit('decision', 'verification', decision=decision, reasons=reasons)
    emit('stage', 'verification', status='done')
    return result


def save(result, events, name, folder=corpus.ROOT / 'runs' / 'mock'):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}_{name}.json"
    path.write_text(json.dumps({'model': llm.model_name(), 'mode': MODE, 'tools': tools.ENABLED, 'result': result, 'events': events},
                               indent=1, default=str))
    return path
