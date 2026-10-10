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
    status: Literal['supported', 'ruled_out', 'unresolved', 'not_investigated']
    reasoning: str
    citations: list[str] = Field(description='Provision IDs you read, e.g. "APIR 18"')
    quote_id: str = Field(min_length=1, description='One passage ID you were shown from a cited provision')


class Requirement(BaseModel):
    id: str = Field(min_length=1, description='Short stable slug you choose, e.g. transfer_route')
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


class Answer(BaseModel):
    question_id: str
    answer: str
    facts: list[FactRef] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    quote_id: str = ''


class DelegateAnswer(BaseModel):
    """A regional or peer specialist answering questions put to it."""
    answers: list[Answer]
    additional_requirements: list[Requirement] = Field(
        default_factory=list, description='Further requirements of your law engaged by the facts that the '
                                          'questions did not ask about')


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
    question_ref: str = Field(description='Ref of an open peer question, e.g. aster:q1')
    to_corpus: str
    question: str = Field(description='The question as the receiving specialist should read it')


class Revision(BaseModel):
    corpus: str
    requirement_ids: list[str] = Field(default_factory=list)
    instruction: str


class Conflict(BaseModel):
    description: str
    requirement_refs: list[str] = Field(description='e.g. aster:agent_contract, corvel:host_retention')
    resolvable: bool
    resolution: str = Field('', description='The route that satisfies both, if resolvable')


class SupervisorReview(BaseModel):
    action: Literal['route_or_revise', 'finish']
    routings: list[Routing] = Field(default_factory=list)
    revisions: list[Revision] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    summary: str
    unresolved: list[str] = Field(default_factory=list, description='Issues that still need human review')
