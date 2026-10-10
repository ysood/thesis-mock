# Generated normative graph

`generated_graph.json` is the reviewed graph from `sandbox/kg_mockgen` (`runs/reviewed`, 11 Oct 2026):
generated from these same corpora by `openai:gpt-5.6-luna` with no requirement catalogue, admitted by
code guardrails (verbatim quotes, typed links, coverage), then corrected by a human review recorded in
`sandbox/kg_mockgen/review/review.json`. See `sandbox/kg_mockgen/FINDINGS.md`.

It is used only when `KG_GRAPH=generated` (or the UI's "Knowledge graph" switch): `engine/graph.py`
then attaches `graph_hints` to `kg_node` and `read_provision` results. Hints are not law and are never
citable; agents still read and cite the provisions. If the corpora change, regenerate the graph.
