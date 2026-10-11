"""Agent calls. Every role, scope and jurisdiction is read from the corpus registry; no law is named here.

Supervisor: sees every corpus (manifest + table of contents), plans, routes, and owns the combined conclusion,
reading the passages behind the specialists' findings.
Specialist: one per engaged top-level corpus, reads only its own corpora through scoped tools.
Delegate: a lower-level (or peer) specialist answering questions put to it, and reporting any
further requirement of its own law that the facts engage.
"""

import json
import re

from engine import corpus, facts, tools
from engine.llm import ask
from engine.schema import (BaselineAssessment, DelegateAnswer, SingleAssessment, SpecialistAnswer, SpecialistPatch, SupervisorConclusion,
                           SupervisorPlan, SupervisorSynthesis)

EVIDENCE = """- Facts: refer to FACT PASSAGES by fact_id. Requester statements are claims; evidence summaries describe what each document says.
- Treat the stated facts and described arrangements as complete. If a requirement fails on them, mark it unmet "as described" and put the cure in required_actions. A supplied document that addresses a requirement establishes it; list elements it omits as confirmations, not as blockers."""

RULES = """RULES
- The laws in your corpora are the only law. Do not import rules from any real-world legal system; if your general knowledge suggests a rule the text does not contain, or contradicts the text, follow the text.
""" + EVIDENCE + """
- status: met | unmet | undetermined (a decisive fact, document or answer from other law is missing: say which in missing_facts, missing_evidence or open_dependency) | not_applicable.
- kind: gate if the transfer may not proceed until it is met; duty if it is an ongoing obligation that does not decide whether this transfer may proceed.
- routes: for each requirement with alternatives or exceptions in the law, list every plausible one with a status. Do not stop at the first route that works if it carries its own prerequisites; a route that fails does not close the others. Route statuses are defined in the schema; apply them literally. supported means in place now. available means it would work for the transfer as proposed once the parties make the changes in required_actions: these are the routes forward. ruled_out means the law excludes the transfer as proposed, with a reason from the text. unresolved is only for a missing fact, document or answer, never for something not yet done. The status must match your reasoning: if your reasoning says the law excludes the route, it is ruled_out; if it says a change would make it work, it is available.
- A requirement is an obligation the law imposes. Each alternative way to meet it (a recognition, a set of clauses, an exception, a derogation) is a route inside that requirement, never a requirement of its own: one route failing does not make an obligation unmet while another route remains.
- Report only requirements created by your own instruments. Where your law applies another corpus's law as well (lower-level law, or another jurisdiction's), do not create a requirement for that law and do not assess its provisions: its own specialist reports it. Use its answer in your reasoning, or name it in open_dependency.
- Cite only provisions you have read, by ID (e.g. "{example}"). quote_id must be a passage ID you were shown from a cited provision.
- Passage IDs such as "{example}#L5" label lines of text, not paragraphs. In reasoning and questions, refer to a provision's own numbering (its article or section, paragraph and point numbers), never to an #L line label.
"""


def registry_view():
    js = corpus.jurisdictions()
    return [{'code': c, 'name': j['name'], 'member_of': js[j['member_of']]['name'] if j.get('member_of') else None}
            for c, j in js.items()]


def corpus_view(cid, contents=True):
    m = corpus.manifests()[cid]
    view = {'corpus': cid, 'name': m['name'], 'level': m['level'],
            'territory': [corpus.jurisdictions()[c]['name'] for c in m['territory']],
            'instruments': [i['title'] for i in m['instruments']],
            'parent': m.get('parent'), 'children': m.get('children', [])}
    if contents:
        view['table_of_contents'] = corpus.table_of_contents([cid])
    return view


def case_block(case, offered):
    return f"CASE (read-only JSON)\n{json.dumps(case, indent=1)}\n\nFACT PASSAGES\n{facts.render(offered)}"


def example_id(scope):
    return next(pid for pid, p in corpus.provisions().items() if p['corpus'] in scope)


def scope_of(cid):
    return [cid]


