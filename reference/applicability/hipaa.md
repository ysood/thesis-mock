# HIPAA routing rubric

Purpose: decide whether to route the case to the HIPAA specialist. This does not decide HIPAA
statuses; if HIPAA is routed, the specialist still owns hipaa.applicability.

## Source law

- [45 CFR 160.102] (a): the rules apply to "(1) A health plan. (2) A health care clearinghouse.
  (3) A health care provider who transmits any health information in electronic form in connection
  with a transaction covered by this subchapter." (b): they apply to a business associate "where provided".
- [45 CFR 160.103 [Covered entity]]: the same three categories.
- [45 CFR 160.103 [Transaction]]: transmissions "to carry out financial or administrative activities
  related to health care", e.g. claims, payment and remittance, eligibility, enrolment, premium payments.
- [45 CFR 160.103 [Business associate]]: a person acting "on behalf of such covered entity", or a
  subcontractor of a business associate.
- [45 CFR 160.103 [Health plan]]: health insurance issuers are those "licensed to engage in the
  business of insurance in a State".

So HIPAA attaches to who an organisation is and what transactions it conducts, not to geography.
Location is only a screening signal.

## Route HIPAA when a supplied fact shows any of these (give the facts in hipaa_plan.facts)

1. A party is a health plan or health care clearinghouse (kind, description or evidence).
2. A party is a health care provider and a fact says it bills, claims from, checks eligibility with,
   or is paid by a health plan electronically (e.g. a US insurer, Medicare, Medicaid).
3. A party acts on behalf of, or is a subcontractor in a chain serving, a health plan,
   clearinghouse or provider meeting point 2.
4. A party is a US health care organisation, or the data concerns a US provider's or plan's
   patients or members. These are strong signals of points 1-3, so route and let the specialist test them.

US storage, US access or a US vendor on their own are NOT enough. A US cloud host for a non-covered
provider is not a business associate. These facts should prompt a check of points 1-3, not route by default.

## Exclude HIPAA when none of points 1-4 is shown

IMPLEMENTATION POLICY (not source law): if no supplied fact shows points 1-4, record a HIPAA
exclusion. Cite the facts relied on (party countries, kinds, descriptions) and state the assumption:
"No supplied fact indicates that any party is a health plan or clearinghouse, conducts HIPAA
transactions with a health plan, or acts for such an entity." The exclusion is reported as an
assumption the requester can rebut with a new fact. It is not a missing fact that blocks the decision.

Do not keep HIPAA in on the reasoning that "the absence of a US entity cannot decide the issue".
Under this policy, that absence is the decision, and it is disclosed.

## Borderline cases: route, with an applicability-first instruction

- A non-US provider treating a US-insured patient and billing that insurer (point 2 may hold).
- A non-US processor whose description mentions US clients or US health plans (point 3 may hold).
- A party's description is ambiguous about insurance billing or payer relationships.
