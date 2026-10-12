CHAPTER 4 RESULTS EXPORT

Start with chapter4_runs.csv: exactly 45 completed runs reported in Chapter 4,
with 159 columns of run metadata and numerical metrics.
All assessment sources come from prototype-mock/analysis/case_05/.

MAIN RUNS
36 framework runs: single/multi crossed with citation/generated graphs, three
reasoning efforts and three repetitions per cell. These have reviewed scores.
9 unguarded baseline runs: three per effort. Their scores are raw, not reviewed.
Each of the five configurations has exactly nine completed runs in the main CSV.
Case 1 and exploratory runs are excluded.

FILES
chapter4_runs.csv   Main completed-run table for RStudio/Excel plots.
failed_attempts.csv One separately saved failed baseline attempt, for reliability.
model_calls.csv     Logged responses/retries for these 45 runs and that failure.
check_scores.csv    Individual raw/reviewed/historical-key selected-check results.
graph_metrics.csv   Original and reviewed full-corpus graph snapshots discussed
                   in Section 4.1.2. These share one generation cost; do not sum it.
raw_numeric.csv     All numeric/boolean leaves in these assessment sources and
                   graph reports, with exact JSON pointers. Repeated fields inside
                   result/events are not independent observations to sum.
data_dictionary.csv Column meanings and missing-value conventions.
validation.json    Per-run checks, source hashes and CSV verification results.

IMPORTANT MEASUREMENTS
elapsed_seconds is saved wall-clock run time. event_span_seconds independently
measures the saved event span. model_response_seconds_sum can include parallel calls
and is not wall time. captured_*_tokens only includes usage of logged final model
responses; intermediate tool-loop usage and failed-retry usage are not fully saved.
Reasoning tokens are already part of output; cache fields are components of input.
Blank fields mean unrecorded or not applicable, not zero. No dollar costs are inferred.
Settings come from the Case 5 cohort notes; the high framework runs use a different
response cap from medium/low. Baseline decision is the model's own label;
decision_from_gates and decision_guarded preserve the other recorded decisions.
Historical-key scores replay the same run and are not additional experiments.

RELIABILITY
The main CSV includes completed runs only. The failed baseline attempt is kept in
failed_attempts.csv, not as a tenth completed baseline run. The separately noted
incomplete single/generated Case 5 attempt has no available source JSON; no numeric
row or measurements were invented for it.

VERIFICATION
Every one of the 46 available attempts was re-read, extracted and checked with the
same loop: 1422 per-attempt assertions and 216 comparisons against existing exports.
The chapter's Case 5 decision and guidance totals agree with the export. Every CSV
cell is checked during authoring, then read back in a separate validation pass.
Source files, keys, reviews and earlier exports remain unchanged.
