# Case 05 runs for analysis

`case.json` and `key.json` are copies of `cases/05_a1_genetic_second_opinion_in_b` (key as source-reviewed
11 Oct 2026; see its `revisions` field and the case README). Each folder holds one configuration; `runN.json` files are
saved runs copied unchanged from `runs/mock/`. Each file records `mode` (single/multi) and `graph`
(runtime/generated), so the folder can be checked against the file.

| folder | architecture | knowledge graph |
|---|---|---|
| `single_no_graph` | single agent, one call | runtime citation graph |
| `single_graph` | single agent, one call | generated normative graph |
| `multi_no_graph` | multi-agent | runtime citation graph |
| `multi_graph` | multi-agent | generated normative graph |

| run | single_no_graph | single_graph | multi_no_graph | multi_graph |
|---|---|---|---|---|
| run1 | 20261011-083550 | 20261011-083546 | 20261011-084256 | 20261011-084102 |
| run2 | 20261011-085037 | 20261011-085051 | 20261011-085647 | 20261011-085538 |
| run3 | 20261011-090442 | 20261011-091147 | 20261011-091145 | 20261011-091133 |
| run4 (medium effort) | 20261011-124822 | 20261011-124824 | 20261011-125108 | 20261011-125049 |
| run5 (medium effort) | 20261011-125912 | 20261011-125916 | 20261011-130155 | 20261011-130034 |
| run6 (medium effort) | 20261011-130630 | 20261011-130644 | 20261011-130901 | 20261011-130849 |
| run7 (low effort) | 20261011-131301 | 20261011-131258 | 20261011-131357 | 20261011-131414 |
| run8 (low effort) | 20261011-132311 | 20261011-132325 | 20261011-132403 | 20261011-132428 |
| run9 (low effort) | 20261011-132556 | 20261011-132632 | 20261011-132649 | 20261011-132748 |

Runs 1-3 used the default `REASONING_EFFORT=high`; runs 4-6 used `REASONING_EFFORT=medium`; run 7 onward used `REASONING_EFFORT=low`. Runs 4 onward also set `MAX_TOKENS=40000`. Same model throughout (gpt-5.6-luna).