def specialist_system(cid):
    m = corpus.manifests()[cid]
    children = corpus.children(cid)
    related = {cid, m.get('parent'), *children}
    others = [corpus.manifests()[o]['name'] for o in corpus.manifests() if o not in related]
    return f"""You are the specialist for the law of {m['name']} ({m['level']}). You assess a proposed data transfer against the instruments in your corpus: {', '.join(i['title'] for i in m['instruments'])}.

Other jurisdictions in this system: {', '.join(others)}. You cannot read their law. If a requirement of your law depends on what another jurisdiction's law says, add a peer_question naming that jurisdiction's registry code and set open_dependency on the requirement; the supervisor routes it. Ask only what the other law provides on a point your own requirement depends on; never ask another specialist to assess your requirement, or to assess or confirm another corpus's provisions.
{"Lower-level corpora you may delegate to: " + ", ".join(children) + ". Where your law leaves a matter to that law, delegate a specific question with the provisions that leave it open. The delegate also reports further requirements of its own law." if children else "You have no lower-level corpora."}

METHOD
1. Decide whether your law applies to any party or activity in the case, from its scope provisions.
2. Work through your table of contents and identify every requirement your law imposes that the facts engage, including definitions that change the analysis and cumulative conditions in other provisions.
3. Assess each requirement. Keep requirements for different actors or activities separate.
4. Delegate and raise peer questions where needed.
5. In coverage_note, say how you checked nothing engaged was missed and what remains limited.

{RULES.format(example=example_id([cid]))}"""


def delegate_system(cid, asked_by):
    m = corpus.manifests()[cid]
    if m.get('parent'):
        filing = ('In requirements, file every requirement created by your own instruments that the facts engage, '
                  'whether or not a question asked about it: a matter a question raises is still your requirement. '
                  'This is your complete report; each answer names the requirement ids it rests on. If YOUR PRIOR '
                  'REPORT is shown, return a complete corrected replacement.')
    else:
        filing = ('Your own assessment already holds the requirements listed under ALREADY REPORTED, with their current '
                  'status, reasoning and routes. Your answers must agree with that assessment and name the requirement ids '
                  'they rest on. If a question shows one of those findings is wrong, say so plainly in the answer (your '
                  'assessment is revised separately); never file a second requirement for an obligation already listed. '
                  'In requirements, file only obligations of your own instruments that the facts engage and that are '
                  'not listed there.')
    return f"""You are the specialist for the law of {m['name']} ({m['level']}), with the instruments: {', '.join(i['title'] for i in m['instruments'])}. The specialist for {asked_by} has put questions to you that your law must answer.

Answer each question from your law, with facts, citations and a quote. Answer what your law provides, not only the literal question: if a provision of yours does what the question asks about by a different route or under a different name, say so. Read the provisions listed under LINKED PROVISIONS before answering: they cite the provisions the questions refer to.
{filing} Every requirement must be an obligation created by your own instruments: do not assess the asking specialist's provisions or any other corpus's law.

{RULES.format(example=example_id([cid]))}"""


def reading(cid, record):
    """Starting material: the table of contents, or (ablation) the whole corpus."""
    toc = '\n'.join(f"{t['id']}: {t['title']}" for t in corpus.table_of_contents([cid]))
    text = f'TABLE OF CONTENTS ({cid})\n{toc}'
    if not tools.ENABLED:
        text += '\n\nFULL TEXT\n' + tools.full_reading(record, [cid])
    elif record['read']:
        text += '\n\nLAW YOU HAVE ALREADY READ\n' + '\n\n'.join(
            f"## {pid} {corpus.provisions()[pid]['title']}\n" +
            '\n'.join(f'[{q}] {t}' for q, t in corpus.passages(pid).items()) for pid in record['read'])
    return text


def call(agent, cid, schema, system, user, record, offered):
    toolset = None
    if tools.ENABLED:
        toolset, _ = tools.toolset(agent, [cid], record)
        system += '\n\n' + tools.prompt([cid], tools.budget([cid]))
    result = ask(agent, schema.__name__, schema, system, user, tools=toolset,
                 budget=tools.budget([cid]) if toolset else 0, fact_ids=list(offered), quote_ids=record['passages'])
    return facts.bind(result, offered) if result else None


NOT_A_CONCLUSION = ('what to reconsider: the supervisor read the passages behind the findings and names a specific '
                    'error, but your law is yours to assess; decide from your law, and keep your finding if your law '
                    'supports it, saying why')
COVERAGE = ('COVERAGE WARNINGS (structural, from the citation graph: provisions of your corpus cited by law you '
            'relied on, which you have not read. Read each one and say in impact whether it changes anything.)\n')


