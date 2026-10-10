"""Run scenarios from the command line and save the full trace of each run.

    .venv/bin/python run.py scenarios/case_study_a_ie_gp_to_ie_cloud_ehr_domestic.json
    .venv/bin/python run.py scenarios/ --repeat 3       # every scenario, 3 times each
    .venv/bin/python run.py scenarios/ --fake           # offline, scripted model

A scenario file is {"request": {...}, "expected": {...}}; "expected" is never
shown to the agents. Results go to runs/<timestamp>/.
"""

import argparse
import json
import time
from pathlib import Path

from app import llm
from app.graph import run


def short(event):
    """One line per event, for --verbose."""
    kind, agent = event["kind"], event["agent"]
    if kind == "stage":
        return f"[{agent}] {event['status']}"
    if kind == "retrieval":
        return f"[{agent}] search '{event['query']}' -> {[h['id'] for h in event['hits']]}"
    if kind == "llm_response":
        return f"[{agent}] model reply ({event.get('purpose')}) ok={event['ok']}"
    if kind in ("gap", "delegation", "routing", "decision"):
        return f"[{agent}] {kind}: " + json.dumps({k: v for k, v in event.items() if k not in ('time', 'kind', 'agent')})[:300]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="scenario files or folders")
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario (to measure consistency)")
    parser.add_argument("--fake", action="store_true", help="use the scripted offline model")
    parser.add_argument("--verbose", action="store_true", help="print trace events as they happen")
    args = parser.parse_args()

    if args.fake:
        from tests.test_offline import fake_model
        llm.FAKE_MODEL = fake_model

    files = []
    for path in map(Path, args.paths):
        files += sorted(path.glob("*.json")) if path.is_dir() else [path]
    out_dir = Path("runs") / time.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)

    rows = []
    for file in files:
        scenario = json.loads(file.read_text())
        request, expected = scenario.get("request", scenario), scenario.get("expected", {})
        for n in range(1, args.repeat + 1):
            on_event = (lambda e: (line := short(e)) and print("   ", line)) if args.verbose else None
            result, events = run(request, on_event=on_event)
            record = {"scenario": file.name, "run": n, "model": "fake" if args.fake else llm.os.environ.get("MODEL"),
                      "expected": expected, "result": result, "events": events, "request": request}
            (out_dir / f"{file.stem}_run{n}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
            wanted = expected.get("decision")
            match = "" if not wanted else ("match" if wanted == result["decision"] else "DIFFERENT")
            print(f"{file.stem} #{n}: {result['decision']}  (expected {wanted or '-'}) {match}  "
                  f"{result['seconds']}s, {len(result['findings'])} findings, {len(result['gaps'])} gaps")
            rows.append({"scenario": file.stem, "run": n, "decision": result["decision"],
                         "expected": wanted})

    (out_dir / "summary.json").write_text(json.dumps(rows, indent=1))
    scored = [r for r in rows if r["expected"]]
    if scored:
        hits = sum(r["decision"] == r["expected"] for r in scored)
        print(f"\nDecision matches expectation: {hits}/{len(scored)}")
    print(f"Saved to {out_dir}/")


if __name__ == "__main__":
    main()