Score every configuration against `key.json` (pass counts per check, mean cost, and a check that
each run's recorded mode/graph matches its folder):

```bash
.venv/bin/python analysis/score_case.py analysis/case_05
```

## Results: raw matching and evidence-reviewed selected checks (runs 1-9)

All 36 completed runs were reviewed against the same draft `key.json`: 16 selected checks per run, 576 checks in total. The offline review repaired 49 false failures and removed two false passes. Raw provision/status matches are preserved, and the model responses and key were not edited. All 24 high/medium runs and 9 of 12 low runs reached the expected `do_not_proceed` decision. The other three returned `needs_review`, not an approval.

The review accepts explicit correct assessment of a selected concept anywhere in the accepted final output, including combined findings, applicability explanations and review notes, using the same criterion for every architecture. Correct references alone are insufficient. This measures selected-concept agreement, not complete legal accuracy. The draft key still requires author sign-off.

| effort and score type | single_no_graph | single_graph | multi_no_graph | multi_graph |
|---|---|---|---|---|
| high raw | 12, 12, 14 (mean 12.67) | 14, 14, 14 (mean 14.00) | 15, 14, 13 (mean 14.00) | 16, 16, 15 (mean 15.67) |
| high reviewed | 15, 16, 16 (mean 15.67) | 16, 16, 16 (mean 16.00) | 15, 14, 15 (mean 14.67) | 16, 16, 16 (mean 16.00) |
| medium raw | 14, 13, 14 (mean 13.67) | 14, 14, 13 (mean 13.67) | 16, 16, 13 (mean 15.00) | 16, 16, 16 (mean 16.00) |
| medium reviewed | 15, 16, 16 (mean 15.67) | 16, 16, 16 (mean 16.00) | 16, 16, 16 (mean 16.00) | 16, 16, 16 (mean 16.00) |
| low raw | 7, 9, 11 (mean 9.00) | 15, 14, 15 (mean 14.67) | 10, 15, 14 (mean 13.00) | 16, 16, 16 (mean 16.00) |
| low reviewed | 10, 10, 15 (mean 11.67) | 16, 16, 15 (mean 15.67) | 10, 16, 15 (mean 13.67) | 16, 16, 16 (mean 16.00) |

| effort: mean seconds / captured output tokens | single_no_graph | single_graph | multi_no_graph | multi_graph |
|---|---|---|---|---|
| high | 162.4 / 11,577 | 167.6 / 12,402 | 575.8 / 56,085 | 507.4 / 56,547 |
| medium | 70.8 / 6,626 | 81.0 / 7,147 | 237.3 / 25,316 | 203.1 / 24,828 |
| low | 51.3 / 4,521 | 70.0 / 5,007 | 111.0 / 13,743 | 147.7 / 17,855 |

Interpretation (n = 3 per cell):

- Generated-KG configurations reached the expected low-effort decision in all six observed runs. Citation-graph configurations missed the decisive consent restriction in three of six, but held those transfers for review.
- After reviewing citation placement and combined findings, the single-agent KG condition is close to multi-agent KG on selected checks: low scores 16, 16, 15 versus 16, 16, 16. The original raw totals overstated their difference.
- Region B scope reasoning is present in the single-agent high/medium outputs. Raw missing operational-duty findings/citations are not automatically failures to understand applicability.
- Two previously passing lawful-ground checks are unsupported: single_no_graph run4 and multi_no_graph run9 establish the sensitive-healthcare condition but do not independently establish an ordinary Article 6 ground.
- The selected checklist does not capture several substantive gaps. All low multi_graph runs inadequately justify excluding the general Article 12(1) risk test; medium runs4/5 have similar issues, while high runs1-3 preserve uncertainty. Several outputs omit recipient responsibilities or broader notice, recordkeeping and security coverage.
- Low multi_graph is 70.9% faster than high and 27.3% faster than medium, with 68.4% and 28.1% fewer captured final-response output tokens respectively. Intermediate tool responses and retries are not fully logged, so this is not a dollar-cost estimate.
- This is one deliberately constructed fictional cross-corpus challenge with a reviewed normative graph. High output cap differs from medium/low, effort configuration is inferred from cohort notes, the key was reviewed post-run, and a known incomplete attempt is missing from completed-run reliability totals.

The complete correction ledger is `score_reviews.json`, mirrored in the source case for the UI/CLI. `scorer_fix_20261011/corrected_scores.json` contains before/after scores; `before_after_scores.png` and `.svg` show the comparison. `scorer_fix_20261011/before/` preserves the prior scorer, exports, hand corrections, README and evaluation. The earlier `evaluation_20261011` figures remain raw automated snapshots.

## Unguarded baseline: full corpus in the prompt (branch v4)

`baseline_corpus/` (runs 1-9) holds `ARCHITECTURE=baseline BASELINE=corpus` runs: one call with the case, the corpus manifests and tables of contents, and the full text of every corpus in the prompt; no tools, strict schema, supplied-ID restriction, corpus-only or evidence rules, method steps, delegation or review. The output contract (schema as text, status, kind and route definitions) is kept, so the same scorer applies. Numbering differs from the system folders: baseline runs 1-3 are low effort, 4-6 medium, 7-9 high.

| run | effort | file | model's decision | decision from its gates | checks passed |
|---|---|---|---|---|---|
| run1 | low | 20261011-234605 | proceed_subject_to_conditions | do_not_proceed | 13/16 |
| run2 | low | 20261011-235612 | proceed_subject_to_conditions | do_not_proceed | 11/16 |
| run3 | low | 20261011-234603 | proceed_subject_to_conditions | do_not_proceed | 12/16 |
| run4 | medium | 20261011-234845 | proceed_subject_to_conditions | do_not_proceed | 11/16 |
| run5 | medium | 20261011-234844 | do_not_proceed | do_not_proceed | 12/16 |
| run6 | medium | 20261011-234848 | proceed_subject_to_conditions | do_not_proceed | 10/16 |
| run7 | high | 20261011-235345 | proceed_subject_to_conditions | do_not_proceed | 13/16 |
| run8 | high | 20261011-235352 | do_not_proceed | do_not_proceed | 13/16 |
| run9 | high | 20261011-235403 | proceed_subject_to_conditions | do_not_proceed | 13/16 |

The first low run 2 (20261011-234620) failed on invalid JSON twice (no strict schema) and is kept as `run2_failed.json`; run 2 was re-run. The headline score uses the model's own decision. Each run also records `decision_from_gates` and `decision_guarded`, and an `audit` of citations, quote IDs and fact IDs.

- The model's own decision was wrong in 7 of 9 runs (proceed_subject_to_conditions while its own gates were unmet); the decision computed from its gate statuses was right in 9 of 9.
- With the text in the prompt it avoided the consent-derogation trap in every completed run.
- It never filed the Region B requirements (0/9). At medium effort it also missed the A1 genetic restriction and the listed impact assessment as requirements (0/3 each); at high effort it found both in all three runs except one listed-impact miss.
- Hallucination was low: no unknown provision IDs, no quote IDs that were not shown (240 quotes), 5 miscopied fact IDs in total. One call in ten (the archived low run) failed on malformed JSON.
- Means (checks passed / 16): low 12.0, medium 11.0, high 13.0. Mean time 36 s, 44 s, 99 s. System means at the same effort: single 12.7-14.0 (high), 13.7 (medium), 9.0-14.7 (low); multi_graph 15.7 (high), 16.0 (medium and low).

## Hand-check notes

- The source review replaces the combined impact-assessment check with the A1-HIA 8 list-only
  check. The general A-REG 12(1) high-risk question is now reviewed manually, along with section 6
  purpose, the conditional Article 18 cure, remaining compliance and consistency. The 16 automated
  checks are selected checks, not proof of full correct reasoning. `score_case.py` does not evaluate
  the key's `manual_checks`; retain execution failures when reporting reliability.
- `key_before_review_20261011.json` preserves the exact earlier key. The source review was after
  exploratory runs; use the recorded key version when comparing scores. Neither the case input nor
  historical run JSONs were edited. `key_review_20261011.json` records an offline before/after replay
  of the saved case-05 runs present at review time; it includes runs not yet copied into this folder.

- run2 `single_no_graph`: the scorer fails `a1_genetic_transfer_restriction` and `a1_hosting_conditions`, but the
  single agent folded both into `region_a:outward_transfer_route` correctly (19(1)(a) ruled out by A1 s.7; s.6 "do
  not apply because this is not a transfer for hosting"). The original hand check was 14/16 (raw 12/16); the complete current review also credits the explicit Region B scope exclusions, giving 16/16.
- run3 `multi_graph`: the scorer fails `region_b_host_retention`, but `region_b:data_host_retention` is correctly
  `not_applicable`; it cites B-HRA 2 and 3 (definition; "section 9 applies to every data host") rather than s.9.
  Hand-checked 16/16 (raw 15/16).
- run3 `multi_no_graph`: the Region B specialist concluded that neither Region B Act applies but filed no findings
  (visible only in the supervisor's notes). Counted as a miss The original findings-only review retained raw 13/16. The current architecture-neutral concept review credits the explicit accepted-output scope reasoning, giving reviewed 15/16; its missing structured findings remain a quality issue.

## Score exports (for R / Excel)

Regenerate after adding runs or updating the bound `score_reviews.json` ledger:

```bash
.venv/bin/python analysis/export_scores.py analysis/case_05
```

- `scores_runs.csv`: one row per key version × configuration × run. Columns: `key_version`, `config`,
  `architecture`, `graph`, `run`, `decision`, `decision_ok`, `checks`, `passed_auto`, `passed_hand`,
  `seconds`, `model_calls`, `tool_calls`, `output_tokens`, `supervisor_passes`, `corrections`, `routings`.
- `scores_checks.csv`: one row per key version × configuration × run × check, with `section`
  (decision/requirement/route/trap), `passed_auto`, `passed_hand`, `hand_note`, `got`, `expected`.
- `score_reviews.json`: authoritative complete current-key review, with key/result/raw-outcome hashes and evidence pointers for every correction. The same scorer entry point supplies UI, CLI, tables and exports.
- `passed_auto` retains the raw matcher result; `passed_reviewed` is populated only for an exact, fully reviewed answer. `passed_hand` is a compatibility column. `review_status`, `checks_reviewed` and `review_corrections` identify coverage.
- `hand_checks.csv` mirrors current corrections for readability and retains legacy partial corrections for the old key. These legacy entries do not count as a complete reviewed score.
- Filter `key_version == reviewed` and `review_status == reviewed` for the 36 current reviewed runs. The other 36 exported rows replay the same answers against the historical key and are not additional experiments.
- `key_version`: `reviewed` (key.json) or `before_review_20261011`. On runs 1–3 both give the same totals.
- `supervisor_passes` is 0 for single-agent runs (no supervisor).

## Ways forward review

`next_steps_review_20261011.json` compares the next steps in runs 1-3 of each configuration against
the fictional sources. It preserves each run's required actions, clauses-route reasoning, general
high-risk findings and final review, alongside qualitative alignment notes. Both single setups
and generated multi identify Article 18 as available after changes in all three runs. Runtime
multi rules it out in run1 and leaves it unresolved on portal questions in runs2/3. Generated
multi also consistently distinguishes the general high-risk screening from absent listed triggers.

That earlier next-steps review covers the first 12 completed analysis runs; the folder now has 36 completed runs. The earlier incomplete single/generated attempt is
described separately in the review metadata; its file is no longer in the current runs folder.
Use all attempts for reliability or attempt-cost claims.
