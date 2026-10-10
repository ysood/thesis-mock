"""Interactive console: run a transfer scenario and watch every agent work.

    .venv/bin/streamlit run ui.py
"""

import json
import os
import time
from pathlib import Path

import streamlit as st

from app import knowledge as kb
from app import llm
from app import requirements as rq
from app.graph import run
from app.schema import AssessmentInput, load_request

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenarios"
NODES = ["supervisor", "gdpr_specialist", "local_law_IE", "hipaa_specialist", "verification"]
COLOURS = {"pending": "#eeeeee", "running": "#ffd966", "done": "#b6d7a8", "failed": "#ea9999", "skipped": "#fafafa"}
DECISIONS = {
    "proceed": ("success", "Proceed on the supplied facts"),
    "needs_review": ("warning", "Needs review"),
    "do_not_proceed": ("error", "Do not proceed as described"),
    "proceed_subject_to_conditions": ("info", "Awaiting evidence: gate requirements are met on the stated facts"),
}

st.set_page_config(page_title="Transfer compliance prototype", layout="wide")


# ------------------------------------------------------------------ requirement table cells


def evidence_used(record):
    """IDs of supplied evidence the specialist actually relied on, e.g. 'ev_dpia, ev_iso'."""
    ids = [e.get("id") or e.get("request_id") for e in record.get("supporting_evidence", [])]
    return ", ".join(i for i in ids if i) or "—"


def outstanding(record):
    """Evidence still requested from the parties; blank when nothing is outstanding."""
    return f"{len(record['evidence'])} requested" if record.get("evidence") else ""


# ------------------------------------------------------------------ pipeline diagram


def diagram(status):
    def node(name, label, shape="box"):
        state = status.get(name, "pending")
        font = "#999999" if state == "skipped" else "#000000"
        return (f'{name} [label="{label}\\n({state})", shape={shape}, style="rounded,filled", '
                f'fillcolor="{COLOURS[state]}", fontcolor="{font}"];')

    return "\n".join([
        'digraph { rankdir=TB; node [fontname=Helvetica, fontsize=11];',
        'request [label="Request and scoped evidence", shape=oval];',
        node("supervisor", "Supervisor: interpret, assign, review, decide"),
        node("gdpr_specialist", "GDPR: own findings and statuses"),
        node("hipaa_specialist", "HIPAA: own findings and statuses"),
        node("local_law_IE", "National law (when requested)"),
        node("verification", "Reference checks and report"),
        'request -> supervisor;',
        'supervisor -> gdpr_specialist [dir=both]; supervisor -> hipaa_specialist [dir=both];',
        'gdpr_specialist -> local_law_IE [dir=both]; supervisor -> verification;',
        '}',
    ])


def update_status(status, event):
    if event["kind"] == "stage":
        status[event["agent"]] = event["status"]
    if event["kind"] == "routing":
        if not event["routing"]["gdpr"]:
            status["gdpr_specialist"] = status["local_law_IE"] = "skipped"
        if not event["routing"]["hipaa"]:
            status["hipaa_specialist"] = "skipped"
    finished_gdpr = event["kind"] == "stage" and event["agent"] == "gdpr_specialist" and event["status"] != "running"
    if finished_gdpr and status["local_law_IE"] == "pending":
        status["local_law_IE"] = "skipped"  # the GDPR specialist did not delegate to Irish law
    if event["kind"] == "stage" and event["agent"] == "supervisor" and event["status"] in ("done", "failed"):
        for name in status:
            if status[name] == "pending":
                status[name] = "skipped"


# ------------------------------------------------------------------ trace events

def bullets(label, items):
    st.markdown(f"**{label}**\n" + ("\n".join(f"- {item}" for item in items) if items else "\n- none"))


