"""Reproduce reviewed score tables and before/after figures without model calls.

Run in the prototype environment; use --figures-only in an environment with matplotlib.
The authoritative evidence judgments live in ../score_reviews.json.
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
CONFIGS = ('single_no_graph', 'single_graph', 'multi_no_graph', 'multi_graph')
EFFORTS = ('high', 'medium', 'low')
LABELS = ('Single + citation graph', 'Single + normative KG',
          'Multi + citation graph', 'Multi + normative KG')
COLORS = ('#8b596c', '#c48726', '#377fa2', '#17856d')


def compute():
    sys.path.insert(0, str(PROTOTYPE))
    from engine import score
    from analysis import export_scores

    baseline = json.loads((OUT / 'before/evaluation.json').read_text())
    original = {(r['config'], r['run']): r for r in baseline['runs']}
    rows = []
    for config in CONFIGS:
        for n in range(1, 10):
            data = json.loads((CASE / config / f'run{n}.json').read_text())
            card = score.score_file(data['result'], CASE / 'key.json')
            raw = score.outcomes(card)
            assert raw == original[(config, n)]['checks'], 'Historical matcher outcomes changed.'
            reviewed = score.outcomes(card['reviewed']) if card.get('reviewed') else None
            rows.append({**original[(config, n)], 'raw_checks': raw,
                         'raw_score': sum(raw.values()),
                         'reviewed_checks': reviewed,
                         'reviewed_score': sum(reviewed.values()) if reviewed is not None else None,
                         'review_status': card['review_status'],
                         'corrections': [r['review'] for r in score.check_rows(card.get('reviewed', card)).values()
                                         if r.get('review')]})
    groups = []
    for config, label in zip(CONFIGS, LABELS):
        for effort in EFFORTS:
            runs = [r for r in rows if r['config'] == config and r['effort'] == effort]
            reviewed = [r for r in runs if r['reviewed_score'] is not None]
            groups.append({'config': config, 'label': label, 'effort': effort,
                           'n_raw': len(runs), 'n_reviewed': len(reviewed),
                           'raw_scores': [r['raw_score'] for r in runs],
                           'reviewed_scores': [r['reviewed_score'] for r in runs],
                           'raw_mean': statistics.mean(r['raw_score'] for r in runs),
                           'reviewed_mean': statistics.mean(r['reviewed_score'] for r in reviewed) if reviewed else None,
                           'seconds_mean': statistics.mean(r['seconds'] for r in runs),
                           'captured_output_tokens_mean': statistics.mean(r['captured_output_tokens'] for r in runs),
                           'correct_decisions': sum(r['decision_ok'] for r in runs)})
    corrections = [c for r in rows for c in r['corrections']]
    report = {'date': '2026-10-11', 'case': baseline['case'], 'runs_reviewed': sum(r['review_status'] == 'reviewed' for r in rows),
              'selected_checks_reviewed': sum(len(r['reviewed_checks'] or {}) for r in rows),
              'false_failures_repaired': sum(c['passed'] for c in corrections),
              'false_passes_removed': sum(not c['passed'] for c in corrections),
              'definition': 'Evidence-reviewed agreement on the same 16 selected concepts, not complete legal accuracy.',
              'reviewer': 'Codex offline source review; draft answer key still awaits author sign-off.',
              'raw_scores_preserved': True, 'decisions_changed': False,
              'scorer_source_sha256': hashlib.sha256((PROTOTYPE / 'engine/score.py').read_bytes()).hexdigest(),
              'review_ledger_sha256': score.fingerprint(json.loads((CASE / 'score_reviews.json').read_text())),
              'limitations': baseline['limitations'], 'groups': groups, 'runs': rows}
    report['limitations'] = [s for s in report['limitations'] if not s.startswith('Raw scorer totals')]
    report['limitations'].append('Reviewed judgments accept correct explicit concepts in any accepted final output compartment. '
                                 'Complete reasoning, conflicting extra grounds and wider compliance remain separate qualitative dimensions.')
    (OUT / 'corrected_scores.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    export_scores.main(CASE)
    print(f"{report['selected_checks_reviewed']} checks reviewed; {report['false_failures_repaired']} false failures repaired; "
          f"{report['false_passes_removed']} false passes removed.")
    for g in groups:
        print(g['config'], g['effort'], g['raw_scores'], '->', g['reviewed_scores'])


def figures():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    report = json.loads((OUT / 'corrected_scores.json').read_text())
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.4), sharex=True, sharey=True)
    for ax, config, label, color in zip(axes.flat, CONFIGS, LABELS, COLORS):
        groups = [next(g for g in report['groups'] if g['config'] == config and g['effort'] == effort)
                  for effort in EFFORTS]
        ax.plot(range(3), [g['raw_mean'] for g in groups], color='#939393', linestyle='--', marker='o', linewidth=2)
        ax.plot(range(3), [g['reviewed_mean'] for g in groups], color=color, marker='o', linewidth=2.5)
        for x, g in enumerate(groups):
            ax.scatter([x - .035, x, x + .035], g['reviewed_scores'], color=color, s=27, alpha=.65)
            ax.annotate(f"{g['raw_mean']:.1f} to {g['reviewed_mean']:.1f}",
                        (x, g['reviewed_mean']), xytext=(0, 10), textcoords='offset points',
                        ha='center', fontsize=10, color=color)
        ax.set(title=label, xticks=range(3), xticklabels=[e.title() for e in EFFORTS],
               ylim=(6.5, 17.1), xlim=(-.25, 2.25), yticks=(8, 10, 12, 14, 16))
        ax.tick_params(labelbottom=True)
        ax.grid(axis='y', alpha=.18)
    for ax in axes[:, 0]: ax.set_ylabel('Selected checks passed (of 16)')
    fig.suptitle('Case 05: raw matching versus evidence-reviewed scores', fontsize=17, y=.98)
    handles = [Line2D([], [], color='#939393', linestyle='--', marker='o', label='Raw automated mean'),
               Line2D([], [], color='#17856d', marker='o', label='Reviewed mean'),
               Line2D([], [], color='#17856d', linestyle='none', marker='o', markersize=4, label='Reviewed individual runs')]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .065), ncol=3, frameon=False)
    fig.text(.5, .018, 'All 576 selected checks reviewed across 36 completed runs (n = 3 per cell). '
             '49 false failures repaired; 2 false passes removed.\n'
             'The same 16-check denominator and model answers are preserved. Reviewed agreement excludes broader reasoning/completeness defects.',
             ha='center', fontsize=9, color='#555555')
    fig.tight_layout(rect=(0, .14, 1, .93))
    for extension in ('png', 'svg'):
        fig.savefig(OUT / f'before_after_scores.{extension}', dpi=170, facecolor='white')
    plt.close(fig)
    print('Rendered before_after_scores.png and .svg.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--figures-only', action='store_true')
    args = parser.parse_args()
    figures() if args.figures_only else compute()
