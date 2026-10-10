"""Reference and coverage integrity. These checks never determine a legal status."""

import re
from collections import Counter
from copy import deepcopy

from app import knowledge as kb, passages
from app.case import evidence_by_id, fact_document, findings

MISSING = object()


def read_pointer(document, pointer):
    if not pointer.startswith('/'):
        return MISSING
    value = document
    try:
        for part in pointer[1:].split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            value = value[int(part)] if isinstance(value, list) and part.isdigit() else value[part]
    except (KeyError, IndexError, TypeError, ValueError):
        return MISSING
    return value


ELLIPSIS = re.compile(r'\s*(?:…|\.\.\.)\s*')


def quote_pieces(quote):
    """An excerpt may skip words with '…' or '...'; each remaining piece must be quoted exactly."""
    return [p for p in (kb.normalise_text(part) for part in ELLIPSIS.split(quote)) if p]


def in_order(pieces, text):
    """True if every piece occurs in text, without overlap and in the given order.

    A single piece keeps the original substring check. When an ellipsis splits the quote, each piece
    must match whole words, so a short piece cannot hide inside a longer word ('ie' in 'reviewed').
    """
    if len(pieces) == 1:
        return pieces[0] in text
    position = 0
    for piece in pieces:
        found = re.compile(r'(?<!\w)' + re.escape(piece) + r'(?!\w)').search(text, position)
        if not found:
            return False
        position = found.end()
    return True


def quoted_fact(ref, document):
    if 'fact_id' in ref:
        selected = passages.input_passages(document).get(ref['fact_id'])
        return (selected is not None and ref.get('path') == selected['path']
                and ref.get('quote') == selected['text'])
    value = read_pointer(document, ref.get('path', ''))
    pieces = quote_pieces(ref.get('quote', ''))
    if value is MISSING or isinstance(value, (list, dict)) or value is None or not pieces:
        return False
    return in_order(pieces, kb.normalise_text(str(value)))


def check_intake(intake, request):
    claims, contradictions, unsourced = [], [], list(intake.get('unsourced', []))
    for claim in intake.get('claims', []):
        (claims if quoted_fact(claim.get('source', {}), request) else unsourced).append(claim)
    for item in intake.get('contradictions', []):
        passages = {(s['path'], kb.normalise_text(s['quote'])) for s in item.get('sources', [])
                    if quoted_fact(s, request)}
        (contradictions if len(passages) >= 2 else unsourced).append(item)
    issues = []
    for item in unsourced:
        if 'source' in item:
            source = item['source']
            if 'fact_id' in source:
                issues.append(f"Intake claim has an invalid fact passage reference: {source['fact_id']}.")
            else:
                issues.append(f"Intake claim quote does not match {source.get('path', '')}: {source.get('quote', '')!r}.")
        else:
            issues.append(f"Intake contradiction needs two distinct matching passages: {item.get('description', '')}.")
    return {**intake, 'claims': claims, 'contradictions': contradictions, 'unsourced': unsourced,
            'reference_issues': issues}


def research_warnings(case):
    """Surface declared legal gaps without research or a stopping reason, never decide merits.

    A search attempt does not establish adequate research. The supervisor still
    reviews its relevance/results and the substance of any stopping explanation.
    """
    branches = {**case['specialists']}
    for branch in case['specialists'].values():
        branches.update({f'local_law_{country}': child for country, child in branch.get('children', {}).items()})
    warnings = []
    for f in findings(case):
        if f['status'] != 'insufficient_information' or f.get('research_stopping_reason', '').strip():
            continue
        national = f.get('national_law_review') == 'required'
        if not (national or f.get('missing_law', '').strip()):
            continue
        branch = branches.get(f['agent'], {})
        questions = set(f['question_ids'])
        if national and f['regime'] == 'GDPR':
            attempted = any(q['requirement'] in questions for q in branch.get('national_questions', []))
        else:
            attempted = any(questions & set(r['question_ids']) for r in branch.get('source_research', []))
        if not attempted:
            warnings.append({'finding_id': f['finding_id'], 'agent': f['agent'],
                             'question_ids': f['question_ids'],
                             'message': 'Missing law is identified, but no corresponding research attempt or '
                                        'stopping reason is recorded. Review whether retrieval/delegation can help; '
                                        'if not, explain the decisive fact gap or research limit.'})
    return warnings


def reference_issues(item, allowed, document):
    notes = []
    for ref in item.get('facts', []):
        if not quoted_fact(ref, document):
            if 'fact_id' in ref:
                notes.append(f"Fact passage reference is unknown or does not match its bound path/text: {ref['fact_id']}.")
            else:
                notes.append(f"Fact reference does not match supplied text: {ref.get('path', '')}.")
    for citation in item.get('citations', []):
        if not kb.resolve(citation, allowed):
            notes.append(f"Citation '{citation}' was not supplied to this agent.")
    return notes


def finding_citations(finding):
    """Include the law used to screen alternatives, even if the main finding cites other law."""
    return list(dict.fromkeys(finding.get('citations', [])
                             + [c for route in finding.get('routes', []) for c in route.get('citations', [])]))


