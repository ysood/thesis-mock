# Transfer compliance prototype, v17

Assesses a supplied cross-border health-data transfer under GDPR, HIPAA and delegated Irish law.
All example parties are fictional. Outputs are conditional assessments of supplied facts, not legal advice.

## Run

Use the existing local environment and configured model:

```bash
.venv/bin/streamlit run ui.py
```

Edit an example, run it and download the full trace. Select **Offline fake model** to exercise
execution and rendering without model API calls. The scripted fixture deliberately leaves legal
questions unresolved; it is not a benchmark of legal accuracy.

```bash
.venv/bin/python run.py scenarios/case_study_a_ie_gp_to_ie_cloud_ehr_domestic.json --fake --verbose
.venv/bin/python -m unittest discover -s tests -q
```

For real assessments, configure `.env` from `.env.example` with `MODEL` and the provider key,
then run the UI or omit `--fake` in the CLI. Each real run invokes the configured paid provider.
The existing `.venv` and `.chroma` index are reused. Dependencies are in `requirements.txt`.

OpenAI calls now use API-enforced Structured Outputs (`json_schema`, `strict: true`)
from the existing Pydantic response models. Each call's factual references are limited
to the actual supplied `f_` IDs, including initial plans, national answers and revisions.
The API schema requires every field and forbids extra keys; unused fields use empty
lists/strings or `null` where the existing model permits it. Saved models are unchanged.
Tool-using calls keep the same response format through lookup and the final reply.
Python still validates output and verifies source/decision consistency. Strict shape
does not prove that a selected fact supports the reasoning or that a legal status is correct.
Other providers retain prompt-based JSON. OpenAI errors do not silently fall back to that mode;
API refusals/incomplete replies are execution failures and are not retried as formatting errors.
The trace records `output_format`, `response_schema` and `fact_choices` on `llm_request`.
No new agent phase or tool/review budget is added. Model support must be verified in a live run.

## Responsibilities

v15 uses one input format throughout: `organisations → transfer → evidence`.
`transfer.sender` and `transfer.recipient` refer to organisation IDs. Identifiability remains
`identified`, `coded`, `anonymous` or `unknown`; agents assess legal classifications. Storage
(`locations.stored_in`) and access (`locations.accessed_from`) remain separate. Evidence is read
directly, with an optional `attested_by` naming the supplied person/role; `between` still specifies
the organisations covered. No attester is synthesized.

Python validates the input and standardizes country codes, retaining omitted fields and explicit
unknowns. `case_record.input` contains that one validated input plus `reference_facts`, with no
`submitted`/`request` copies, generated legal labels or converted attestations. Agents and the fact
checker all use this same shape, for example `/organisations/0/country`,
`/transfer/data/categories/0` and `/evidence/0/summary`. Stored country metadata is collected from
both location lists without replacing them; geography flags are not legal conclusions.

Older input formats are intentionally rejected. `scenarios/` holds the two case studies: case study A (domestic
Irish GP cloud EHR) and 28 (Irish GP to a US cloud EHR). Fixed test inputs live in `tests/fixtures/`.

Input references now use source-bound passage selection: each agent receives the original JSON plus
labelled `FACT PASSAGES` and returns `{"fact_id": "f_..."}` for each reference. Python copies the exact
text and its JSON pointer together, including for supervisor intake/corrections and national-law answers.
Sentences stay whole so a negated list cannot become an invented shorter quotation. Saved reports retain
readable `fact_id/path/quote` references. Unknown IDs and altered saved pairs are reference defects;
agents still judge whether selected facts support their conclusions. No extra model call is added.

1. Supervisor interprets roles, data and activity scope, then assigns initial review plans or explains exclusions.
   Routing rubrics in `reference/applicability/` (HIPAA so far) guide that choice: inclusion cites engaging facts,
   exclusion cites facts and states a rebuttable assumption (reported in `result.exclusions`). A rubric regime routed
   without facts gets a non-blocking `checks.routing_warnings` entry. To test routing alone (one model call per case):
   `.venv/bin/python scripts/probe_routing.py tests/fixtures/hipaa_routing_probes.json`.
   v11: specialists can also traverse the KG and read further law during their call (`app/traversal.py`;
   `TRAVERSAL_TOOLS=0` turns this off, `MAX_TOOL_CALLS` caps it at 8 per call).
   Search hits remain IDs, titles and scores. Opening a provision adds up to 12 one-hop KG suggestions
   (IDs, types, relationship directions and labels of at most 120 characters), containing other
   provisions connected by citation/amendment/definition links. No linked legal text is fetched or
   made citable automatically. In v15, `kg_node` accepts provision IDs only and exposes outgoing
   and incoming citation/amendment/definition links, including omitted suggestions. There are no
   requirement, route, condition or concept nodes in the runtime graph.
   `read_provision(provision_id, start=0)` pages whole labelled passages, targeting
   6,000 source-text characters (one oversized passage is returned whole).
   Continue with the same ID and returned `next_start`; each page costs one tool call.
