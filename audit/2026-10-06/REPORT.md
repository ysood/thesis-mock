# Corpus and knowledge-graph audit, 6 October 2026

Fresh, independent check of `laws/*.md` and `reference/knowledge_graph.json` against official texts
downloaded today. It is independent of the 5 October audit (`audit/2026-10-05/`, whose evidence files
are retained) and does not rely on its snapshots.

Reproduce from `prototype/`:

    .venv/bin/python audit/2026-10-06/fetch.py         # official texts -> sources/, hashes -> sources.json
    .venv/bin/python audit/2026-10-06/check_corpus.py  # -> corpus_check.json
    .venv/bin/python audit/2026-10-06/check_graph.py   # -> graph_check.json

Matching ignores case, spacing and punctuation but keeps word and number order.

## Verdict

| Check | Result |
|---|---|
| GDPR text is official and current | **Yes.** All 99 articles and 173 recitals present; every line matches the Publications Office text. No amendment in force. |
| HIPAA text is official and current | **Yes.** Part 160 and Part 164 (Subparts A, C, D, E) complete (only the reserved § 160.302 absent); every line matches eCFR as of 2 Oct 2026, including the 2026 claims-attachments amendment. |
| Irish text is official and current | **Yes, for what it holds.** 9 DPA 2018 sections and 3 S.I.s; every line matches the Irish Statute Book. None of the 9 sections has been textually amended (LRC revised Act, to 17 Sep 2026). It is a selection, not the whole Act. |
| Graph quotes are grounded | **Yes.** 303 of 303 quotes found in the local provision and in the fresh official text; 237 pinpoints machine-checked (4 flags verified correct by hand); 0 structural issues; every bundle ID exists; every node reachable and quoted. |
| Graph mappings are complete and well-founded | **Mostly; three substantive problems** (below), two of which bear directly on scenario 18. |

## Official sources (links)

GDPR, Regulation (EU) 2016/679
- Reader (EUR-Lex): https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng
- Articles, consolidated with corrigendum (Cellar): http://publications.europa.eu/resource/celex/02016R0679-20160504
- Recitals, Official Journal L 119, 4.5.2016 (Cellar): http://publications.europa.eu/resource/celex/32016R0679
- Amendment status ("Modified by": corrigenda only; proposals COM(2025) 501 and COM(2025) 837 not adopted): https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX:32016R0679

HIPAA, 45 CFR Parts 160 and 164
- eCFR reader: https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C
- eCFR full text used (2 Oct 2026): https://www.ecfr.gov/api/versioner/v1/full/2026-10-02/title-45.xml?part=160 and `?part=164`
- Amendment history: https://www.ecfr.gov/api/versioner/v1/versions/title-45.json?part=160 and `?part=164`
- Operative-law notice (Purl v. HHS, N.D. Tex., 18 June 2025, vacating most of the 2024 reproductive-health rule): https://www.hhs.gov/hipaa/for-professionals/special-topics/reproductive-health/final-rule-fact-sheet/index.html

Ireland
- Data Protection Act 2018, as enacted (Irish Statute Book): https://www.irishstatutebook.ie/eli/2018/act/7/enacted/en/html
- Revised Act, updated to 16 July 2026, changes in force to 17 Sep 2026 (Law Reform Commission): https://revisedacts.lawreform.ie/eli/2018/act/7/revised/en/html
- Legislation affecting the 2018 Act: https://www.irishstatutebook.ie/eli/isbc/2018_7.html
- Health Research Regulations, S.I. 314/2018: https://www.irishstatutebook.ie/eli/2018/si/314/made/en
- Amendment S.I. 188/2019: https://www.irishstatutebook.ie/eli/2019/si/188/made/en
- Amendment S.I. 18/2021: https://www.irishstatutebook.ie/eli/2021/si/18/made/en

SHA-256 of every downloaded file is in `sources.json`.

## Corpus results