def legal_quote_issues(item, allowed, *, required=False):
    """Check selected source text, without judging the legal conclusion it is used for."""
    notes = []
    resolved = list(dict.fromkeys(p for c in item.get('citations', []) for p in kb.resolve(c, allowed)))
    quote = kb.normalise_text(item.get('quote', ''))
    quote_found = bool(quote) and any(quote in kb.normalise_text(kb.provisions()[p]['text']) for p in resolved)
    if item.get('quote_selection_error'):
        notes.append(item['quote_selection_error'])
    if item.get('quote_id'):
        from app.passages import offered_passages
        selected = offered_passages(resolved).get(item['quote_id'])
        if selected is None or selected['text'] != item.get('quote', ''):
            notes.append('Quote ID does not match its exact source passage in the cited provisions.')
    if quote and not quote_found:
        notes.append('Quote not found word-for-word in the cited provisions.')
    if required and (not resolved or not quote_found):
        notes.append('A conclusive finding needs a supplied citation and exact legal quote.')
    return resolved, notes


def check_finding(finding, case, questions=()):
    f = deepcopy(finding)
    allowed, document = f.get('allowed', []), fact_document(case)
    notes = reference_issues(f, allowed, document)
    resolved, quote_notes = legal_quote_issues(f, allowed, required=f['status'] != 'insufficient_information')
    notes += quote_notes
    if not f.get('route_coverage', '').strip():
        notes.append('Explain route coverage, or why this is a single duty or applicability exclusion.')
    for route in f.get('routes', []):
        route_resolved, route_notes = legal_quote_issues(route, allowed, required=True)
        route_notes += reference_issues(route, allowed, document)
        if not route.get('quote_id'):
            route_notes.append('A route needs a shown legal quote ID.')
        route['resolved_citations'] = route_resolved
        resolved += [p for p in route_resolved if p not in resolved]
        notes += [f"Route '{route['name']}': {note}" for note in route_notes]
    if f['status'] != 'insufficient_information':
        if not f.get('facts'):
            notes.append('A conclusive finding needs references to supplied facts.')
    evidence = evidence_by_id(case)
    for evidence_id in f.get('evidence_ids', []):
        if evidence_id not in evidence:
            notes.append(f'Unknown evidence ID: {evidence_id}.')
    delegated = {q['question_id']: q for q in questions}
    answered = {q for branch in case['specialists'].values() for f in branch.get('findings', [])
                if f['agent'].startswith('local_law_') for q in f['question_ids']}
    for dependency in f.get('national_dependencies', []):
        q = delegated.get(dependency['question_id'])
        if not q or q['country'] != dependency['country']:
            notes.append(f"Unknown national-law dependency: {dependency['question_id']}.")
        elif dependency['question_id'] not in answered and case['specialists']:
            notes.append(f"No current child answer for dependency: {dependency['question_id']}.")
    if f.get('agent_failed'):
        notes.append('The specialist model call failed.')
    # Deliberately preserve status and reasoning.
    return {**f, 'resolved_citations': resolved, 'verified': not notes, 'verification_notes': notes}


def coverage(agent, regime, assigned, returned, errors=()):
    counts = Counter(q for f in returned for q in f.get('question_ids', []))
    missing = sorted(set(assigned) - set(counts))
    unexpected = sorted(set(counts) - set(assigned))
    duplicate = sorted(q for q, count in counts.items() if count != 1)
    issues = list(errors)
    if missing:
        issues.append('Unanswered questions: ' + ', '.join(missing))
    if unexpected:
        issues.append('Unassigned questions: ' + ', '.join(unexpected))
    if duplicate:
        issues.append('More than one finding for a question: ' + ', '.join(duplicate))
    if any(len(f.get('question_ids', [])) != 1 for f in returned):
        issues.append('Return one finding per assigned question.')
    return {'agent': agent, 'regime': regime, 'expected_questions': list(assigned),
            'answered_questions': sorted(set(assigned) & set(counts)), 'unexpected_questions': unexpected,
            'issues': issues, 'complete': not issues}


def inspect_case(case):
    questions = [q for branch in case['specialists'].values() for q in branch.get('national_questions', [])]
    checked = [check_finding(f, case, questions) for f in findings(case)]
    records = [r for b in case['specialists'].values() for r in b.get('coverage', [])]
    issues = list(case['checks'].get('setup_issues', []))
    issues += ['Supervisor interpretation update rejected: ' + issue
               for issue in case['checks'].get('interpretation_update_issues', [])]
    issues += ['Supervisor intake update rejected: ' + issue
               for issue in case['checks'].get('intake_update_issues', [])]
    issues += ['Supervisor exclusion update rejected: ' + issue
               for issue in case['checks'].get('exclusion_update_issues', [])]
    for record in records:
        issues += [f"{record['agent']}: {issue}" for issue in record['issues']]
    for f in checked:
        issues += [f"{f['finding_id']}: {issue}" for issue in f['verification_notes']]
    return checked, records, list(dict.fromkeys(issues))


