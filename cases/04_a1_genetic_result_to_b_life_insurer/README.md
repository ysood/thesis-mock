# Case 04: genetic test result to a life insurer

Research notes and a draft expected analysis (11 Oct 2026). Only `case.json` is model input; this file
and `key.json` are not sent to the model.

An A1 clinical genetics service sends one adult's existing diagnostic genetic test report to a
Region B life insurer, at the patient's written request, for an insurance application. The clinic
relies on explicit, written, informed consent for both the disclosure and the transfer. The insurer
holds an active Trusted Recipient Scheme certificate.

## Expected result

**Do not proceed.** No change to the arrangements cures it: the obstacle is the purpose (insurance)
combined with the kind of information (genetic).

## The conditionals this case tests

1. **Consent that is valid but cannot be relied on.** A-REG 8(2)(a) allows explicit consent "except
   where Subregion law provides that the prohibition may not be lifted by consent". A1-HIA 7 provides
   exactly that for genetic information processed for insurance or employment purposes, and A-REG 21(3)
   applies A1 law to a custodian established in A1. No other Art 8(2) point fits underwriting.
2. **The same consent works elsewhere.** A-REG 6(1)(a) (with Art 7) and A1-HIA 5(2) professional secrecy
   both accept the consent. A1-HIA 7 does not touch them. A system that turns A1-HIA 7 into a blanket
   "consent is void" is over-reading it.
3. **A route closed for one kind of information.** A1-HIA 7 also excludes the Art 19(1)(a) consent
   derogation for genetic information, so "occasional + informed consent" is not enough. 19(1)(b) needs
   a contract between the person and the custodian that the transfer is needed to perform; the clinic's
   old testing contract is not one.
4. **A certificate that does not help.** Annex II limits the Region B recognition to certified
   recipients AND to information that is not sensitive. Genetic information is sensitive (Art 4(4)).
5. **Category boundaries in Region B.** A "covered provider" is a health care provider billing a Region B
   health insurer, or a health insurer licensed in Region B (B-HRA 2). A life insurer holding no health
   licence is neither, so B-HRA 4-8 do not apply. It keeps the report for itself, so it is not a data
   host and B-HRA 9 does not apply either.
6. **Impact assessment.** One person is below Art 12(2)(a). A1-HIA 8(b) lists "matching of health
   information with information held by an insurer"; the clinic only discloses, and the insurer is outside
   Region A's scope (Art 3(2): it does not offer services in Region A). But the clinic sends the report
   precisely so it is matched with the insurer's file, and the text does not say who must do the matching.
   The key accepts unmet or not_applicable (revised after all four first runs read 8(b) as engaged).

## Evaluation notes

Draft key, to be signed off by the author. The scorer matches by cited provisions; review reasons too.
`must_cite: A1-HIA 7` on the Art 8 item means the finding must rest on the A1 restriction, not on a
made-up reason.
