"""Console for the corpus-driven engine: pick a mock case, run it, read the reviewer brief.

    .venv/bin/streamlit run ui_mock.py --server.address 127.0.0.1 --server.port 8503
"""

import json
import os
import queue
import threading
import time
from pathlib import Path

import streamlit as st

from engine import corpus, llm, pipeline, tools

ROOT = Path(__file__).resolve().parent
CASES = ROOT / 'cases'
ICONS = {'met': '🟢', 'unmet': '🔴', 'undetermined': '🟡', 'not_applicable': '⚪'}
DECISIONS = {'proceed': ('success', 'Proceed on the supplied facts'),
             'proceed_subject_to_conditions': ('info', 'Proceed subject to conditions'),
             'needs_review': ('warning', 'Needs human review'),
             'do_not_proceed': ('error', 'Do not proceed as described')}

st.set_page_config(page_title='Mock corpus engine', layout='wide')


# ------------------------------------------------------------------ sidebar

with st.sidebar:
    st.header('Case')
    folders = sorted(p for p in CASES.iterdir() if (p / 'case.json').exists())
    folder = st.selectbox('Mock case', folders, format_func=lambda p: p.name)
    st.header('Model')
    choice = st.radio('Model', ['luna', 'haiku'], format_func=lambda c: os.environ.get(
        'MODEL' if c == 'luna' else 'HAIKU_MODEL') or c)
    llm.CHOICE = choice
    st.header('Ablations')
    tools.ENABLED = st.toggle('Traversal tools (off = whole corpus in context)', value=True)
    lexical = st.toggle('Lexical search (BM25) instead of embeddings', value=False)
    os.environ['SEARCH'] = 'lexical' if lexical else 'vector'
    tools.MAX_TOOL_CALLS = st.slider('Tool calls per agent call', 4, 40, 20)
    pipeline.MAX_REVIEWS = st.slider('Supervisor review rounds', 1, 5, 3)
    st.header('Saved runs')
    saved_runs = sorted((ROOT / 'runs' / 'mock').glob('*.json'), reverse=True) if (ROOT / 'runs' / 'mock').exists() else []
    st.selectbox('Open a saved run', [None] + saved_runs, format_func=lambda p: p.name if p else '—',
                 key='picked_run', on_change=lambda: st.session_state.update(open_run=st.session_state['picked_run']))


# ------------------------------------------------------------------ agent diagram (built from the registry)

COLOURS = {'pending': '#eeeeee', 'running': '#ffd966', 'idle': '#cfe2f3', 'done': '#b6d7a8', 'failed': '#ea9999',
           'skipped': '#fafafa'}
EDGE_STYLE = {'delegation': 'color="#38761d", penwidth=2', 'routing': 'color="#cc0000", style=dashed, penwidth=2',
              'revision': 'color="#674ea7", style=dotted, penwidth=2'}


def new_diagram_state():
    agents = ['supervisor', 'verification'] + [f'{cid}_specialist' for cid in corpus.manifests()]
    return {'status': {a: 'pending' for a in agents}, 'edges': []}


def update_diagram(state, event):
    """Returns True when the picture changed."""
    kind = event['kind']
    if kind == 'stage' and event['agent'] in state['status']:
        state['status'][event['agent']] = event['status']
    elif kind == 'plan':
        for cid in corpus.top_level():
            if cid not in event['engaged']:
                for name in [cid] + corpus.children(cid):
                    state['status'][f'{name}_specialist'] = 'skipped'
    elif kind == 'edge':
        edge = (event['source'], event['target'], event['relation'])
        if edge not in state['edges']:
            state['edges'].append(edge)
    elif kind == 'decision':
        for name, value in state['status'].items():
            if value == 'pending':
                state['status'][name] = 'skipped'
            elif value == 'idle':
                state['status'][name] = 'done'
    else:
        return False
    return True


