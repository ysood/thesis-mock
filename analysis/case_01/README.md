# Case 01 runs for analysis

`case.json` and `key.json` are copies of `cases/01_a1_gp_to_region_b_host`, frozen on 11 Oct 2026 before
any run in this folder (key last changed in commit `75eacd0`; sha256 prefix `1de710a579ddd4c1`). If
the key needs changing, keep this one as `key_before_review_<date>.json` and re-score every run.

Case 01 is the one case that exercises all three specialists, a cross-jurisdiction question and a
conflict to reconcile:

- Region A: lawful ground, Art 8, agent contract, transfer route (unmet: recognition excludes sensitive
  information, derogations exclude ongoing transfers, approved clauses fail Art 18(2)-(3) while the host
  holds the keys).
- Region B: Northgate is a data host (B-HRA 9 seven-year retention); covered-provider rules not applicable.
- Subregion A1 (delegation): A1-HIA 4 health-care basis; A1-HIA 6 notice and Region A-only keys (unmet);
  A1-HIA 8(a) impact assessment regardless of numbers (unmet).
- Conflict: B-HRA 9 retention vs deletion within 30 days; resolvable by choosing return (A-REG 9(2)(f))
  under B-HRA 9(2).
- Question: Art 18(2) needs Region B access law (B-RAA 3-6).

| folder | architecture | knowledge graph |
|---|---|---|
| `single_no_graph` | single agent, one call | runtime citation graph |
| `single_graph` | single agent, one call | generated normative graph |
| `multi_no_graph` | multi-agent | runtime citation graph |
| `multi_graph` | multi-agent | generated normative graph |

Run settings must match case 05 so the configurations are comparable: same model, 20 tool calls per
agent, 1 correction round.

| run | single_no_graph | single_graph | multi_no_graph | multi_graph |
|---|---|---|---|---|
| run1 | 20261011-092321 | 20261011-092247 | 20261011-094004 | 20261011-093914 |

## Scoring

```bash
.venv/bin/python analysis/score_case.py analysis/case_01      # summary table
.venv/bin/python analysis/export_scores.py analysis/case_01   # scores_runs.csv, scores_checks.csv
```

Manual overrides go in `hand_checks.csv` (key_version, config, run, check, passed, note); they change
`passed_hand` only.

Architecture caveat: `question:region_b_access_law` checks that a peer question was routed and answered.
The single agent has no peer questions, so it fails by design. Exclude that check (or judge by hand whether
the single answer used Region B's access law) when comparing single with multi.

## Hand-check notes

- Two earlier multi runs (20261011-092733, -092912) used 2 correction rounds by choice and were deleted; the
  multi run1s above are reruns at 1 round. Single runs are unaffected by that setting.
- run1 `multi_graph`: approved clauses and the return route both `unresolved` (assessment "not supplied";
  record origin "not expressly established"), as in the deleted 2-round graph run. Counted as misses.
- `scope` fails in most runs (scope is decided in planning, not filed as a finding); `question:region_b_access_law`
  fails for single by design. Exclude both when comparing configurations.