- 546 provisions, 0 with any line not in the official text (`corpus_check.json`).
- Official paragraphs absent locally are only editorial: CFR source notes (`[65 FR ...]`), the Art. 4
  lead-in "For the purposes of this Regulation:", and LRC annotations in ss. 36 and 38.
- GDPR: the Official Journal and consolidated articles differ only where the 2018 corrigendum applies;
  the corpus uses the consolidated (corrected) articles.
- HIPAA: § 160.103 was amended at 91 FR 14404 (24 Mar 2026, effective 26 May 2026): "Health claims
  attachments" became "Health care claims attachments". The corpus has the new wording. The
  vacated 2024 text is still printed in eCFR; `reference/legal_status.json` carries the HHS notice.
- Ireland: s. 36(2) and s. 38(4) have only "power exercised" notes; s. 38 and 38(4) have "application
  restricted" notes from the Data Sharing and Governance Act 2019 (public-body-to-public-body sharing,
  16 Dec 2022). Neither changes the text; the restriction is not modelled. The Health Research
  Regulations' only amendments under s. 36(2) are S.I. 188/2019 and S.I. 18/2021, both in the corpus.

## Graph results

276 nodes (20 requirements, 52 routes, 67 conditions, 21 concepts, 73 provisions, 43 request values),
471 edges. 291 edges carry a statutory quote; the rest are authored dependencies (`requires`,
`scoped_by`, `gated_by`, `uses_concept`, `implemented_by`: 110), intake bindings (`claims`/`denies`: 65)
and cross-regime correspondences (5). Quote checks prove provenance, not that a legal reading is right;
the review below is the substantive part.

### Substantive findings (manual review of every node statement against its quotes)

1. **Art. 9(3) is narrowed.** `gdpr.cond.art9_3_professional_secrecy` quotes and states only
   "professional secrecy under Union or Member State law". The official text continues "or rules
   established by national competent bodies or by another person also subject to an obligation of
   secrecy". Rules of a professional regulator (for Irish doctors, the Medical Council) are exactly
   that limb, and scenario 18's runs held registration with the Irish Medical Council insufficient.
   No Irish provision implements this condition.
2. **The public-task chain stops one statute short.** Art. 6(1)(e) → Art. 6(3) opening →
   `ie.public_function_basis` (DPA s. 38) requires "a function ... conferred by or under an enactment".
   The enactment conferring the HSE's functions is not in the corpus, so the national-law specialist
   correctly says "law not in sources" (scenario 18 runs).
3. **"Health practitioner" is defined outside the corpus.** DPA s. 52(3) takes the meaning from the
   Health Identifiers Act 2014, which is absent; `ie.cond.health_practitioner_responsibility` depends on it.
4. Weak but valid grounding: the scope nodes `hipaa.cond.recipient_covered_entity` (quotes the
   § 164.530(c)(1) safeguards duty) and `hipaa.cond.recipient_business_associate` (quotes
   § 164.504(e)(2)(ii) "Provide that the business associate will:") are classifications better grounded
   in the § 160.103 definitions, which are in the corpus.
5. Route-list basis quotes: the four GDPR Art. 3 routes share the Art. 3(1) sentence as their
   `has_route` basis (pinpoint 3(1)-(3)); the quote does not itself show the alternatives. Cosmetic.
6. Several condition statements are broader than their single quote (e.g. `gdpr.cond.dpia_before_processing`
   states Art. 35(2), (7)-(9), (11) content but quotes 35(1); likewise Art. 30(5), Art. 32). The bundles
   hand the specialist the whole article, so the text is available; the edge quote under-documents it.
7. Openings with no Irish implementation: Art. 6(3) for 6(1)(c), Art. 9(2)(b), 9(2)(g), 49(4) and 9(3).
   Only 6(1)(e) (s. 38), 9(2)(h) (s. 52), 9(2)(i) (s. 53), 9(2)(j) (s. 54/42) and 9(4) (HRR) are linked.

HIPAA in scenario 18 is not a corpus gap: the covered-entity test needs § 160.103's "Covered entity"
and "Transaction" definitions, both present. The unresolved status there is the specialist's reasoning.