def show_event(event):
    """Render one trace event. Used live during a run and when replaying a saved trace."""
    kind, agent = event["kind"], event["agent"]
    if kind == "stage":
        if event["status"] in ("running", "failed"):
            st.caption(f"▶ **{agent}** {event['status']}")
        return
    if kind == "routing":
        r = event["routing"]
        with st.expander(f"🧭 {agent}: GDPR {'✔' if r['gdpr'] else '✘'} · HIPAA {'✔' if r['hipaa'] else '✘'}", expanded=True):
            bullets("GDPR reasons", r["gdpr_reasons"])
            bullets("HIPAA reasons", r["hipaa_reasons"])
    elif kind == "llm_request":
        with st.expander(f"💬 {agent} → model: {event['purpose']}"):
            st.markdown("**System prompt**")
            st.code(event["system"], language=None, wrap_lines=True)
            st.markdown("**User prompt**")
            st.code(event["user"], language=None, wrap_lines=True)
    elif kind == "llm_response":
        if event["ok"]:
            with st.expander(f"✅ {agent} ← model: {event['purpose']}" + (f" ({event['seconds']}s)" if "seconds" in event else "")):
                st.json(event["output"])
        else:
            st.error(f"{agent}: model call failed: {event.get('error')}")
    elif kind == "llm_retry":
        st.warning(f"{agent}: invalid reply, retrying. {event['error'][:300]}")
    elif kind == "bundle":
        st.caption(f"📌 {agent} pinned sources for `{event['requirement']}`: " + ", ".join(event["ids"]))
    elif kind == "retrieval":
        with st.expander(f"🔎 {agent} searched: “{event['query']}”"):
            st.caption(event["question"])
            provisions = kb.provisions()
            st.table([{"provision": h["id"], "title": provisions[h["id"]]["title"][:80], "distance": h["distance"]}
                      for h in event["hits"]])
    elif kind == "sources":
        with st.expander(f"📚 {agent} received {len(event['ids'])} legal sources"):
            st.write(", ".join(event["ids"]))
    elif kind == "delegation":
        st.info(f"↪ {agent} delegated to **{event['to']}**:\n" + "\n".join(f"- {q}" for q in event["questions"]))
    elif kind == "supervisor_action":
        if event["accepted"]:
            st.caption("Supervisor accepted current findings and completed its review.")
        else:
            st.warning("Supervisor action rejected: " + event["reason"])
    elif kind == "gap":
        st.warning(f"⚠️ {agent}: " + event["description"])
    elif kind == "sources_added":
        st.caption(f"📎 additional sources for {event.get('to', agent)}: " + ", ".join(event["ids"]))
    elif kind == "id_normalised":
        st.caption(f"🔧 {agent}: corrected question-ID formatting " + ", ".join(f"{a} → {b}" for a, b in event["changes"]))
    elif kind == "assessment":
        st.caption(f"📝 {agent}: regime applies = **{event['regime_applies']}**, {event['count']} findings")
    elif kind == "verification":
        icon = "🧪" if not event["notes"] else "❗"
        with st.expander(f"{icon} reference check [{event['regime']}] {event['issue']} → {event['status']}"):
            st.write("Resolved citations:", event["resolved"])
            for note in event["notes"]:
                st.warning(note)
    elif kind == "tool_call":
        detail = (f" → {', '.join(event['hits'])}" if event.get("hits") else
                  f" → read {', '.join(event['read'])}" if event.get("read") else "")
        st.caption(f"{'🛠' if event['ok'] else '⚠️'} {agent} `{event['tool']}`"
                   f"({', '.join(f'{k}={v!r}' for k, v in event['args'].items())}){detail}")
        if event.get("suggested"):
            with st.expander("Knowledge-graph links suggested"):
                st.json(event["suggested"])
    elif kind == "tool_sources":
        st.caption(f"📖 {agent} read via tools: " + ", ".join(event["ids"]))
    elif kind == "request_validated":
        with st.expander(f"✔ {agent} {event['request_type']} validated"
                         + (f" ({len(event['changes'])} corrections)" if event["changes"] else "")):
            st.json(event)
    elif kind == "request_rejected":
        st.warning(f"{agent}: {event['request_type']} rejected: {event['reason'][:300]}")
    elif kind == "decision":
        level, label = DECISIONS[event['decision']]
        getattr(st, level)(f"Decision: {label}")


# ------------------------------------------------------------------ results


