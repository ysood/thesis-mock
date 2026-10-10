# v15 provision-only knowledge graph

The active graph is a lookup and navigation layer over stored law. It contains
source provisions and recitals, connected by citation, amendment and definition
links. It contains no authored requirements, routes, conditions or concept nodes.

## Construction and lookup

- `app/knowledge.py:provisions` reads provision IDs, titles and full text from `laws/*.md`.
- `app/knowledge.py:graph` extracts explicit references and adds the small curated
  amendment/definition links in `reference/legal_relationships.json`.
- `cites` and `cited_by` identify outgoing and incoming references. `amends` and
  `amended_by` record amendments; `definitions` records curated dependencies.
- Curated links must reference existing source IDs. An edge records a textual
  relationship; it does not establish applicability, legal support or compliance.
- `app/traversal.py:kg_node` returns a provision's ID/title/regime and relationships,
  without source text. Checklist question IDs are not graph nodes.
- Opening a provision adds at most 12 one-hop suggestions, preferring outgoing
  links and supporting context. Full relationships remain inspectable via `kg_node`.
  Links and search hits are not read or made citable automatically.

## Checklist and corpus retrieval

The 15 fixed GDPR/HIPAA review questions remain in `reference/requirements.json`.
Their anchors identify starting provisions through `app/requirements.py:source_ids`.
These questions are coverage policy outside the graph, not legal predicate nodes.
Initial reading includes known amendments and curated definition dependencies,
without recursively loading every cited article. Every specialist can search its
regime's full stored corpus and open additional provisions within the existing budgets.

The specialist derives applicable routes, prerequisites, exceptions and scope
from legal text it reads. No `KG GUIDANCE` block or `condition_answers` output
schema is sent. Python validates facts, citations, quote IDs, assignments and
coverage; specialists retain legal judgment and the supervisor retains final review.
The evidence, closed-world corpus and assessment-as-described policies are unchanged.

## National law

GDPR delegates a specific legal question with a country, parent checklist ID and
at least one referring GDPR provision. There is no graph-opening field or
predefined condition-to-national-implementation mapping. The national child gets
the cited GDPR text, searches its country's corpus and can follow reverse citation
links from those GDPR provisions. Known amendments and definition dependencies
still accompany retrieved local provisions. GDPR reassesses the affected findings.

## Archived model and comparison

The previous authored model, shared sources, notes and design documentation are in
`reference/archive/normative_kg_v15/`. No active code loads those files.
An exact pre-experiment working-tree snapshot and before/after measurements are
saved locally under `runs/experiments/provision_links_before/` (Git-ignored).
This allows a local revert without discarding unrelated v15 intake changes.

The measured initial labelled legal-source context fell from 88,773 to 62,159
characters for GDPR (30%) and from 124,510 to 71,018 for HIPAA (43%). This includes
removal of the former guidance and narrower initial reading, not the case input or
output schema. Additional research may grow later prompts. Offline checks verify
execution and source integrity; legal accuracy still needs comparable live runs.
