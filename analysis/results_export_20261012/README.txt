MOCK PROTOTYPE RESULTS EXPORT

Start with all_runs.csv: one row per unique saved assessment attempt, 75 rows.
It has 159 columns covering configuration, scores, decisions, wall time, captured
token usage, retries, calls, findings, reference issues, questions, routes and briefs.

FILES
all_runs.csv       Main table for plotting run-level measurements.
model_calls.csv    Individual logged responses/retries, plus graph-generation cache
                  records. Filter record_type=assessment for assessment usage.
check_scores.csv   One row per current-key selected check of an accepted attempt.
                  Raw, hash-bound reviewed and preserved historical-key results are
                  separate columns. Historical scores are replays, not extra runs.
graph_metrics.csv  Raw, reviewed and early Region B graph snapshots. Raw and reviewed
                  share one build cost, identified by shared_generation_id.
raw_numeric.csv    Every numeric/boolean leaf in unique assessment JSONs, graph reports
                  and generation-cache timing/usage, with source JSON pointers.
                  Fields repeated in result/events must not be summed together.
data_dictionary.csv Column meanings, data types and missing-value convention.
validation.json   Per-run check results, source hashes and export verification.

COHORTS AND FILTERS
case_05_comparison: 36 completed framework runs (four configurations, three efforts,
                   three repetitions per cell). All have hash-bound reviewed scores.
case_05_baseline:    9 completed baseline runs plus 1 saved failed attempt.
case_01_comparison: 4 completed comparison runs. Some key checks inherently depend
                   on multi-agent questions; see the original case_01 README.
exploratory:        25 earlier runs. Settings/case/corpus versions can differ. These
                   are labelled separately; their current-key scores are replays.

For the principal Case 5 analysis, filter cohort=case_05_comparison.
To include its baseline, also use cohort=case_05_baseline and assessment_accepted=1.
Keep failed attempts when analysing execution reliability.
Reasoning effort and response caps come from documented cohort notes. Exploratory
effort/caps are unknown, not assumed from today's environment or code defaults.
The baseline's own decision is decision; decision_from_gates is a separate field.

TIME AND TOKEN MEASUREMENTS
elapsed_seconds is the saved result.seconds. event_span_seconds is independently
computed from timestamps. model_response_seconds_sum can overlap in parallel runs.
captured_*_tokens sums the usage metadata of logged final model responses only.
Intermediate tool-loop model responses and failed retries are not fully logged.
Those totals are captured usage, not complete API billing. Reasoning output tokens
are part of output tokens; do not add them again. Input cache fields are components
of input usage, not extra tokens to add to total_tokens. Coverage columns indicate
how many response records actually reported each usage field.
No dollar-cost figures are supplied: reliable billing amounts and alias pricing
are unavailable. cost_usd_recorded is blank; billing_cost_available is 0.
Graph-generation cache records span builds/probes and are not assigned to a build;
use graph_metrics.csv for build totals rather than summing cache records blindly.

PROVENANCE AND MISSING DATA
91 physical assessment files were compared; 16 duplicate copies were removed.
run_id identifies a complete saved attempt using a semantic SHA-256 fingerprint.
source_path, source_aliases and source hashes retain its original locations.
Blank fields mean missing, unrecorded or not applicable; zero is an observed zero.
Binary flags use 1/0 and fractional scores use 0-1, not percentage strings.
The known incomplete Case 5 single/generated attempt and two deleted Case 1 runs
have no source JSON in the inventoried folders. Their measurements are unavailable.
raw_numeric includes numeric case facts as source observations, not runtime metrics.
CSV data is UTF-8 with standard quoting and a single header row, suitable for R/Excel.

GUIDANCE FLAGS
consent_route_closed and clauses_route_available reproduce Case 5 brief statuses.
execute_clauses_action_keyword_match is an explicit mechanical action-text flag.
It is not a substitute for evaluating every action or for the chapter's hand review.

VALIDATION
The extractor loops over every attempt: load, normalise legacy names, extract,
score, reconcile response usage/status totals and retain the source fingerprints.
It made 2420 per-run assertions and 236 comparisons with existing score exports.
The CSV authoring step checks every written cell. A separate readback pass then
checks every field, all source numeric pointers and that source files are unchanged.
No model calls, law refreshes or changes to saved runs/keys were made.
