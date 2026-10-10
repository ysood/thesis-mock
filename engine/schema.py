"""Input and agent output shapes. Nothing here names a law, a regime or a requirement:
jurisdictions come from the corpus registry and requirements are identified by the agents."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine import corpus


def check_jurisdiction(code):
    code = code.strip().upper()
    if code not in corpus.jurisdictions():
        raise ValueError(f"'{code}' is not a jurisdiction in corpora/registry.json ({', '.join(corpus.jurisdictions())})")
    return code


# ------------------------------------------------------------------ input

class Organisation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1)
    name: str
    jurisdiction: str = Field(description='Registry code where it is established')
    kind: str = Field('other', description='e.g. health_care_provider, cloud_provider, research_body')
    description: str = ''

    _code = field_validator('jurisdiction')(lambda cls, v: check_jurisdiction(v))


class People(BaseModel):
    model_config = ConfigDict(extra='forbid')
    where: list[str] = Field(default_factory=list)
    how_many: int | None = None
    includes_children: bool | None = None

    _codes = field_validator('where')(lambda cls, v: [check_jurisdiction(c) for c in v])


class Data(BaseModel):
    model_config = ConfigDict(extra='forbid')
    description: str
    categories: list[str] = Field(default_factory=list)
    identifiability: Literal['identified', 'pseudonymised', 'anonymous', 'unknown'] = 'unknown'
    people: People = Field(default_factory=People)


class Locations(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stored_in: list[str] = Field(default_factory=list)
    accessed_from: list[str] = Field(default_factory=list)

    _codes = field_validator('stored_in', 'accessed_from')(lambda cls, v: [check_jurisdiction(c) for c in v])


class Transfer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str
    sender: str
    recipient: str
    data: Data
    purpose: str
    purpose_description: str = ''
    frequency: Literal['one_off', 'occasional', 'ongoing', 'unknown'] = 'unknown'
    locations: Locations = Field(default_factory=Locations)
    retention: str = ''
    onward: str = ''
    method: str = ''
    additional_info: str = ''


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1)
    kind: str
    title: str
    between: list[str] = Field(default_factory=list, description='Organisation IDs it concerns')
    summary: str
    dated: str = ''
    attested_by: str = ''


class Case(BaseModel):
    model_config = ConfigDict(extra='forbid')
    organisations: list[Organisation] = Field(min_length=1)
    transfer: Transfer
    evidence: list[Evidence] = Field(default_factory=list)

    def model_post_init(self, _):
        ids = {o.id for o in self.organisations}
        for role in ('sender', 'recipient'):
            if getattr(self.transfer, role) not in ids:
                raise ValueError(f'transfer.{role} must be an organisation id')
        for e in self.evidence:
            if not set(e.between) <= ids:
                raise ValueError(f'evidence {e.id} names unknown organisations')


# ------------------------------------------------------------------ shared output parts

class FactRef(BaseModel):
    fact_id: str = Field(description='ID of a supplied FACT PASSAGE')
    path: str = Field('', description='Filled by the system; leave empty')
    quote: str = Field('', description='Filled by the system; leave empty')


class Route(BaseModel):
    name: str = Field(min_length=1, description='A legal route, alternative or exception, naming who and what it covers')
    status: Literal['supported', 'available', 'ruled_out', 'unresolved', 'not_investigated'] = Field(
        description='supported: in place on the facts as they stand. available: not in place yet, but it would work '
                    'for the transfer as proposed in the case once the parties make the changes in the requirement\'s '
                    'required_actions. ruled_out: the law excludes the transfer as proposed from this route; changes '
                    'that would amount to proposing a different transfer do not make it available. unresolved: whether '
                    'it works depends on a fact, document or answer that has not been supplied; never use it for '
                    'something the parties have simply not done yet. not_investigated: an optional fallback left '
                    'unassessed because another route already works.')
    reasoning: str
    citations: list[str] = Field(description='IDs of provisions you read, exactly as shown in your table of contents')
    quote_id: str = Field(min_length=1, description='One passage ID you were shown from a cited provision')


class Requirement(BaseModel):
    id: str = Field(min_length=1, description='Short stable slug you choose (lowercase words joined by underscores)')
    title: str
    kind: Literal['gate', 'duty'] = Field(description='gate: must be met before the transfer may proceed; '
                                                       'duty: ongoing obligation reported but not decisive')
    status: Literal['met', 'unmet', 'undetermined', 'not_applicable']
    reasoning: str
    facts: list[FactRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list, description='Provision IDs you read')
    quote_id: str = Field('', description='One passage ID you were shown from a cited provision')
    routes: list[Route] = Field(default_factory=list, description='Plausible alternatives you found in the law, '
                                                                   'with explicit status')
    missing_facts: list[str] = Field(default_factory=list, description='Facts not supplied that decide this')
    missing_evidence: list[str] = Field(default_factory=list, description='Documents that would establish it')
    required_actions: list[str] = Field(default_factory=list, description='What would cure an unmet requirement')
    confirmations: list[str] = Field(default_factory=list, description='Non-decisive points to confirm')
    open_dependency: str = Field('', description='A question this depends on that another jurisdiction\'s law '
                                                 'or a lower-level law must answer, if still open')


class Delegation(BaseModel):
    corpus: str = Field(description='A subordinate corpus ID available to you')
    requirement_id: str
    question: str
    referring_provisions: list[str] = Field(description='Your provisions that leave this to lower-level law')


class PeerQuestion(BaseModel):
    jurisdiction: str = Field(description='Registry code of the jurisdiction whose law is needed')
    requirement_id: str
    question: str
    why: str


class SpecialistAnswer(BaseModel):
    applies: bool = Field(description='Whether this corpus applies to any party or activity in the case')
    applicability_reasoning: str
    applicability_citations: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    coverage_note: str = Field(description='How you checked that no engaged requirement, alternative or '
                                           'cumulative duty in your corpora was missed, and any remaining limit')
    delegations: list[Delegation] = Field(default_factory=list)
    peer_questions: list[PeerQuestion] = Field(default_factory=list)


class SpecialistPatch(BaseModel):
    """A reassessment: only what changes. Python merges it into the prior assessment by requirement id."""
    impact: str = Field(description='Which of your requirements the new information affects and why; why the '
                                    'others stay as they are')
    changed_requirements: list[Requirement] = Field(
        default_factory=list, description='Complete replacements for requirements that change (same id), and any '
                                          'new requirements (new id). Unchanged requirements are kept automatically.')
    removed_requirement_ids: list[str] = Field(default_factory=list,
                                               description='Requirements to withdraw, explained in impact')
    coverage_note: str = Field('', description='Updated coverage note, or empty to keep the prior one')
    peer_questions: list[PeerQuestion] = Field(default_factory=list, description='New questions only')


class Answer(BaseModel):
    question_id: str
    answer: str
    facts: list[FactRef] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    quote_id: str = ''
    requirement_ids: list[str] = Field(default_factory=list, description='Ids of your requirements this answer rests on')


class DelegateAnswer(BaseModel):
    """A lower-level or peer specialist answering questions put to it. Obligations of its own law are filed as
    requirements (they are findings of this corpus); answers explain and point to them."""
    answers: list[Answer]
    requirements: list[Requirement] = Field(
        default_factory=list, description='Requirements created by your own instruments that the facts engage, '
                                          'filed as the instructions say; answers point to them by id')


# ------------------------------------------------------------------ supervisor

class Engagement(BaseModel):
    corpus: str
    engaged: bool
    reason: str
    facts: list[FactRef] = Field(default_factory=list)
    focus: str = Field('', description='What the specialist should look at first, without legal conclusions')


class SupervisorPlan(BaseModel):
    understanding: str = Field(description='Plain account of who sends what to whom, where, and why')
    engagements: list[Engagement]


class Routing(BaseModel):
    question_ref: str = Field(description='Ref of an open peer question, exactly as listed in open_questions')
    to_corpus: str
    question: str = Field(description='The question as the receiving specialist should read it')


class Correction(BaseModel):
    corpus: str
    requirement_ids: list[str] = Field(min_length=1, description='The requirements the error is in')
    kind: Literal['contradiction', 'unsupported_status', 'missed_provision', 'stale_answer'] = Field(
        description='contradiction: the finding contradicts a passage shown under LAW BEHIND THE FINDINGS or another '
                    'finding. unsupported_status: the passages its specialist cited do not carry its status. '
                    'missed_provision: a provision of that corpus (e.g. a coverage warning) that could change a gate or '
                    'route is not addressed. stale_answer: the finding predates an answer it depends on.')
    quote_ids: list[str] = Field(default_factory=list, description='Passage IDs from LAW BEHIND THE FINDINGS that '
                                                                   'show the error (required for contradiction and '
                                                                   'unsupported_status)')
    instruction: str = Field(description='The specific error and what to reconsider; never the status to give')


class Conflict(BaseModel):
    description: str
    kind: Literal['incompatible_law', 'disagreement'] = Field(
        description='incompatible_law: the law of two corpora makes demands on the same actor, data or time that '
                    'pull apart. disagreement: two findings contradict each other on the same point.')
    requirement_refs: list[str] = Field(description='Refs of the requirements involved ("<corpus>:<requirement id>"), '
                                                    'exactly as listed in the current state')
    resolvable: bool = Field(description='incompatible_law: a combination of routes satisfies both. disagreement: '
                                         'always false')
    resolution: str = Field('', description='The route that satisfies both, if resolvable')
    quote_ids: list[str] = Field(default_factory=list, description='Passage IDs from LAW BEHIND THE FINDINGS it rests on')


class PlannedRoute(BaseModel):
    requirement_ref: str = Field(description='"<corpus>:<requirement id>" of a gate, exactly as listed')
    route: str = Field(description='Name of one of its routes, exactly as listed, or "met" if it has no routes')


class Blocker(BaseModel):
    requirement_ref: str = Field(description='"<corpus>:<requirement id>" of the gate it blocks, exactly as listed')
    gap: str = Field(description='The decisive missing fact, document or answer, and why the gate cannot be decided '
                                 'without it')
    why_not_a_confirmation: str = Field(description='If the gate already lists confirmations, why confirming them '
                                                    'later is not enough; otherwise empty')


class SupervisorConclusion(BaseModel):
    """The supervisor's combined conclusion: whether the gates of every corpus can be satisfied together.
    Specialists own their findings; the supervisor owns how they combine."""
    outcome: Literal['satisfiable_together', 'satisfiable_with_changes', 'not_satisfiable_together', 'undetermined'] = Field(
        description='satisfiable_together: one route per gate, all supported, work together on the facts as they '
                    'stand. satisfiable_with_changes: they work together once the required actions are taken. '
                    'not_satisfiable_together: no combination of routes meets every gate at once, or a gate is unmet '
                    'with no available route. undetermined: a missing fact, document or answer decides it (name it in '
                    'blockers), or findings still disagree.')
    route_plan: list[PlannedRoute] = Field(default_factory=list, description='The combination of routes that meets '
                                                                             'every engaged gate together, if any')
    reasoning: str = Field(description='Why the requirements can or cannot be satisfied together, from the passages')
    quote_ids: list[str] = Field(default_factory=list, description='Passage IDs from LAW BEHIND THE FINDINGS it rests on')
    conflicts: list[Conflict] = Field(default_factory=list)
    summary: str
    blockers: list[Blocker] = Field(default_factory=list, description='Decisive gaps a human must close before the '
                                                                      'transfer may proceed, each tied to a gate')
    notes: list[str] = Field(default_factory=list, description='Anything else worth a reviewer\'s attention; '
                                                               'notes never block')


class SupervisorSynthesis(SupervisorConclusion):
    """First pass: the conclusion so far, plus the bounded follow-ups that would settle it."""
    routings: list[Routing] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list)


# ------------------------------------------------------------------ single-agent baseline

def check_corpus(cid):
    if cid not in corpus.manifests():
        raise ValueError(f"'{cid}' is not a corpus ({', '.join(corpus.manifests())})")
    return cid


class CorpusApplicability(BaseModel):
    corpus: str = Field(description='Corpus ID')
    applies: bool = Field(description='Whether this corpus applies to any party or activity in the case')
    reasoning: str
    citations: list[str] = Field(default_factory=list)

    _corpus = field_validator('corpus')(lambda cls, v: check_corpus(v))


class SingleRequirement(Requirement):
    corpus: str = Field(description='ID of the corpus whose instrument creates this requirement')

    _corpus = field_validator('corpus')(lambda cls, v: check_corpus(v))


class SingleAssessment(BaseModel):
    """One agent assessing every corpus in one call. conflicts and unresolved play the supervisor's final-review role."""
    understanding: str = Field(description='Plain account of who sends what to whom, where, and why')
    applicability: list[CorpusApplicability] = Field(description='One entry for each corpus')
    requirements: list[SingleRequirement] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    coverage_note: str = Field(description='How you checked that no engaged requirement, alternative or '
                                           'cumulative duty in any corpus was missed, and any remaining limit')
    unresolved: list[str] = Field(default_factory=list, description='Issues that still need human review')