def assess(cid, case, offered, record, focus='', prior=None, answers=(), instruction='', asked=(), coverage=()):
    parts = [case_block(case, offered), reading(cid, record)]
    if focus:
        parts.append(f'SUPERVISOR FOCUS (not a legal conclusion)\n{focus}')
    if prior:
        parts.append('YOUR PRIOR ASSESSMENT (still in force; return only what changes)\n' + prior.model_dump_json(indent=1))
    if asked:
        parts.append('QUESTIONS YOU HAVE ALREADY ASKED (do not ask them again, however rephrased; if an answer is '
                     'not enough, ask one narrower follow-up that says what is still missing)\n' + json.dumps(list(asked), indent=1))
    if answers:
        parts.append('ANSWERS FROM OTHER SPECIALISTS (their requirements are reported separately; do not restate '
                     'their law as your own. Each answer carries, under law, the text of the provisions it relies on as '
                     'its specialist read them, and under issues any citation it could not support. Reason from that '
                     'text, not only from the answer\'s summary. You cannot cite it: cite your own provisions)\n'
                     + json.dumps(list(answers), indent=1))
    if instruction:
        parts.append(f'SUPERVISOR INSTRUCTION ({NOT_A_CONCLUSION})\n{instruction}')
    if coverage:
        parts.append(COVERAGE + json.dumps(list(coverage), indent=1))
    if not prior:
        return call(f'{cid}_specialist', cid, SpecialistAnswer, specialist_system(cid), '\n\n'.join(parts), record, offered)
    return call(f'{cid}_specialist', cid, SpecialistPatch, specialist_system(cid) + REVISE, '\n\n'.join(parts), record, offered)


REVISE = """

REASSESSMENT
Your prior assessment stays in force. New information has arrived (answers, a supervisor instruction, or both). Work out which of your requirements it affects, including requirements that depend on an affected one, and return complete replacements only for those (same id), plus any new requirement it reveals. Unchanged requirements are kept as they are, so do not repeat them. Explain the reach of the change in impact."""


def linked_provisions(cid, questions):
    """Structural pointers from the citation graph: provisions of this corpus that cite the provisions
    the questions name. They locate law to read; they decide nothing."""
    named = {corpus.resolve(ref) for q in questions for ref in q.get('referring_provisions', [])}
    prefixes = '|'.join(re.escape(i['prefix']) for m in corpus.manifests().values() for i in m['instruments'])
    named |= {corpus.resolve(m) for q in questions for m in re.findall(rf'(?:{prefixes}) \d+', q['question'])}
    found = []
    for target in sorted(filter(None, named)):
        for source in corpus.cited_by(target):
            if corpus.provisions()[source]['corpus'] == cid:
                found.append(f"{source} ({corpus.provisions()[source]['title']}) cites {target}")
    return found


def answer_questions(cid, asked_by, questions, case, offered, record, already=(), prior=(), instruction='', coverage=()):
    parts = [case_block(case, offered), reading(cid, record),
             'QUESTIONS\n' + json.dumps(questions, indent=1),
             'LINKED PROVISIONS\n' + '\n'.join(linked_provisions(cid, questions) or ['none']),
             'ALREADY REPORTED\n' + json.dumps(list(already), indent=1)]
    if prior:
        parts.append('YOUR PRIOR REPORT\n' + json.dumps(list(prior), indent=1))
    if instruction:
        parts.append(f'SUPERVISOR INSTRUCTION ({NOT_A_CONCLUSION})\n{instruction}')
    if coverage:
        parts.append(COVERAGE + json.dumps(list(coverage), indent=1))
    return call(f'{cid}_specialist', cid, DelegateAnswer, delegate_system(cid, asked_by), '\n\n'.join(parts), record, offered)


SUPERVISOR = """You supervise a multi-jurisdiction assessment of a proposed data transfer. You can see every corpus in the system (manifests and tables of contents). Specialists, each limited to its own corpus, read the law and own their findings.

{rules}"""

PLAN_RULES = """PLAN
- Return exactly one engagement for each top-level corpus: {top}. Lower-level corpora are reached only by delegation from their parent.
- Engage a corpus when any party, data subject, storage location, access point or activity falls within its territory, or its scope provisions could plausibly reach the case. When unsure, engage: a specialist can conclude its law does not apply, but an unengaged corpus is never examined.
- reason must cite facts. focus may point to features of the case, not to legal conclusions.
- Jurisdictions: {registry}"""

