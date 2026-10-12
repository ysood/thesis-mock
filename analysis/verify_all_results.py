"""Independent CSV readback and source-pointer reconciliation. Offline only."""

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intermediate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.intermediate.read_text())
    report = json.loads((args.output / "validation.json").read_text())
    readback, cell_count = {}, 0
    for name, expected_rows in payload["tables"].items():
        path = args.output / (name + ".csv")
        columns = list(dict.fromkeys(k for r in expected_rows for k in r))
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == columns, (name, "headers")
            rows = list(reader)
        assert len(rows) == len(expected_rows), (name, "row count")
        for i, (actual, expected) in enumerate(zip(rows, expected_rows)):
            assert None not in actual, (name, i, "extra CSV fields")
            for column in columns:
                wanted, got = expected.get(column), actual[column]
                if wanted is None or wanted == "":
                    assert got == "", (name, i, column, "missing value")
                elif isinstance(wanted, (int, float)):
                    assert math.isfinite(float(got)), (name, i, column)
                    assert float(got) == wanted, (name, i, column, got, wanted)
                elif column == "started_at_utc":
                    assert datetime.fromisoformat(got.replace("Z", "+00:00")) == datetime.fromisoformat(wanted), (name, i, column)
                else:
                    assert got == wanted, (name, i, column, got, wanted)
                cell_count += 1
        readback[name] = rows
        assert hashlib.sha256(path.read_bytes()).hexdigest() == report["exported"][name]["fileSha256"], name
        print(f"Readback: {name}, {len(rows)} rows, every field matches")

    # Source files are loaded afresh, independently of the extraction objects.
    source_cache = {}
    pointers = 0
    for row in readback["raw_numeric"]:
        source_path = row["source_path"]
        if source_path not in source_cache:
            source_cache[source_path] = json.loads((WORKSPACE / source_path).read_text())
        value = source_cache[source_path]
        for key in row["json_pointer"].split("/")[1:]:
            key = key.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
        assert isinstance(value, (int, float)), row
        assert float(row["value"]) == value, row
        pointers += 1

    files = 0
    for source, expected_hash in report["source_hashes"].items():
        assert hashlib.sha256((WORKSPACE / source).read_bytes()).hexdigest() == expected_hash, source
        files += 1

    calls = defaultdict(list)
    for row in readback["model_calls"]:
        if row["record_type"] == "assessment" and row["event_kind"] == "llm_response":
            calls[row["run_id"]].append(row)
    main_rows = readback.get("chapter4_runs", readback.get("all_runs", []))
    attempt_rows = main_rows + readback.get("failed_attempts", [])
    for row in attempt_rows:
        assert int(row["model_response_records_count"]) == len(calls[row["run_id"]])
        for field in ("input_tokens", "output_tokens", "total_tokens", "reasoning_output_tokens"):
            known = [int(c[field]) for c in calls[row["run_id"]] if c[field] != ""]
            assert row["captured_" + field] == str(sum(known)) if known else row["captured_" + field] == ""
    baseline = [r for r in main_rows if r["cohort"] == "case_05_baseline" and r["assessment_accepted"] == "1"]
    assert len(baseline) == 9
    assert sum(int(r["decision_label_matches_gates"]) for r in baseline) == 2
    assert all(r["decision_from_gates"] == "do_not_proceed" for r in baseline)
    if report.get("export_scope") == "chapter4":
        assert len(main_rows) == 45 and len(readback["failed_attempts"]) == 1
        assert {r["cohort"] for r in main_rows} == {"case_05_comparison", "case_05_baseline"}
        assert all("prototype-mock/analysis/case_05/" in r["source_path"] for r in attempt_rows)
        for config in ("single_no_graph", "single_graph", "multi_no_graph", "multi_graph", "baseline_corpus"):
            assert sum(r["config"] == config for r in main_rows) == 9
    report["readback"] = dict(status="passed", fields_checked=cell_count, numeric_source_pointers_checked=pointers,
        original_assessment_files_unchanged=files, cross_table_usage_totals="matched for every attempt",
        baseline_decisions="2/9 stated labels match gates; 9/9 gate-derived decisions do_not_proceed")
    (args.output / "validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["readback"],indent=2))


if __name__ == "__main__":
    main()
