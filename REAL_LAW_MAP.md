# Real-law map for the fictional corpora

The corpora in `corpora/` are fictional. This file records which real provision, decision or guidance each fictional provision is modelled on, how closely it follows that source, and where it departs on purpose. It is a **research record only**:

- It is never sent to a model. Nothing in `engine/` reads it. Do not quote it, or paraphrase it, in prompts, schema descriptions or cases (the same leakage rule as in `CHANGE_JOURNAL.md`, 10 Oct 2026).
- It was written after the corpora, on 10 October 2026. It explains the selection after the fact. It does not claim the corpora were drafted from official guidance step by step.
- Each real-law reference was checked against the primary text on 10 October 2026: the local official copies in `../prototype/laws/` (GDPR, HIPAA, SCC 2021/914, Irish Data Protection Act 2018, Health Research Regulations 2018, DPC impact-assessment list), the EDPB Recommendations 01/2020 PDF, and the Schrems II judgment on EUR-Lex. Two items rest on secondary summaries and are marked as such.

**Fidelity labels.** *Faithful*: same rule, renamed terms. *Simplified*: same rule, fewer limbs or exceptions. *Changed*: real rule altered on purpose (the note says how). *Invented*: no real counterpart, added to create a testable question.

## 1. Why these provisions: the selection against official guidance

Real GDPR has 99 articles and HIPAA's Privacy, Security and Breach Rules run to hundreds of sections. The corpora keep the provisions that official guidance puts at the centre of a cross-border hosting decision, then add a smaller set of plainly irrelevant provisions (section 5) so that ignoring law is also tested.

| Official guidance step | What it asks | Corpus provisions |
|---|---|---|
| EDPB Recommendations 01/2020, Step 1 *Know your transfers* (incl. para 13: remote access and storage in a non-EEA cloud are transfers) | Is there a transfer, of what, to whom | A-REG 4(9) outward transfer (incl. hosting and access), A-REG 3 territorial scope |
| EDPB Guidelines 05/2021 (v2.0, 14 Feb 2023): three cumulative criteria for a transfer | Exporter subject to GDPR; disclosure to another party; importer in a third country | A-REG 3, A-REG 4(5), (6), (8), (9) |
| Recs 01/2020 Step 2 *Identify the transfer tool* | Adequacy (Art 45), safeguards (Art 46), derogations (Art 49) | A-REG 16–19, Annex II |
| Recs 01/2020 Step 3 *Assess the law and practice of the third country* | Public-authority access to the data | A-REG 18(2); the whole Region B Records Access Act |
| Recs 01/2020 Step 4 *Supplementary measures* (Use Case 1, para 84: encryption effective only if keys stay with the exporter; Use Case 6, para 94: no effective measure where the processor needs data in the clear) | Can encryption or other measures close the gap | A-REG 18(2)–(3); A1-HIA 6(1)(b) (keys); case fact: keys held by the host in Region B |
| Steps 5–6 *Procedural steps; re-evaluate* | Ongoing obligations | not modelled (outside a single-decision assessment) |
| Lawfulness of processing health data before any transfer (GDPR Arts 6, 9, 9(3), 9(4)) | Lawful ground plus special-category condition, with national add-ons | A-REG 6, 8; A1-HIA 4, 5 |
| Processor arrangements (GDPR Art 28) | Contract terms with the host | A-REG 9 |
| Transparency and impact assessment (GDPR Arts 13(1)(f), 35, 35(4) national lists) | Telling patients; assessing high-risk processing | A-REG 11, 12; A1-HIA 8 |
| HHS, *Guidance on HIPAA & Cloud Computing* (OCR, Oct 2016; **secondary summaries only**, the hhs.gov page returned 403) | A cloud host of covered-entity data is a business associate, even without the key; offshore storage is allowed with a BAA but is a risk-analysis factor | B-HRA 2–3, 5, 7 |

## 2. Region A Personal Information Regulation ↔ GDPR (Regulation (EU) 2016/679)