def show_brief(result):
    b = result.get("brief")
    if not b:
        st.write("No reviewer brief in this run (saved before v21).")
        return
    icons = {"met": "🟢", "unmet": "🔴", "undetermined": "🟡", "not_applicable": "⚪"}
    st.markdown("**What the law requires**")
    st.table([{"": icons[r["status"]], "requirement": r["title"], "status": r["status"], "class": r["class"],
               "scope": r["scope"], "blocking": "yes" if r["blocking"] else "", "cites": ", ".join(r["citations"]),
               "refs verified": "✓" if r["verified"] else "✗"} for r in b["required"]])
    st.markdown("**What is missing**")
    if b["missing"]:
        st.table([{"blocking": "yes" if m["blocking"] else "", "kind": m["kind"], "requirement": m["requirement"],
                   "what": m["description"]} for m in b["missing"]])
    else:
        st.write("Nothing missing.")
    st.markdown("**Routes forward**")
    marks = {"supported": "✅", "unresolved": "❓", "not_investigated": "…", "ruled_out": "✗"}
    for row in b["routes"] or []:
        with st.expander(f"{icons[row['status']]} {row['requirement']}" + ("  ·  blocking" if row["blocking"] else "")):
            for x in row["routes"]:
                st.markdown(f"{marks[x['status']]} **{x['name']}** ({x['status']}; {', '.join(x['citations'])})")
                st.caption(x["reasoning"])
            bullets("To close", row["to_close"])
            bullets("Stated facts that fail as described", row["failing_facts"])
    if not b["routes"]:
        st.write("No routes recorded.")
    st.markdown("**What we know (facts the findings relied on)**")
    st.table([{"fact": k["text"], "where": k["path"], "used by": ", ".join(k["used_by"])} for k in b["known"]])


def show_requirements(result):
    icons = {"met": "🟢", "unmet": "🔴", "undetermined": "🟡", "not_applicable": "⚪"}
    for cls, label in (("gate", "Gate requirements (decide the outcome)"),
                       ("advisory", "Ongoing obligations (reported, not blocking)")):
        rows = [r for r in result["requirements"] if r["class"] == cls]
        if rows:
            st.markdown(f"**{label}**")
            st.table([{"": icons[r["status"]], "requirement": r["title"], "key": r["key"], "status": r["status"],
                       "scope": r.get("obligation_scope", "transfer"),
                       "evidence used": evidence_used(r), "outstanding": outstanding(r),
                       "note": r["note"]} for r in rows])


def show_evidence(result):
    supported = [{"requirement": r["key"], "evidence": e}
                 for r in result.get("requirements", []) for e in r.get("supporting_evidence", [])]
    if supported:
        st.caption("Evidence explicitly used by specialists, retaining its supplied scope.")
        st.json(supported)
    requested = [{"request id": e["request_id"], "type": e["evidence_type"], "what": e["description"],
                  "from": e["from_party"]}
                 for r in result.get("requirements", []) if rq.is_gate(r) for e in r["evidence"]]
    if requested:
        st.table(requested)
    else:
        st.write("No evidence requested.")
    if result.get("evidence_template"):
        st.caption("Add the requested evidence to the input's evidence list with its ID, organisation scope "
                   "a factual summary and an attester when known, then reassess. The specialist decides what it establishes.")
        st.code(json.dumps(result["evidence_template"], indent=2), language="json")


def show_conditions(result):
    for c in result["conditions"] or ["None."]:
        st.write("☐", c)


def show_finding(f, provisions):
    if f["regime"] == "GDPR":
        st.write("National-law dependency:", f["national_law_review"])
        st.write(f.get("national_law_reason", ""))
        if f.get("national_dependencies"):
            st.json(f["national_dependencies"])
    st.write(f["reasoning"])
    if f.get("route_coverage"):
        st.write("Routes considered:", f["route_coverage"])
    if f.get("routes"):
        st.table([{"route and scope": r["name"], "status": r["status"],
                   "reason or gap": r["reasoning"], "law": ", ".join(r["citations"])}
                  for r in f["routes"]])
    if f.get("facts"):
        st.table([{"fact path": r["path"], "supplied text": r["quote"]} for r in f["facts"]])
    if f.get("evidence_ids"):
        st.write("Supporting evidence IDs:", f["evidence_ids"])
    if f.get("obligation_scope"):
        st.caption("Duty scope: " + f["obligation_scope"])
    if f.get("confirmations"):
        bullets("Non-decisive confirmations", f["confirmations"])
    if f["quote"]:
        st.markdown(f"Quote: *“{f['quote']}”* {'✅ verified' if not any('Quote' in n for n in f['verification_notes']) else '❌ not found'}")
    notes = f["verification_notes"]
    for label, items in (("Relies on claims", f.get("relies_on_claims")),
                         ("Missing information", f.get("missing_information")),
                         ("Required actions", f.get("required_actions")), ("Verification notes", notes)):
        if items:
            bullets(label, items)
    for pid in f["resolved_citations"]:
        st.markdown(f"**[{pid}]** {provisions[pid]['title']} — [source]({provisions[pid]['source']})")
        st.code(provisions[pid]["text"][:3000], language=None, wrap_lines=True)


