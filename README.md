# Mock corpus engine

A corpus-driven multi-agent framework for assessing proposed cross-border data transfers. No
jurisdiction, law or requirement is written into the code: everything comes from `corpora/`.
The included corpora are **fictional** (Region A, Region B, Subregion A1),
so results can be scored against known answers and cannot be produced from memorised real law.

```text
corpora/   registry.json + one folder per corpus (corpus.json manifest, provisions in markdown)
engine/    corpus registry, scoped KG tools, agents, pipeline, verification, brief (see engine/README.md)
cases/     mock cases: case.json (model input) and key.json (answer key, never sent to the model)
runs/mock/ saved runs (git-ignored)
```

`REAL_LAW_MAP.md` records which GDPR/HIPAA/Irish provision each fictional provision is modelled on, and every deliberate departure. It is a research record only and is never sent to a model.

## Run

```bash
.venv/bin/streamlit run ui_mock.py --server.address 127.0.0.1 --server.port 8503
.venv/bin/python run_mock.py cases/01_a1_gp_to_region_b_host
.venv/bin/python score_mock.py        # score every saved run against its key, with a consistency matrix
.venv/bin/python -m unittest discover -s tests
```

Copy `.env.example` to `.env` and set `MODEL` and the provider key. Ablations: `TRAVERSAL_TOOLS=0`
(whole corpus in context) and `MAX_TOOL_CALLS`.

## Adding a corpus

Add a folder under `corpora/` with a `corpus.json` (id, name, level, territory, parent/children,
unit word, instruments with prefix and aliases) and markdown provisions headed `## [ID] Title`,
then list it in `corpora/registry.json`. Cross-references are read from the prose.