| Mock | Real counterpart | Fidelity | Note |
|---|---|---|---|
| A-REG 1 | Art 1(1) | Simplified | 1(2) states the opening-clause idea as a single rule; GDPR has no such article. |
| A-REG 2 | Art 2(1), 2(2)(c); Recital 26 (anonymous data) | Simplified | |
| A-REG 3 | Art 3(1), 3(2) | Faithful | |
| A-REG 4 | Art 4(1), (13), (15), (7), (8), (5), (21); Art 9(1) | Changed | "Sensitive information" narrows special categories to health, genetic and biometric. 4(9) *outward transfer* is defined (GDPR does not define "transfer"), built from EDPB Guidelines 05/2021 and Recs 01/2020 para 13. |
| A-REG 5 | Art 5(1), 5(2) | Changed | 5(1)(c) adds "use pseudonymised data where the purpose allows", which GDPR expresses through Arts 25 and 89(1), not Art 5. |
| A-REG 6 | Art 6(1)(a)–(f) and the subparagraph after it | Changed | 6(2) also bars legitimate interests for sensitive information. In GDPR, Art 6(1)(f) is not barred, but Art 9 has no legitimate-interests condition, so the practical result is similar. |
| A-REG 7 | Art 7; Art 8(1) (age 16, Member States may lower to 13) | Changed | GDPR Art 8 covers only information society services offered to a child; the mock applies the age rule to all consent. |
| A-REG 8 | Art 9(1), 9(2)(a), (c), (h) with 9(3), (i), (j); 9(4) | Simplified | 8(2)(c) merges Art 9(2)(h) and the professional-secrecy condition in 9(3). |
| A-REG 9 | Art 28(1), 28(3)(a)–(h), 28(10) | Faithful | 9(2)(f) is Art 28(3)(g) (delete or return, at the controller's choice). |
| A-REG 10 | Art 26 | Simplified | |
| A-REG 11 | Art 13(1)–(2); 11(2) is Art 13(1)(f) | Simplified | |
| A-REG 12 | Art 35(1), 35(3)(b)–(c), 35(4), 35(7) | Changed | "Large scale" (35(3)(b)) is replaced with an objective threshold of 5,000 persons. |
| A-REG 13 | Art 30 | Simplified | No small-organisation exemption (Art 30(5)). |
| A-REG 14 | Art 32(1) | Simplified | |
| A-REG 15 | Art 33(1)–(2) | Changed | 48 hours instead of 72; no Art 34 notice to individuals. |
| A-REG 16 | Art 44 | Changed | Closed list of routes (Arts 17–19). GDPR also has binding corporate rules (Art 47), other Art 46 tools and the Art 49(1) second-subparagraph fallback. |
| A-REG 17 | Art 45; Implementing Decision (EU) 2023/1795 (EU–US Data Privacy Framework, 10 July 2023), which covers only certified US organisations | Simplified | 17(3) (active certification, kind of information) makes the certified-recipient limit explicit. |
| A-REG 18 | Art 46(1), 46(2)(c); SCC Decision (EU) 2021/914, Clause 14; *Schrems II* (C-311/18, 16 July 2020) paras 133–135 | Faithful | 18(2) is the exporter's case-by-case assessment (para 134; Clause 14(a)–(b)). 18(3) is "suspend or end the transfer" (para 135). |
| A-REG 19 | Art 49(1)(a), (b), (f), (d); 49(3); 49(4); Recital 111 | Changed | 19(1)(c) is GDPR 49(1)(f). The "occasional" limit (Recital 111 speaks of occasional transfers) is made a rule for (a) and (b). 19(3) leaves out (c) and the second subparagraph. |
| A-REG 20 | Art 89(1); Art 9(2)(j) | Simplified | |
| A-REG 21 | Art 51(1); GDPR opening clauses | Simplified / invented | 21(2) lists the opening clauses used. 21(3) (law of the custodian's Subregion applies) is invented: GDPR has no conflict-of-laws rule for Member State law. |
| A-REG 22–28 | Arts 52, 57, 58, 68/70/71, 77, 78(1)/79(1), 82(1)–(2) | Simplified | Filler, added 10 Oct 2026. |
| A-REG 29 | Art 83(1), (2), (4)(a), (5)(a)–(c) | Faithful | Both tiers follow GDPR's lists: Art 28, 30, 32, 33 and 35 analogues at 2%; Art 5–7, 9, 13 and 44–49 analogues at 4%. |
| A-REG 30–32 | Arts 85, 88, 99 | Simplified | Filler. |
| Annex I | Member States | Faithful | |
| Annex II | Commission adequacy list; Decision 2023/1795 | Changed | The exclusion of sensitive information from Region B's recognition is an invented twist, not a feature of the real Framework. It makes the certificate in case 01 a trap (key `must_not`: `recognition_relied_on`). |

## 3. Region B ↔ HIPAA (45 CFR Parts 160, 164) and US access law

**Health Records Act**

| Mock | Real counterpart | Fidelity | Note |
|---|---|---|---|
| B-HRA 2 | 160.103: *protected health information*, *covered entity* (para (3): provider transmitting health information electronically in a covered transaction), *business associate* | Simplified | "Bills a health insurer electronically" stands in for the covered-transaction test. *Data host* is invented. |
| B-HRA 3 | 160.102; the business-associate definition is "with respect to a covered entity" | Faithful in effect / invented | 3(2) follows from the definition: a host for a non-covered client is not a business associate. 3(3) is invented. |
| B-HRA 4 | 164.502(a), 164.506 (treatment, payment, operations), 164.508 (authorisation) | Simplified | |
| B-HRA 5 | 164.502(e), 164.504(e) incl. (2)(ii)(J) "return or destroy… if feasible" | Simplified | |
| B-HRA 6 | 164.502(b) incl. (b)(2)(i) treatment exception | Faithful | |
| B-HRA 7 | 164.306(a) | Simplified | |
| B-HRA 8 | 164.404(b), 60 calendar days | Faithful | |
| B-HRA 9 | none | Invented | A seven-year retention duty on any host, with a return-and-keep-no-copy escape. It deliberately collides with A-REG 9(2)(f). The real-world pattern exists: SCC Module Two Clause 8.5 provides for "local laws applicable to the data importer that prohibit return or deletion". |
| B-HRA 10 | 164.524(b)(2) (30 days), 164.524(c)(4) (cost-based fee) | Faithful | Filler. Applies only to covered providers. |
| B-HRA 11 | 160.306(a), 160.306(c)(1) (investigate where wilful neglect is indicated) | Faithful | Filler. |
| B-HRA 12 | 160.404 (per-violation and calendar-year caps), 160.410 (affirmative defences) | Simplified | Filler. Tiers collapsed into one; caps use the regulation's printed figures, before inflation adjustment. |
| B-HRA 13 | none checked | Invented | Filler: generic regulation-making power. |

**Records Access Act**

| Mock | Real counterpart | Fidelity | Note |
|---|---|---|---|
| B-RAA 2–3 | CLOUD Act, 18 U.S.C. § 2713 (disclose data in the provider's possession, custody or control, wherever stored; **checked via enrolled-bill copies, not uscode.gov**); FISA s. 702 as assessed in *Schrems II* paras 179–181 | Changed | Deliberately harsher: no court authorisation at all, whereas s. 702 programmes are certified by the FISC (para 179). It reaches providers incorporated in Region B even for data held elsewhere, like § 2713. |
| B-RAA 4 | none mapped | Invented | Indefinite secrecy of orders. |
| B-RAA 5 | Logic of EDPB Recs 01/2020 Use Case 1 | Invented | A provider cannot be made to hand over keys it does not hold. This is what makes A1-HIA 6(1)(b) and exporter-held keys decisive. |
| B-RAA 6 | *Schrems II* para 192 (no effective remedy), para 180 (no guarantees for non-US persons) | Simplified | |

## 4. Subregion A1 Health Information Act ↔ Member State law (Ireland as the model)

| Mock | Real counterpart | Fidelity | Note |
|---|---|---|---|
| A1-HIA 1–3 | Data Protection Act 2018 (designation of the Data Protection Commission under GDPR Art 51) | Simplified | |
| A1-HIA 4 | Data Protection Act 2018 s. 52(1)(c)–(d), 52(2)(a)–(b) (health practitioner, or a person owing an equivalent duty of confidentiality), made under GDPR Art 9(2)(h) | Simplified | 4(2) (an agent acting on instructions counts as "under the responsibility" of the practitioners) is invented. |
| A1-HIA 5 | GDPR Art 9(3) professional secrecy; Irish medical-practice rules | Simplified | 5(3) (an agent is not a third party) is invented. |
| A1-HIA 6 | GDPR Art 9(4) (further conditions on health data) | Invented | 30-day notice to the Commission is invented. 6(1)(b) (keys held only in Region A) puts EDPB Use Case 1 condition 6 (keys retained by the exporter in the EEA or an equivalent jurisdiction) into statute. Case 01 fails it, because the host holds the keys in Region B. |
| A1-HIA 7 | GDPR Art 9(4) | Invented | Genetic-data limits; filler for case 01 (no genetic data). |
| A1-HIA 8 | GDPR Art 35(4); Data Protection Commission DPIA list (15 Nov 2018) | Changed | The listed kinds of processing are invented. 8(a) makes an impact assessment mandatory for case 01 regardless of patient numbers, so A-REG 12's 5,000 threshold is not the deciding rule. |
| A1-HIA 9 | GDPR Art 8(1) (Member State may set an age down to 13) | Changed | Age 14. A trap for case 01: no ground relies on consent. |
| A1-HIA 10 | Health Research Regulations 2018 (S.I. 314/2018) reg 3(1) (ethics approval by a research ethics committee) | Simplified | Filler. The pseudonymisation condition in 10(2) is invented. |
| A1-HIA 11 | none | Invented | Filler: offence. |

## 5. Deliberate departures that carry case 01

Most of what is *changed* or *invented* is there to create a question with a known answer that recall of real law cannot supply:

1. **Annex II excludes sensitive information** → the Trusted Recipient certificate cannot cover health records (trap: relying on A-REG 17).
2. **A1-HIA 6(1)(b) keys rule** with host-held keys → a Subregion condition fails even though Region A's routes might not.
3. **B-HRA 9 retention vs A-REG 9(2)(f) deletion** → a cross-jurisdiction conflict, resolvable by choosing return over deletion.
4. **B-RAA 3–6** → the A-REG 18(2) assessment needs Region B's law, which only the Region B specialist can read (the peer question in the key).
5. **A-REG 19(2) occasional limit** → derogations cannot carry an ongoing hosting arrangement.
6. **A1-HIA 8(a)** → an impact assessment is required at 3,200 patients, which A-REG 12(2)(a) alone would not require.

Filler added on 10 Oct 2026 (A-REG 22–32, B-HRA 10–13, A1-HIA 10–11) is not engaged by case 01. It mirrors the institutional, remedial and enforcement chapters that make up most of the real instruments.

## 6. Limits of the map

- The mapping supports a claim of **structural fidelity**: the corpora pose the same kinds of questions as the real regimes. It is not a claim that results on the fictional corpora carry over to real law.
- Paraphrase lowers, but does not remove, the chance that a model recognises GDPR/HIPAA patterns and brings in real-law knowledge. Section 5's departures are the check: an answer that follows real law instead of the corpus is wrong on those points.
- Secondary-only items: the HHS cloud guidance (hhs.gov blocked automated fetch) and 18 U.S.C. § 2713 (checked from copies of the enacted bill). Check both against the primary page before citing them in the thesis.

## Sources

- GDPR, Regulation (EU) 2016/679: https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng (local copy `../prototype/laws/gdpr.md`)
- Standard contractual clauses, Decision (EU) 2021/914: https://eur-lex.europa.eu/eli/dec_impl/2021/914/oj/eng (local copy `../prototype/laws/eu_scc_2021_914.md`)
- CJEU, C-311/18 *Data Protection Commissioner v Facebook Ireland and Schrems* (16 July 2020): https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:62018CJ0311
- EDPB Recommendations 01/2020 on supplementary measures, v2.0 (18 June 2021): https://www.edpb.europa.eu/system/files/documents/2021-06/edpb_recommendations_202001vo.2.0_supplementarymeasurestransferstools_en.pdf
- EDPB Guidelines 05/2021 on the interplay between Article 3 and Chapter V, v2.0 (14 Feb 2023): https://edpb.europa.eu/system/files/2023-02/edpb_guidelines_05-2021_interplay_between_the_application_of_art3-chapter_v_of_the_gdpr_v2_en_0.pdf
- Commission Implementing Decision (EU) 2023/1795 (EU–US Data Privacy Framework): https://commission.europa.eu/system/files/2023-07/Adequacy%20decision%20EU-US%20Data%20Privacy%20Framework_en.pdf
- HIPAA, 45 CFR Parts 160 and 164 (eCFR, current as of 29 Sep 2026; local copy `../prototype/laws/hipaa.md`)
- HHS OCR, *Guidance on HIPAA & Cloud Computing*: https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html
- CLOUD Act, 18 U.S.C. § 2713 (enrolled H.R. 1625, DOJ copy): https://www.justice.gov/d9/pages/attachments/2019/04/09/cloud_act.pdf
- Ireland: Data Protection Act 2018 (local copy `../prototype/laws/ie_data_protection_act_2018.md`); Health Research Regulations 2018, S.I. 314/2018 (`../prototype/laws/ie_health_research_regulations.md`); Data Protection Commission DPIA list, 15 Nov 2018 (`../prototype/laws/ie_dpc_dpia_list_2018.md`)