def diagram(state):
    status = state['status']

    def node(name, label):
        value = status.get(name, 'pending')
        return (f'"{name}" [label="{label}\\n({value})", shape=box, style="rounded,filled", '
                f'fillcolor="{COLOURS[value]}", fontcolor="{"#999999" if value == "skipped" else "#000000"}"];')

    lines = ['digraph { rankdir=TB; node [fontname=Helvetica, fontsize=11]; edge [fontsize=9];',
             'case [label="Case: facts and evidence", shape=oval];',
             node('supervisor', 'Supervisor: plan, route, reconcile\\n(sees every corpus)'),
             node('verification', 'Reference checks, decision, brief')]
    for cid, m in corpus.manifests().items():
        lines.append(node(f'{cid}_specialist', f"{m['name']}\\n{m['level']} specialist"))
    lines += ['case -> supervisor;', 'supervisor -> verification;']
    lines += [f'supervisor -> "{cid}_specialist" [dir=both];' for cid in corpus.top_level()]
    lines += [f'"{cid}_specialist" -> "{child}_specialist" [dir=both, style=dashed, color="#999999"];'
              for cid in corpus.manifests() for child in corpus.children(cid)]
    lines += [f'"{a}_specialist" -> "{b}_specialist" [{EDGE_STYLE[r]}, label="{r}", constraint=false];'
              for a, b, r in state['edges']]
    return '\n'.join(lines + ['}'])


# ------------------------------------------------------------------ result views

def bullets(label, items):
    if items:
        st.markdown(f'**{label}**\n' + '\n'.join(f'- {i}' for i in items))


def show_brief(result):
    b = result['brief']
    st.markdown('**What the law requires**')
    st.dataframe([{'': ICONS[r['status']], 'requirement': r['ref'], 'title': r['title'], 'kind': r['kind'],
                   'status': r['status'], 'blocking': '●' if r['blocking'] else '',
                   'cites': ', '.join(r['citations']), 'refs': '✓' if r['verified'] else '✗', 'source': r['source']}
                  for r in b['required']], width='stretch', hide_index=True)
    st.markdown('**What is missing**')
    if b['missing']:
        st.dataframe([{'blocking': '●' if m['blocking'] else '', 'kind': m['kind'], 'requirement': m['requirement'],
                       'what': m['description']} for m in b['missing']], width='stretch', hide_index=True)
    else:
        st.write('Nothing missing.')
    st.markdown('**Routes forward**')
    marks = {'supported': '✅', 'unresolved': '❓', 'not_investigated': '…', 'ruled_out': '✗'}
    for row in b['routes']:
        with st.expander(f"{ICONS[row['status']]} {row['requirement']}" + ('  ·  blocking' if row['blocking'] else '')):
            for r in row['routes']:
                st.markdown(f"{marks[r['status']]} **{r['name']}** · {r['status']} · {', '.join(r['resolved_citations'])}")
                st.caption(r['reasoning'])
                if r['quote']:
                    st.markdown(f"> {r['quote']}")
            bullets('To close', row['to_close'])
    st.markdown('**Conflicts between jurisdictions**')
    for c in b['conflicts']:
        (st.info if c['resolvable'] else st.error)(
            f"{'Resolvable' if c['resolvable'] else 'Unresolved'}: {c['description']}\n\n→ {c['resolution']}  \n"
            f"({', '.join(c['requirement_refs'])})")
    if not b['conflicts']:
        st.write('None recorded.')
    with st.expander(f"What we know: {len(b['known'])} facts the findings relied on"):
        st.dataframe([{'fact': k['text'], 'where': k['path'], 'used by': ', '.join(k['used_by'])} for k in b['known']],
                     width='stretch', hide_index=True)


