# Corpus-driven engine

No law, regime, jurisdiction or requirement is named in code. Everything comes from `corpora/`.

```text
corpora/registry.json      jurisdictions (registry codes, membership) and the list of corpora
corpora/<id>/corpus.json   name, level, territory, parent/children, unit word, instruments (file, prefix, aliases)
corpora/<id>/*.md          provisions headed "## [ID] Title"

1. Load corpora                                                         [Python]  corpus.py
   Parse provisions; build the citation graph from the prose (own-instrument refs, ranges,
   "of the <alias>", "of that Regulation", unit-word mismatch -> nearest earlier instrument).
   Chroma + MiniLM index over passage-packed windows.
2. Validate the case against registry jurisdiction codes; label FACT PASSAGES   [Python]  schema.py, facts.py
3. Supervisor plan: sees the case + every corpus manifest and table of contents;  [LLM]  agents.plan
   one engagement per top-level corpus, with facts. Lower-level corpora only by delegation.
4. One specialist per engaged top-level corpus, in parallel (2 workers)            [LLM]  agents.assess
   Reads only its corpus via kg_node / search_law / read_provision (TRAVERSAL_TOOLS=0:
   whole corpus in context). Identifies the requirements the facts engage (no checklist),
   assesses each with routes, gaps, facts and quotes; delegates down to its children;
   raises peer questions about other jurisdictions' law.
5. Delegation round: each child answers its parent's questions and reports further  [LLM]  agents.answer_questions
   requirements of its own law; the parent reassesses with the answers.
   Every reassessment returns a patch (SpecialistPatch: changed/new requirements,     [LLM]  agents.assess(prior=...)
   withdrawn ids, impact) that Python merges by requirement id; unchanged ones stay.  [Python] pipeline.merge
6. Supervisor synthesis: reads LAW BEHIND THE FINDINGS (the passages each           [Python] pipeline.Run.law
   specialist was shown from the provisions its findings and routes cite) and owns    [LLM]  agents.synthesise
   the combined conclusion: one route per engaged gate that work together (route_plan),
   an outcome, conflicts (incompatible_law / disagreement), with quote_ids from that law.
   It may request one bounded round of follow-ups: routings of open peer questions,
   and corrections that name corpus, requirement ids, error kind and the passages
   showing it. Python drops a correction with unknown requirements, unshown passages,
   or (contradiction / unsupported_status) no passage; it answers routed questions,    [Python] pipeline.Run.route
   then reassesses askers and correction targets (instruction + passage text).
   Then a final conclusion pass (SupervisorConclusion, no follow-ups).               [LLM]  agents.synthesise(final)
   CORRECTION_ROUNDS (default 1; 0 = the first pass is final).
7. Verify every requirement and route: facts supplied, cited law actually read by     [Python] pipeline.verify
   that agent, quote shown to it and from a cited provision. Verify the conclusion:   [Python] pipeline.check_conclusion
   passages shown to the supervisor, refs and planned routes exist, a "satisfiable"
   plan covers every engaged gate, a "not satisfiable" conclusion cites a passage.
8. Decide from verified statuses (refusal: a verified unmet gate, or a verified       [Python] pipeline.decide
   not_satisfiable_together conclusion; hold: defects, undetermined gates or outcome,
   conclusion defects, unanswered questions, unresolvable conflicts, supervisor
   blockers; else proceed with or without conditions).                                [Python] pipeline.supervisor_items
   A supervisor blocker blocks only if it names a gate in play and, where that gate lists confirmations, says why
   they are not enough; otherwise it becomes a note. "undetermined" blocks only while a blocker or unresolvable
   conflict remains. An unanswered peer question does not block when the requirement it was asked for is a verified
   met / not_applicable finding or a duty (pipeline.blocking_question): it concerns a route the decision does not use.
9. Brief: known / required / missing / routes / conflicts.                           [Python] brief.py

Scoring (offline, after a run): engine/score.py + score_mock.py compare a saved run with cases/<case>/key.json.
Findings are matched to key items by the provisions they cite (definitions ignored; a finding is "about" an item
when >= half its substantive citations are listed), never by requirement id. Reports requirement status, routes,
conflicts, routed questions, traps, and blocking findings the key does not explain. Runs saved before the rename
are translated (APIR -> A-REG, aster -> region_a, ...).
```

Each corpus agent keeps one read record across all its calls, so law it read earlier stays citable.
Each corpus reports only requirements created by its own instruments; other corpora's law reaches it as answers.
A lower-level delegate files every engaged obligation of its own law as a requirement, asked about or not, and its
answers point to them by id; each report replaces its previous one, so every call (delegation, routed
question or revision) shows it its previous report. A top-level corpus answering a peer question sees its current
findings (status, reasoning, routes) under ALREADY REPORTED, must answer consistently with them (or say plainly which is
wrong, for a separate revision) and adds only requirements its own assessment lacks.
Peer questions ask only what another jurisdiction's law provides on a point the asker's own requirement depends on.
Ownership: specialists own their findings; the supervisor owns how they combine. It may point out a specific error from
the passages, but never tells a specialist what status to give; for a disagreement it sets out both positions for the
owner. It folds a route-shaped requirement only within its own corpus, applies the specialists' evidence policy (agents.EVIDENCE), puts
confirmations, duties and unchosen fallback routes in notes, never blockers, and records a disagreement that survives the correction round as a non-resolvable conflict with
outcome undetermined (needs_review). Specialists read every correction as "what to reconsider; keep your finding if your
law supports it". The supervisor has no tools: it reads only the passages behind the findings. Tool budget per call (tools.budget): MAX_TOOL_CALLS per corpus in scope, never fewer than the
provisions in scope (Region A 34, single agent 64 at the default 20).
Answers carry their law (pipeline.answer_law): every answer handed to its asker (delegation or routed peer question)
includes the selected quote and the text of each cited provision of the answering corpus that its agent read, as shown
to it, plus issues for citations it could not support (unread, unknown or another corpus's). The asker reasons from that
text but cannot cite it (only its own reading is citable). Python adds text; it decides nothing.
Coverage warnings (pipeline.Run.coverage): provisions of an agent's corpus that are cited by law the agent relied on
and that it never read, from the citation graph. Shown to the supervisor in every review, and to the agent when it
is reassessed or revised. Structural only; they decide nothing.
Route statuses: supported (in place), available (a route forward the parties could adopt via required_actions),
ruled_out (no change could make it work), unresolved, not_investigated.
Peer questions: each asker sees the questions it already asked with their answers; Python drops a question that
mostly repeats an earlier one to the same jurisdiction (word overlap >= 0.6 of the shorter), even under a renamed requirement.
Single-agent baseline (ARCHITECTURE=single, or the UI's Architecture switch): steps 3-6 are replaced by one LLM call
(agents.single, SingleAssessment). One agent sees the case and every corpus manifest + table of contents, with tools
scoped to all corpora (budget MAX_TOOL_CALLS x number of corpora; TRAVERSAL_TOOLS=0 gives it every corpus as full
text). Its prompt is the specialist METHOD + RULES (minus the own-instruments ownership rule) + the supervisor's
applicability and conflict rules; each requirement names the corpus whose instrument creates it. No delegation, peer
questions, coverage warnings or review rounds. Steps 7-9 are unchanged; its conflicts and unresolved stand in for the
final review. Saved runs record "mode".
Run: `.venv/bin/python run_mock.py cases/01_a1_gp_to_region_b_host`. Keys in `cases/*/key.json` never reach the model.
