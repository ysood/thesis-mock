"""Score saved runs against their case's answer key.

    .venv/bin/python score_mock.py                       # every saved run that has a key, plus a consistency matrix
    .venv/bin/python score_mock.py runs/mock/<run>.json  # one run, with details
    .venv/bin/python score_mock.py --json scores.json    # also write all scorecards to a file
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

from engine import score

ROOT = Path(__file__).resolve().parent
TICK = {True: '✓', False: '✗'}


def load(path):
    data = json.loads(path.read_text())
    case = score.case_name(path.name)
    key_path = ROOT / 'cases' / case / 'key.json'
    if not key_path.exists():
        return None
    card = score.score_file(data['result'], key_path)
    card['cost'] = score.cost(data.get('events', []))
    card['run'], card['case'], card['model'] = path.name, case, data.get('model')
    return card


def details(card):
    print(f"\n=== {card['run']}  ({card['model']})")
    print(f"decision {TICK[card['decision']['ok']]} {card['decision']['got']} (expect {card['decision']['expect']}) · "
          f"engaged {TICK[card['engaged']['ok']]} · refs verified {card['verified']} · "
          f"{card['cost']['seconds']}s, {card['cost']['model_calls']} calls, {card['cost']['output_tokens']} output tokens")
    if card.get('reviewed'):
        m = card['review_metadata']
        print(f"selected checks: raw {m['raw_passed']} / reviewed {m['reviewed_passed']} "
              f"({m['checks_reviewed']} checks; {m['reviewer']})")
        for section, row in score.check_rows(card['reviewed']).items():
            if row.get('review'):
                r = row['review']
                print(f"  reviewed {section}: {TICK[r['passed']]} {r['reason']}")
    print('requirements')
    for r in card['requirements']:
        extra = f"  missing citation {r['missing_citation']}" if r.get('missing_citation') else ''
        extra += f"  (also: {', '.join(r['disagreeing'])})" if r.get('disagreeing') else ''
        print(f"  {TICK[r['ok']]} {r['id']:26} {str(r['status']):16} expect {'/'.join(r['expect']):16} {r['best'] or 'NOT FOUND'}{extra}")
    print('routes')
    for r in card['routes']:
        print(f"  {TICK[r['ok']]} {r['id']:30} {', '.join(r['statuses']) or 'NOT FOUND':32} expect {'/'.join(r['expect'])}")
    for label in ('conflicts', 'questions'):
        print(label)
        for r in card[label]:
            print(f"  {TICK[r['ok']]} {r['id']}" + (f"  (asked {r['times_asked']}x)" if 'times_asked' in r else ''))
    print('traps')
    for r in card['must_not']:
        print(f"  {'✗ VIOLATED' if r['violated'] else '✓'} {r['id']}" + (f": {'; '.join(r['hits'])}" if r['hits'] else ''))
    if card['extra_blocking']:
        print('blocking findings not in the key (check by hand):', ', '.join(card['extra_blocking']))


def matrix(cards):
    print(f"\n=== consistency: {cards[0]['case']} over {len(cards)} runs")
    rows = [('decision', [c['decision']['ok'] for c in cards])]
    for section in ('requirements', 'routes', 'conflicts', 'questions'):
        for i, item in enumerate(cards[0][section]):
            rows.append((f"{section[:-1]}:{item['id']}", [c[section][i]['ok'] for c in cards]))
    rows += [(f"trap:{item['id']}", [not c['must_not'][i]['violated'] for c, _ in zip(cards, cards)])
             for i, item in enumerate(cards[0]['must_not'])]
    print(f"{'check':42} " + ' '.join(c['run'][9:15] for c in cards) + '  pass')
    for name, oks in rows:
        print(f"{name:42} " + ' '.join(f'{TICK[o]:^6}' for o in oks) + f"  {sum(oks)}/{len(oks)}")
    if any(c.get('reviewed') for c in cards):
        print(f"{'reviewed selected-check total':42} " + ' '.join(
            f"{sum(score.outcomes(c['reviewed']).values()):^6}" if c.get('reviewed') else '  -   ' for c in cards))
    print(f"{'seconds':42} " + ' '.join(f"{c['cost']['seconds']:^6}" for c in cards))
    print(f"{'model calls':42} " + ' '.join(f"{c['cost']['model_calls']:^6}" for c in cards))


def main(args):
    out = None
    if '--json' in args:
        out = Path(args[args.index('--json') + 1])
        args = [a for a in args if a not in ('--json', str(out))]
    paths = [Path(a) for a in args] or sorted((ROOT / 'runs' / 'mock').glob('*.json'))
    cards = [c for c in (load(p) for p in paths) if c]
    for card in cards:
        details(card)
    by_case = defaultdict(list)
    for card in cards:
        by_case[card['case']].append(card)
    for group in by_case.values():
        if len(group) > 1:
            matrix(group)
    if out:
        out.write_text(json.dumps(cards, indent=1))
        print(f'\nWrote {out}')


if __name__ == '__main__':
    main(sys.argv[1:])