def show_findings(result):
    for f in result['findings']:
        with st.expander(f"{ICONS[f['status']]} {f['ref']} · {f['title']} · {f['kind']}"
                         + ('' if f['verified'] else '  ·  ✗ refs')):
            st.write(f['reasoning'])
            if f['quote']:
                st.markdown(f"> {f['quote']}  \n— {', '.join(f['resolved_citations'])}")
            for label in ('missing_facts', 'missing_evidence', 'required_actions', 'confirmations', 'issues'):
                bullets(label.replace('_', ' ').capitalize(), f[label])
            if f['open_dependency']:
                st.markdown(f"**Open dependency:** {f['open_dependency']}")
            if f['facts']:
                st.caption('Facts: ' + ' · '.join(x['quote'] for x in f['facts']))
            st.caption(f"Source: {f['source']}")


def show_coordination(result):
    st.markdown('**Plan**')
    if result['plan']:
        st.write(result['plan']['understanding'])
        st.dataframe([{'corpus': e['corpus'], 'engaged': e['engaged'], 'reason': e['reason'], 'focus': e['focus']}
                      for e in result['plan']['engagements']], width='stretch', hide_index=True)
    st.markdown('**Specialists**')
    for cid, a in result['specialists'].items():
        with st.expander(f"{cid}: applies={a['applies']}"):
            st.write(a['applicability_reasoning'])
            st.caption('Coverage: ' + a['coverage_note'])
    st.markdown('**Delegations and routed questions**')
    st.json(result['delegations'], expanded=False)
    st.dataframe([{'ref': q['ref'], 'from': q['from'], 'to': q.get('routed_to', ''), 'status': q['status'],
                   'question': q['question'], 'answer': q['answer']} for q in result['questions']],
                 width='stretch', hide_index=True)
    st.markdown('**Supervisor reviews**')
    for i, r in enumerate(result['reviews'], 1):
        with st.expander(f"Review {i}: {r['action'] if r else 'failed'}"):
            st.json(r)
    st.markdown('**Law read by each agent**')
    st.json(result['read'], expanded=False)


def show_key(folder, result):
    path = folder / 'key.json'
    if not path.exists():
        st.write('No answer key for this case.')
        return
    key = json.loads(path.read_text())
    st.caption(key.get('status', ''))
    st.markdown(f"Expected decision: **{key['decision']}** · this run: **{result['decision']}**")
    st.dataframe([{'expected': k['id'], 'expect': k['expect'], 'provisions': ', '.join(k['provisions']),
                   'why': k.get('why', '')} for k in key['must_find']], width='stretch', hide_index=True)
    bullets('Must not', key.get('must_not', []))
    st.json({'conflicts': key.get('conflicts'), 'cross_jurisdiction': key.get('cross_jurisdiction')}, expanded=False)


def show_result(result, folder):
    level, label = DECISIONS[result['decision']]
    getattr(st, level)(f"**{label}** · {result['seconds']}s")
    for reason in result['reasons']:
        st.write('•', reason)
    tabs = st.tabs(['Brief', 'Findings', 'Coordination', 'Answer key', 'Case'])
    with tabs[0]:
        show_brief(result)
    with tabs[1]:
        show_findings(result)
    with tabs[2]:
        show_coordination(result)
    with tabs[3]:
        show_key(folder, result)
    with tabs[4]:
        st.json(result['case'], expanded=False)


# ------------------------------------------------------------------ live run

def describe(event):
    kind, agent = event['kind'], event['agent']
    if kind == 'stage':
        return f"**{agent}** {event['status']}"
    if kind == 'tool_call':
        arg = next(iter(event['args'].values()))
        return f"  · `{agent}` {event['tool']}({arg})" + ('' if event.get('ok') else ' ✗')
    if kind == 'llm_request':
        return f"→ `{agent}` {event['purpose']}"
    if kind == 'llm_response':
        return (f"← `{agent}` {event['purpose']} ({event.get('seconds', '?')}s, {event.get('tool_calls', 0)} tool calls)"
                if event.get('ok') else f"⚠ `{agent}` failed: {str(event.get('error'))[:200]}")
    if kind == 'llm_retry':
        return f"↻ `{agent}` retry: {event['error'][:150]}"
    if kind == 'decision':
        return f"**Decision:** {event['decision']}"
    return None


