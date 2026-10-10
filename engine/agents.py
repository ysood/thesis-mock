"""Agent calls. Every role, scope and jurisdiction is read from the corpus registry; no law is named here.

Supervisor: sees every corpus (manifest + table of contents), plans, routes and reconciles.
Specialist: one per engaged top-level corpus, reads only its own corpora through scoped tools.
Delegate: a lower-level (or peer) specialist answering questions put to it, and reporting any
further requirement of its own law that the facts engage.
"""

import json
import re

from engine import corpus, facts, tools
from engine.llm import ask
from engine.schema import DelegateAnswer, SpecialistAnswer, SpecialistPatch, SupervisorPlan, SupervisorReview

RULES = """RULES
- The laws in your corpora are the only law. Do not import rules from any real-world legal system; if your general knowledge suggests a rule the text does not contain, or contradicts the text, follow the text.
- Facts: refer to FACT PASSAGES by fact_id. Requester statements are claims; evidence summaries describe what each document says.
- Treat the stated facts and described arrangements as complete. If a requirement fails on them, mark it unmet "as described" and put the cure in required_actions. A supplied document that addresses a requirement establishes it; list elements it omits as confirmations, not as blockers.
- status: met | unmet | undetermined (a decisive fact, document or answer from other law is missing: say which in missing_facts, missing_evidence or open_dependency) | not_applicable.
- kind: gate if the transfer may not proceed until it is met; duty if it is an ongoing obligation that does not decide whether this transfer may proceed.
- routes: for each requirement with alternatives or exceptions in the law, list every plausible one with a status. Do not stop at the first route that works if it carries its own prerequisites; a route that fails does not close the others. ruled_out needs a reason from the text, and means no change by the parties could make the route work. A route the parties could still adopt (a different contract term, a document, a notification, a technical measure) is available, with the changes in required_actions: these are the routes forward.
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

Other jurisdictions in this system: {', '.join(others)}. You cannot read their law. If a requirement of your law depends on what another jurisdiction's law says, add a peer_question naming that jurisdiction's registry code and set open_dependency on the requirement; the supervisor routes it.
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
    return f"""You are the specialist for the law of {m['name']} ({m['level']}), with the instruments: {', '.join(i['title'] for i in m['instruments'])}. The specialist for {asked_by} has put questions to you that your law must answer.

Answer each question from your law, with facts, citations and a quote. Answer what your law provides, not only the literal question: if a provision of yours does what the question asks about by a different route or under a different name, say so. Read the provisions listed under LINKED PROVISIONS before answering: they cite the provisions the questions refer to.
Then report in additional_requirements every further requirement of your law that the facts engage and that the questions did not ask about. Each must be an obligation created by your own instruments: do not assess the asking specialist's provisions or any other corpus's law. Do not repeat requirements listed under ALREADY REPORTED. If YOUR PRIOR REPORT is shown, return a complete corrected replacement of those additional requirements.

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
        system += '\n\n' + tools.prompt([cid])
    result = ask(agent, schema.__name__, schema, system, user, tools=toolset,
                 budget=tools.MAX_TOOL_CALLS if toolset else 0, fact_ids=list(offered), quote_ids=record['passages'])
    return facts.bind(result, offered) if result else None


def assess(cid, case, offered, record, focus='', prior=None, answers=(), instruction='', asked=()):
    parts = [case_block(case, offered), reading(cid, record)]
    if focus:
        parts.append(f'SUPERVISOR FOCUS (not a legal conclusion)\n{focus}')
    if prior:
        parts.append('YOUR PRIOR ASSESSMENT (still in force; return only what changes)\n' + prior.model_dump_json(indent=1))
    if asked:
        parts.append('QUESTIONS YOU HAVE ALREADY ASKED (do not ask them again, however rephrased; if an answer is '
                     'not enough, ask one narrower follow-up that says what is still missing)\n' + json.dumps(list(asked), indent=1))
    if answers:
        parts.append('ANSWERS FROM OTHER SPECIALISTS (their additional requirements are reported separately; '
                     'use the answers, do not restate their law as your own)\n' + json.dumps(list(answers), indent=1))
    if instruction:
        parts.append(f'SUPERVISOR INSTRUCTION\n{instruction}')
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


def answer_questions(cid, asked_by, questions, case, offered, record, already=(), prior=(), instruction=''):
    parts = [case_block(case, offered), reading(cid, record),
             'QUESTIONS\n' + json.dumps(questions, indent=1),
             'LINKED PROVISIONS\n' + '\n'.join(linked_provisions(cid, questions) or ['none']),
             'ALREADY REPORTED\n' + json.dumps(list(already), indent=1)]
    if prior:
        parts.append('YOUR PRIOR REPORT\n' + json.dumps(list(prior), indent=1))
    if instruction:
        parts.append(f'SUPERVISOR INSTRUCTION\n{instruction}')
    return call(f'{cid}_specialist', cid, DelegateAnswer, delegate_system(cid, asked_by), '\n\n'.join(parts), record, offered)


SUPERVISOR = """You supervise a multi-jurisdiction assessment of a proposed data transfer. You can see every corpus in the system (manifests and tables of contents) but you do not assess the law yourself: specialists do, each limited to its own corpus.

{rules}"""

PLAN_RULES = """PLAN
- Return exactly one engagement for each top-level corpus: {top}. Lower-level corpora are reached only by delegation from their parent.
- Engage a corpus when any party, data subject, storage location, access point or activity falls within its territory, or its scope provisions could plausibly reach the case. When unsure, engage: a specialist can conclude its law does not apply, but an unengaged corpus is never examined.
- reason must cite facts. focus may point to features of the case, not to legal conclusions.
- Jurisdictions: {registry}"""

REVIEW_RULES = """REVIEW
- OPEN QUESTIONS are peer questions specialists could not answer from their own law. Route each to the corpus whose law answers it (a top-level corpus or a lower-level one), restating the question for that specialist.
- Compare requirements across corpora that concern the same actor, data or time. Record each real conflict, whether a route satisfies both (resolvable) and what it is. Apparent conflicts with a compatible route are resolvable.
- A requirement that is really one route of another requirement (an alternative way to meet the same obligation) is a defect: ask its specialist to fold it into that requirement's routes.
- Request a revision only for a concrete defect that could change a gate's status, the decision or the set of gates: an unsupported gate status, an engaged provision in that corpus's table of contents (top-level or lower-level) that no requirement addresses, or a stale answer after new information. Do not request revisions of wording, or of the status of duties that cannot change the decision. Name the corpus, requirement IDs and the defect. Lower-level corpora can be revised too.
- You cannot change findings. finish when nothing remains to route or revise; list anything still needing human review in unresolved."""


def plan(case, offered):
    system = SUPERVISOR.format(rules=PLAN_RULES.format(top=', '.join(corpus.top_level()),
                                                       registry=json.dumps(registry_view())))
    user = '\n\n'.join([case_block(case, offered), 'CORPORA\n' + json.dumps([corpus_view(c) for c in corpus.manifests()], indent=1)])
    result = ask('supervisor', 'plan', SupervisorPlan, system, user, fact_ids=list(offered))
    return facts.bind(result, offered) if result else None


def review(case, offered, view):
    system = SUPERVISOR.format(rules=REVIEW_RULES)
    user = '\n\n'.join([case_block(case, offered),
                        'CORPORA\n' + json.dumps([corpus_view(c) for c in corpus.manifests()], indent=1),
                        'CURRENT STATE\n' + json.dumps(view, indent=1)])
    return ask('supervisor', 'review', SupervisorReview, system, user, fact_ids=list(offered))
