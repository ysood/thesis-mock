"""Offline Case 05 evaluation. Does not call models or alter historical runs.

Compute with the prototype environment:
  prototype-mock/.venv/bin/python prototype-mock/analysis/case_05/evaluation_20261011/evaluate.py
Render with a Python environment containing matplotlib:
  python evaluate.py --figures-only
"""

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
CASE = OUT.parent
PROTOTYPE = CASE.parent.parent
CONFIGS = ("single_no_graph", "single_graph", "multi_no_graph", "multi_graph")
EFFORTS = ("high", "medium", "low")
LABELS = {
    "single_no_graph": "Single + citation graph",
    "single_graph": "Single + normative KG",
    "multi_no_graph": "Multi + citation graph",
    "multi_graph": "Multi + normative KG",
}
COLORS = ("#8b596c", "#c48726", "#377fa2", "#17856d")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute():
    sys.path.insert(0, str(PROTOTYPE))
    from engine import score
    from engine.schema import Case
    from analysis.score_case import checks

    key = json.loads((CASE / "key.json").read_text())
    case = Case.model_validate(json.loads((CASE / "case.json").read_text())).model_dump()
    rows = []
    for config in CONFIGS:
        for run in range(1, 10):
            path = CASE / config / f"run{run}.json"
            data = json.loads(path.read_text())
            expected = ("single" if config.startswith("single") else "multi",
                        "runtime" if config.endswith("no_graph") else "generated")
            assert (data["mode"], data["graph"]) == expected, path
            result, events = data["result"], data["events"]
            assert result["case"] == case, path
            card = score.score_file(result, CASE / 'key.json')
            check_map = checks(card)
            assert len(check_map) == 16, path
            replies = [e for e in events if e["kind"] == "llm_response"]
            usage = [e.get("usage") or {} for e in replies]
            cost = score.cost(events)
            rows.append({
                "config": config, "label": LABELS[config], "run": run,
                "effort": EFFORTS[(run - 1) // 3],
                "effort_source": "README cohort assignment, not stored API configuration",
                "model": data["model"], "source": str(path.relative_to(CASE)),
                "source_sha256": digest(path), "decision": result["decision"],
                "decision_ok": card["decision"]["ok"],
                "checks_passed": sum(check_map.values()), "checks_total": len(check_map),
                "check_pass_rate": sum(check_map.values()) / len(check_map),
                "checks": check_map, "seconds": result["seconds"],
                "review_status": card['review_status'],
                "reviewed_checks": score.outcomes(card['reviewed']) if card.get('reviewed') else None,
                "checks_passed_reviewed": sum(score.outcomes(card['reviewed']).values()) if card.get('reviewed') else None,
                "event_span_seconds": cost["seconds"],
                "captured_output_tokens": cost["output_tokens"],
                "captured_input_tokens": sum(u.get("input_tokens", 0) for u in usage),
                "captured_cached_input_tokens": sum(
                    (u.get("input_token_details") or {}).get("cache_read", 0) for u in usage),
                "captured_reasoning_tokens": sum(
                    (u.get("output_token_details") or {}).get("reasoning", 0) for u in usage),
                "logged_assessment_responses": len(replies), "tool_calls": cost["tool_calls"],
                "logged_failed_responses": sum(e.get("ok") is False for e in replies),
                "logged_retries": sum(e["kind"] == "llm_retry" for e in events),
                "findings": len(result["findings"]),
                "verified_findings": sum(f["verified"] for f in result["findings"]),
                "unscored_open_gates": card["extra_blocking"],
                "conclusion_issues": result.get("conclusion_issues", []),
            })
    groups = []
    for config in CONFIGS:
        for effort in EFFORTS:
            runs = [r for r in rows if r["config"] == config and r["effort"] == effort]
            group = {"config": config, "label": LABELS[config], "effort": effort,
                     "n": len(runs), "scores": [r["checks_passed"] for r in runs],
                     "decisions_correct": sum(r["decision_ok"] for r in runs)}
            reviewed = [r for r in runs if r['checks_passed_reviewed'] is not None]
            group['n_reviewed'] = len(reviewed)
            group['reviewed_scores'] = [r['checks_passed_reviewed'] for r in runs]
            group['checks_passed_reviewed_mean'] = statistics.mean(r['checks_passed_reviewed'] for r in reviewed) if reviewed else None
            for field in ("checks_passed", "check_pass_rate", "seconds", "captured_output_tokens",
                          "captured_input_tokens", "captured_cached_input_tokens",
                          "captured_reasoning_tokens", "logged_assessment_responses", "tool_calls"):
                values = [r[field] for r in runs]
                for suffix, fn in (("mean", statistics.mean), ("sd", statistics.stdev),
                                   ("median", statistics.median), ("min", min), ("max", max)):
                    group[f"{field}_{suffix}"] = fn(values)
            groups.append(group)
    mg = {g["effort"]: g for g in groups if g["config"] == "multi_graph"}
    savings = {}
    for baseline in ("high", "medium"):
        savings[f"multi_graph_low_vs_{baseline}"] = {
            field: 1 - mg["low"][f"{field}_mean"] / mg[baseline][f"{field}_mean"]
            for field in ("seconds", "captured_output_tokens", "captured_input_tokens")}
    report = {
        "case": "05_a1_genetic_second_opinion_in_b", "date": "2026-10-11",
        "n_completed_runs": len(rows), "n_correct_decisions": sum(r["decision_ok"] for r in rows),
        "metric_name": "Selected automated checklist pass rate, not full legal accuracy",
        "key_sha256": digest(CASE / "key.json"), "key_status": key.get("status"),
        "current_case_sha256": digest(CASE / "case.json"),
        "current_graph_sha256": digest(PROTOTYPE / "kg/generated_graph.json"),
        "scorer_sha256": digest(PROTOTYPE / "engine/score.py"),
        "limitations": [
            "One purpose-designed fictional case, three completed repetitions per experimental cell.",
            "Four configurations have nine runs each: 36 runs, not nine independent cases.",
            "16 checks: one decision, nine requirements, four routes and two absence-based traps; correlated checks.",
            "Raw totals and plots are retained; reviewed checks and means are separately labelled when an exact bound review exists.",
            "The no_graph folder names refer to a runtime citation graph, not absence of graph retrieval.",
            "High cohorts used default 16000 output cap; medium/low reportedly used 40000.",
            "Effort and output cap are inferred from README, not recorded per API request.",
            "Usage records only final responses within assessment tool loops; intermediate and retry usage omitted.",
            "Logged assessment response counts are not the count of all underlying API invocations.",
            "Output tokens are an incomplete token proxy, not dollar cost; input and caching also matter.",
            "At least one omitted incomplete single/KG high attempt prevents full attempt reliability or cost estimates.",
            "The key is draft and was reviewed after exploratory runs; qualitative manual checks are outside 16-point total.",
            "Verified findings establish reference integrity, not semantic correctness.",
            "Hashes identify current analysis artifacts; corpus/graph/code hashes were not saved at run time.",
        ],
        "savings": savings, "groups": groups, "runs": rows,
    }
    (OUT / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    for g in groups:
        print(g["config"], g["effort"], g["scores"],
              f'{g["seconds_mean"]:.1f}s', f'{g["captured_output_tokens_mean"]:.0f} output tokens',
              f'{g["decisions_correct"]}/3 decisions')
    print("Savings", savings)


def render():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from matplotlib.lines import Line2D

    report = json.loads((OUT / "evaluation.json").read_text())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none"})
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.4))
    metrics = (("checks_passed", "Selected checklist score", "Passed checks (of 16)", 1),
               ("seconds", "End-to-end latency", "Seconds", 1),
               ("captured_output_tokens", "Captured output token proxy", "Tokens (thousands)", 1000))
    for ax, (field, title, ylabel, scale) in zip(axes, metrics):
        for i, (config, color) in enumerate(zip(CONFIGS, COLORS)):
            x = np.arange(3) + (i - 1.5) * .04
            means = []
            for j, effort in enumerate(EFFORTS):
                runs = [r for r in report["runs"] if r["config"] == config and r["effort"] == effort]
                means.append(statistics.mean(r[field] for r in runs) / scale)
                ax.scatter([x[j] - .018, x[j], x[j] + .018], [r[field] / scale for r in runs],
                           color=color, alpha=.4, s=25, zorder=3)
            ax.plot(x, means, color=color, marker="o", linewidth=2, markersize=5, label=LABELS[config])
        ax.set(title=title, ylabel=ylabel, xticks=range(3), xticklabels=[e.title() for e in EFFORTS])
        ax.set_xlim(-.18, 2.18)
        ax.grid(axis="y", alpha=.18)
        if field == "checks_passed":
            ax.set_ylim(6, 16.5)
            ax.set_yticks(range(6, 17, 2))
        else:
            ax.set_ylim(bottom=0)
    fig.suptitle("Case 05: reasoning effort across four configurations", fontsize=17, y=.98)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=4, frameon=False,
               bbox_to_anchor=(.5, .08))
    fig.text(.5, .025, "Dots: individual completed runs. Lines: cell means (n = 3). Fictional diagnostic case.\n"
             "Checklist scores omit manual reasoning checks. Captured tokens omit intermediate tool responses and retries.",
             ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, .19, 1, .9))
    for suffix in ("png", "svg"):
        fig.savefig(OUT / f"effort_comparison.{suffix}", dpi=170, facecolor="white")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 7.5))
    for i, (config, color) in enumerate(zip(CONFIGS, COLORS)):
        for effort, marker in zip(EFFORTS, ("s", "^", "o")):
            g = next(g for g in report["groups"] if g["config"] == config and g["effort"] == effort)
            ax.errorbar(g["seconds_mean"], g["checks_passed_mean"],
                        xerr=g["seconds_sd"], yerr=g["checks_passed_sd"],
                        fmt=marker, color=color, capsize=3, markersize=8, alpha=.85)
            if effort == "low" and config.endswith("graph") and not config.endswith("no_graph"):
                ax.annotate(f'{LABELS[config]}, low',
                            (g["seconds_mean"], g["checks_passed_mean"]), xytext=(9, 11),
                            textcoords="offset points", fontsize=9, color=color)
    ax.set(xlabel="Mean end-to-end latency (seconds)", ylabel="Mean selected checklist score (of 16)",
           title="Observed latency versus checklist coverage", ylim=(6.5, 17.1), xlim=(0, 750))
    ax.grid(alpha=.15)
    handles = [Line2D([], [], color=color, linewidth=2, label=LABELS[config])
               for config, color in zip(CONFIGS, COLORS)]
    handles += [Line2D([], [], color="#555555", marker=marker, linestyle="none", label=effort.title())
                for effort, marker in zip(EFFORTS, ("s", "^", "o"))]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .085), ncol=4, frameon=False)
    fig.text(.5, .025, "Error bars: sample standard deviations across three completed runs, not confidence intervals.\n"
             "Equal checklist scores do not establish equal substantive reasoning quality.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .21, 1, 1))
    for suffix in ("png", "svg"):
        fig.savefig(OUT / f"latency_checklist_tradeoff.{suffix}", dpi=170, facecolor="white")
    plt.close(fig)

    low = [r for config in CONFIGS for r in report["runs"]
           if r["config"] == config and r["effort"] == "low"]
    names = list(low[0]["checks"])
    matrix = np.array([[int(r["checks"][name]) for r in low] for name in names])
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(matrix, cmap=ListedColormap(["#cb6764", "#72b99b"]), vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(low)), [f'{LABELS[r["config"]]}\nRun {r["run"]}' for r in low],
                  rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(len(names)), [n.replace("requirement:", "req: ").replace("route:", "route: ")
                                    .replace("trap:", "trap: ") for n in names], fontsize=9)
    for y in range(len(names)):
        for x in range(len(low)):
            ax.text(x, y, "Pass" if matrix[y, x] else "Fail", ha="center", va="center", fontsize=8)
    for x in (2.5, 5.5, 8.5): ax.axvline(x, color="white", linewidth=3)
    ax.set_title("Low effort: raw automated checks, including citation-matching misses", pad=16, fontsize=15)
    fig.text(.5, .025, "A failed check can reflect citation placement or omitted structured findings.\n"
             "Manual review finds correctly explained A1 restrictions in Single + KG runs 7/8 despite failed matches.\n"
             "All Multi + KG runs pass this checklist but leave the general high-risk assessment insufficiently reasoned.",
             ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, .1, 1, 1))
    for suffix in ("png", "svg"):
        fig.savefig(OUT / f"low_effort_checks.{suffix}", dpi=170, facecolor="white")
    plt.close(fig)
    print("Rendered three figures as PNG and SVG.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--figures-only", action="store_true")
    args = parser.parse_args()
    if args.figures_only:
        render()
    else:
        compute()
