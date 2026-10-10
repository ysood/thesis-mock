# v17 pipeline pseudocode

`[Python]` executes and checks integrity. `[LLM]` owns interpretation and legal judgment.
The runtime is stateful through one `case_record`; model calls receive current JSON views,
not conversation transcripts. See [architecture.md](architecture.md) for writer ownership.

```text
1. Validate the single input and create one read-only snapshot             [Python]
   Accept organisations → transfer → evidence only.
   transfer.sender and transfer.recipient are organisation IDs, not copied objects.
   Validate IDs, organisation/evidence scope, country codes and vocabulary.
   Standardize country codes; retain omitted fields and supplied unknowns.
   Preserve identifiability (identified/coded/anonymous/unknown) without mapping
     to GDPR/HIPAA legal labels. Agents assess those classifications.
   Preserve locations.stored_in and locations.accessed_from separately.
   Read evidence directly: id/kind/title/between/summary, optional attested_by,
     dated and valid_until. Never generate an attester or convert to attestations.
   Collect country metadata from sender/recipient IDs, people.where and both
     location lists; add it under reference_facts without replacing input fields.
   Store these in case_record.input, alongside empty supervisor/specialists/checks
     sections. No second normalized request or submitted snapshot.
   Show this same input document in every prompt and use it for fact checks.
     References use /organisations/0/country, /transfer/data/categories/0,
       /transfer/locations/accessed_from/0 or /evidence/0/summary.
     During supervisor review this document is CASE RECORD.input; pointers
       omit the input prefix. Resolve sender/recipient by ID, not array order.
   Label nonempty scalar input passages with stable f_ IDs bound to their
     escaped pointer, source offsets and exact text; keep sentences whole.
     Include country reference facts, numbers, booleans and explicit unknowns.
     Omitted/null/empty fields do not become selectable evidence.
     Show the same FACT PASSAGES with the original JSON to every agent.
   Open the local legal index. Do not refresh source law texts.
   Build a provision-only graph from stored legal text and curated citation,
     amendment and definition links. No requirement/route/condition nodes.
   The fixed checklist supplies starting provision IDs outside the graph.
   Keep provision headings; pack paragraphs/numbered clauses into chunks.
     Split oversized units by sentences, then words, then characters.
     Keep the parent provision ID/title and a unique chunk ID; count heading,
       body and special tokens against MiniLM's 256-token embedding limit.
     Rebuild embeddings if the chunk version/content fingerprint changed
       or the stored count is incomplete; otherwise reuse the index.
     Record the fingerprint only after all chunks have been indexed.

2. Interpret case and assign initial reviews, one supervisor call          [LLM]
   Identify requester claims, contradictions and instructions.
   Propose scoped roles, data classifications and activity scope.
   Select supplied fact_ids and cite legal sources for those proposals.
   Intake claims/contradictions, classifications, exclusions and plan facts
     select IDs; Python copies their exact pointer and text before checks.
   Assign GDPR/HIPAA plans, or provide a sourced exclusion.
   Apply ROUTING RUBRICS (reference/applicability/; HIPAA now): a routed plan
     cites engaging facts; an exclusion cites facts and states the rubric's
     assumption. Python checks plan fact quotes and adds a non-blocking
     routing warning when a rubric regime is routed without facts.  [Python]
   Plans contain applicability and review focus, not national questions.
   Preserve GDPR's independent ownership of national-law research.
   These proposals are not requester facts and may be challenged.
   Initial sources: checklist starting provisions for applicability and GDPR
     roles, their supporting context, and routing-rubric sources.

3. Validate references and execute the initial plans                       [Python]
   Check intake quotes and classification references.
   Read each assigned checklist item's starting provisions, including known
     amendments and curated definition dependencies.
   Run independent GDPR/HIPAA reviews in parallel, at most two workers.
   No separate supervisor scheduling call for each assignment.

4. Assess assigned checklist, one finding per question                     [LLM]
   Compose the shared source/authority/decision/research instructions,
     existing policy blocks and current fact-reference/output rules.              [Python]
     Add GDPR delegation guidance only for GDPR, national-role guidance
       only for child specialists, and revision guidance only for reviews.
   At every ask() boundary, for OpenAI calls adapt the existing output
     schema to strict API JSON Schema: require every object field,
     forbid extra keys, remove defaults, retain existing nullable unions.
     Inline references that carry descriptions or other sibling fields,
     preserving those instructions; leave plain references intact.
     Restrict fact_id to this call's actual input passage IDs.
     Restrict quote_id to displayed legal passages, with one shared enum for
       findings/routes. Findings may leave it empty where policy permits;
       routes must select a passage. Refresh choices before each model
       invocation as read_provision displays additional passages. Do not
       offer unread pages or search/KG suggestions. Keep citation checks.
     Send this schema as the API response format, not a prompt attachment.
     Other providers retain the prompt JSON schema.                      [Python]
     Strict output returns all fields, with empty lists/strings when unused
       and null only for nullable fields. Keep Python/Pydantic validation.
     Record output_format, response_schema, fact_choices and initial quote_choices
       in request events.
   Label source text with stable v2 passage IDs, without a word cap.      [Python]
     Preserve blank-line paragraphs and numbered blocks; keep subordinate
       list text and colon-led numbered lists with their introduction.
     Keep ambiguous/unmarked structure intact rather than cut sentences.
     Apply only to quotation passages; embedding windows stay unchanged.
     Bind IDs to provision, offsets and content; keep full initial source text.
   Specialist receives immutable input, provisional interpretation,
     review focus, starting sources and fixed checklist. No KG guidance block.
   Derive routes, prerequisites, scope and exceptions from legal text.     [LLM]
   In this same call, screen the relevant alternatives/exceptions before
     choosing a conclusion. Record route_coverage with specific grouped
     exclusions or remaining limits; a single duty/applicability exclusion
     may explain this without a separate routes list.
   For materially plausible alternatives, record compact routes:
     scoped name, supported/ruled_out/unresolved/not_investigated,
     assessment or deferral reason,
     citations and a shown quote_id. No authored legal-route catalogue.
   Distinguish assessed exclusion from not choosing an alternative.
     not_investigated records an optional fallback recognised in read law whose
     feasibility was not assessed: name the supported route that suffices for
     the same actor/activity and explain why the fallback cannot change the answer.
     Do not claim that an uninvestigated fallback works or fails.
     Assess mandatory prerequisites, safeguards, restrictions and exceptions
     separately; these cannot be deferred because another route works.
   A failed alternative/national branch does not close unresolved alternatives.
     A supported alternative still needs prerequisites and cumulative duties.
     Separate actors/activities; include route gaps in the finding's existing
     missing_information/missing_law/research_stopping_reason fields.
   Specialist decides applicability, exceptions, evidence sufficiency,
     (v10 temporary evidence-presence policy: evidence addressing a requirement
     establishes it; omitted elements become confirmations),
     status, reasons, input fact_ids, evidence IDs, supporting citations
     and one quote_id selected from a shown passage in a cited provision.
   Distinguish transfer/activity/advisory scope and non-decisive confirmations.
   Evaluate plausible routes against combined facts; an undeclared legal basis
     is not itself a missing predicate. Identify the actual gap.
   Declare missing_law where relevant; if research cannot help, provide a
     research_stopping_reason identifying the fact gap or research limit.
   Python never anchors legal predicates or recomputes these statuses.
   Closed-world corpus policy (prompt rule 11): starting passages are a selection,
     not the whole stored corpus. Before dismissing a relevant dependency, reuse
     relevant read law, retrieve it, or explain from read law/facts why it does
     not apply. GDPR delegates relevant national checks; a supported GDPR route
     does not itself exclude cumulative national safeguards. Explain the checked
     sources or exclusion in reasoning/national_law_reason. Search hits and KG
     links alone are not read law; unavailable corpus/budget is a limit, not absence.
     After a focused check finds no restriction, treat it as absent and report a
     confirmation. Stop at the resolved dependency; no exhaustive KG traversal or
     repeated proof of absence. Enabling rules still need a stated source.
   National-law questions come only from GDPR's own requests; Python does
     not insert companion questions for particular additional openings.
   Assessment as described (prompt rule 12): stated facts and listed
     arrangements are complete; a requirement whose routes all fail on them
     is not_satisfied as described, with the cure in required_actions.
   v11 traversal tools (TRAVERSAL_TOOLS=1, default): within this same call the
     specialist may call kg_node / search_law / read_provision, at most
     MAX_TOOL_CALLS (8) times; every call is answered and logged as a tool_call
     event, and once the budget is spent the model must answer without tools.
     Starting provisions provide initial reading. Provisions read through tools
     join this agent's citable sources and later revisions.          [LLM+Python]
     search_law returns IDs, titles and scores without graph expansion.
     read_provision(provision_id, start=0) returns labelled complete passages,
       targeting 6,000 source-text characters per page; an oversized passage
       is shown whole. Register only shown IDs. next_start continues across
       all resolved provision chunks using the same provision_id. Each page
       uses one existing tool call; a remaining tail stays explicitly truncated.
     read_provision adds at most 12 one-hop graph suggestions, with IDs,
       types, relation directions and labels capped at 120 characters.
       Includes outgoing/incoming citation, amendment and definition links
       between provisions only; no linked text or citable IDs are added.
     kg_node exposes incoming/outgoing edges, including omitted suggestions.
     v19: GDPR nodes list national_provisions (citing Member State law);
     the national child starts from kg_node on the referring GDPR provision.
     Specialist chooses which links to inspect, sources to read and national
       questions to request. This supports discovery, without ensuring coverage.
     Keep the strict response format bound during tool rounds and the final
       reply after the tool budget is exhausted. No extra final-output phase.
     Reject API refusal/incomplete replies as execution failures without
       treating them as malformed legal answers or retrying for formatting.
     Parse completed strict replies as a single JSON object; retain the existing
       bounded validation retry. OpenAI errors never silently fall back to prompt JSON.

   After each specialist reply, resolve finding and route quote_ids against that call
     source pack and tool-read passages and its selected citations.         [Python]
     Copy exact source text into the saved quote; an invalid selection is
       a reference defect, never replaced by model-generated text.
   Resolve selected fact_ids against the shown immutable input passages.
     Copy the exact scalar pointer and text together into saved facts. Ignore
     model-generated pointer/text; an unknown ID stays an invalid reference.
     Do this for initial, retrieved-law, national and targeted assessments.

   If additional law is needed:
     specialist requests up to three specific source queries              [LLM]
     prepare_request normalizes and validates each typed request against
       current question IDs and the specialist's legal corpus             [Python]
     retrieve by exact provision ID and/or vector query within its regime [Python]
     select at most ten base provisions, then include their known
       amendments and curated definition dependencies                    [Python]
     log added/already-available IDs; reassess only when new text arrived
     record executed requests by question, including searches with no hits;
       retain this history across targeted revisions and child revisits
     one targeted reassessment of affected questions with extra sources    [LLM]
     no unlimited retrieval loop; missing law remains unresolved

   GDPR national-law branch, only when requested:
     GDPR names country, specific question, served checklist item and
       referring GDPR provisions; no condition-node opening ID            [LLM]
     prepare_request validates country, parent, nonempty GDPR sources
       and any revisit ID; a revisit cannot change the question's scope   [Python]
     assign stable delegated question IDs                                 [Python]
     retrieve local law via vector search and reverse provision citations  [Python]
     No predefined condition-to-national-implementation mapping is loaded.
     include the exact GDPR provisions named in the delegated question
       as parent context; add curated definition dependencies after
       selecting the capped base source pack                              [Python]
     local specialist answers delegated questions with reasons             [LLM]
     GDPR reassesses only affected checklist questions                     [LLM]
     child answers never automatically establish a GDPR status
     at most two child reviews per country; absent corpus is explicit
     new requests after reassessment remain pending without predicted IDs;
       revising that parent refreshes its pending request list

5. Build current review view                                              [Python]
   Check one answer per assigned question and assigned IDs.
   Check fact quotes, evidence IDs, legal citations, exact legal quotes
     and references to delegated question IDs. For new quote IDs also check
     that the saved quote still exactly matches its bound source passage.
   For fact_ids, recheck the bound exact pointer/text pair against this input
     snapshot. Reject changed text/pointers and stale IDs whose source changed.
   Require a nonempty route_coverage explanation and validate each route's
     citations/selected quote against shown law, including not_investigated
     fallbacks. Preserve each route's assessment/deferral status.
     Include route-only citations
     in review sources, targeted revisions and national-child source handoff.
     These structural checks do not prove that all legal alternatives were found.
   Keep legacy saved text quotes readable under their existing exact checker.
   Preserve specialist status even when a reference fails.
   Put defects under checks; do not promote unknowns or change legal findings.
   Surface research_warnings for unresolved findings declaring missing law
     (including required national review or structured law gaps) without
     corresponding research or a stopping reason. Pending requests are not
     executed searches. A GDPR national dependency needs national research,
     not just a search within GDPR. Warnings do not force calls or statuses.
   Give supervisor compact current findings, cited legal texts (including routes),
     and assigned checklist starting law with supporting context. An omitted
     route produces no citation; starting law lets the supervisor detect it.
   Include compact child research history and pending requests alongside
     flattened child findings, without repeating whole child source packs.
   List each available target's assignable question IDs and map delegated
     child question IDs to their parent GDPR requirement.
   Include checks.requirement_policy for every assigned checklist question:
     class and class_reason from the same catalogue used by decision checks.
     Keep this metadata present even when a target's review budget is exhausted.

6. Review and reconcile, normally second supervisor call                  [LLM]
   Confirm or challenge each status against facts, evidence scope and law.
   Compare route_coverage/routes with source clauses: check omitted alternatives,
     exceptions, scoped prerequisites and cumulative duties. Do not accept a
     completeness claim on trust. Accept justified optional deferrals without
     requiring investigation of every fallback. Challenge omissions that could
     change the conclusion: identify the finding and specific branch/duty,
     why current reasoning does not settle it, and what focused check would.
     Record unresolved decisive coverage limits with the existing review fields.
   Under the v10 evidence-presence policy, omitted evidence elements are
     conditions, not unresolved issues or reasons to delegate.
   Review research warnings, search results and stopping explanations. Request
     useful follow-up, or explain why missing facts/corpus/budget prevent it.
   Also review absence claims in satisfied findings with national review declared
     not_required, even without a research warning. Require relevant law reviewed
     or a source/fact-supported exclusion; otherwise ask GDPR for a focused check.
     Once resolved, do not repeat research solely to prove a negative.
   Check that intake claims mean what their quoted passages support; exact
     text matching does not establish semantic support.
   Compare requirements concerning the same actor/activity/data/time.
   Read catalogue class separately from obligation_scope: transfer scope alone
     does not make an advisory requirement a blocking gate. Report ongoing duties.
   May update its own provisional interpretation with sources.
   Validate an optional interpretation update independently of its action:
     reject an invalid update, keep prior interpretation and record defects;
     a valid needs_review finish or delegation may still proceed.
   Those defects block other final decisions until a valid update clears them.
   May also correct/withdraw its own intake claims with a complete replacement
     during the same review response; preserve supported claims and input.
   Supervisor review also receives FACT PASSAGES; replacements select IDs.
     Python binds selections before validating the optional update.
   Python validates the replacement against the immutable fact document:
     accept valid corrections and recompute setup defects, or retain the prior
     intake and record the exact rejected references. Validate the requested
     finish/delegation independently, as with interpretation updates.
   If a withdrawn claim materially affected a specialist, request reassessment.
   May repair its existing exclusions with a complete replacement in this same
     response. Validate fact/legal references and exactly the existing regime list;
     never add/remove/duplicate exclusions or change routed plans.       [Python]
     Accept and recompute setup defects, or keep prior exclusions and log defects.
     Check finish/delegation independently. Valid correction clears prior repair
     defects; unresolved defects block favourable completion, while needs_review
     or an independently established gate refusal can still finish.
   May request a targeted revision for a concrete issue or additional law.
   Cannot rewrite specialist findings; responsible specialist must revise.

   Targeted revision:
     check budget; prepare_request validates target, assigned question IDs,
       current finding IDs and regime-specific provision IDs              [Python]
     normalize brackets/case and unambiguous short IDs consistently across
       all request types; reject unknown, ambiguous or mismatched IDs
     log each validated/rejected request; valid siblings may still execute
     for child issues, assign the parent GDPR requirement and ask GDPR
       to revisit its child; never assign a child ID as a main checklist ID
     specialist revises only assigned questions                            [LLM]
     give only affected questions' pinned law, previously cited law and
       explicitly requested additional sources                            [Python]
     replace those answers; keep unaffected answers and IDs                [Python]
     a failed/incomplete patch keeps previous answers with a visible defect
     return to supervisor review; no status calculator in between

7. Finish explicitly                                                     [LLM]
   Supervisor accepts every current finding ID exactly once.
   Returns reconciliation, overall decision and reasons.
   Refusal requires a verified unmet main transfer gate or an explicit
     incompatibility between conclusive, verified main transfer findings. A failed national
     branch alone is insufficient. Python rejects unsupported refusal proposals.
   A rejection identifies unmet non-gate requirement keys/classes from the
     catalogue and asks for a corrected decision or a supported refusal ground.
   Explain significance of any unresolved/activity-level matter.
   Missing decisive facts/law cannot be presented as mere confirmations.

8. Assemble report and full case_record                                   [Python]
   Check acceptance/conflict references and report integrity.
   Reject a favourable decision contradicting an accepted unresolved or
     unmet transfer gate (status consistency, not legal inference).
   Decision rules (v12, status consistency): a verified, not_satisfied,
     transfer-scope gate from GDPR/HIPAA in a regime whose applicability is
     met makes the decision do_not_proceed, whatever else is open; otherwise
     defects give needs_review; proceed with conditions or outstanding
     evidence becomes proceed_subject_to_conditions. The supervisor's
     proposal is kept as proposed_decision.
   Render each requirement directly from its specialist's status.
   Retain route coverage and exact route quotes in findings and the case record;
     show the compact route record alongside the finding in the UI.
   Render evidence support only from explicitly cited evidence IDs.
   Outstanding evidence is not closed by document type or graph node.
   Broken references/coverage or unfinished supervision hold the report
     as needs_review, preserving specialist statuses and supervisor proposal.
   Save full trace separately; superseded answers are not active context.
   Include research warnings separately from reference/coverage defects.
   v21 reviewer brief (app/brief.py): regroup the same records and checked
     findings as known (cited fact passages and the requirements using them),
     required (status, class, scope, blocking, citations, verified), missing
     (fact/evidence/law/confirm/review gaps, blocking first) and routes
     (specialist routes with required_actions and failing facts). Blocking =
     transfer-scope gate that is unmet/undetermined. Copies fields only; no
     new status, gap or route is inferred. UI shows it as the first tab.
   Evidence templates use the same id/kind/title/between/summary shape,
     with an empty attested_by for the requester to fill when known.
   Legacy input schemas are rejected without conversion.
```

Budgets: four supervisor review calls after the initial plan; two supervisor-assigned
reviews per main specialist (initial plus one follow-up); one extra retrieval round per
assessment; two child reviews per country. These are execution limits, not legal rules.
The usual path is two supervisor calls and one assessment per assigned main specialist.
National questions or targeted retrieval/revisions add calls only when requested.
The shared request function runs behind the existing JSON response protocol. It adds no
model call and does not use a provider-native tool-calling API. Lookup stays within the
stored corpus; it cannot browse for missing law or turn source availability into a status.

No paid runs are required for verification. Offline tests block model/provider calls and
stub embedding/vector retrieval; the CLI and UI use the same scoped fake-model fixture.
