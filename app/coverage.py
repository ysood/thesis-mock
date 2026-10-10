"""Formatting-only normalization of assigned IDs. Coverage checks live in review.py."""

import re

def canonical(question_id):
    """Comparison key that ignores case and punctuation: gdpr-specialist:Q1 == gdpr_specialist:q1."""
    return re.sub(r"[^a-z0-9]", "", question_id.lower())


def resolve_id(question_id, assigned):
    """The assigned ID a returned ID evidently means, or the returned ID unchanged.

    Formatting slips only: the same characters ignoring case and punctuation, or a dropped
    namespace when exactly one assigned ID ends with what was returned (local1 ->
    gdpr_specialist:local1, lawful_basis -> gdpr.lawful_basis).
    """
    key = canonical(question_id)
    exact = [i for i in assigned if canonical(i) == key]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return question_id
    tail = [i for i in assigned if canonical(re.split(r"[.:]", i)[-1]) == key]
    return tail[0] if len(tail) == 1 else question_id


def normalise_ids(assessment, question_ids, national_ids=()):
    """Map returned IDs onto the assigned IDs they evidently mean (formatting slips only).

    IDs that match no assigned ID are left unchanged for coverage checks.
    Returns the corrections made, for the trace.
    """
    changes = []
    for finding in assessment.findings:
        fixed = [resolve_id(i, question_ids) for i in finding.question_ids]
        changes += [(old, new) for old, new in zip(finding.question_ids, fixed) if old != new]
        finding.question_ids = fixed
        for dependency in finding.national_dependencies:
            new = resolve_id(dependency.question_id, national_ids)
            if new != dependency.question_id:
                changes.append((dependency.question_id, new))
                dependency.question_id = new
    return sorted(set(changes))
