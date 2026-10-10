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
6. Supervisor review loop (max 3): routes open peer questions to the corpus whose   [LLM]  agents.review
   law answers them, records conflicts (resolvable + route), requests revisions.
   Python answers routed questions, then reassesses askers and revision targets.     [Python] pipeline.Run.route
   If the budget ends right after changes, one last review is taken without acting on it.
7. Verify every requirement and route: facts supplied, cited law actually read by     [Python] pipeline.verify
   that agent, quote shown to it and from a cited provision.
8. Decide from verified statuses (refusal: a verified unmet gate; hold: defects,      [Python] pipeline.decide
   undetermined gates, unanswered questions, unresolvable conflicts, supervisor unresolved;
   else proceed with or without conditions).
9. Brief: known / required / missing / routes / conflicts.                           [Python] brief.py
```

Each corpus agent keeps one read record across all its calls, so law it read earlier stays citable.
Each corpus reports only requirements created by its own instruments; other corpora's law reaches it as answers.
Route statuses: supported (in place), available (a route forward the parties could adopt via required_actions),
ruled_out (no change could make it work), unresolved, not_investigated.
Peer questions: each asker sees the questions it already asked with their answers; Python drops a question that
mostly repeats an earlier one to the same jurisdiction (word overlap >= 0.6 of the shorter), even under a renamed requirement.
Run: `.venv/bin/python run_mock.py cases/01_a1_gp_to_region_b_host`. Keys in `cases/*/key.json` never reach the model.
