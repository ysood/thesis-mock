# Case 05: genetic report sent abroad for a second opinion

Research notes and a draft expected analysis (11 Oct 2026). Only `case.json` is model input; this file
and `key.json` are not sent to the model.

An A1 clinical genetics service sends one adult patient's genetic test report, ECG summary and referral
letter to a private specialist in Region B for a second opinion. The purpose is health care. The clinic
relies on health care (A1-HIA 4) for the processing, and on the patient's explicit, informed consent for
the transfer (Art 19(1)(a)). The transfer is one-off.

## Expected result

**Do not proceed as described.** The transfer route the clinic chose is decisively excluded:
A1-HIA 7 says genetic information "may not be made the subject of an outward transfer on the basis of
Article 19(1)(a)". Approved clauses are a potential route forward (`available` in the output schema):
execute them, assess recipient-applicable law and practice under Art 18(2), and adopt effective
supplementary measures where necessary. Art 18(3) excludes that route if necessary effective measures
cannot be adopted. This does not establish that every other obligation is already met.

## Why this case tests graph support

The corpora are fixed (changing them would invalidate the generated graph), so this uses the
cross-corpus rule with the weakest textual pointer:

- Art 19(1)(a) itself says nothing about Subregion law, and Art 21(2)'s list of openings omits it.
  The restriction rests on the general Art 8(3) power ("further conditions, including limitations,
  with regard to the processing of ... genetic information"), and A1-HIA 7 does not say so.
- Runtime citation graph: `kg_node`/`read_provision` on A-REG 19 lists A1-HIA 7 under
  `lower_level_provisions` (ID and title only). Region A cannot read it; it must delegate.
- Generated graph: reading A-REG 19 shows "A1-HIA 7 restricts_route: makes the 19(1)(a) consent route
  unavailable, when the transfer concerns genetic information".
- Misreading risk: A1-HIA 7 has two limbs and only the second (consent cannot lift Art 8(1)) is limited
  to insurance or employment. A delegate that reads the whole section as insurance-only reports it as
  not engaged, and the consent derogation looks perfect: explicit, informed, one-off.

Honest limit: the runtime system can still reach A1-HIA 7 through delegation (Art 8(3), A1-HIA 4), and
A1 delegates file every engaged obligation of their own law. This case measures whether the restriction
is applied to the right route reliably, not whether it can be found at all.

## Other checks

- Art 8: 8(2)(c) health care with A1-HIA 4; 8(2)(a) consent also works (not insurance/employment). The
  trap `genetic_consent_bar_overextended` catches ruling out 8(2)(a) with s.7's second limb.
- A1-HIA 5(2): disclosure with the patient's consent is permitted.
- Region B: Harrow bills no insurer and is not one (not a covered provider); keeps records for its own
  care (not a data host); not a computing provider (B-RAA not engaged). Recognition: no certificate, and
  Annex II excludes sensitive information anyway.
- A1-HIA 8: neither listed impact-assessment trigger is present. The general high-risk test in
  A-REG 12(1) still needs its own reasoning; one patient only rules out the numerical threshold.
- A1-HIA 6: the default interpretation is that the purpose is independent clinical care, with
  incidental retention, rather than a hosting/storage transfer. Section 6 has a purpose limit but
  no express agent requirement. Harrow's independent-custodian role alone does not exclude it;
  a broader reading of the storage wording must be considered on its merits.

## Key review (11 Oct 2026, after exploratory runs)

The combined `impact_assessment` automated check has been replaced by
`a1_listed_impact_assessment`, covering only A1-HIA 8. The old check could pass on an A1 list finding
marked `not_applicable` while the same answer left A-REG 12(1) `undetermined` or marked it `unmet`.
These are different questions. The general high-risk test is now in `manual_checks`: the source
supplies no objective threshold for it, so a citation/status match cannot determine whether the
reasoning is sound. `undetermined` is a defensible cautious conclusion; other conclusions need
reasoning that actually addresses Art 12(1).

There are still 16 automated checks, covering selected issues, plus manual review of risk,
section 6 purpose, the conditional cure, remaining compliance and reasoning consistency. A perfect
automated score is not full source-checked correctness. Missing notices, security/record details,
minimisation and Harrow's own Region A responsibilities also prevent a claim that everything else
is established. The execution failure that produced no accepted answer remains a failure; passing
the absence-based trap checks does not turn it into a substantive assessment.

Region B planning engagement is no longer required by the key: multi planning may consult a
specialist to establish that the law does not apply, whereas single mode reports applicability
directly. The scope conclusion is reviewed separately. This prevents a correct single-agent
non-applicability conclusion failing an architecture-dependent planning check.

The original key is preserved at `analysis/case_05/key_before_review_20261011.json`. This is a
post-run correction; report the reviewed key version and keep exploratory results distinct from
a future frozen evaluation. No case facts, laws, graph, engine or historical model results changed.

Draft key, to be signed off by the author.
