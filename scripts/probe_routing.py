"""Run only the supervisor's initial call and print how it routes each regime.

    .venv/bin/python scripts/probe_routing.py scenarios/28_ie_gp_practice_to_us_cloud_ehr.json
    .venv/bin/python scripts/probe_routing.py tests/fixtures/hipaa_routing_probes.json --repeat 3
    .venv/bin/python scripts/probe_routing.py tests/fixtures/hipaa_routing_probes.json --only plain: --repeat 3
    .venv/bin/python scripts/probe_routing.py tests/fixtures/hipaa_routing_probes.json --fake

One model call per case instead of a full assessment. A probe file lists cases, each a scenario
plus optional text appended to fields of its request (JSON pointers), and the expected routing.
Results go to runs/probe-<timestamp>/.
"""

import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import llm  # noqa: E402
from app.schema import load_request  # noqa: E402
from app.supervisor import plan_case  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def append_at(document, pointer, text):
    parts = pointer.strip('/').split('/')
    target = document
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = int(parts[-1]) if isinstance(target, list) else parts[-1]
    target[last] = (target[last] + ' ' + text).strip()


def cases(path):
    data = json.loads(path.read_text())
    if 'cases' not in data:  # a plain scenario file
        return [{'name': path.stem, 'request': data.get('request', data), 'expect': {}}]
    out = []
    for case in data['cases']:
        request = deepcopy(json.loads((ROOT / case['scenario']).read_text())['request'])
        for pointer, text in case.get('append', {}).items():
            append_at(request, pointer, text)
        out.append({'name': case['name'], 'request': request, 'expect': case.get('expect', {})})
    return out


def probe(request):
    case, setup, _ = plan_case({'request': load_request(request)})
    if setup is None:
        return {'error': 'Supervisor planning call failed.'}
    routed = {r: getattr(setup, f'{r.lower()}_plan') is not None for r in ('GDPR', 'HIPAA')}
    return {'routed': routed,
            'plans': {r: getattr(setup, f'{r.lower()}_plan').model_dump() for r in routed if routed[r]},
            'exclusions': [e.model_dump() for e in setup.exclusions],
            'setup_issues': case['checks']['setup_issues'],
            'routing_warnings': case['checks']['routing_warnings']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='+', help='scenario or probe files')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--only', default='', help='run only cases whose name contains this text')
    parser.add_argument('--fake', action='store_true', help='use the scripted offline model')
    args = parser.parse_args()
    if args.fake:
        from tests.test_offline import fake_model
        llm.FAKE_MODEL = fake_model
    out_dir = ROOT / 'runs' / time.strftime('probe-%Y%m%d-%H%M%S')
    out_dir.mkdir(parents=True)
    rows = []
    for path in map(Path, args.paths):
        for case in [c for c in cases(path) if args.only in c['name']]:
            for n in range(1, args.repeat + 1):
                started = time.time()
                result = probe(case['request'])
                result.update(name=case['name'], run=n, expect=case['expect'], seconds=round(time.time() - started, 1))
                rows.append(result)
                routed = result.get('routed', {})
                verdict = ' '.join(f"{r}={'in' if routed.get(r) else 'out'}" for r in ('GDPR', 'HIPAA'))
                misses = [r for r, want in case['expect'].items() if routed.get(r) != (want == 'in')]
                mark = '' if not case['expect'] else ('match' if not misses else 'DIFFERENT: ' + ', '.join(misses))
                print(f"{case['name']} #{n}: {result.get('error') or verdict}  {mark}  {result['seconds']}s")
                for w in result.get('routing_warnings', []) + result.get('setup_issues', []):
                    print('    !', w)
    (out_dir / 'probe.json').write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    scored = [r for r in rows if r['expect'] and 'routed' in r]
    if scored:
        hits = sum(all(r['routed'].get(k) == (v == 'in') for k, v in r['expect'].items()) for r in scored)
        print(f'\nRouting matches expectation: {hits}/{len(scored)}')
    print(f'Saved to {out_dir.relative_to(ROOT)}/')


if __name__ == '__main__':
    main()