def show_findings(result):
    provisions = kb.provisions()
    for f in result["findings"]:
        badge = {"satisfied_if_verified": "🟢", "not_satisfied": "🔴", "insufficient_information": "🟡",
                 "not_applicable": "⚪"}[f["status"]]
        with st.expander(f"{badge} [{f['regime']}] {f['issue']} — {f['status']}"):
            show_finding(f, provisions)


def show_relationships(result):
    for c in result["conflicts"] or []:
        st.caption(c["kind"])
        st.markdown(f"**{' vs '.join(c['regimes'])}:** {c['description']}")
        st.write("How to satisfy both:", c["how_to_satisfy_both"], "· Citations:", c["citations"])
    if not result["conflicts"]:
        st.write("No relationships reported.")


def show_gaps(result):
    for g in result["gaps"] or []:
        label = "Blocking" if g["blocking"] else "Advisory"
        (st.error if g["blocking"] else st.info)(f"{label} ({g['source']}): {g['description']}")
    if not result["gaps"]:
        st.write("No knowledge gaps.")


def show_intake_checks(result):
    bullets("Ignored instructions to the reviewer", result["ignored_instructions"])
    bullets("Contradictions", [c["description"] if isinstance(c, dict) else c for c in result["contradictions"]])
    bullets("Intake items not traceable to the request (reported, no effect on the decision)",
            [i.get("statement") or i.get("description") for i in result.get("unsourced_intake", [])])
    bullets("Clarifications flagged at intake (advisory: specialists decide whether a conclusion needs them)",
            result["missing_information"])


def show_applicability(result):
    st.json({"routing": result["routing"], "applicability": result["applicability"]})
    st.json({"coverage": result.get("coverage", [])})
    st.json({"national_questions": result.get("national_questions", [])})


def show_case_record(result):
    st.caption("Input is read-only. The supervisor owns interpretation and review; specialists own findings. "
               "Reference defects are reported separately and never rewrite legal statuses.")
    st.json(result["case_record"])


def show_result(result, expected):
    level, label = DECISIONS[result["decision"]]
    getattr(st, level)(f"**{label}**  ·  {result['seconds']}s")
    if expected.get("decision"):
        st.caption(f"Scenario author's expectation: {expected['decision']} (not ground truth)")
    for reason in result["reasons"]:
        st.write("•", reason)
    for line in result.get("outcome", []):
        st.markdown(f"**{line.split(':')[0]}:**{line.split(':', 1)[1]}")
    if result["summary"]:
        st.markdown(f"> {result['summary']}")

    tabs = st.tabs(["Brief", "Requirements", "Evidence", "Conditions", "Findings", "Relationships", "Gaps",
                    "Intake checks", "Applicability", "Case record"])
    for tab, show in zip(tabs, (show_brief, show_requirements, show_evidence, show_conditions, show_findings,
                                show_relationships, show_gaps, show_intake_checks, show_applicability,
                                show_case_record)):
        with tab:
            show(result)


# ------------------------------------------------------------------ page

with st.sidebar:
    st.header("Scenario")
    files = sorted(p.name for p in SCENARIOS.glob("*.json"))
    choice = st.selectbox("Load", files)
    scenario = json.loads((SCENARIOS / choice).read_text())
    st.caption(scenario["request"]["transfer"].get("title", ""))
    st.divider()
    st.header("Model")
    fake = st.toggle("Offline fake model (no API key)", value=not os.environ.get("MODEL"))
    st.caption(f"MODEL = `{llm.model_name() or 'not set'}`")
    key_name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(
        (llm.model_name() or "openai:").split(":")[0], "provider API key")
    st.caption(f"{key_name} set" if os.environ.get(key_name) else f"No {key_name} in environment")
    st.caption(f"Knowledge base: {len(kb.provisions())} provisions · local law: {', '.join(sorted(kb.LOCAL_LAW_COUNTRIES))}")

