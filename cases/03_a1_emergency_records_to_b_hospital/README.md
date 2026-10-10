# Case 03: emergency treatment handoff

Research notes and a draft expected analysis. Only `case.json` is model input; this file and
`key.json` are not sent to either architecture.

An A1 practice sends a small, clinically selected packet to a hospital in B treating one
unconscious adult. The packet includes a relevant genetic diagnostic report. The hospital
needs it immediately to prevent a serious and imminent threat to life. It treats the patient
independently and keeps the packet in its own clinical record. There is no cloud-hosting
service, processing-service agreement, consent or executed transfer-clause agreement.

## Expected result

**Proceed as described**, on the supplied facts. Three separate Region A questions have
answers: A-REG 6(1)(d) provides the processing ground; A-REG 8(2)(b) permits sensitive
processing while the patient cannot consent; A-REG 16 with 19(1)(c) permits the outward
transfer. A-REG 8(2)(c), supported by A1-HIA 4 and 5, is another possible sensitive-processing
condition. A receiving-country permission alone is insufficient to establish these answers.

## Cross-references and reconciliation

1. **Secrecy and the emergency:** A1-HIA 5(2) permits a registered practitioner to disclose
   to a third party where necessary to prevent a serious and imminent threat to life. The
   hospital is another treating organisation, so the agent exception in 5(3) is unnecessary.
2. **Genetic information and the correct route:** A1-HIA 7 excludes the consent transfer
   route under A-REG 19(1)(a) for genetic information. It does not exclude 19(1)(c).
   Its separate sensitive-processing restriction concerns insurance or employment, neither
   of which is the proposed purpose. Article 19(2)'s recurring-transfer restriction concerns
   points (a) and (b), rather than every derogation.
3. **Treatment and hosting have different boundaries:** A1-HIA 6 concerns outward transfers
   for hosting or storage. Keeping an independently treating hospital's clinical record does
   not make this a hosting service. B-HRA 2/3 likewise distinguishes covered providers,
   service agents and data hosts. The hospital's electronic insurer billing engages the
   provider rules, while the absence of storage on another person's behalf leaves the
   data-host retention rule outside scope.

The requirements are compatible. The packet is already limited to necessary material,
satisfying A-REG 5 and the hospital's B-HRA 6 obligation. B-HRA 4 permits treatment use
without written authorisation, but does not waive the exporter's minimisation or transfer
requirements. Section 6's treatment-disclosure exception must not be expanded into an
exception for all internal uses. Both organisations' safeguards and processing records are
supplied. A publication record settles A-REG 32's temporal application.

## Evaluation notes

The key is draft research ground truth, requiring author review before reported evaluation.
It does not require additional agents, a fixed conversation path, a conflict record or peer
questions. A single agent can correctly reason through the same corpus. Review reasons and
source scope as well as the decision; the existing citation-based scorer is an aid rather
than a semantic verifier. No live model run was performed during case authoring.
