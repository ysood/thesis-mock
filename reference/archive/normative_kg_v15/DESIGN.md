> v9 runtime note (2026-10-06): the graph supplies source bundles, guidance and national-law
> links. Agents decide statuses and evidence sufficiency. Sections describing deterministic
> status evaluation document the v5-v8 ontology/audit semantics, retained for offline comparison,
> not the current assessment runtime. See [architecture.md](architecture.md) and [pseudocode.md](pseudocode.md).
>
> v13 note (2026-10-07): the rule evaluator (`evaluate`, `route_value`, `conjunction`), request anchoring
> (`anchor`, `anchored`, `supplied`) and the 46 request-field bindings (CQ8) were removed from the code and
> `reference/knowledge_graph.json`. Sections below that describe them are historical; the code is on branch v12.

# Knowledge graph: design and rationale

v15 storage cleanup: `reference/knowledge_graph.json` contains requirements,
routes, conditions, concepts and their connections. Citation fields contain IDs
resolved against `reference/knowledge_graph_sources.json`, which stores each
distinct provision/pinpoint/quotation record once. `reference/knowledge_graph_notes.json`
holds node and cross-regime modelling explanations. Routine source bundles and
guidance do not load those notes; explicit node inspection and the offline
correspondence query still expose them. Source quotations, logical connections
and legal statements are preserved. This is a storage simplification, not a
change to legal assessment or a conversion to an article-only graph.

Data: `reference/knowledge_graph.json`. Code: `app/kg.py`. Tests: `tests/test_kg.py`.
Status (v5): built and validated. **Wired in (section 10): checklist sources (CQ1); the conditions and
routes each finding answers, checked under the trust model; graph routes in place of the specialists'
own alternative groups; supplied classifications deciding what they settle (CQ8); and one evaluation
per checklist item across its findings, with national answers flowing through openings (CQ2-6, CQ9).**

Audit checkpoint (2026-10-05): **not frozen**. See [the audit report](audit/2026-10-05/REPORT.txt),
[requirement reviews](audit/2026-10-05/review.json) and the complete
[edge ledger](audit/2026-10-05/edge_ledger.json). Official quote matching verifies provenance,
not the correctness of every inference. Multi-actor assessment and coverage gaps remain.

## 1. What it is for

The system has two layers of legal knowledge.

- The **textual layer** (existing, `app/knowledge.py`) holds the law texts as
  provisions, plus citation and amendment links read off the texts. It answers
  "what does the law say?" and is what specialists quote.
- The **normative layer** (this graph) records *what the law requires for a
  transfer and how its parts relate*: the requirements a transfer must meet, the
  alternative routes that satisfy each, the conditions each route needs, the
  exceptions that displace them, where the GDPR defers to national law and which
  Irish provisions supply it, how concepts compare across regimes, and how the
  structured request anchors onto all of this.

The normative layer never copies law text. Every element points into the textual
layer with a provision ID and a short verbatim quote, and code checks every quote.

## 2. Method: scope set by competency questions

Following Grüninger and Fox (1995), the graph's scope is fixed by the questions it
must answer for the pipeline (competency questions). A node type, edge type or
attribute exists only if a question needs it. This is what "minimal" means here.

| CQ | Question the pipeline asks | Answered by |
|---|---|---|
| CQ1 | Which provisions must a specialist read for requirement R? | `grounded_in`, `defined_in`, `uses_concept`; `kg.bundle` |
| CQ2 | In how many ways can R be satisfied, and is that list closed? | `has_route`, `closed`; `kg.routes` |
| CQ3 | What must all hold for a route, or for R itself? | `requires`; `kg.conditions`, `kg.answerable` |
| CQ4 | When does R arise at all? | `gated_by`, `scoped_by`, condition `kind`; `kg.scope` |
| CQ5 | What displaces R or a route? | `excepted_by` with its quote; `kg.exceptions` |
| CQ6 | Where does the GDPR defer to Member State law, and what supplies it for Ireland? | `opening`, `implemented_by`; `kg.openings`, `kg.implementation` |
| CQ7 | Which concepts correspond across regimes, and how far? | `corresponds_to` (SKOS); `kg.correspondences` |
| CQ8 | Which parts of the graph does a request fact bear on, and does it settle them? | `claims`, `denies`, `partial`; `kg.anchor`, `kg.supplied` |
| CQ9 | Who must satisfy a condition, and what evidence shows it? | `actor`, `evidence` attributes |
| CQ10 | Is R owed for each transfer, or once for the processing activity the transfer belongs to? | requirement `unit` with its quoted `basis`; `kg.unit` |