SYNTHESIS_RULES = """SYNTHESIS
You own the combined conclusion: whether the requirements of every corpus can be satisfied together. Each specialist owns its individual findings; you cannot change them.
- Read LAW BEHIND THE FINDINGS: the passages each specialist was shown from the provisions its findings and routes cite. It is the only law you may rely on; cite it by quote_ids. Do not import rules from any real-world legal system.
- Check each gate's status and routes against those passages. Then choose one route per engaged gate so that all of them work together: compare requirements and required actions of different corpora that concern the same actor, data or time, and check that taking one route does not defeat another. Record that combination in route_plan, and the outcome as the schema defines it.
- Conflicts: incompatible_law where the law of two corpora pulls apart (resolvable if some combination of routes satisfies both, and name it); disagreement where two findings contradict each other on the same point. Apparent conflicts with a compatible route are resolvable.
- Evidence: the same standard the specialists apply.
{evidence}
- Blockers: a blocker names the gate it blocks (requirement_ref) and the decisive gap: a fact, document or answer without which that gate cannot be decided. If the gate already lists confirmations, say why confirming them later is not enough. Points already listed as confirmations, duties, and routes outside your route_plan (fallbacks you did not choose) are never blockers: put them in notes. The outcome is undetermined only when a blocker or a disagreement remains. A missing fact or document cannot be supplied by a specialist: do not ask for it.
{follow_ups}"""

FOLLOW_UPS = """FOLLOW-UPS (one bounded round; the next pass is final)
- Each follow-up must settle a named legal dependency or a specific error that could change a gate, a route in your route_plan, or the outcome. Nothing else: no wording, no duties that cannot change the decision, no general re-checks.
- routings: OPEN QUESTIONS are peer questions specialists could not answer from their own law. Route each to the corpus whose law answers it (a top-level corpus or a lower-level one), restating it narrowly.
- corrections: name the corpus, the requirement ids, the kind of error, the passages that show it (quote_ids), and exactly what to reconsider. You may say what a passage appears to provide; never tell a specialist what status to give. For a disagreement, set out both positions with their refs and send it to the owning specialist. COVERAGE WARNINGS (structural: provisions a specialist's own cited law points to that it never read) justify a missed_provision correction only when the unread provision could change a gate or a route.
- A requirement that is really one route of another requirement of the same corpus is a defect: ask its specialist to fold it in. Never ask to fold requirements of different corpora together."""

FINAL = """FINAL PASS
- This is the last pass: no further follow-ups. A disagreement that remains is a conflict of kind disagreement (not resolvable) and the outcome is undetermined; anything else a human must decide goes in blockers, under the rules above."""


def plan(case, offered):
    system = SUPERVISOR.format(rules=PLAN_RULES.format(top=', '.join(corpus.top_level()),
                                                       registry=json.dumps(registry_view())))
    user = '\n\n'.join([case_block(case, offered), 'CORPORA\n' + json.dumps([corpus_view(c) for c in corpus.manifests()], indent=1)])
    result = ask('supervisor', 'plan', SupervisorPlan, system, user, fact_ids=list(offered))
    return facts.bind(result, offered) if result else None


SINGLE = """You assess a proposed data transfer alone, against every corpus in this system. There are no other specialists and no supervisor: you decide applicability, read the law, assess the requirements and reconcile them across corpora yourself, in this one reply.

CORPORA
{corpora}
Jurisdictions: {registry}

METHOD
1. For each corpus, decide whether its law applies to any party or activity in the case, from its scope provisions, and record it in applicability. Where a lower-level corpus fills in its parent's law, its law applies wherever the parent leaves a matter to it and the case falls within its territory.
2. Work through every applicable corpus's table of contents and identify every requirement its law imposes that the facts engage, including definitions that change the analysis and cumulative conditions in other provisions.
3. Assess each requirement. Keep requirements for different actors or activities separate. File each under the corpus whose instrument creates it (its corpus field). Where one corpus's law depends on what another corpus's law provides (lower-level law, or another jurisdiction's), read that law yourself and use it; set open_dependency only for law that no corpus here contains.
4. Compare requirements across corpora that concern the same actor, data or time. Record each real conflict in conflicts, whether a route satisfies both (resolvable) and what it is, using refs "<corpus>:<requirement id>". Apparent conflicts with a compatible route are resolvable.
5. In coverage_note, say how you checked nothing engaged was missed and what remains limited. List anything still needing human review in unresolved.

{rules}"""