MAIN_SPECIALISTS = ('gdpr_specialist', 'hipaa_specialist')


def established_refusals(checked):
    """Accepted, verified, transfer-level gate findings that are not met, in a regime that applies.

    One such finding is enough to refuse: other open matters or unrelated reference defects are listed
    alongside, not used to downgrade the refusal (run0009). Applicability findings themselves never refuse.
    """
    from app import requirements as rq
    gates = {i['key'] for i in rq.catalogue()['requirements'] if i['class'] == 'gate'}
    applies = {f['regime'] for f in checked if f['agent'] in MAIN_SPECIALISTS and f['verified']
               and f['status'] == 'satisfied_if_verified' and rq.applicability_key(f['regime']) in f['question_ids']}
    return [f for f in checked if f['agent'] in MAIN_SPECIALISTS and f['verified'] and f['status'] == 'not_satisfied'
            and f.get('obligation_scope', 'transfer') == 'transfer' and f['regime'] in applies
            and set(f['question_ids']) & gates and rq.applicability_key(f['regime']) not in f['question_ids']]


def final_decision(proposed, issues, checked, conditions, outstanding):
    """Apply the decision consistency rules to the supervisor's proposal. Returns (decision, rule notes)."""
    refusals = established_refusals(checked)
    if refusals:
        ids = ', '.join(f['finding_id'] for f in refusals)
        note = [f'Decision rule: verified unmet transfer gate ({ids}) requires do_not_proceed; other open matters are listed as further issues.']
        return 'do_not_proceed', note if proposed != 'do_not_proceed' else []
    if issues:
        return 'needs_review', []
    if proposed == 'proceed' and (conditions or outstanding):
        return 'proceed_subject_to_conditions', ['Decision rule: proceed with listed conditions or outstanding evidence is proceed_subject_to_conditions.']
    return proposed, []


def finish_issues(action, checked, records, cited):
    from app import requirements as rq
    issues = []
    current = {f['finding_id'] for f in checked}
    accepted = action.accepted_finding_ids
    if set(accepted) != current or len(accepted) != len(set(accepted)):
        issues.append('Accept every current finding ID exactly once; do not accept superseded or invented IDs.')
    if action.reconciliation is None or not action.reasons:
        issues.append('Finish requires reconciliation and decision reasons.')
    if action.reconciliation:
        for conflict in action.reconciliation.conflicts:
            if not conflict.citations or not conflict.shared_scope.strip() or len(set(conflict.finding_ids)) < 2:
                issues.append('A relationship needs distinct finding references, shared scope and legal sources.')
            if not set(conflict.finding_ids) <= current:
                issues.append('A reconciliation references non-current findings.')
            if any(not kb.resolve(c, cited) for c in conflict.citations):
                issues.append('A reconciliation cites sources absent from this review.')
    if action.decision == 'do_not_proceed' and not established_refusals(checked):
        transfer_findings = {f['finding_id'] for f in checked if f['agent'] in MAIN_SPECIALISTS and f['verified']
                             and f['status'] in ('satisfied_if_verified', 'not_satisfied')
                             and f.get('obligation_scope', 'transfer') == 'transfer'}
        incompatible = action.reconciliation and any(
            c.kind == 'incompatibility' and len(set(c.finding_ids)) >= 2
            and set(c.finding_ids) <= transfer_findings for c in action.reconciliation.conflicts)
        if not incompatible:
            issues.append('Refusal needs a verified unmet transfer gate or an explicit incompatibility between '
                          'conclusive, verified main transfer findings; a failed alternative or national-law branch is insufficient.')
            policy = {i['key']: i['class'] for i in rq.catalogue()['requirements']}
            non_gates = sorted({f"{key} ({policy[key]})" for f in checked
                                if f['agent'] in MAIN_SPECIALISTS and f['status'] == 'not_satisfied'
                                for key in f['question_ids'] if key in policy and policy[key] != 'gate'})
            if non_gates:
                issues.append('These unmet requirements cannot independently establish a transfer gate: '
                              + ', '.join(non_gates) + '. Use checks.requirement_policy to revise the decision '
                              'or identify a verified unmet gate or supported incompatibility.')
    # A report with broken references or coverage can still finish as needs_review.
    refusing = action.decision == 'do_not_proceed' and bool(established_refusals(checked))
    if action.decision != 'needs_review' and not refusing and (any(not f['verified'] for f in checked)
                                                               or any(not r['complete'] for r in records)):
        issues.append('Reference or coverage defects require needs_review until repaired.')
    if action.decision in ('proceed', 'proceed_subject_to_conditions'):
        gates = {i['key'] for i in rq.catalogue()['requirements'] if i['class'] == 'gate'}
        if any(set(f['question_ids']) & gates and f.get('obligation_scope', 'transfer') == 'transfer'
               and f['status'] in ('not_satisfied', 'insufficient_information') for f in checked):
            issues.append('The proposed decision contradicts an accepted unmet or unresolved transfer finding; request specialist revision or finish needs_review/do_not_proceed.')
    return issues
