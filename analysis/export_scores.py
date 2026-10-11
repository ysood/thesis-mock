"""Export an analysis case folder's scores as tidy CSVs for R / Excel.

    .venv/bin/python analysis/export_scores.py analysis/case_05

Writes, in the case folder:
  scores_checks.csv  one row per key version x configuration x run x check
  scores_runs.csv    one row per key version x configuration x run (totals, decision, cost, supervisor passes)

Key versions: key*.json containing actual decision/requirement keys (review reports are skipped).
score_reviews.json supplies hash-bound, complete reviews shared with the UI and CLI.
Legacy hand_checks.csv applies only where no complete bound review exists.
passed_auto is always the unedited matcher result; passed_reviewed is blank for unreviewed runs.
passed_hand is retained as a compatibility column. Never calls a model.
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import score  # noqa: E402

CONFIGS = {'single_no_graph': ('single', 'runtime'), 'single_graph': ('single', 'generated'),
           'multi_no_graph': ('multi', 'runtime'), 'multi_graph': ('multi', 'generated')}


def version(path):
    return 'reviewed' if path.name == 'key.json' else path.stem.replace('key_', '')


def rows_for(card):
    """(section, check, passed, got, expected) for every automated check."""
    out = [('decision', 'decision', card['decision']['ok'], card['decision']['got'], str(card['decision']['expect']))]
    for r in card['requirements']:
        out.append(('requirement', r['id'], r['ok'], r['status'] or 'not_found', '/'.join(r['expect'])))
    for r in card['routes']:
        out.append(('route', r['id'], r['ok'], ','.join(r['statuses']) or 'not_found', '/'.join(r['expect'])))
    for r in card['conflicts']:
        out.append(('conflict', r['id'], r['ok'], str(r['resolvable']), ''))
    for r in card['questions']:
        out.append(('question', r['id'], r['ok'], f"asked {r['times_asked']}", ''))
    for r in card['must_not']:
        out.append(('trap', r['id'], not r['violated'], '; '.join(r['hits']) or 'not violated', 'not violated'))
    return out


def supervisor(result):
    reviews = [r for r in (result.get('reviews') or []) if r]
    if result.get('reviews') and 'single_agent' in str(result['reviews'][0].get('action', '')):
        return 0, 0, 0
    return (len(reviews), sum(len(r.get('corrections') or []) for r in reviews),
            sum(len(r.get('routings') or []) for r in reviews))


def main(folder):
    folder = Path(folder)
    hand = {}
    if (folder / 'hand_checks.csv').exists():
        for h in csv.DictReader((folder / 'hand_checks.csv').open()):
            hand[(h['key_version'], h['config'], h['run'], h['check'])] = (h['passed'].strip().lower() == 'true', h['note'])
    checks_out, runs_out = [], []
    for key_path in sorted(folder.glob('key*.json')):
        kv, key = version(key_path), json.loads(key_path.read_text())
        if 'decision' not in key or 'requirements' not in key:
            continue
        for config, (arch, graph) in CONFIGS.items():
            for path in sorted((folder / config).glob('run*.json'), key=lambda p: int(p.stem[3:])):
                data = json.loads(path.read_text())
                if (data.get('mode'), data.get('graph', 'runtime')) != (arch, graph):
                    raise SystemExit(f'{path}: recorded {data.get("mode")}/{data.get("graph")} does not match folder')
                result, card = data['result'], score.score_file(data['result'], key_path)
                cost = score.cost(data.get('events', []))
                reviewed = card.get('reviewed')
                reviewed_rows = score.check_rows(reviewed) if reviewed else {}
                reviewed_outcomes = score.outcomes(reviewed) if reviewed else {}
                auto = hand_total = 0
                rows = rows_for(card)
                for section, check, passed, got, expected in rows:
                    override = hand.get((kv, config, path.stem, check))
                    label = 'decision' if section == 'decision' else f'{section}:{check}'
                    correction = reviewed_rows.get(label, {}).get('review', {})
                    passed_hand = reviewed_outcomes[label] if reviewed else override[0] if override else passed
                    auto += passed
                    hand_total += passed_hand
                    checks_out.append({'key_version': kv, 'config': config, 'architecture': arch, 'graph': graph,
                                       'run': path.stem, 'section': section, 'check': check,
                                       'passed_auto': int(passed), 'passed_hand': int(passed_hand),
                                       'passed_reviewed': int(passed_hand) if reviewed else '',
                                       'hand_note': correction.get('reason', '') if reviewed else override[1] if override else '',
                                       'review_status': card['review_status'],
                                       'review_evidence': json.dumps(correction.get('evidence', []), ensure_ascii=False),
                                       'got': got, 'expected': expected})
                passes, corrections, routings = supervisor(result)
                runs_out.append({'key_version': kv, 'config': config, 'architecture': arch, 'graph': graph,
                                 'run': path.stem, 'decision': result['decision'],
                                 'decision_ok': int(card['decision']['ok']), 'checks': len(rows),
                                 'passed_auto': auto, 'passed_hand': hand_total,
                                 'passed_reviewed': hand_total if reviewed else '',
                                 'review_status': card['review_status'],
                                 'checks_reviewed': card.get('review_metadata', {}).get('checks_reviewed', 0),
                                 'review_corrections': len(card.get('review_metadata', {}).get('changed_checks', [])),
                                 'seconds': result.get('seconds'), 'model_calls': cost['model_calls'],
                                 'tool_calls': cost['tool_calls'], 'output_tokens': cost['output_tokens'],
                                 'supervisor_passes': passes, 'corrections': corrections, 'routings': routings,
                                 'source_run': data.get('model', ''),
                                 'source_path': str(path.relative_to(folder)),
                                 'result_sha256': score.fingerprint(score.modernise(result))})
    if not runs_out:
        raise SystemExit(f'No runs yet in {folder} (expected <config>/run1.json ...)')
    for name, rows in (('scores_checks.csv', checks_out), ('scores_runs.csv', runs_out)):
        with (folder / name).open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f'{len(checks_out)} check rows, {len(runs_out)} run rows -> {folder}/scores_checks.csv, scores_runs.csv')


if __name__ == '__main__':
    main(sys.argv[1])