2. Assigned GDPR/HIPAA specialists execute independently in parallel. They own statuses, reasons, fact references
   and evidence support. The fixed checklist provides starting provision IDs. Specialists identify
   routes, prerequisites and exceptions from the source text; no authored KG guidance is injected.
   Each finding explains `route_coverage`; alternatives/exceptions needing individual
   treatment have compact `routes` with actor/activity scope, status, decisive reason,
   citations and a shown quote ID. A simple duty or applicability exclusion needs only
   the explanation. The record appears with the finding in the UI and saved report.
   Route statuses distinguish assessed support/exclusion (`supported`, `ruled_out`),
   an assessed gap (`unresolved`), and an optional fallback whose feasibility was
   deliberately left unassessed (`not_investigated`). A deferred fallback names the
   supported route that suffices for the same actor/activity. Mandatory prerequisites,
   safeguards, restrictions and exceptions to that route still need assessment.
3. Specialists can request bounded extra legal retrieval. GDPR owns national-law delegation and reassesses
   affected questions after child answers arrive.
4. Supervisor reviews current findings, challenges specific issues, reconciles and explicitly accepts finding IDs.
   It owns the final decision. A status change requires the responsible specialist's revision.
   It receives the assigned checklist's starting law as well as cited law, so omitted
   alternatives remain reviewable. It checks source clauses, including exceptions and cumulative
   duties. A failed national branch does not close unresolved alternatives.
   A route challenge identifies the specific branch or mandatory duty, why existing
   reasoning does not settle it, and what focused check would. Justified optional
   deferrals do not require further research solely to finish every alternative.
   Refusal needs a verified unmet main transfer gate or explicit incompatibility between
   conclusive, verified main transfer findings. This uses existing calls and budgets.
5. Python executes calls, stores current state, validates references and coverage, and renders the report.
   It preserves legal statuses even when references fail and holds defective reports as `needs_review`.
   Question `coverage.complete` means all assigned questions received answers;
   it does not certify that every legal alternative or graph path was checked.

Agent requests share `app.requests.prepare_request`, which validates references and normalizes ID
formatting before execution. This uses the existing typed JSON protocol and adds no model call.
Legal retrieval combines exact IDs/vector search with curated amendment and definition links.
The Irish corpus includes the Health Identifiers Act's complete health-practitioner definition and
the referenced Medical Practitioners Act definitions, linked to DPA 2018 s. 52. See the
[targeted source verification](audit/2026-10-07/REPORT.md). Restart the app after corpus changes;
the local vector index rebuilds when its chunk fingerprint changes, then is reused.
Each search chunk retains its provision ID and title. Short provisions stay whole; longer ones
are packed at paragraph or numbered-clause boundaries, falling back to sentences, words and
finally characters only for an oversized unit. The complete chunk, including its heading,
must fit the default MiniLM tokenizer's 256-token limit. There is no fixed word overlap;
retrieval still resolves matches to the original provision text. Changing the corpus or chunking
requires re-embedding once, not on every search. This does not refresh law texts or call a paid model.

The usual path uses two supervisor calls, initial interpretation and final review, plus one call per assigned
main specialist. Retrieval, national-law questions or targeted revisions add calls only when requested.
Calls are stateless; orchestration is stateful through the case record. Unaffected findings retain their IDs.
Superseded model responses stay in the trace, rather than accumulating in prompts.
Legal sources shown to specialists have labelled structural passages, without a 40-word cap.
Quotation splitting preserves blank-line paragraphs and numbered blocks, retaining subordinate
list items and colon-led numbered lists with their introduction. Ambiguous/unmarked structures
remain whole; this is a conservative text-formatting rule, not a full legal hierarchy parser.
Long blocks remain selectable intact, so some saved quotations and review contexts can be longer.
Embedding windows and their index are unchanged. A finding selects
`quote_id`; Python copies that passage into the saved `quote`. IDs are bound to the exact provision,
source span and content. Unknown, unread or uncited IDs fail reference checks, including passages beyond
a tool read's text limit. This prevents wording drift, but does not prove the passage supports the judgment.
Existing saved findings with text quotes remain readable; new runs use v2 passage IDs.
Route quotes use the same shown-passage checks; route-only law remains available during
supervisor review, targeted revisions and national-child source handoff. Structural checks
cannot guarantee that a model discovered every relevant route in the supplied corpus.
v15 retains the v14 shared prompt structure, with fact-reference instructions updated for the single input.
GDPR alone receives national-law delegation instructions, children receive national-role instructions,
and revisions receive reassessment instructions. Existing evidence, corpus and assessment-as-described
policy text and switches are retained. The supervisor retains its legal review and policy instructions.
Supervisor plans leave national-law delegation to GDPR. Research warnings surface declared legal
gaps without a corresponding attempt or stopping explanation for supervisor review, without forcing
calls or changing legal statuses. The supervisor can correct or withdraw its own intake claims in
the existing review response; Python rechecks quotations and retains prior intake if a replacement
is invalid. Exact quotation checks do not establish that a claim's meaning is supported.

