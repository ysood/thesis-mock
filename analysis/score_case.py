"""Score an analysis case folder: every <config>/runN.json against the folder's key.json.

    .venv/bin/python analysis/score_case.py analysis/case_05

Prints, for every key check, how many runs of each configuration passed it, then cost per configuration.
Shows raw provision matches and evidence-reviewed scores separately; never calls a model.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import score  # noqa: E402

CONFIGS = ['single_no_graph', 'single_graph', 'multi_no_graph', 'multi_graph']


def checks(card):
    out = {'decision': card['decision']['ok']}
    for section in ('requirements', 'routes', 'conflicts', 'questions'):
        out |= {f"{section[:-1]}:{r['id']}": r['ok'] for r in card[section]}
    out |= {f"trap:{r['id']}": not r['violated'] for r in card['must_not']}
    return out


def main(folder):
    folder = Path(folder)
    key = json.loads((folder / 'key.json').read_text())
    cards = {}
    for config in CONFIGS:
        runs = sorted((folder / config).glob('run*.json'), key=lambda p: int(p.stem[3:]))
        cards[config] = []
        for path in runs:
            data = json.loads(path.read_text())
            card = score.score_file(data['result'], folder / 'key.json')
            card['cost'], card['run'] = score.cost(data.get('events', [])), path.stem
            card['config_check'] = (data.get('mode'), data.get('graph', 'runtime'))
            cards[config].append(card)
    configs = [c for c in CONFIGS if cards[c]]
    if not configs:
        raise SystemExit(f'No runs yet in {folder} (expected <config>/run1.json ...)')
    names = list(checks(cards[configs[0]][0]))
    print(f"| check | {' | '.join(f'{c} (n={len(cards[c])})' for c in configs)} |")
    print('|---|' + '---|' * len(configs))
    for name in names:
        print(f'| {name} | ' + ' | '.join(f"{sum(checks(k)[name] for k in cards[c])}/{len(cards[c])}" for c in configs) + ' |')
    totals = [sum(sum(checks(k).values()) for k in cards[c]) for c in configs]
    print('| **total passed** | ' + ' | '.join(f'**{t}/{len(names) * len(cards[c])}**' for t, c in zip(totals, configs)) + ' |')
    if any(k.get('reviewed') for c in configs for k in cards[c]):
        print('| **reviewed total passed** | ' + ' | '.join(
            f"**{sum(sum(checks(k['reviewed']).values()) for k in cards[c] if k.get('reviewed'))}/"
            f"{len(names) * sum(bool(k.get('reviewed')) for k in cards[c])}**"
            for c in configs) + ' |')
        for effort, run_names in (('high', {'run1', 'run2', 'run3'}),
                                 ('medium', {'run4', 'run5', 'run6'}), ('low', {'run7', 'run8', 'run9'})):
            print(f'| reviewed {effort}: per-run scores | ' + ' | '.join(
                ', '.join(str(sum(checks(k['reviewed']).values())) if k.get('reviewed') else '-'
                          for k in cards[c] if k['run'] in run_names)
                for c in configs) + ' |')
        print('Reviewed totals apply only to hash-matched, fully reviewed answers. Raw totals remain unchanged.')
    for field in ('seconds', 'model_calls', 'tool_calls', 'output_tokens'):
        print(f'| mean {field} | ' + ' | '.join(
            str(round(sum(k['cost'][field] for k in cards[c]) / len(cards[c]))) for c in configs) + ' |')
    print()
    for c in configs:
        print(c, '; '.join(f"{k['run']}={k['config_check'][0]}/{k['config_check'][1]}" for k in cards[c]))


if __name__ == '__main__':
    main(sys.argv[1])
