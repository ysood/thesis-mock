# Mock corpus engine

A corpus-driven multi-agent framework for assessing proposed cross-border data transfers. No
jurisdiction, law or requirement is written into the code: everything comes from `corpora/`.
The included corpora are **fictional** (Region A, Region B, Subregion A1),
so results can be scored against known answers and cannot be produced from memorised real law.

```text
corpora/   registry.json + one folder per corpus (corpus.json manifest, provisions in markdown)
engine/    corpus registry, scoped KG tools, agents, pipeline, verification, brief (see engine/README.md)
kg/        generated normative graph (optional agent hints; see kg/README.md)
cases/     mock cases: case.json (model input) and key.json (answer key, never sent to the model)
runs/mock/ saved runs (git-ignored)
```

`REAL_LAW_MAP.md` records which GDPR/HIPAA/Irish provision each fictional provision is modelled on, and every deliberate departure. It is a research record only and is never sent to a model.

## Cases

- `01_a1_gp_to_region_b_host`: ongoing patient-record hosting with host-held keys and missing safeguards.
- `02_a1_gp_keys_held_in_a1`: hosting variant with practice-held keys and supporting documents.
- `03_a1_emergency_records_to_b_hospital`: one patient's emergency treatment handoff to an independent hospital, including relevant genetic information. Its research notes explain the cross-corpus checks; the draft expected result is proceed.

- `04_a1_genetic_result_to_b_life_insurer`: one genetic test result sent to a Region B life insurer on explicit written consent. A1-HIA 7 stops that consent lifting the sensitive-information prohibition for insurance and excludes the consent derogation for genetic information; the same consent still works for the lawful ground and professional secrecy. Draft expected result is do not proceed.

Case folders are discovered automatically by the UI. Answer keys and case research notes are never model input.

## Run

```bash
.venv/bin/streamlit run ui_mock.py --server.address 127.0.0.1 --server.port 8503
.venv/bin/python run_mock.py cases/01_a1_gp_to_region_b_host
.venv/bin/python score_mock.py        # score every saved run against its key, with a consistency matrix
.venv/bin/python -m unittest discover -s tests
```

Graph support: `KG_GRAPH=generated` (or the UI's "Knowledge graph" switch) gives agents hints from the
generated normative graph in `kg/` on `kg_node` and `read_provision`. `graph_test.py run <case> <runtime|generated>`
saves to `runs/graph_test/`; `graph_test.py report` compares the modes check by check.

Copy `.env.example` to `.env` and set `MODEL` and the provider key. Ablations: `TRAVERSAL_TOOLS=0`
(whole corpus in context) and `MAX_TOOL_CALLS`.

## Adding a corpus

Add a folder under `corpora/` with a `corpus.json` (id, name, level, territory, parent/children,
unit word, instruments with prefix and aliases) and markdown provisions headed `## [ID] Title`,
then list it in `corpora/registry.json`. Cross-references are read from the prose.