def single(case, offered):
    """Single-agent baseline: one call over every corpus, with every corpus in tool scope.
    Tool budget = tools.budget(every corpus), the same rule the specialists get for their own corpus."""
    scope = list(corpus.manifests())
    record = tools.new_record()
    rules = '\n'.join(line for line in RULES.format(example=example_id(scope)).splitlines()
                      if not line.startswith('- Report only requirements created by your own instruments'))
    system = SINGLE.format(corpora=', '.join(scope), registry=json.dumps(registry_view()), rules=rules)
    parts = [case_block(case, offered), 'CORPORA\n' + json.dumps([corpus_view(c) for c in scope], indent=1)]
    toolset, budget = None, 0
    if tools.ENABLED:
        budget = tools.budget(scope)
        toolset, _ = tools.toolset('single_agent', scope, record)
        system += '\n\n' + tools.prompt(scope, budget)
    else:
        parts.append('FULL TEXT\n' + tools.full_reading(record, scope))
    result = ask('single_agent', 'SingleAssessment', SingleAssessment, system, '\n\n'.join(parts), tools=toolset,
                 budget=budget, fact_ids=list(offered), quote_ids=record['passages'])
    return (facts.bind(result, offered) if result else None), record


BASELINE = """You assess whether a proposed data transfer may proceed under the laws of the jurisdictions listed below. Reply in one go.

CORPORA
{corpora}
Jurisdictions: {registry}

Record whether each corpus applies, the requirements its law imposes that the facts engage (filed under the corpus whose instrument creates it), any conflicts between them, and your decision.

DEFINITIONS
{definitions}
- Cite provisions by ID (e.g. "{example}"). quote_id: the passage ID (e.g. "{example}#L2") of the line of law you rely on, or "none"."""

BASELINE_DEFINITIONS = ('- status:', '- kind:', '- routes:', '- A requirement is')


def baseline(case, offered, level):
    """Unguarded baseline (see BaselineAssessment). Same case, corpus manifests and tables of contents as the single
    agent; level 'corpus' adds the full text of every corpus to the prompt. No tools, corpus-only or evidence rules,
    supplied-ID restrictions or strict schema: only the output contract (schema as text and status definitions)."""
    scope = list(corpus.manifests())
    record = tools.new_record()
    definitions = '\n'.join(line for line in RULES.format(example=example_id(scope)).splitlines()
                            if line.startswith(BASELINE_DEFINITIONS))
    system = BASELINE.format(corpora=', '.join(scope), registry=json.dumps(registry_view()),
                             definitions=definitions, example=example_id(scope))
    parts = [case_block(case, offered), 'CORPORA\n' + json.dumps([corpus_view(c) for c in scope], indent=1)]
    if level == 'corpus':
        parts.append('FULL TEXT\n' + tools.full_reading(record, scope))
    result = ask('baseline', f'BaselineAssessment ({level})', BaselineAssessment, system, '\n\n'.join(parts),
                 strict=False)
    return (facts.bind(result, offered) if result else None), record


def law_block(shown):
    """The passages behind the findings, grouped by provision."""
    grouped = {}
    for qid, text in shown.items():
        grouped.setdefault(qid.rsplit('#', 1)[0], []).append(f'[{qid}] {text}')
    return '\n\n'.join(f"## {pid} {corpus.provisions()[pid]['title']} ({corpus.provisions()[pid]['corpus']})\n"
                        + '\n'.join(lines) for pid, lines in grouped.items()) or 'none'


def synthesise(case, offered, view, shown, final=False):
    """Supervisor synthesis. A first pass may request one bounded round of follow-ups; the final pass concludes."""
    system = SUPERVISOR.format(rules=SYNTHESIS_RULES.format(evidence=EVIDENCE,
                                                            follow_ups=FINAL if final else FOLLOW_UPS))
    user = '\n\n'.join([case_block(case, offered),
                         'CORPORA\n' + json.dumps([corpus_view(c) for c in corpus.manifests()], indent=1),
                         'CURRENT STATE\n' + json.dumps(view, indent=1),
                         'LAW BEHIND THE FINDINGS\n' + law_block(shown)])
    schema = SupervisorConclusion if final else SupervisorSynthesis
    return ask('supervisor', 'conclusion' if final else 'synthesis', schema, system, user, fact_ids=list(offered),
               quote_ids=shown)
