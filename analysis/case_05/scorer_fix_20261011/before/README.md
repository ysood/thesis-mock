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

## Results: high, medium and low reasoning effort (runs 1-9)

Scored against `key.json` (16 automated checks) with `engine/score.py`, 11 October 2026. Runs 1-3: `REASONING_EFFORT=high`; runs 4-6: `medium` (`MAX_TOKENS=40000`). Same model (gpt-5.6-luna). All 24 runs reached `do_not_proceed` (the key's decision).

| | single_no_graph | single_graph | multi_no_graph | multi_graph |
|---|---|---|---|---|
| high: checks passed per run (mean) | 12, 12, 14 (12.7) | 14, 14, 14 (14.0) | 15, 14, 13 (14.0) | 16, 16, 15 (15.7) |
| medium: checks passed per run (mean) | 14, 13, 14 (13.7) | 14, 14, 13 (13.7) | 16, 16, 13 (15.0) | 16, 16, 16 (16.0) |
| high: mean seconds / output tokens | 162 / 11,577 | 167 / 12,402 | 576 / 56,085 | 507 / 56,547 |
| medium: mean seconds / output tokens | 71 / 6,626 | 81 / 7,147 | 237 / 25,316 | 203 / 24,828 |

Checks not passed in every run (high / medium, out of 3 each); all other checks passed in all 24 runs:

| check | single_no_graph | single_graph | multi_no_graph | multi_graph |
|---|---|---|---|---|
| requirement:region_b_sector_rules | 0/3 / 0/3 | 0/3 / 0/3 | 2/3 / 2/3 | 3/3 / 3/3 |
| requirement:region_b_host_retention | 0/3 / 0/3 | 0/3 / 0/3 | 2/3 / 2/3 | 2/3 / 3/3 |
| requirement:a1_genetic_transfer_restriction | 2/3 / 3/3 | 3/3 / 2/3 | 3/3 / 2/3 | 3/3 / 3/3 |
| requirement:a1_hosting_conditions | 1/3 / 3/3 | 3/3 / 3/3 | 3/3 / 3/3 | 3/3 / 3/3 |
| requirement:a1_listed_impact_assessment | 2/3 / 2/3 | 3/3 / 3/3 | 3/3 / 3/3 | 3/3 / 3/3 |
| route:approved_clauses | 3/3 / 3/3 | 3/3 / 3/3 | 0/3 / 3/3 | 3/3 / 3/3 |
| route:vital_interests_derogation | 3/3 / 3/3 | 3/3 / 3/3 | 2/3 / 3/3 | 3/3 / 3/3 |

Observations (n = 3 per cell; selected automated checks only, manual checks not scored):

- The single agent missed both Region B requirements (sector rules, host retention) in all 12 runs; multi-agent found them in 10 of 12 (all 6 with the generated graph).
- multi_graph was the most stable configuration: no run below 15, and all three medium runs scored 16/16. Without the graph, multi-agent ranged 13-16.
- The generated graph made no difference to the single agent's mean score.
- Medium effort matched or exceeded high effort in every configuration, at about 40-45% of the time and output tokens.

### Low effort (runs 7-9)

| | single_no_graph | single_graph | multi_no_graph | multi_graph |
|---|---|---|---|---|
| low: checks passed per run (mean) | 7, 9, 11 (9.0) | 15, 14, 15 (14.7) | 10, 15, 14 (13.0) | 16, 16, 16 (16.0) |
| low: correct decision | 1/3 | 3/3 | 2/3 | 3/3 |
| low: mean seconds / output tokens | 51 / 4,521 | 70 / 5,007 | 111 / 13,743 | 148 / 17,855 |

Low-effort checks not passed in every run (out of 3): decision, transfer_route, consent_derogation, vital_interests_derogation and trap:consent_derogation_relied_on (single_no_graph 1/3, multi_no_graph 2/3; both graph configurations 3/3); a1_genetic_transfer_restriction (0/3, 1/3, 1/3, 3/3); region_b_sector_rules (0/3, 3/3, 2/3, 3/3); region_b_host_retention (1/3, 2/3, 3/3, 3/3); a1_listed_impact_assessment (single_no_graph 1/3); a1_professional_secrecy (single 2/3 in both graph modes); a1_hosting_conditions (multi_no_graph 2/3).

- At low effort the generated graph decides correctness: every run with the graph reached `do_not_proceed` (6/6); without it, 3 of 6 runs relied on the explicit-consent derogation that A1-HIA 7 excludes for genetic information and returned `needs_review`.
- multi_graph scored 16/16 in all six medium and low runs, and was the only configuration that never dropped below 15 at any effort level.
- Effort mainly affects configurations without the graph: single_no_graph fell from 13.7 (medium) to 9.0 (low); single_graph and multi_graph did not drop.

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
  not apply because this is not a transfer for hosting"). Hand-checked score 14/16 (raw 12/16).
- run3 `multi_graph`: the scorer fails `region_b_host_retention`, but `region_b:data_host_retention` is correctly
  `not_applicable`; it cites B-HRA 2 and 3 (definition; "section 9 applies to every data host") rather than s.9.
  Hand-checked 16/16 (raw 15/16).
- run3 `multi_no_graph`: the Region B specialist concluded that neither Region B Act applies but filed no findings
  (visible only in the supervisor's notes). Counted as a miss (raw 13/16 stands).

## Score exports (for R / Excel)

Regenerate after adding runs or editing `hand_checks.csv`:

```bash
.venv/bin/python analysis/export_scores.py analysis/case_05
```

- `scores_runs.csv`: one row per key version × configuration × run. Columns: `key_version`, `config`,
  `architecture`, `graph`, `run`, `decision`, `decision_ok`, `checks`, `passed_auto`, `passed_hand`,
  `seconds`, `model_calls`, `tool_calls`, `output_tokens`, `supervisor_passes`, `corrections`, `routings`.
- `scores_checks.csv`: one row per key version × configuration × run × check, with `section`
  (decision/requirement/route/trap), `passed_auto`, `passed_hand`, `hand_note`, `got`, `expected`.
- `hand_checks.csv`: the manual overrides (with reasons). They change only `passed_hand`; `passed_auto` is
  always the unedited scorer result. Report which one you use.
- `key_version`: `reviewed` (key.json) or `before_review_20261011`. On runs 1–3 both give the same totals.
- `supervisor_passes` is 0 for single-agent runs (no supervisor).

## Ways forward review

`next_steps_review_20261011.json` compares the next steps in runs 1-3 of each configuration against
the fictional sources. It preserves each run's required actions, clauses-route reasoning, general
high-risk findings and final review, alongside qualitative alignment notes. Both single setups
and generated multi identify Article 18 as available after changes in all three runs. Runtime
multi rules it out in run1 and leaves it unresolved on portal questions in runs2/3. Generated
multi also consistently distinguishes the general high-risk screening from absent listed triggers.

These are the 12 completed analysis runs. The earlier incomplete single/generated attempt is
described separately in the review metadata; its file is no longer in the current runs folder.
Use all attempts for reliability or attempt-cost claims.
