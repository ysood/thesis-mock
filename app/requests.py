"""Shared request boundary for model-authored reviews, national questions and retrieval.

The existing JSON output schemas are the tool arguments. This function validates
them against current assignments before execution; it never supplies legal answers.
"""

from app import knowledge as kb
from app.coverage import resolve_id
from app.llm import emit
from app.schema import NationalLawRequest, SourceRequest, SupervisorAction, check_country


class RequestError(ValueError):
    pass


def _ids(values, allowed, label, changes, *, required=False):
    if required and not values:
        raise RequestError(f'{label} requires at least one assigned ID.')
    result = []
    for value in values:
        fixed = resolve_id(value, allowed)
        if fixed not in allowed:
            raise RequestError(f'Unassigned {label}: {value}. Use a current assigned ID; '
                               'for a child question, assign its parent requirement and ask GDPR to revisit it.')
        if fixed != value:
            changes.append([value, fixed])
        if fixed not in result:
            result.append(fixed)
    return result


def _provisions(values, regime, changes):
    allowed = [p for p, item in kb.provisions().items() if item['regime'] == regime]
    result = []
    for value in values:
        hits = kb.resolve(value, allowed)
        if not hits:
            raise RequestError(f'Provision unavailable in {regime}: {value}. '
                               'Use a source query when the provision ID is unknown.')
        if hits != [value]:
            changes.append([value, hits])
        result += [p for p in hits if p not in result]
    return result


def prepare_request(request, *, actor, questions, regime, targets=(), finding_ids=(), national=()):
    """Return a normalized, validated copy; log rejection without executing any work.

    questions is the current owner's allowed checklist/delegated IDs. targets
    contains available supervisor destinations (after budget checks). national
    contains already registered child questions, never predicted future IDs.
    """
    name = type(request).__name__
    changes = []
    try:
        if isinstance(request, SupervisorAction):
            if request.action != 'delegate':
                raise RequestError('Only delegation actions are assignment requests.')
            target = _ids([request.target], targets, 'target', changes)[0]
            ids = _ids(request.question_ids, questions, 'question IDs', changes, required=True)
            refs = _ids(request.finding_ids, finding_ids, 'finding IDs', changes)
            provisions = _provisions(request.provision_ids, regime, changes)
            if not request.instruction.strip():
                raise RequestError('A review request needs a specific instruction.')
            result = request.model_copy(update={'target': target, 'question_ids': ids, 'finding_ids': refs,
                                                'provision_ids': provisions, 'instruction': request.instruction.strip()})
        elif isinstance(request, SourceRequest):
            ids = _ids(request.question_ids, questions, 'question IDs', changes, required=True)
            provisions = _provisions(request.provision_ids, regime, changes)
            if not request.query.strip() and not provisions:
                raise RequestError('A source request needs a query or a known provision ID.')
            result = request.model_copy(update={'question_ids': ids, 'provision_ids': provisions,
                                                'query': request.query.strip()})
        elif isinstance(request, NationalLawRequest):
            parent = _ids([request.requirement], questions, 'parent requirement', changes)[0]
            country = check_country(request.country)
            if country != request.country:
                changes.append([request.country, country])
            if not request.question.strip():
                raise RequestError('A national-law request needs a specific question.')
            provisions = _provisions(request.gdpr_provisions, 'GDPR', changes)
            if not provisions:
                raise RequestError('A national-law request needs at least one referring GDPR provision.')
            revisit = request.revisit_question_id
            if revisit:
                known = {q['question_id']: q for q in national}
                revisit = _ids([revisit], known, 'national revisit', changes)[0]
                old = known[revisit]
                if old['country'] != country or old['requirement'] != parent:
                    raise RequestError('A national revisit cannot change its country or parent requirement.')
            result = request.model_copy(update={'requirement': parent, 'country': country,
                                                'gdpr_provisions': provisions, 'revisit_question_id': revisit,
                                                'question': request.question.strip()})
        else:
            raise RequestError(f'Unsupported request type: {name}.')
    except ValueError as exc:
        emit('request_rejected', actor, request_type=name, request=request.model_dump(), reason=str(exc))
        raise RequestError(str(exc)) from exc
    emit('request_validated', actor, request_type=name, request=result.model_dump(), changes=changes)
    return result