### What the official texts point to for findings 1–3 (not yet added)

Verified on the Irish Statute Book, 6 Oct 2026:
- Health Act 2004 (No. 42), s. 7 "Object and functions of Executive" (finding 2): https://www.irishstatutebook.ie/eli/2004/act/42/enacted/en/html
- Health Identifiers Act 2014 (No. 15), s. 2: "health practitioner" means (a) a registered medical practitioner
  within the meaning of s. 2 of the Medical Practitioners Act 2007 ... (finding 3): https://www.irishstatutebook.ie/eli/2014/act/15/section/2/enacted/en/html
- Medical Practitioners Act 2007 (No. 25): registration and the Medical Council (findings 1, 3): https://www.irishstatutebook.ie/eli/2007/act/25/enacted/en/html
- Medical Council (the "national competent body" for Art. 9(3); its conduct and ethics guide is the
  candidate "rules" text, edition not yet checked): https://www.medicalcouncil.ie/

Each would need its revised (LRC) status checked before use, as was done here for the DPA.

## Limits

- Matching ignores punctuation and spacing; it is not proof of legal entailment.
- Pinpoints are checked to the first level only (Art. 9(2), § 164.502(e), s. 52(1)); 66 quotes
  (recitals, definitions, S.I. regulations) are matched at unit level only.
- The Irish S.I.s are matched at instrument level.
- The substantive review is one reader's analysis, not a lawyer's sign-off.

## Addendum (same day): finding 1 fixed, Art. 9(3) answered for doctors

Changes, and nothing else:

- `gdpr.cond.art9_3_professional_secrecy`: full Art. 9(3) quote and statement (both limbs; law or
  competent-body rules), and an opening on "under Union or Member State law or rules established by
  national competent bodies".
- New Irish national requirement `ie.medical_professional_secrecy` (implements that opening) and
  condition `ie.cond.registered_medical_practitioner_responsibility`.
- Two corpus files, fetched by `scripts/fetch_laws.py`:
  - `laws/ie_medical_practitioners_act_2007.md`: s. 7 only, Law Reform Commission revised text
    (updated to 29 July 2026; changes in force to 17 Sep 2026), because s. 7 has been amended
    (e.g. Regulated Professions (Health and Social Care) (Amendment) Act 2020). Source:
    https://revisedacts.lawreform.ie/eli/2007/act/25/revised/en/html#SEC7
  - `laws/ie_medical_council_guide_2024.md`: Medical Council, Guide to Professional Conduct and Ethics
    for Registered Medical Practitioners, 9th edition (2024; launched November 2023, the current edition on
    the publication page), Introduction and para. 25 only. Source PDF (SHA-256 `ef5dc845...313353`):
    https://www.medicalcouncil.ie/news-and-publications/publications/guide-to-professional-conduct-and-ethics-for-registered-medical-practitioners-2024.pdf
    Publication page: https://www.medicalcouncil.ie/news-and-publications/publications/overview/guide-to-professional-conduct-and-ethics.html
- The national-law specialist now also receives the pinned bundle of each opening's national requirement
  (`app/agents.py`), so these texts reach it even when search misses them.

Interpretation, stated in the graph and KNOWLEDGE_GRAPH.md section 6: the guide is issued under s. 7(2)(i)
but says "It is not a legal code". Reading it as "rules established by national competent bodies" is the
model's interpretation, not a quotation. It covers registered medical practitioners only; a failed Irish
answer leaves Art. 9(3) undetermined (another secrecy source may apply), never failed.

Re-check after the change: 549 provisions, 0 unmatched lines (LRC amendment markers such as "F21 [" are
removed from both sides); 309 quotes, 0 local or official mismatches; 0 validation issues; 281 nodes,
478 edges; 224 offline tests pass.

The 5 October check (`audit/2026-10-05/check_sources.py`) is a dated check of the graph as it stood that
day (it pins that graph's hash) and does not know the two new Irish sources; it now stops on them. It is
left unchanged as a record. Use the 6 October scripts for the current graph.