run_tab, law_tab = st.tabs(['Run a case', 'Corpora'])

with run_tab:
    case_text = st.text_area('case.json (editable; the answer key is never sent to the model)',
                             (folder / 'case.json').read_text(), height=260, key=f'case-{folder.name}')
    if st.button('Run assessment', type='primary'):
        try:
            case = json.loads(case_text)
        except json.JSONDecodeError as exc:
            st.error(f'Invalid JSON: {exc}')
            st.stop()
        events, outbox = [], queue.Queue()

        def work():
            try:
                outbox.put(('done', pipeline.run(case, on_event=lambda e: outbox.put(('event', e)))))
            except Exception as exc:  # shown in the page, not swallowed
                outbox.put(('error', exc))

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        picture_col, log_col = st.columns([1, 1])
        picture = picture_col.empty()
        drawing = new_diagram_state()
        picture.graphviz_chart(diagram(drawing))
        status = log_col.status('Running…', expanded=True)
        outcome = None
        while outcome is None:
            try:
                kind, payload = outbox.get(timeout=0.3)
            except queue.Empty:
                continue
            if kind == 'event':
                if update_diagram(drawing, payload):
                    picture.graphviz_chart(diagram(drawing))
                line = describe(payload)
                if line:
                    status.markdown(line)
            else:
                outcome = (kind, payload)
        if outcome[0] == 'error':
            status.update(label='Failed', state='error')
            st.exception(outcome[1])
        else:
            result, events = outcome[1]
            path = pipeline.save(result, events, folder.name)
            status.update(label=f"Done: {result['decision']} · saved {path.name}", state='complete', expanded=False)
            st.session_state.update(result=result, folder=folder, events=events, drawing=drawing,
                                    saved=json.dumps({'model': llm.model_name(), 'tools': tools.ENABLED,
                                                      'result': result, 'events': events},
                                                     indent=1, ensure_ascii=False, default=str),
                                    saved_name=path.name)
            st.rerun()
    if st.session_state.get('open_run'):
        path = st.session_state.pop('open_run')
        data = json.loads(path.read_text())
        drawing = new_diagram_state()
        for event in data['events']:
            update_diagram(drawing, event)
        name = path.name.split('_', 1)[1].rsplit('.', 1)[0]
        st.session_state.update(result=data['result'], events=data['events'], drawing=drawing,
                                folder=CASES / name if (CASES / name).exists() else folder,
                                saved=path.read_text(), saved_name=path.name)
    if 'result' in st.session_state:
        top_left, top_right = st.columns([1, 1])
        if 'drawing' in st.session_state:
            top_left.graphviz_chart(diagram(st.session_state['drawing']))
        if 'saved' in st.session_state:
            top_right.download_button('Download full run (JSON)', st.session_state['saved'],
                                      file_name=st.session_state['saved_name'], mime='application/json')
            top_right.caption(f"{len(st.session_state.get('events', []))} trace events · runs/mock/{st.session_state['saved_name']}")
        show_result(st.session_state['result'], st.session_state['folder'])

with law_tab:
    for cid, m in corpus.manifests().items():
        st.subheader(f"{m['name']} · {m['level']}")
        st.caption(f"corpus `{cid}` · territory {', '.join(m['territory'])} · parent {m.get('parent') or '—'} · "
                   f"children {', '.join(m.get('children', [])) or '—'}")
        for pid, p in corpus.provisions().items():
            if p['corpus'] == cid:
                with st.expander(f"{pid} · {p['title']}"):
                    st.text(p['text'])
                    links = corpus.citations()[pid]
                    if links:
                        st.caption('Cites: ' + ', '.join(links))
                    cited = corpus.cited_by(pid)
                    if cited:
                        st.caption('Cited by: ' + ', '.join(cited))