choices = ["luna", "haiku"] if os.environ.get("HAIKU_MODEL") else ["luna"]
llm.CHOICE = st.radio("Model", choices, horizontal=True, key="model_choice",
                      format_func=lambda c: f"{c}: {os.environ.get('HAIKU_MODEL' if c == 'haiku' else 'MODEL')}")

run_tab, kb_tab = st.tabs(["Run a transfer", "Knowledge base"])

with run_tab:
    left, right = st.columns([2, 3])
    with left:
        st.subheader("Transfer request")
        st.caption("Edit freely. Everything here is treated as an unverified claim.")
        text = st.text_area("JSON", json.dumps(scenario["request"], indent=2, ensure_ascii=False),
                            height=620, key=f"editor_{choice}", label_visibility="collapsed")
        error = None
        try:
            request = json.loads(text)
            load_request(request)  # validate while preserving the original structured evidence scope
        except Exception as exc:
            error = str(exc)
            st.error(error[:1500])
        go = st.button("Run assessment", type="primary", disabled=bool(error), width="stretch")
        with st.expander("Input schema"):
            st.json(AssessmentInput.model_json_schema(by_alias=True))

    with right:
        st.subheader("Pipeline")
        picture = st.empty()
        status = {name: "pending" for name in NODES}
        picture.graphviz_chart(diagram(status))
        log = st.container(height=520)

        if go:
            llm.FAKE_MODEL = None
            if fake:
                from tests.test_offline import fake_model
                llm.FAKE_MODEL = fake_model

            def on_event(event):
                if event["kind"] in ("stage", "routing"):  # redraw only when an agent's status changes
                    update_status(status, event)
                    picture.graphviz_chart(diagram(status))
                with log:
                    show_event(event)

            try:
                result, events = run(request, on_event=on_event)
                st.session_state["last"] = {"model": "fake" if fake else llm.model_name(),
                                            "result": result, "events": events, "expected": scenario.get("expected", {}),
                                            "status": dict(status), "request": request}
                runs = ROOT / "runs" / "ui"
                runs.mkdir(parents=True, exist_ok=True)
                (runs / f"{time.strftime('%Y%m%d-%H%M%S')}_{Path(choice).stem}.json").write_text(
                    json.dumps(st.session_state["last"], indent=1, ensure_ascii=False))
            except Exception as exc:
                st.exception(exc)
        elif "last" in st.session_state:
            picture.graphviz_chart(diagram(st.session_state["last"]["status"]))
            with log:
                for event in st.session_state["last"]["events"]:
                    show_event(event)

    if "last" in st.session_state:
        st.divider()
        st.subheader("Assessment")
        last = st.session_state["last"]
        show_result(last["result"], last["expected"])
        st.download_button("Download full run (JSON)", json.dumps(last, indent=1, ensure_ascii=False),
                           file_name="run.json", mime="application/json")

with kb_tab:
    st.subheader("Search the law corpus")
    st.caption("The same vector search and knowledge graph the agents use.")
    query = st.text_input("Search", "transfer to a third country on the basis of appropriate safeguards")
    regime = st.selectbox("Corpus", ["GDPR", "HIPAA", "IE"])
    provisions, graph = kb.provisions(), kb.graph()
    for pid, distance in kb.search(query, regime, k=8):
        with st.expander(f"[{pid}] {provisions[pid]['title']}  ·  distance {distance:.3f}"):
            st.code(provisions[pid]["text"], language=None, wrap_lines=True)
            st.caption(f"Cites: {sorted(graph['cites'][pid]) or '-'}  ·  Cited by: {sorted(graph['cited_by'][pid]) or '-'}"
                       + ("  ·  Refers to Member State law" if pid in graph["defers_to_national_law"] else ""))
            st.markdown(f"[Official source]({provisions[pid]['source']})")