The final report includes `case_record` with one read-only input snapshot, supervisor sections, current specialist
outputs and separate checks. [architecture.md](architecture.md) charts information flow and writer ownership.
[pseudocode.md](pseudocode.md) gives the execution steps and budgets.

Evidence authenticity is assumed for this prototype. The UI provides fill-in evidence templates in the input's schema.

Design decision, evidence presence (v10): a supplied evidence item that addresses a requirement for the named
parties and activity establishes it, and elements its summary omits become confirmations. It is a prompt rule for
specialists and the supervisor, not a Python status calculation, and it does not supply missing law, outside facts
or applicability. Evidence about other parties or activities, or with adverse content, is decided on its content.

Design decision, closed-world corpus (v11): starting passages are a selection
from the available stored corpus. Before dismissing a relevant restriction or national condition, specialists
must make a focused check of relevant law or explain from read law and case facts why the dependency does not
apply. GDPR delegates national checks when needed, including cumulative safeguards alongside a supported GDPR
route. The supervisor reviews this reasoning even for satisfied findings with no research warning. Once a
focused check finds no restriction, it is treated as absent and reported as a confirmation ("confirm none applies
outside the supplied corpus"); repeated proof of absence or exhaustive KG exploration is not required. Unavailable
law or exhausted budgets are research limits, not proof of absence. Enabling rules still need a source stating
them. These prompt rules do not add automatic delegation or a Python legal judgment. Conclusions remain limited
to the curated corpus (`laws/`), not all of the law.

Design decision, assessment as described (v11): the requester's stated facts and
listed arrangements are taken as complete. A requirement whose every route fails on the described facts (e.g. the
only transfer mechanism is unsigned SCCs) is not met as described, with the cure stated, and a failed gate leads to
`do_not_proceed`. `needs_review` is kept for ambiguous or inconsistent decisive facts, missing or disputed law and
reference defects. This is the facts-side counterpart of the closed-world corpus: the system assesses the transfer
as described, against the curated law.

v12 decision rules (code, status consistency): one verified, unmet, transfer-level gate in an applicable regime
gives `do_not_proceed` even if other matters stay open or other findings have reference defects (they are listed as
further issues). Approvals stay strict. `proceed` with any conditions or outstanding evidence is reported as
`proceed_subject_to_conditions`. The supervisor's own choice is kept as `proposed_decision`.
National-law questions are selected by GDPR; Python no longer adds companion questions for additional openings.
Article 9(4) remains in the stored Article 9 text. GDPR can request a national-law review by a
specific question and referring GDPR provisions, without a predefined opening or implementation node.
Suggestions support discovery but do not guarantee that an agent investigates every applicable restriction.

Decisions are `proceed`, `proceed_subject_to_conditions`, `do_not_proceed`, and `needs_review`.
Saved older runs retain their legacy names. Scenario expectations written for older versions are historical
assertions, not legal ground truth; compare their reasoning and facts before interpreting decision matches.

## Files and verification

- `app/schema.py`, `app/case.py`: input/output schemas and case ownership.
- `app/supervisor.py`: interpretation, parallel initial dispatch, targeted review and acceptance.
- `app/agents.py`: specialist assessments, bounded retrieval, national-law children and reporting.
- `app/review.py`, `app/requirements.py`: integrity checks and direct requirement display.
- `app/knowledge.py`, `app/traversal.py`: stored law, vector retrieval and provision-only graph lookup.
- `app/graph.py`, `app/llm.py`: graph wiring, model calls and full trace.

Removed from runtime and deleted: `app/decisions.py` (graph-derived statuses/trust overrides) and
`app/national.py` (Python dependency/status reconciliation). The unused standalone intake/planner/reconciler,
code coordinator, alternative-group handling, automatic evidence matching and full-assessment carry-forward
helpers are also removed. Their v8 implementation remains in Git history.

The v5-v8 KG rule evaluator and request-field bindings were removed in v13 to keep the code to what the pipeline uses; they remain on branch v12.
The earlier normative model and its design notes are archived under
`reference/archive/normative_kg_v15/`; they are not loaded by the runtime. The existing
[graph audit](audit/2026-10-05/REPORT.txt) documents that historical model. Stored law and
legal-status notices remain unchanged. See [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md) for the current design.

Offline tests cover ownership, unknown preservation, parallel dispatch, national delegation, retrieval,
targeted/failed revisions, provenance, source integrity, immutable input, UI and model-call failures.
These tests do not prove real model legal accuracy or measured token savings. Evaluate real scenarios before freezing.