The tests answer each question for real cases, which is also the method's
evaluation step: the graph is adequate if it answers its competency questions.

## 3. Design principles and their lineage

**P1. Follow the law's own logical form.** Every gate in both regimes has the same
shape: a default rule plus an enumerated list of ways to satisfy it. Art. 6(1):
lawful "only if ... at least one of the following applies". Art. 9: prohibited,
but "shall not apply if one of the following applies". Art. 44: transfer "only if
... the conditions laid down in this Chapter are complied with". 45 CFR
164.502(a): "may not use or disclose ... except as permitted". The graph mirrors
that shape: requirement → routes (any one suffices) → conditions (all must hold),
with statutory exceptions as defeaters. This is the obligation/permission/exception
structure of PrOnto's deontic module and of LegalRuleML/DAPRECO's defeasible rules,
flattened into the AND/OR tree the verifier already evaluates (`evaluate_routes`
uses the same conjunction-within-route, alternatives-between-routes logic).

**P2. Granularity follows the statutory decision.** GDPR route sets generally follow
lettered alternatives (6(1)(e), 9(2)(j), 49(1)(a)). HIPAA combines multiple sections,
so its list is explicitly open. A full route statement qualifies its short label.

**P3. Decompose a route only where the law changes source or evidence.** A route
node stands for its own lettered text (its *core*). It gets separate conditions
only for conjuncts that come from a different provision or body of law, or that
are shown by a different document. So 9(2)(j) has three parts: its core, Art.
89(1) safeguards, and the Member State law it must be based on. 9(2)(c), whose
qualifiers all sit in its own text, stays one node. This keeps the graph small
and makes every split traceable to a source or an evidence type.

**P4. Separate scope from substance.** Conditions are either `scope` (a factual
classification that decides whether something arises or is displaced; never
reported as unmet) or `substantive` (must be met; can be unmet). This is
GraphCompliance's meta-CU versus actor-CU distinction, and it is why an
applicability requirement's "unmet" means "the regime does not apply", never a
violation.

