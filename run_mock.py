"""Run a mock case end to end and print the reviewer brief.

    .venv/bin/python run_mock.py cases/01_a1_gp_to_region_b_host
    TRAVERSAL_TOOLS=0 .venv/bin/python run_mock.py <case>   # ablation: whole corpus in context
"""

import json
import sys
from pathlib import Path

from engine import pipeline

ICONS = {'met': '🟢', 'unmet': '🔴', 'undetermined': '🟡', 'not_applicable': '⚪'}


def show(event):
    if event['kind'] == 'stage':
        print(f"  [{event['agent']}] {event['status']}")
    elif event['kind'] == 'tool_call':
        print(f"    · {event['agent']} {event['tool']}({next(iter(event['args'].values()))})")
    elif event['kind'] == 'llm_response' and not event.get('ok'):
        print(f"  ! {event['agent']} call failed: {event.get('error', '')[:200]}")


def main(folder):
    folder = Path(folder)
    case = json.loads((folder / 'case.json').read_text())
    result, events = pipeline.run(case, on_event=show)
    path = pipeline.save(result, events, folder.name)
    b = result['brief']
    print(f"\nDECISION: {result['decision']}  ({result['seconds']}s)")
    for reason in result['reasons']:
        print('  -', reason)
    print('\nREQUIRED')
    for r in b['required']:
        print(f"  {ICONS[r['status']]} {r['ref']:40} {r['kind']:5} {'BLOCKING' if r['blocking'] else '':8} "
              f"{', '.join(r['citations'])}{'' if r['verified'] else '  [refs ✗]'}")
    print('\nMISSING')
    for m in b['missing']:
        print(f"  {'!' if m['blocking'] else '-'} [{m['kind']}] {m['requirement']}: {m['description'][:160]}")
    print('\nROUTES')
    for row in b['routes']:
        print(f"  {row['requirement']} ({row['status']})")
        for r in row['routes']:
            print(f"    {r['status']:16} {r['name'][:90]}")
        for action in row['to_close']:
            print(f"    → {action[:150]}")
    print('\nCONFLICTS')
    for c in b['conflicts']:
        print(f"  {'resolvable' if c['resolvable'] else 'UNRESOLVED'}: {c['description'][:150]}\n    → {c['resolution'][:150]}")
    print(f'\nSaved {path}')


if __name__ == '__main__':
    main(sys.argv[1])
