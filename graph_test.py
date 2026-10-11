"""With vs without the generated normative graph: repeated runs of the same cases, scored against their keys.

    .venv/bin/python graph_test.py run cases/04_a1_genetic_result_to_b_life_insurer generated   # one run
    .venv/bin/python graph_test.py report                                                        # compare

Runs are saved to runs/graph_test/ with their graph mode. The report groups them by case and mode and
gives, for every key check, how many runs passed it, the "tricky conditional" checks first. The tricky
set is the reviewer's choice of checks that turn on an exception, a cross-corpus restriction, a category
boundary or another jurisdiction's law; it is evaluation only and never reaches a model.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from engine import graph, pipeline, score

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / 'runs' / 'graph_test'
TRICKY = {
    '01_a1_gp_to_region_b_host': [
        'requirement:transfer_route', 'requirement:a1_transfer_conditions', 'requirement:impact_assessment',
        'requirement:host_retention', 'requirement:region_b_sector_rules', 'route:recognition', 'route:derogations',
        'route:legitimate_interests', 'route:approved_clauses_with_measures', 'route:return_and_keep_no_copy',
        'conflict:retention_vs_deletion', 'question:region_b_access_law', 'trap:recognition_relied_on',
        'trap:derogation_relied_on'],
    '04_a1_genetic_result_to_b_life_insurer': [
        'requirement:sensitive_condition', 'requirement:transfer_route', 'requirement:a1_genetic_restriction',
        'requirement:lawful_ground', 'requirement:a1_professional_secrecy', 'requirement:region_b_sector_rules',
        'route:sensitive_consent', 'route:consent_derogation', 'route:recognition',
        'trap:consent_lifts_genetic_prohibition', 'trap:consent_derogation_relied_on', 'trap:recognition_relied_on',
        'trap:secrecy_blocks_consented_disclosure'],
    '05_a1_genetic_second_opinion_in_b': [
        'decision', 'requirement:transfer_route', 'requirement:a1_genetic_transfer_restriction',
        'requirement:sensitive_condition', 'route:consent_derogation', 'route:approved_clauses',
        'trap:consent_derogation_relied_on', 'trap:genetic_consent_bar_overextended'],
}


def run(case_dir, mode):
    graph.MODE = mode
    case_dir = Path(case_dir)
    case = json.loads((case_dir / 'case.json').read_text())
    result, events = pipeline.run(case)
    path = pipeline.save(result, events, f'{mode}_{case_dir.name}', folder=FOLDER)
    print(f"{case_dir.name} [{mode}] -> {result['decision']} ({result['seconds']}s) {path.name}")


def checks(card):
    out = {'decision': card['decision']['ok']}
    for section in ('requirements', 'routes', 'conflicts', 'questions'):
        out |= {f"{section[:-1]}:{r['id']}": r['ok'] for r in card[section]}
    out |= {f"trap:{r['id']}": not r['violated'] for r in card['must_not']}
    return out


def report():
    groups = defaultdict(list)
    for path in sorted(FOLDER.glob('*.json')):
        data = json.loads(path.read_text())
        mode = data.get('graph', 'runtime')
        case = path.stem.split('_', 2)[2] if path.stem.split('_')[1] in ('runtime', 'generated') else path.stem
        key = json.loads((ROOT / 'cases' / case / 'key.json').read_text())
        card = score.score_file(data['result'], ROOT / 'cases' / case / 'key.json')
        card['cost'] = score.cost(data.get('events', []))
        card['got'] = data['result']['decision']
        groups[(case, mode)].append(card)
    lines = ['# Graph support test: runtime citation graph vs generated normative graph\n']
    for case in sorted({c for c, _ in groups}):
        modes = [m for m in ('runtime', 'generated') if (case, m) in groups]
        cards = {m: groups[(case, m)] for m in modes}
        lines.append(f"## {case}\n")
        lines.append('| check | ' + ' | '.join(f'{m} (n={len(cards[m])})' for m in modes) + ' |')
        lines.append('|---|' + '---|' * len(modes))
        names = list(checks(cards[modes[0]][0]))
        tricky = [n for n in TRICKY.get(case, []) if n in names]
        rest = [n for n in names if n not in tricky]
        totals = {m: [0, 0] for m in modes}
        for label, group in (('**tricky**', tricky), ('other', rest)):
            lines.append(f'| {label} |' + ' |' * len(modes))
            for n in group:
                row = []
                for m in modes:
                    ok = sum(checks(c)[n] for c in cards[m])
                    row.append(f'{ok}/{len(cards[m])}')
                    if group is tricky:
                        totals[m][0] += ok
                        totals[m][1] += len(cards[m])
                lines.append(f'| {n} | ' + ' | '.join(row) + ' |')
        lines.append('| **tricky total** | ' + ' | '.join(f'**{a}/{b}**' for a, b in totals.values()) + ' |')
        lines.append('| decisions | ' + ' | '.join(', '.join(c['got'] for c in cards[m]) for m in modes) + ' |')
        if any(c.get('reviewed') for m in modes for c in cards[m]):
            lines.append('| reviewed checks passed per run | ' + ' | '.join(', '.join(
                str(sum(checks(c['reviewed']).values())) if c.get('reviewed') else '-'
                for c in cards[m]) for m in modes) + ' |')
        for field in ('seconds', 'model_calls', 'tool_calls', 'output_tokens'):
            lines.append(f'| mean {field} | ' + ' | '.join(
                str(round(sum(c['cost'][field] for c in cards[m]) / len(cards[m]))) for m in modes) + ' |')
        lines.append('')
    text = '\n'.join(lines)
    (FOLDER / 'report.md').write_text(text)
    print(text)


if __name__ == '__main__':
    if sys.argv[1] == 'run':
        run(sys.argv[2], sys.argv[3])
    else:
        report()