**P5. Every element and every cross-provision link is grounded in quoted text.**
Each requirement, route, condition and concept cites at least one provision with a
verbatim quote. A `requires` or `scoped_by` link must either join two nodes that
cite the same provision, or carry its own quote (e.g. 9(2)(j)'s "in accordance
with Article 89(1)" is what links it to the Art. 89 safeguards). Every exception
quotes the "shall not apply" text that creates it. Quotes are checked with the
same normalisation the verifier uses for finding quotes.

**P6. Non-statutory sources only where the statute alone would mislead.** Four
interpretive references are used, each beside a statutory hook rather than in
place of one: EDPB Guidelines 05/2021 (what counts as a "transfer"), Schrems II
and EDPB Recommendations 01/2020 (reading Art. 46(1) as requiring a transfer
impact assessment), and the 2023 Data Privacy Framework decision (the partial US
adequacy decision). These cannot be quote-checked; they are listed in
`meta.references` and the validator rejects unknown keys.

**P7. Be honest about incompleteness.** Each route set declares `closed`: true only
when the statute's list is exhaustive and every item is a route. Routes whose
conditions are not modelled are marked `modelled: false`. Openings with no Irish
implementation in the corpus are reported, not hidden. This is what lets "no
route is available" be stated precisely: unmet among a closed list, as described.

**P8. One node per legal condition, shared where the law repeats it.** Art. 89(1)
safeguards serve both `gdpr.research_safeguards` and route 9(2)(j); the data use
agreement serves both `hipaa.required_agreements` and the limited-data-set route;
the business associate contract serves both that requirement and the
business-associate disclosure route. One node means one answer, so the same legal
question cannot be answered two ways in one assessment.

**P9. Cross-regime links are mappings, not equivalences.** Concepts in different
regimes are linked with W3C SKOS mapping relations, and only `relatedMatch` is used
so far. `exactMatch` is excluded by the validator: legal tests in different
systems are not interchangeable. Each mapping carries a note on how the concepts
diverge. This is the bridging-concept layer that Bella et al. (2020) propose
between per-jurisdiction knowledge bases.

**P10. Anchor the request onto the graph deterministically.** GraphCompliance's
largest ablation effect came from its context graph (removing it cost 10.2 F1
points, against 4.0 for the policy graph): normalising scenario facts onto the
policy vocabulary. Here the request already uses closed vocabularies (roles, data
statuses, arrangement types, purpose), so anchoring is a lookup table rather than
an LLM step. A binding says a fact *bears on* a node (`claims`) or contradicts it
(`denies`). Under the trust model of Chapter 3 a supplied classification is taken
as true only for the exact predicate it asserts. A non-partial binding can settle
that predicate. Negative inference from other filled values additionally requires
`exhaustive: true`, currently used for the asserted HIPAA capacity. A closed input
vocabulary is not an exhaustive list of ways to satisfy a legal test.
Purpose, arrangement status, GDPR relational roles, biometric labels and country
flags only bear on the qualified legal test (`partial: true`). In particular, a
negative EEA-to-non-EEA flag does not exclude an Article 3(2) exporter or an
international-organisation transfer. Unknown and other values remain open.
Bindings are validated against the request schema's `Literal` values.

**P11. Two layers, no copied text.** Text stays in `laws/*.md`; the graph holds
IDs, pinpoints and short quotes. Citation and amendment links remain in the
textual layer and are not duplicated.

## 4. Schema

**Node types**

- `requirement`: a catalogue item (GDPR and HIPAA, keyed by catalogue key) or a
  national requirement (Ireland). Its `role` is `applicability`, `obligation` or
  `national`. An optional `unit` says what it is owed at: `transfer` (the default)
  or `activity`, with a `basis` quoting one of the requirement's own sources.
- `route`: one statutory alternative for a requirement. It belongs to exactly one
  requirement, and may be marked `modelled: false`.
- `condition`: an atomic judgeable unit (≈ a GraphCompliance compliance unit). It
  has a `kind` (`scope`/`substantive`), an `actor`, `evidence`, and an optional
  `opening`. A scope condition carries evidence when relying on it relieves a duty
  (section 6).
- `concept`: a defined term (≈ a GraphCompliance premise; PrOnto's concept classes).
  The actor vocabulary points at concepts.
- `provision`: a corpus provision (textual layer).
- `request_value`: a closed-vocabulary request value (context layer).

**Edge types** (each with the CQ it answers)

| Edge | From → to | Meaning | CQ |
|---|---|---|---|
| `grounded_in` / `defined_in` | node → provision | quoted source | 1 |
| `uses_concept` | node → concept | its definition is needed to apply it | 1 |
| `has_route` | requirement → route | alternatives (OR) | 2 |
| `requires` | requirement/route → condition | conjuncts (AND) | 3 |
| `gated_by` | requirement → applicability requirement | regime must apply | 4 |
| `scoped_by` | requirement/condition → scope condition | arises only if | 4 |
| `excepted_by` | requirement/route → scope condition or route | displaced if (quoted) | 5 |
| `implemented_by` | opening condition → national requirement | supplies the opening | 6 |
| `corresponds_to` | concept → concept (other regime) | SKOS mapping + note | 7 |
| `claims` / `denies` | request value → condition or route | anchoring | 8 |

A binding marked `partial` bears on a condition without settling it: encryption is one
security measure among several, a transfer impact assessment may conclude either way, and a
treatment purpose does not show that the recipient is a health care provider.

## 5. Semantics

`kg.evaluate(requirement, facts, country=None)` gives the graph a precise meaning
over three values (true, false, unknown), so the structure can be tested and later
used by the verifier. `facts` maps condition and route IDs to true, false or
unknown; a route's own ID stands for its core text.

- A **condition** whose own scope is false does not arise. If its scope is unknown
  and it is not shown true, it is unknown.
- A **route** holds if its full core, scope and conditions hold and no exception
  applies. A false scope or true exception makes it unavailable. Unknown scope
  or exception keeps a positive result unknown. A `modelled: false` placeholder
  cannot establish permission.
- A **requirement**:
  - is not applicable if its gate is unmet or not applicable, its scope is false,
    or a requirement-level exception holds;
  - is also not applicable if every condition it imposes is out of scope and it
    has no routes (e.g. independent controllers need neither Art. 26 nor Art. 28);
  - otherwise is met if all its live conditions hold and, when it has routes, at
    least one route holds;
  - is unmet only if that fails *and* nothing that could change the answer is
    unknown (gate, scope or exception). Failure of all routes in an open list
    remains unknown. An unresolved exception keeps a failure
    open. This is GraphCompliance's reference closure ("check reachable exceptions
    before confirming a violation") expressed as a rule, not an extra LLM call.
- With `country="IE"`, an **opening** without a direct fact takes its value from
  the selected Irish requirement. A met enabling basis supplies the opening, but
  its failure does not exclude other national/Union law or a contract alternative.
  An `opening_kind: additional` condition instead represents additional duties:
  met or out-of-scope gives true, unmet gives false, otherwise unknown.

Statuses match the requirement records the verifier already produces (met, unmet,
undetermined, not applicable). `evaluate(..., gates=False)` evaluates one item on its own,
as one finding answers it; `route_value` evaluates one route; `conjunction` gives the meaning
of a route the graph does not model, made of conditions it does.

The verifier evaluates a checklist item **as described** (`decisions.as_described`,
`decisions.evaluate_items`):
- the answers of all the item's findings are merged; where findings disagree the node is
  unknown;
- supplied classifications decide what they settle (P10), unless an answer cites two
  supplied facts that conflict there, which leaves it open for clarification;
- once an obligation has been assessed, a route nothing in the request invokes (no supplied
  fact bears on it, none is cited for it) is unavailable as described: the requester
  describes how a duty is met. Applicability is never concluded from silence, so its
  routes stay unknown;
- an opening left to national law takes its value from the national requirement that
  implements it, from the national-law specialist's answers (`evaluate` with `country`);
- a delegated national question is moot when its opening cannot change the item (another
  route already decides it), and then raises no blocking gap.

## 6. Modelling decisions to be able to defend

- **Art. 49 subsidiarity is part of each full route core.** A derogation cannot be
  described as valid merely because the OR tree would already be met by adequacy
  or safeguards. The compelling-interest fallback also requires unavailability of
  the preceding derogations. Those prerequisites must be judged explicitly within
  the route statement; they are not inferred from the absence of another answer.
- **Art. 6(3) is two openings, not one.** It applies to both 6(1)(c) and (e), but
  the national basis differs: s. 38 Data Protection Act 2018 supplies public-task
  processing; a legal obligation's basis is whatever enactment imposes it (not in
  the corpus).
- **Transfer impact assessment** is grounded in Art. 46(1)'s second conjunct
  ("enforceable data subject rights and effective legal remedies ... are
  available"), read through Schrems II and EDPB Recommendations 01/2020. It is a
  separate condition from the SCCs themselves because it is shown by a different
  document.
- **US adequacy is partial**: Art. 45 covers a US recipient only if it is certified
  under the Data Privacy Framework (system reference data).
- **HIPAA applicability is a retrieval gate for either party.** Sender duties have
  their own scope. Covered-entity disclosure permissions are separate from a
  business associate's contract/law authority under 164.502(a)(3)-(4). Recipient
  safeguards distinguish covered entities under 164.530(c) and business associates
  under 164.504(e). Country alone establishes neither status. Special scope
  exclusions and operation-specific capacities remain a coverage boundary.
- **De-identification is applicability, not a permission.** De-identified
  information is not PHI (164.514(a)), so it sits under `hipaa.applicability`. Live
  run 42 filed it under the disclosure question, which triggered a gating bug.
- **Irish health research has both a basis and additional measures.** DPA 2018
  s. 54, subject to s. 42, supplies the selected Article 9(2)(j) basis. The Health
  Research Regulations impose separate safeguards, including where the Article 9
  route is explicit consent. Regulation 3(1)(e) uses the SI 18/2021 substitution.
  Chart review, deferred consent and declarations have qualified core statements;
  the alternatives are open and the transitional placeholder cannot establish
  compliance. Reaching these rules for non-special-category personal-data health
  research is still an unresolved gap.
- **Ethics approval, the data-protection assessment and governance measures are
  separate Irish conditions** because each is shown by a different document;
  Reg. 3(1)(a)-(d)'s many procedural measures share one evidence type and are
  bundled.
- **The 9(2)(a) proviso** is an exception predicate. Consent cannot establish the
  route until an applicable prohibition against lifting the restriction is resolved.

- **Evidence for scope conditions.** Chapter 3 asks for human-check flags on the
  material assertions a conclusion relies on, such as the reported treatment of
  identifiers. A scope condition that relieves a duty when relied on therefore names
  the document that shows it: an anonymisation or de-identification assessment for
  `gdpr.cond.material_scope` and `hipaa.cond.phi_involved`, a role determination for
  party roles and regulated status, a data specification for special categories and
  limited data sets, and a DPIA screening for `gdpr.cond.likely_high_risk`. Purpose,
  research purpose and whether data leave the EEA carry none: they are the transfer as
  described, and no separate document shows them. Evidence is asked for only when a
  favourable status depends on the answer (section 10), so a role that imposes a duty is
  never proved.
- **Either party can be the processor.** Both role labels are partial hints. The
  specialist must establish that one party acts on behalf of the other for this
  processing; a processor may have that role for an unrelated controller.
- **The disclosing party as an actor.** `sender` joins the actor vocabulary for
  `hipaa.cond.sender_regulated`, whose subject is the disclosing party whatever its role.
- **Some duties are owed once per activity, not per transfer.** The texts attach the
  DPIA to a "type of processing" whose single assessment "may address a set of similar
  processing operations" (Art. 35(1)), the records to "processing activities" (Art.
  30(1)), and a covered entity's safeguards to the entity, which "must have in place"
  them (164.530(c)(1)). WP248 (III.A, III.C) reads the DPIA the same way: none is
  needed for operations already studied, only for new ones or a change of risk. These
  three carry `unit: activity`. When a request says the transfer is one instance of
  an existing activity, the decision treats them as standing: confirmed once for the
  activity, blocking only on an explicit adverse fact. That is a workflow policy,
  not a statutory exemption or proof of a previously completed assessment. Everything else stays per
  transfer, including both security items, because the safeguards for each
  transmission (its channel and encryption) are checked for each transfer.
  Relationship-level agreements (Art. 26/28 arrangements, BAAs) are a candidate for
  the same treatment but are not tagged: whether one is needed depends on the
  parties' roles in this transfer.
- **Recital 91 limits "large scale".** `gdpr.cond.likely_high_risk` quotes Recital 91
  as well as Art. 35(1): an individual physician's or other health care professional's
  processing of patients' data is not large-scale, and a DPIA should not be mandatory.
  Without it, a single-patient treatment transfer (scenario 13) left the DPIA screening
  unknown, because the bundle offered nothing on what "large scale" excludes.

- **Art. 9(3) is an opening, answered for doctors by the Medical Council's guide (added 2026-10-06).**
  Art. 9(3) accepts secrecy "under Union or Member State law or rules established by national competent
  bodies", so `gdpr.cond.art9_3_professional_secrecy` carries that phrase as its opening, implemented by
  `ie.medical_professional_secrecy`. Its sources: Medical Practitioners Act 2007 s. 7(2)(i) (the Council
  specifies standards of practice and guidance on professional conduct and ethics; LRC revised text) and
  the Council's Guide to Professional Conduct and Ethics, 9th ed. (2024), para. 25.2 ("Doctors have a
  professional and ethical duty to maintain patient confidentiality"). Reading the guide as such "rules"
  is an interpretation: the guide says "It is not a legal code", and the node quotes that too. It covers
  registered medical practitioners only (guide n. 1); other professions' and statutory secrecy duties are
  not modelled, so a failed Irish answer leaves Art. 9(3) open, not failed. Only the Introduction and
  para. 25 are in the corpus.

## 7. Coverage and remaining limits

The 2026-10-07 definition addition links `ie.cond.health_practitioner_responsibility` to
`ie.concept.health_practitioner`. Its sources include the complete Health Identifiers Act 2014
s. 2(1) definition and the Medical Practitioners Act 2007 s. 2 definitions of registered medical
practitioner and register, retaining the section 56A qualification. The Irish healthcare bundle now
contains these texts even when vector search returns no hits. Curated definition links in
`reference/legal_relationships.json` also bring the same chain when DPA s. 52 is retrieved directly.
This supplies missing law, without determining whether any case satisfies that law. Other referenced
professions' Acts and all subsequent statutory cross-references are not comprehensively included.
The targeted source snapshots and checks are under `audit/2026-10-07`; earlier audits remain dated
records of their original corpus versions.

- Condition answers are keyed by node, not independently by actor and operation.
- Irish health-research safeguards for ordinary personal data need a separate path.
- Irish openings without an implementation: Art. 6(3) for 6(1)(c), Art. 9(2)(b), 9(2)(g) and 49(4)
  (DPA ss. 46-51 are not in the corpus). The public-task chain (s. 38) needs the enactment conferring
  the controller's function (for the HSE, Health Act 2004 s. 7), which is not in the corpus.
- Onward transfers, purpose compatibility, many individual rights and national
  measures are not independently decomposed; the checklist is bounded.
- HIPAA special scope exclusions, other federal rules and US state law are incomplete.
- Several legal tests remain bundled in full statements. Fact-pointer validation
  checks that cited facts exist, not that they entail the entire legal test.
- HHS reports vacatur of most of the 2024 reproductive-health rule. A dated notice
  accompanies affected sources through `reference/legal_status.json`; this is not
  a machine-enforced effective-law filter.
- Art. 35(10), all six HIPAA minimum-necessary exception categories, and selected
  Article 9(4) national conditions are now represented. They are no longer listed
  as wholly omitted.

The audit report sets the acceptance criteria for a future freeze.

## 8. How it is checked

`kg.validate()` (run by the tests) enforces:

- unique, regime-prefixed IDs;
- every quote found verbatim in its cited provision;
- known interpretive references, evidence types and actors;
- typed edges: scopes are scope conditions, gates are applicability requirements,
  exceptions quote their text, only openings are implemented, and mappings are
  cross-regime SKOS relations other than `exactMatch`;
- the shared-provision-or-quote rule for links;
- closed route sets with at least two alternatives;
- a unit from the vocabulary, and a unit other than `transfer` quoting its basis
  from one of the requirement's own sources;
- no orphan conditions or concepts;
- bindings that use the request schema's real fields and values;
- the same requirement set as the catalogue, with the graph reaching every
  catalogue anchor.

The tests also mutate the graph to show the validator catches each kind of error.
These checks cannot establish legal entailment from shared citations. The dated audit
adds official publisher snapshots, a hash manifest, 303 quote checks, a complete edge
inventory, requirement-level interpretation reviews and legal counterexamples.
Run `.venv/bin/python audit/2026-10-05/check_sources.py` for the offline evidence check.
An independent 2026-10-06 audit
(`audit/2026-10-06/REPORT.md`, scripts `check_corpus.py` and `check_graph.py`) re-checks every
provision and quote against texts downloaded that day.

**Bundle adequacy against live runs.** Before bundles replaced search, they were
compared with the provisions specialists actually cited in live runs 41 and 42. The
first version missed six cited provisions that answer checklist questions, and they
were added to existing nodes:
- Art. 12(2), for rights;
- 164.502(d)(2), "the requirements of this subpart do not apply" to de-identified
  information, and its rule that disclosing a re-identification code is disclosing
  PHI;
- 164.514(c), re-identification codes;
- 164.508(c), authorization core elements;
- the 164.512 introduction;
- 164.306, security general rules.

The historical runs also cited provisions outside the initial bundles. Some remain
outside the bounded checklist:
- Arts. 15-19 individually, Art. 25 and Recitals 75 and 84;
- 164.402 (breach), 164.512(a) and (f).

The audit added 164.310, 164.314 and 164.316 to the security bundle.

The supervisor can add any of them to a specialist's sources by ID in a follow-up.

## 9. Size

As audited on 2026-10-05: 276 nodes and 471 edges, including 20 requirements
(15 catalogue and 5 selected Irish), 52 routes, 67 conditions and 21 concepts.
After 2026-10-06 (Art. 9(3) opening): 281 nodes, 21 requirements (6 Irish) and 68 conditions;
see audit/2026-10-06/REPORT.md.
There are 46 bindings and 5 non-inferential concept mappings. The exact typed
inventory and graph hash are in `audit/2026-10-05/verification.json`.

## 10. Wiring into the v9 assessment

- Fixed checklist items use `kg.bundle` for initial source packs.
- `agents.guidance` presents conditions and alternatives without request anchors or decided predicates.
- Specialists may request bounded retrieval within their regime. GDPR requests national-law children.
- National questions can name an opening; `agents.national_target` uses `kg.implementation` to pin
  the national sources. A missing mapping does not prevent vector retrieval of the stated question.
- Child answers go back to GDPR for a targeted reassessment. Python does not evaluate the opening
  to calculate the parent finding's status.
- `app/review.py` checks reference/coverage integrity. `app/requirements.py` maps specialist status
  names to display names directly. Evidence support comes from explicit agent-selected evidence IDs.
- `kg.evaluate`, request bindings and semantic helpers are retained for offline graph audit tests only.
  Their audit tests establish the authored graph's behavior, not v9 legal accuracy.

The removed runtime modules are `app/decisions.py` and `app/national.py`. Source-law text and
reference graph data are unchanged. Graph consistency still depends on the quality of its authored
relations; quoting the right source alone does not certify a legal judgment.
