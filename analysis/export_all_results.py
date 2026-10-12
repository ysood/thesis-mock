"""Extract every saved mock attempt, then reconcile every row with its source.

Offline only. Produces a typed JSON intermediate for the CSV authoring step.
No saved runs, keys, reviews or existing exports are modified.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(ROOT))
from engine import score

CONFIGS = {"single_no_graph": ("single", "runtime"), "single_graph": ("single", "generated"),
           "multi_no_graph": ("multi", "runtime"), "multi_graph": ("multi", "generated"),
           "baseline_corpus": ("baseline", "none")}
TOKEN_PATHS = {
    "input_tokens": ("input_tokens",), "output_tokens": ("output_tokens",),
    "total_tokens": ("total_tokens",), "cache_read_input_tokens": ("input_token_details", "cache_read"),
    "cache_creation_input_tokens": ("input_token_details", "cache_creation"),
    "reasoning_output_tokens": ("output_token_details", "reasoning"),
    "audio_input_tokens": ("input_token_details", "audio"),
    "audio_output_tokens": ("output_token_details", "audio"),
}
STATUS = ("met", "unmet", "undetermined", "not_applicable")
ROUTE_STATUS = ("supported", "available", "ruled_out", "unresolved", "not_investigated")


def read(path):
    return json.loads(path.read_text())


def digest_bytes(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return str(path.relative_to(WORKSPACE))


def get(value, keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def total(values):
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def decision_value(value):
    return value.get("decision") if isinstance(value, dict) else value


def numeric_leaves(value, pointer=""):
    if isinstance(value, (int, float)):
        yield pointer, int(value) if isinstance(value, bool) else value, "boolean" if isinstance(value, bool) else "number"
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from numeric_leaves(v, pointer + "/" + k.replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from numeric_leaves(v, pointer + "/" + str(i))


def identify(path, aliases, data):
    analysis = next((p for p in aliases if p.parent.name in CONFIGS and p.stem.startswith("run")), None)
    raw = next((p for p in aliases if p.parent == ROOT / "runs/mock"), None)
    r = score.modernise(data["result"])
    if analysis:
        number = int(re.search(r"run(\d+)", analysis.stem)[1])
        case_num = analysis.parents[1].name
        case_dir = next((p for p in (ROOT / "cases").iterdir() if p.name.startswith(case_num[5:] + "_")), None)
        case_id = case_dir.name if case_dir else case_num
        config = analysis.parent.name
        expected = CONFIGS[config]
        assert (data.get("mode"), data.get("graph", "runtime")) == expected, str(analysis)
        cohort = "case_05_baseline" if config == "baseline_corpus" else case_num + "_comparison"
        effort = ("low" if number <= 3 else "medium" if number <= 6 else "high") if config == "baseline_corpus" else (
            "high" if number <= 3 else "medium" if number <= 6 else "low")
        limit = (40000 if config == "baseline_corpus" or effort != "high" else 16000)
        metadata_basis = relative(analysis.parents[1] / "README.md")
        key_path = analysis.parents[1] / "key.json"
    else:
        number, effort, limit = None, "unknown", None
        case_id = score.case_name(raw.name)
        config = (data.get("mode") or "multi") + ("_graph" if data.get("graph") == "generated" else "_no_graph")
        expected = (data.get("mode") or "multi", data.get("graph", "runtime"))
        cohort, metadata_basis = "exploratory", "architecture/graph: saved metadata or legacy default; effort and cap unrecorded"
        key_path = ROOT / "cases" / case_id / "key.json"
    return r, dict(case_id=case_id, cohort=cohort, config=config, architecture=expected[0], graph=expected[1],
                   run_number=number, reasoning_effort=effort, reasoning_effort_basis="cohort_notes" if analysis else "unrecorded",
                   response_token_limit=limit, settings_source=metadata_basis,
                   scoring_key_path=relative(key_path) if key_path.exists() else None), key_path


def call_rows(run_id, path, data, record_type="assessment"):
    out = []
    for i, e in enumerate(data.get("events", [])):
        if e.get("kind") not in ("llm_response", "llm_retry"):
            continue
        usage = e.get("usage") or {}
        row = dict(record_type=record_type, run_id=run_id, event_index=i, event_kind=e["kind"],
                   model=data.get("model"), agent=e.get("agent"), purpose=e.get("purpose"),
                   attempt_number=e.get("attempt"), ok=int(e["ok"]) if "ok" in e else None,
                   event_time_unix=e.get("time"), response_seconds=e.get("seconds"),
                   reported_tool_calls=e.get("tool_calls"), usage_present=int(bool(usage)),
                   error=e.get("error"), source_path=relative(path), source_pointer=f"/events/{i}")
        for label, keys in TOKEN_PATHS.items():
            row[label] = get(usage, keys)
        out.append(row)
    return out


def scores(run_id, path, result, key_path, accepted):
    rows, summary = [], {"score_status": "not_scored_failed_attempt" if not accepted else "key_unavailable"}
    if not accepted or not key_path.exists():
        return rows, summary
    card = score.score_file(result, key_path)
    raw = score.outcomes(card)
    reviewed = score.outcomes(card["reviewed"]) if card.get("reviewed") else {}
    meta = card.get("review_metadata", {})
    historical_path = key_path.parent / "key_before_review_20261011.json"
    historical = score.outcomes(score.score(result, read(historical_path))) if historical_path.exists() else {}
    old_hand = {}
    hand_path = key_path.parent / "hand_checks.csv"
    if hand_path.exists() and path.parent.name in CONFIGS:
        for h in csv.DictReader(hand_path.open()):
            if h["key_version"] == "reviewed" and h["config"] == path.parent.name and h["run"] == path.stem:
                name = "decision" if h["check"] == "decision" else h["check"]
                old_hand[name] = int(h["passed"].lower() == "true")
    for name, outcome in raw.items():
        item = score.check_rows(card)[name]
        correction = score.check_rows(card["reviewed"])[name].get("review", {}) if reviewed else {}
        rows.append(dict(run_id=run_id, check_id=name, section=name.split(":")[0],
                         passed_raw=int(outcome), passed_reviewed=int(reviewed[name]) if reviewed else None,
                         passed_historical_key=int(historical[name]) if name in historical else None,
                         legacy_hand_override=old_hand.get(name), found=int(item["found"]) if "found" in item else None,
                         review_changed=int(name in meta.get("changed_checks", [])) if reviewed else None,
                         review_status=card["review_status"], review_reason=correction.get("reason"),
                         expected=json.dumps(item.get("expect")), got=json.dumps(item.get("status", item.get("statuses", item.get("got")))),
                         key_path=relative(key_path), source_path=relative(path)))
    summary.update(score_status="scored", score_basis="current_saved_key_replay", review_status=card["review_status"],
                   checks_count=len(raw), checks_passed_raw=sum(raw.values()),
                   checks_passed_reviewed=sum(reviewed.values()) if reviewed else None,
                   checks_passed_historical_key=sum(historical.values()) if historical else None,
                   checks_reviewed_count=meta.get("checks_reviewed", 0),
                   review_changes_count=len(meta.get("changed_checks", [])),
                   decision_matches_key=int(card["decision"]["ok"]), engagement_matches_key=int(card["engaged"]["ok"]),
                   extra_blocking_findings_count=len(card["extra_blocking"]),
                   checks_raw_fraction=sum(raw.values()) / len(raw),
                   checks_reviewed_fraction=sum(reviewed.values()) / len(reviewed) if reviewed else None)
    for section in ("requirements", "routes", "conflicts", "questions", "must_not"):
        summary["key_" + section + "_count"] = len(card[section])
        summary["key_" + section + "_passed_raw"] = sum(not x["violated"] if section == "must_not" else x["ok"] for x in card[section])
    return rows, summary


def extract(run_id, path, aliases, data):
    r, row, key_path = identify(path, aliases, data)
    events = data.get("events", [])
    responses = [e for e in events if e["kind"] == "llm_response"]
    times = [e["time"] for e in events if isinstance(e.get("time"), (int, float))]
    accepted = bool(r.get("findings")) and bool(responses) and all(e.get("ok") is not False for e in responses)
    row.update(run_id=run_id, model=data.get("model"), decision=r["decision"], assessment_accepted=int(accepted),
               decision_from_gates=decision_value(r.get("decision_from_gates")), decision_guarded=decision_value(r.get("decision_guarded")),
               decision_label_matches_gates=int(r["decision"] == decision_value(r["decision_from_gates"])) if "decision_from_gates" in r else None,
               started_at_utc=datetime.fromtimestamp(min(times), timezone.utc).isoformat() if times else None,
               start_time_unix=min(times) if times else None, end_time_unix=max(times) if times else None,
               elapsed_seconds=r.get("seconds"), event_span_seconds=max(times)-min(times) if times else None,
               event_span_seconds_rounded=round(max(times)-min(times)) if times else None,
               elapsed_minutes=r["seconds"]/60 if r.get("seconds") is not None else None,
               model_response_records_count=len(responses), llm_request_records_count=sum(e["kind"] == "llm_request" for e in events),
               failed_model_responses_count=sum(e.get("ok") is False for e in responses),
               llm_retry_events_count=sum(e["kind"] == "llm_retry" for e in events),
               tool_calls_count=sum(e["kind"] == "tool_call" for e in events),
               failed_tool_calls_count=sum(e["kind"] == "tool_call" and e.get("ok") is False for e in events),
               model_response_seconds_sum=total([e.get("seconds") for e in responses]),
               usage_response_records_count=sum(bool(e.get("usage")) for e in responses),
               usage_scope="logged_final_model_responses_only; intermediate responses and failed retries may be missing",
               cost_usd_recorded=None, billing_cost_available=0,
               source_path=relative(path), duplicate_source_files_count=len(aliases)-1,
               source_aliases=";".join(relative(p) for p in aliases), source_file_sha256=digest_bytes(path),
               source_semantic_sha256=run_id, result_sha256=score.fingerprint(r),
               case_input_sha256=score.fingerprint(r.get("case", {})), total_events_count=len(events))
    for label, keys in TOKEN_PATHS.items():
        values = [get(e.get("usage") or {}, keys) for e in responses]
        row["captured_" + label] = total(values)
        row[label + "_response_records_count"] = sum(v is not None for v in values)
    fs = r.get("findings", [])
    routes = [route for f in fs for route in f.get("routes", [])]
    questions = r.get("questions", [])
    reviews = [v for v in r.get("reviews", []) if v]
    brief = r.get("brief", {})
    row.update(findings_count=len(fs), verified_findings_count=sum(bool(f.get("verified")) for f in fs),
               finding_reference_issues_count=sum(len(f.get("issues", [])) for f in fs),
               conclusion_issues_count=len(r.get("conclusion_issues", [])),
               finding_citations_count=sum(len(f.get("resolved_citations", [])) for f in fs),
               unique_finding_citations_count=len({p for f in fs for p in f.get("resolved_citations", [])}),
               fact_references_count=sum(len(f.get("facts", [])) for f in fs),
               unique_fact_references_count=len({x.get("fact_id") for f in fs for x in f.get("facts", [])}),
               evidence_references_count=sum(len(f.get("evidence_ids", [])) for f in fs),
               routes_count=len(routes), questions_count=len(questions),
               answered_questions_count=sum(q.get("status") == "answered" for q in questions),
               open_questions_count=sum(q.get("status") != "answered" for q in questions),
               delegations_count=sum(x.get("kind") == "delegation" for x in r.get("delegations", [])),
               peer_routings_count=sum(x.get("kind") == "routing" for x in r.get("delegations", [])),
               supervisor_passes_count=0 if row["architecture"] in ("single", "baseline") else len(reviews),
               supervisor_corrections_count=sum(len(v.get("corrections", [])) for v in reviews),
               supervisor_routings_count=sum(len(v.get("routings", [])) for v in reviews),
               conflicts_count=len(brief.get("conflicts", [])),
               unresolved_conflicts_count=sum(c.get("resolvable") is False for c in brief.get("conflicts", [])),
               required_actions_count=sum(len(f.get("required_actions", [])) for f in fs),
               finding_missing_facts_count=sum(len(f.get("missing_facts", [])) for f in fs),
               finding_missing_evidence_count=sum(len(f.get("missing_evidence", [])) for f in fs),
               confirmations_count=sum(len(f.get("confirmations", [])) for f in fs),
               open_dependencies_count=sum(bool(f.get("open_dependency")) for f in fs),
               brief_known_facts_count=len(brief.get("known", [])), brief_requirements_count=len(brief.get("required", [])),
               brief_missing_items_count=len(brief.get("missing", [])),
               brief_blocking_missing_items_count=sum(bool(x.get("blocking")) for x in brief.get("missing", [])),
               brief_actions_count=sum(len(x.get("to_close", [])) for x in brief.get("routes", [])),
               brief_route_groups_count=len(brief.get("routes", [])))
    for kind in ("gate", "duty", "applicability"):
        row["findings_" + kind + "_count"] = sum(f.get("kind") == kind for f in fs)
    for status in STATUS:
        row["findings_" + status + "_count"] = sum(f["status"] == status for f in fs)
    for status in ROUTE_STATUS:
        row["routes_" + status + "_count"] = sum(x["status"] == status for x in routes)
    for cid in ("region_a", "region_b", "subregion_a1"):
        row[cid + "_findings_count"] = sum(f.get("corpus") == cid for f in fs)
        row[cid + "_provisions_read_count"] = len(r.get("read", {}).get(cid, []))
    row["unique_provisions_read_count"] = len({p for ps in r.get("read", {}).values() for p in ps})
    for tool in ("search_law", "read_provision", "kg_node"):
        row[tool + "_calls_count"] = sum(e["kind"] == "tool_call" and e.get("tool") == tool for e in events)
    for kind in ("fact", "evidence", "confirm", "other_law", "reference_defect", "open_question", "review", "review_note"):
        row["brief_missing_" + kind + "_count"] = sum(x.get("kind") == kind for x in brief.get("missing", []))
    for k, v in (r.get("audit") or {}).items():
        row["baseline_audit_" + k + ("_count" if isinstance(v, list) else "")] = len(v) if isinstance(v, list) else v
    if row["case_id"].startswith("05_") and accepted:
        flat_routes = [x for group in brief.get("routes", []) for x in group.get("routes", [])]
        consent = [x for x in flat_routes if "A-REG 19" in x.get("resolved_citations", []) and "consent" in x.get("name", "").lower()]
        clauses = [x for x in flat_routes if "A-REG 18" in x.get("resolved_citations", []) and any(t in x.get("name", "").lower() for t in ("clause", "safeguard"))]
        row.update(consent_route_entries_count=len(consent), clauses_route_entries_count=len(clauses),
                   consent_route_closed=int(bool(consent) and all(x["status"] == "ruled_out" for x in consent)),
                   clauses_route_available=int(any(x["status"] == "available" for x in clauses)))
        transfer_refs = {f["ref"] for f in fs if "A-REG 16" in f.get("resolved_citations", []) and f.get("kind") == "gate"}
        actions = [a for g in brief.get("routes", []) if g.get("requirement") in transfer_refs for a in g.get("to_close", [])]
        row["transfer_gate_unmet"] = int(any(f["ref"] in transfer_refs and f["status"] == "unmet" for f in fs))
        row["execute_clauses_action_keyword_match"] = int(any(re.search(r"\b(execut|sign|enter|put in place)\w*\b.{0,130}\bclause", a, re.I) for a in actions))
    check_rows, score_summary = scores(run_id, path, r, key_path, accepted)
    row.update(score_summary)
    return row, call_rows(run_id, path, data), check_rows


def verify_row(row, calls, checks, source):
    """Independent per-attempt controls, run after each extraction, not just totals."""
    assertions = 0
    def check(condition, label):
        nonlocal assertions
        assert condition, f"{row['source_path']}: {label}"
        assertions += 1
    check(row["decision"] == source["result"]["decision"], "decision")
    if "decision_from_gates" in source["result"]:
        check(row["decision_from_gates"] == decision_value(source["result"]["decision_from_gates"]), "gate-derived decision")
        check(row["decision_guarded"] == decision_value(source["result"]["decision_guarded"]), "guarded decision")
    check(row["elapsed_seconds"] == source["result"].get("seconds"), "elapsed time")
    check(row["source_file_sha256"] == digest_bytes(WORKSPACE / row["source_path"]), "file hash")
    check(row["model_response_records_count"] == len([x for x in calls if x["event_kind"] == "llm_response"]), "model responses")
    check(row["llm_retry_events_count"] == len([x for x in calls if x["event_kind"] == "llm_retry"]), "retry count")
    check(row["tool_calls_count"] == len([e for e in source["events"] if e["kind"] == "tool_call"]), "tool calls")
    for label in TOKEN_PATHS:
        call_values = [x[label] for x in calls if x["event_kind"] == "llm_response"]
        check(row["captured_" + label] == total(call_values), label)
        check(row[label + "_response_records_count"] == sum(x is not None for x in call_values), label + " coverage")
    check(sum(row["findings_" + s + "_count"] for s in STATUS) == row["findings_count"], "finding statuses")
    check(sum(row["routes_" + s + "_count"] for s in ROUTE_STATUS) == row["routes_count"], "route statuses")
    if checks:
        check(row["checks_count"] == len(checks), "check denominator")
        check(row["checks_passed_raw"] == sum(x["passed_raw"] for x in checks), "raw checks")
        if row.get("checks_passed_reviewed") is not None:
            check(row["checks_passed_reviewed"] == sum(x["passed_reviewed"] for x in checks), "reviewed checks")
    for e in source["events"]:
        u = e.get("usage") or {}
        if all(k in u for k in ("input_tokens", "output_tokens", "total_tokens")):
            check(u["input_tokens"] + u["output_tokens"] == u["total_tokens"], "usage arithmetic")
    return assertions


def graph_data(numeric, snapshots=("latest", "reviewed", "probe_region_b")):
    rows = []
    for name in snapshots:
        folder = WORKSPACE / "sandbox/kg_mockgen/runs" / name
        path = folder / "report.json"
        d, g = read(path), read(folder / "graph.json")
        row = dict(snapshot=name, record_type="graph_snapshot", model=d["model"], source_path=relative(path),
                   source_file_sha256=digest_bytes(path), shared_generation_id="full_corpus_build" if name != "probe_region_b" else "region_b_probe",
                   generation_seconds=d["seconds"], generation_calls=d["usage"]["calls"],
                   input_tokens=d["usage"]["input_tokens"], output_tokens=d["usage"]["output_tokens"],
                   reasoning_tokens=d["usage"].get("reasoning_tokens"), cached_calls=d["usage"].get("cached"),
                   total_tokens=d["usage"]["input_tokens"] + d["usage"]["output_tokens"],
                   requirements_count=len(g["requirements"]), conditions_count=len(g["conditions"]),
                   concepts_count=len(g["concepts"]), typed_cross_corpus_links_count=len(g["links"]),
                   interactions_count=len(g["interactions"]),
                   routes_count=sum(len((x.get("routes") or {}).get("items", [])) for x in g["requirements"]),
                   quarantined_count=len(d["quarantined"]), review_operations_count=d.get("review", {}).get("operations", 0))
        for k in ("provisions_classified", "provisions_total", "normative_provisions", "normative_provisions_in_graph"):
            row[k] = d[k]
        for category in ("nodes", "links"):
            for k,v in d[category].items():
                row["report_" + category + "_" + k.lower() + "_count"] = v
        for stage, items in d["stages"].items():
            row[stage + "_items_count"] = len(items)
            row[stage + "_first_time_accepted_count"] = sum(x["accepted"] and len(x["issues_per_attempt"]) == 1 for x in items.values())
            row[stage + "_repaired_count"] = sum(x["accepted"] and len(x["issues_per_attempt"]) > 1 for x in items.values())
            row[stage + "_quarantined_count"] = sum(not x["accepted"] for x in items.values())
            row[stage + "_attempts_count"] = sum(len(x["issues_per_attempt"]) for x in items.values())
            row[stage + "_issues_over_attempts_count"] = sum(sum(x["issues_per_attempt"]) for x in items.values())
        rows.append(row)
        for pointer,v,kind in numeric_leaves(d):
            numeric.append(dict(record_type="graph_report", run_id=name, source_path=relative(path), json_pointer=pointer, value=v, value_type=kind))
    return rows


def definition(name):
    exact = {
        "run_id": "Semantic SHA-256 of the complete saved attempt, used to deduplicate copies and join tables.",
        "cohort": "case_05_comparison, case_05_baseline, case_01_comparison or exploratory. Do not pool cohorts by default.",
        "reasoning_effort": "Effort inferred from the documented cohort/run number; unknown for exploratory runs.",
        "response_token_limit": "Documented response cap by cohort, not an observed output token count.",
        "elapsed_seconds": "Run's result.seconds, the wall-clock assessment time in seconds.",
        "event_span_seconds": "Maximum minus minimum saved event timestamp; distinct from rounded result.seconds.",
        "model_response_seconds_sum": "Sum of recorded final model-response durations. Parallel calls overlap; this is not run elapsed time.",
        "cost_usd_recorded": "Unavailable: saved artifacts do not contain reliable billing amounts or pricing for the model alias.",
        "assessment_accepted": "1 when findings were accepted and saved final model responses did not fail; 0 for the saved failed attempt.",
        "checks_passed_reviewed": "Pass count from a complete hash-bound source-evidence review; blank without such review.",
        "score_basis": "Current saved key replay. Exploratory runs may use earlier cases/corpora and are not comparable controlled replications.",
        "checks_passed_historical_key": "Same accepted response replayed against the preserved earlier key, not an additional run.",
        "consent_route_closed": "Case 5 brief: a consent route citing Article 19 exists and every matching route is ruled_out.",
        "clauses_route_available": "Case 5 brief: a clauses/safeguards route citing Article 18 is available.",
        "execute_clauses_action_keyword_match": "Mechanical keyword flag on actions for transfer gates citing Article 16. This is not the prose chapter's hand-reviewed guidance judgment.",
        "shared_generation_id": "Raw and reviewed snapshots share one generation cost. Do not add their token usage or elapsed time together.",
        "json_pointer": "Exact JSON-pointer location in source_path; numerics may repeat in result and events, so do not sum this table indiscriminately.",
        "value": "Verbatim numeric or boolean source value. Numeric facts inside the case are data, not runtime metrics.",
    }
    if name in exact:
        return exact[name]
    if name.startswith("captured_"):
        return "Sum of this usage field over saved final llm_response events with the field present. Blank if absent everywhere; excludes unlogged intermediate and retry usage."
    if name.endswith("_response_records_count"):
        return "Number of final model-response records reporting the named usage field; use to inspect measurement coverage."
    if name.startswith("baseline_audit_"):
        return "Recorded baseline audit field, or the number of items in its recorded issue list."
    if name.startswith("brief_missing_"):
        return "Count of missing items of this kind in the saved reviewer brief."
    if name.endswith("_fraction"):
        return "Pass count divided by the number of scored checks, on a 0-to-1 scale."
    if name.endswith("_count"):
        return "Count of the named records/items, computed from the saved source; repeated references count separately unless labelled unique."
    if name.endswith("_tokens"):
        return "Recorded token usage for the named input/output category. Reasoning tokens are included in output, not an extra additive charge."
    if "sha256" in name:
        return "SHA-256 provenance fingerprint; file hashes use original bytes, semantic hashes use canonical JSON."
    if name.endswith("_path"):
        return "Source location relative to the thesis workspace."
    return "Recorded source metadata or derived metric named by this column; see export README for scope and missing-value rules."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intermediate", type=Path, required=True)
    parser.add_argument("--scope", choices=("all", "chapter4"), default="all")
    args = parser.parse_args()
    paths = sorted(set((ROOT / "runs/mock").glob("*.json")) | set((ROOT / "analysis").glob("case_*/*/run*.json")))
    if args.scope == "chapter4":
        paths = sorted(p for p in (ROOT / "analysis/case_05").glob("*/run*.json")
                       if p.parent.name in CONFIGS and re.fullmatch(r"run\d+(?:_failed)?", p.stem))
    groups = defaultdict(list)
    for path in paths:
        data = read(path)
        groups[score.fingerprint(data)].append(path)
    tables = {"all_runs": [], "model_calls": [], "check_scores": [], "graph_metrics": [], "raw_numeric": []}
    audits, sources = [], {}
    for index, (run_id, aliases) in enumerate(sorted(groups.items()), 1):
        path = min(aliases, key=lambda p: ("/analysis/" not in str(p), str(p)))
        data = read(path)
        row, calls, checks = extract(run_id, path, aliases, data)
        assertions = verify_row(row, calls, checks, read(path))
        tables["all_runs"].append(row)
        tables["model_calls"].extend(calls)
        tables["check_scores"].extend(checks)
        for pointer,v,kind in numeric_leaves(data):
            tables["raw_numeric"].append(dict(record_type="assessment", run_id=run_id, source_path=relative(path), json_pointer=pointer, value=v, value_type=kind))
        audits.append(dict(run_id=run_id, source_path=relative(path), assertions_passed=assertions, status="passed"))
        for alias in aliases:
            sources[relative(alias)] = digest_bytes(alias)
        print(f"[{index:02d}/{len(groups)}] {row['cohort']} {row['config']} {path.stem}: {assertions} checks passed", flush=True)
    tables["all_runs"].sort(key=lambda r: (r["case_id"], r["cohort"], r["config"], r["run_number"] or 0, r["started_at_utc"] or ""))
    tables["graph_metrics"] = graph_data(tables["raw_numeric"],
        ("latest", "reviewed") if args.scope == "chapter4" else ("latest", "reviewed", "probe_region_b"))
    cache_paths = sorted((WORKSPACE / "sandbox/kg_mockgen/cache").glob("*.json")) if args.scope == "all" else []
    for path in cache_paths:
        d = read(path)
        usage = d.get("usage") or {}
        c = dict(record_type="graph_generation_cache", run_id="cache_" + path.stem, event_index=0, event_kind="cached_model_response",
                 model=d.get("model"), agent=None, purpose="unassigned_build_stage", attempt_number=None, ok=None,
                 event_time_unix=None, response_seconds=d.get("seconds"), reported_tool_calls=None, usage_present=int(bool(usage)),
                 error=None, source_path=relative(path), source_pointer="")
        c.update({label:get(usage, keys) for label,keys in TOKEN_PATHS.items()})
        tables["model_calls"].append(c)
        for pointer,v,kind in numeric_leaves({k:d[k] for k in ("seconds", "usage") if k in d}):
            tables["raw_numeric"].append(dict(record_type="graph_generation_cache", run_id=c["run_id"], source_path=relative(path), json_pointer=pointer, value=v, value_type=kind))
    # Match every main controlled-run row against the already-established export.
    existing_checks = 0
    for case in ("case_01", "case_05"):
        old = list(csv.DictReader((ROOT / "analysis" / case / "scores_runs.csv").open()))
        for row in tables["all_runs"]:
            if row["cohort"] != case + "_comparison":
                continue
            match = next(x for x in old if x["key_version"] == "reviewed" and x["config"] == row["config"] and x["run"] == "run" + str(row["run_number"]))
            for old_field,new_field in (("seconds","elapsed_seconds"),("model_calls","model_response_records_count"),
                ("tool_calls","tool_calls_count"),("output_tokens","captured_output_tokens"),
                ("passed_auto","checks_passed_raw"),("passed_reviewed","checks_passed_reviewed")):
                if match.get(old_field, "") != "":
                    assert math.isclose(float(match[old_field]), float(row[new_field]), rel_tol=0, abs_tol=1e-8), (row["source_path"],old_field)
                    existing_checks += 1
    controlled = [r for r in tables["all_runs"] if r["cohort"] == "case_05_comparison"]
    assert len(controlled) == 36 and sum(r["checks_count"] for r in controlled) == 576
    assert sum(r["decision_matches_key"] for r in controlled) == 33
    assert sum(r["review_changes_count"] for r in controlled) == 51
    assert len(groups) == len(tables["all_runs"]) and len({r["run_id"] for r in tables["all_runs"]}) == len(groups)
    if args.scope == "chapter4":
        tables["failed_attempts"] = [r for r in tables["all_runs"] if not r["assessment_accepted"]]
        tables["chapter4_runs"] = [r for r in tables.pop("all_runs") if r["assessment_accepted"]]
        assert len(tables["chapter4_runs"]) == 45 and len(tables["failed_attempts"]) == 1
    dictionaries = []
    for table, rows in tables.items():
        columns = list(dict.fromkeys(k for row in rows for k in row))
        for col in columns:
            values = [r[col] for r in rows if r.get(col) is not None]
            dtype = "number" if values and all(isinstance(v,(int,float)) for v in values) else "text"
            dictionaries.append(dict(table=table + ".csv", column=col, data_type=dtype, missing_value="empty field", description=definition(col)))
    tables["data_dictionary"] = dictionaries
    main_rows = tables.get("chapter4_runs", tables.get("all_runs", []))
    payload = dict(tables=tables, audit=dict(export_scope=args.scope, physical_assessment_files=len(paths), unique_assessment_attempts=len(groups),
        duplicate_files_removed=len(paths)-len(groups), per_run_checks=audits, existing_export_comparisons_passed=existing_checks,
        cohort_counts=dict(Counter(r["cohort"] for r in main_rows)), source_hashes=sources,
        table_row_counts={k:len(v) for k,v in tables.items()},
        known_unavailable_attempts=("Case 5 single/generated incomplete attempt is mentioned in notes but its source JSON is unavailable. No measurements were fabricated."
          if args.scope == "chapter4" else "Case 5 single/generated incomplete attempt and two deleted Case 1 multi runs are mentioned in notes but have no saved source JSON in the inventoried folders. No measurements were fabricated.")))
    args.intermediate.parent.mkdir(parents=True, exist_ok=True)
    args.intermediate.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False))
    print(json.dumps(payload["audit"]["table_row_counts"]),flush=True)
    print(f"Existing-export comparisons passed: {existing_checks}",flush=True)


if __name__ == "__main__":
    main()
