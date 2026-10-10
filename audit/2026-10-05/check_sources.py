"""Offline, reproducible provenance audit against retained publisher snapshots.

Quote matching is a mechanical check, never a semantic or currency certificate.
The companion review and limitations explain what each class of link means.
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from app import kg, knowledge as kb


def norm(text):
    # Publisher HTML sometimes splits punctuation and words over inline tags.
    return re.sub(r'[^\w]', '', kb.normalise_text(text))


def load_sources():
    result = {}
    for name in ('gdpr_articles', 'gdpr_recitals', 'ie_dpa_revised', 'ie_314_2018', 'ie_188_2019', 'ie_18_2021'):
        result[name] = BeautifulSoup((HERE / 'sources' / (name + '.html')).read_bytes(), 'html.parser')
    for part in (160, 164):
        tree = ET.parse(HERE / 'sources' / f'hipaa_{part}_annual.xml')
        result[f'hipaa_{part}'] = {re.search(r'\d+\.\d+', section.findtext('SECTNO')).group(): ''.join(section.itertext())
                                 for section in tree.findall('.//SECTION') if section.findtext('SECTNO')}
    return result


SOURCES = load_sources()


def official(pid):
    if pid.startswith('GDPR'):
        number = re.search(r'\d+', pid).group()
        recital = 'Recital' in pid
        key = 'gdpr_recitals' if recital else 'gdpr_articles'
        el = SOURCES[key].find(id=('rct_' if recital else 'art_') + number)
        anchor = ('rct_' if recital else 'art_') + number
        return key, el.get_text(' ', strip=True), f'https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng#{anchor}'
    if pid.startswith('45 CFR'):
        section = re.search(r'(160|164)\.\d+', pid).group()
        part = section.split('.')[0]
        return f'hipaa_{part}_annual', SOURCES[f'hipaa_{part}'][section], f'https://www.govinfo.gov/content/pkg/CFR-2025-title45-vol2/xml/CFR-2025-title45-vol2-part{part}.xml'
    if pid.startswith('IE DPA'):
        number = pid.rsplit(' ', 1)[-1]
        el = SOURCES['ie_dpa_revised'].find(id='SEC' + number)
        return 'ie_dpa_revised', el.get_text(' ', strip=True), f'https://revisedacts.lawreform.ie/eli/2018/act/7/revised/en/html#SEC{number}'
    instrument, year = re.search(r'(\d+)/(\d{4})', pid).groups()
    key = f'ie_{instrument}_{year}'
    return key, SOURCES[key].get_text(' ', strip=True), f'https://www.irishstatutebook.ie/eli/{year}/si/{instrument}/made/en/print'


def main():
    g = kg.graph()
    review = json.loads((HERE / 'review.json').read_text())
    manifest = json.loads((HERE / 'sources.json').read_text())
    snapshot_errors = []
    for name, record in manifest.items():
        if record['status'] != 'retrieved':
            continue
        suffix = '.xml' if name.endswith('_annual') else '.html'
        path = HERE / 'sources' / (name + suffix)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            snapshot_errors.append(name)
    # Attach the authored review of each requirement to all its reachable legal edges.
    owners = {}
    for record in review['requirements']:
        pending, seen = [record['id']], set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            owners.setdefault(current, []).append(record['id'])
            pending.extend(e['target'] for e in g['edges'] if e['source'] == current
                           and e['type'] not in ('corresponds_to', 'claims', 'denies'))
    checks, provisions = [], {}
    for edge in g['edges']:
        quote = edge.get('provenance')
        if not quote:
            continue
        key, text, url = official(quote['provision'])
        checks.append({'source': edge['source'], 'relation': edge['type'], 'target': edge['target'],
                       'provision': quote['provision'], 'pinpoint': quote['pinpoint'], 'quote': quote['text'],
                       'publisher_url': url, 'snapshot': key,
                       'publisher_quote_match': norm(quote['text']) in norm(text)})
        provisions[quote['provision']] = {'snapshot': key, 'publisher_url': url,
            'stored_provision_sha256': hashlib.sha256(kb.provisions()[quote['provision']]['text'].encode()).hexdigest()}
    # Opening and assessment-unit quotes are metadata, not always separate edges.
    for node in g['nodes'].values():
        for role, quote in [('opening', node.get('opening')), ('unit', (node.get('unit') or {}).get('basis'))]:
            if quote:
                key, text, url = official(quote['provision'])
                checks.append({'source':node['id'], 'relation':role, 'target':quote['provision'],
                    **quote, 'publisher_url':url, 'snapshot':key,
                    'publisher_quote_match':norm(quote['text']) in norm(text)})
    rows = []
    descriptions = {
        'defined_in':'The source identifies or explains this concept; it does not transfer another regime\'s definition.',
        'grounded_in':'The provision supplies source text for the node. The complete node statement and statutory qualifications must be read together.',
        'uses_concept':'Definition-retrieval link. This is an authored dependency, not a claim that a statute creates an ontology edge.',
        'has_route':'An alternative within the stated requirement. The route core, scopes, conditions and exceptions all apply; open lists are not exhaustive.',
        'requires':'The target is a necessary conjunct, subject to the target\'s own scope. A shared article alone is not proof of this logical relationship.',
        'scoped_by':'The source arises only in the target factual scope; a route outside its scope is unavailable.',
        'gated_by':'Assessment dependency on regime applicability, an authored model of the scope provisions rather than a quoted statutory edge.',
        'excepted_by':'The quoted statutory exception defeats only this source predicate when all of the exception\'s conditions hold.',
        'implemented_by':'A selected national provision can supply this opening. Enabling bases are not exhaustive; additional safeguards have distinct scope semantics.',
        'corresponds_to':'Non-inferential analyst mapping. relatedMatch is not equivalence or a statutory assertion.',
        'claims':'Intake-policy mapping. A partial value is a retrieval/judgment hint and does not prove the complete legal test.',
        'denies':'Intake-policy mapping. Only the expressly classified predicate may be negated; geography and purpose are not general exclusions.',
    }
    for index, edge in enumerate(g['edges']):
        refs = []
        if edge.get('provenance'):
            refs.append(edge['provenance'])
        for node_id in [edge['source'], edge['target']]:
            refs += [e['provenance'] for kind in ['grounded_in','defined_in'] for e in kg.edges_from(node_id,kind) if e['provenance']]
        refs = list({json.dumps(q,sort_keys=True):q for q in refs}.values())
        category = 'statutory_quote' if edge.get('provenance') else (
            'intake_policy' if edge['type'] in ['claims','denies'] else
            'analyst_mapping' if edge['type']=='corresponds_to' else 'authored_legal_dependency')
        rows.append({'index':index, **edge, 'category':category, 'review_rule':descriptions[edge['type']],
                     'supporting_sources':[dict(q, publisher_url=official(q['provision'])[2]) for q in refs],
                     'requirement_reviews':sorted(set(owners.get(edge['source'], []) + owners.get(edge['target'], []))),
                     'semantic_status':'qualified_model_interpretation' if category == 'authored_legal_dependency'
                                       else 'source_or_policy_inventory',
                     'qualification':'Quote matches validate provenance, not entailment. Read review.json for substantive findings and unresolved coverage.'})
    report = {'graph_sha256':hashlib.sha256(kg.PATH.read_bytes()).hexdigest(),
        'graph_validation_issues':kg.validate(), 'snapshot_hash_errors':snapshot_errors,
        'nodes':len(g['nodes']), 'edges':len(g['edges']), 'quote_checks':len(checks),
        'publisher_matches':sum(c['publisher_quote_match'] for c in checks),
        'publisher_mismatches':[c for c in checks if not c['publisher_quote_match']],
        'provisions':provisions, 'edge_categories':dict(Counter(r['category'] for r in rows)),
        'limits':['Mechanical matching ignores spacing and punctuation but preserves word/number order.',
                  'HIPAA snapshot is the official 2025 annual CFR; current eCFR was inspected separately. Neither printed version incorporates a court order automatically.',
                  'Irish Revised Act advertises changes known in force through 2026-09-17; later changes are not certified.',
                  'Irish instrument quote matching is at instrument level; pinpoints/amendments are reviewed separately.',
                  'Matching quotes and complete edge inventory do not certify semantic correctness or exhaustive legal coverage.']}
    for filename, data in [('provenance_checks.json',checks), ('edge_ledger.json',rows), ('verification.json',report)]:
        (HERE / filename).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['provisions','limits']},indent=2))
    if report['graph_validation_issues'] or snapshot_errors or report['publisher_mismatches']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
