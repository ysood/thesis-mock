// CSV authoring from the offline extractor's typed tables.
// Run with the bundled Node runtime and @oai/artifact-tool available beside this file.
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import assert from "node:assert/strict";
import { Workbook } from "@oai/artifact-tool";

const [inputPath, outputDir] = process.argv.slice(2);
if (!inputPath || !outputDir) throw new Error("Usage: export_all_results.mjs tables.json output-directory");
const payload = JSON.parse(await fs.readFile(inputPath, "utf8"));
await fs.mkdir(outputDir, { recursive: true });

function csvCell(value) {
  if (value === null || value === undefined || value === "") return "";
  const text = value instanceof Date ? value.toISOString() : String(value);
  return /[,"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const exported = {};
for (const [name, rows] of Object.entries(payload.tables)) {
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))];
  const matrix = [columns, ...rows.map(row => columns.map(col => row[col] ?? null))];
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Data");
  // One flat data table. CSVs intentionally have no charts, formatting or formula layer.
  const range = sheet.getRangeByIndexes(0, 0, matrix.length, columns.length);
  range.values = matrix;
  workbook.recalculate();
  const savedValues = range.values;
  assert.equal(savedValues.length, matrix.length);
  let cellChecks = 0;
  for (let r = 0; r < matrix.length; r++) {
    assert.equal(savedValues[r].length, columns.length);
    for (let c = 0; c < columns.length; c++) {
      const original = matrix[r][c] ?? "";
      const actual = savedValues[r][c] ?? "";
      if (actual instanceof Date) {
        assert.equal(actual.getTime(), Date.parse(original), `${name} row ${r}, ${columns[c]}`);
      } else {
        assert.equal(actual, original, `${name} row ${r}, ${columns[c]}`);
      }
      cellChecks++;
    }
  }
  const inspection = await workbook.inspect({ kind: "table", range: "Data!A1:F4", include: "values",
    tableMaxRows: 4, tableMaxCols: 6, maxChars: 600 });
  assert.ok(inspection.ndjson);
  const text = savedValues.map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
  const target = path.join(outputDir, name + ".csv");
  await fs.writeFile(target, text, "utf8");
  exported[name] = { rows: rows.length, columns: columns.length, cellChecks,
    fileSha256: crypto.createHash("sha256").update(text).digest("hex") };
  console.log(`${name}.csv: ${rows.length} rows, ${columns.length} columns; ${cellChecks} cells verified`);
}

const readme = payload.audit.export_scope === "chapter4" ? `CHAPTER 4 RESULTS EXPORT

Start with chapter4_runs.csv: exactly 45 completed runs reported in Chapter 4,
with ${exported.chapter4_runs.columns} columns of run metadata and numerical metrics.
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
same loop: ${payload.audit.per_run_checks.reduce((n, r) => n + r.assertions_passed, 0)} per-attempt assertions and ${payload.audit.existing_export_comparisons_passed} comparisons against existing exports.
The chapter's Case 5 decision and guidance totals agree with the export. Every CSV
cell is checked during authoring, then read back in a separate validation pass.
Source files, keys, reviews and earlier exports remain unchanged.
` : `MOCK PROTOTYPE RESULTS EXPORT

Start with all_runs.csv: one row per unique saved assessment attempt, ${exported.all_runs.rows} rows.
It has ${exported.all_runs.columns} columns covering configuration, scores, decisions, wall time, captured
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
It made ${payload.audit.per_run_checks.reduce((n, r) => n + r.assertions_passed, 0)} per-run assertions and ${payload.audit.existing_export_comparisons_passed} comparisons with existing score exports.
The CSV authoring step checks every written cell. A separate readback pass then
checks every field, all source numeric pointers and that source files are unchanged.
No model calls, law refreshes or changes to saved runs/keys were made.
`;
await fs.writeFile(path.join(outputDir, "README.txt"), readme);
payload.audit.exported = exported;
payload.audit.authoring = "@oai/artifact-tool typed tables, verified cell by cell, serialized to CSV";
await fs.writeFile(path.join(outputDir, "validation.json"), JSON.stringify(payload.audit, null, 2));
