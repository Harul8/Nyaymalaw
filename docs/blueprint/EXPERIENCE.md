# NM experience and live-validation guide

Status: proposed experience contracts and implementation instructions. No screen, feature, security property or rehearsal is marked built or passed by this document. The module plan owns build order; current backlog evidence owns completion. Use this guide alongside the data architecture, legal-brain and security guides.

## 1. What the user should experience

An advocate opens a matter and NM understands the instruction, the file and the work already done. It can explain what it knows, how it knows it, what remains unsettled and what needs to happen next. The advocate can correct it without restarting the case, inspect the source behind a material proposition, take a reasoned decision and leave knowing what was saved and what remains live.

The product is an advocate's working environment, not an unrestricted direct-to-litigant service, a generic chat history, a legal search box with confident prose, or an autonomous filing agent. Client input can be collected through an explicitly authorised channel; the responsible advocate retains the professional relationship and consequential decisions.

The experience has three recurring modes:

- **Take the brief:** listen, retrieve relevant held material, reflect understanding, identify gaps, ask purposeful questions and accept correction.
- **Work the file:** examine evidence, law, thresholds, adverse material, competing routes and practical constraints.
- **Advise:** take a supported position, explain alternatives and uncertainty, prepare work products and seek the necessary decisions or authority.

These are not three irreversible stages. An opponent's new affidavit can reopen the brief; a research result can change the case theory; a hearing order can change the commission and next action. Preserve continuity when the advocate changes mode.

### Autonomous preparation, visible control

Within the recorded commission NM should decide what useful work comes next: read the file, retrieve, test a contrary account, ask a material question, request bounded specialist help, revise or stop. The advocate sets the objective and boundaries; they do not have to click through every search or internal phase. Show a concise plan and material changes to it, sources examined, meaningful limitations, current work and stop reason—not a stream of agent messages or private internal deliberation. Optional research and draft/document specialists remain invisible implementation details unless explaining their separate result materially helps the user.

The work controls are **Pause**, **Stop**, **Narrow the task**, **Correct the file**, and an explicitly budgeted **Continue**. A changed objective is a new mandate version, not a silent expansion. Show actual saved/progress/partial/waiting/failed/stale state; report a specialist failure as incomplete work rather than “nothing adverse found.” Stop prevents new dispatch and late release; disclose in-flight cost that cannot be undone. Sign-out clears protected output and stops session-bound work; separately authorised durable service work follows its recorded mandate and never implies continued recording or unrestricted monitoring.

The first autonomous rehearsal is one synthetic evolving matter: request a supported draft; let NM discover a contradictory source, retrieve the referenced material, change its approach, ask only the unanswered material question, then correct a fact while a specialist is running. Observe the old result being rejected and only the affected work reopened. Open each material claim's original locator in the final draft and its Word/PDF versions. The test judges sound adaptation, grounded results and boundary enforcement, not one hardcoded sequence of agent calls. BK-91/BK-92 and [autonomy.json](autonomy.json) own these future obligations; this description is not a claim that the interface exists.

## 2. Design principles with observable behaviour

| Principle | What the advocate can observe | What must fail validation |
|---|---|---|
| Matter before message | The objective, client side, live proceeding and next obligation remain visible | The answer forgets the matter when the advocate asks a short follow-up |
| Purposeful interaction | NM explains why a necessary question matters and accepts “unknown”, “not available” or “later” | Repeatedly asks a resolved question, or forces invented answers to continue |
| Traceable professional judgment | Material conclusions open supporting/adverse sources and limitations | A plausible citation cannot be opened at its claimed version/location |
| Calm, not complacent | Important urgency, uncertainty and changed assumptions are prominent without a flood of warnings | A critical warning is collapsed, colour-only or lost in a transient toast |
| User control | The advocate can correct, pause, narrow scope, stop work and distinguish proposed from performed actions | One click approves an unspecified future document or recipient |
| Truthful progress | Saved, reviewing, partly read, awaiting decision, unavailable and failed are distinguishable | “Done” means only the request was queued or the model stopped producing text |
| Proportionate depth | A short, direct answer is available, with the reasoning record and sources one action away | Every exchange becomes a seven-section report, or concise mode suppresses material risk |
| Professional candour | NM surfaces inconvenient facts, weak evidence and viable alternatives | It becomes more certain merely because the advocate insists |
| Confidentiality by default | Matter content appears only after authorised access; external alerts are generic | Browser back, another workspace or a diagnostic panel reveals private content |
| Accessible independence | Core work can be completed by keyboard, screen reader, zoom and text; voice is optional | Dragging, colour, hearing, a precise pointer or microphone permission is required |

Trust is earned by accurate useful work, corrections handled honestly and reliable follow-through. Do not manufacture it with a numerical “case strength” gauge or a confident persona. Where probability estimates are appropriate, explain the model, reference population and uncertainty; otherwise use reasoned qualitative assessment.

## 3. Information architecture and layout

### Global navigation

Use four top-level destinations: **My work**, **Matters**, **Research**, **Practice settings**. Identity and active workspace remain visible in the header. The prototype's current HTML/JavaScript can evolve incrementally: split state management and reusable components, add types and route contracts, preserve served-path tests. A framework rewrite is a separate decision, not a prerequisite for good design.

“My work” shows obligations and matters needing attention; “Matters” shows all authorised matters with honest loading/incomplete states; “Research” holds exploratory work that is not automatically added to a matter; “Practice settings” is permission-scoped and separates account security from practice administration. Support/build information belongs in a controlled diagnostics surface, not a permanent wall of engineering terms.

### Matter workspace at desktop width

```text
NM   Practice / workspace                 Account and security   Help
Matters > [matter reference and short name]     Saved [time] / connection state
[client + role] [proceeding / posture] [objective] [next obligation]

Matter navigation     Main work surface                     Source inspector
Overview              Current question / work product       Original page or
Take the brief        Discussion or selected file view      time-coded media
Work the file         with concise status and next step     + provenance
Advice & drafts                                             + related sources
Actions & dates       [type / attach / record]               + limits
Record
```

The source inspector opens when useful and can be dismissed; it is not permanently competing with the writing area. Keep one primary action per decision area. Matter navigation changes the view, not the active matter. The top context strip remains visible in every view, including exports and approvals.

On tablet, use two panes with an overlay/drawer source inspector. At narrow width, use one main pane with an explicit **Matter menu** and **Back to matters** control. Do not hide the only navigation route behind a CSS breakpoint. Source inspection returns to the same scroll position and focus. A wide evidence table offers a labelled alternative list view instead of shrinking text until unreadable.

### Visual system

Use a restrained, high-contrast, document-oriented appearance: warm or neutral backgrounds, dark readable text, one primary action colour, a clear type scale and consistent spacing. Use a screen-readable body face; legal-document styling can differ in a generated pleading. Avoid unnecessary animations, pulsing AI icons, simulated typing, decorative confidence scores and constant full-screen modal interruptions. Host fonts and assets within the approved boundary; a legal workspace must not contact third-party font or analytics services merely to render.

Colours supplement written labels and icons. “Needs your decision” is not the same colour/label as “Security restriction”. A persistent narrow status region is preferable to repeated toasts. Use skeletons only for actual loading, not to disguise an unavailable service. Keep controls stable while progress updates so a moving button cannot cause an accidental approval.

## 4. State and language contract

The UI renders typed server states, not guesses made from missing fields or HTTP timing. The exact copies below are defaults to refine through user testing while preserving their meaning.

| Situation | Default visible language | Required action |
|---|---|---|
| Sign-in has not resolved | “Checking your session…” | No matter content requested or painted |
| Workspace missing/unavailable | “I could not confirm your workspace. No matter has been opened.” | Retry or contact the practice administrator |
| Matter list partly unreadable | “Some matters could not be loaded. This list may be incomplete.” | Identify only authorised affected references; retry/help |
| Unsaved text | “Not yet saved” | Preserve in memory; retry/leave decision |
| Input durably accepted | “Saved to this matter. I am reviewing it.” | Safe to navigate; reopen operation status |
| Response outcome unknown | “I have not confirmed whether this finished. Check its status before sending it again.” | Check the same operation; do not create a duplicate |
| Uploaded, not reviewed | “Received. Not yet read.” | Show processing/admission status |
| Partial document extraction | “I read 8 of 10 pages. Pages 4 and 7 could not be read.” | Inspect, replace, or proceed with explicit limitation |
| Transcript uncertainty | “Please check this name/date at 02:14.” | Play the original segment and correct the derivative |
| Unsupported material | “This format is not supported here. I have not read it.” | State a supported alternative; no silent conversion/provider switch |
| No established authority | “This step needs authority from [recorded role/person].” | Request or record authority, not a generic override |
| Legal coverage limit | “This question needs [jurisdiction/source] that has not been verified in this workspace.” | Limit the answer, use approved research, or refer for review |
| Changed input | “The receipt date changed. The limitation assessment and draft need review.” | Open impact list; block stale consequential action |
| Insufficient support for conclusion | “I can set out the possible routes, but cannot recommend one yet because…” | Name the smallest decisive gap and usable interim work |
| Provider unavailable | “Research is temporarily unavailable. Your brief is saved.” | Continue permitted file work; explicit retry/cancel |
| Session ended | “Your session ended. I stopped showing this file. Sign in to continue.” | Clear protected view and reconnect only after authorisation |
| Signed out | “Signed out.” | Do not imply downloaded files were erased |

Do not expose “RRF”, “CAS”, “token window”, “embedding”, “schema”, “grounding gate” or “provider exception” in ordinary advocate-facing copy. The diagnostics view may carry precise technical details for authorised operators with content redacted.

## 5. Journey contract: arrival through sign-out

### 5.1 Arrive and establish the working context — M01

The invitation explains who issued it and which practice/workspace it joins without exposing private roster data to someone who merely possesses an invalid token. Sign-in works with password managers and accessible authentication. Recovery, MFA/passkey enrolment, device/session review and sign-out are reachable without opening a matter. A high-assurance production gate is separate from a local demo; never describe a demo exception as completed production security.

After authentication, show the verified account identity, active workspace, permitted role and scope of the current product. If the identity belongs to multiple approved workspaces, switching is deliberate and clears the previous matter context. A solo advocate sees a meaningful private-practice workspace, not an unexplained tenant ID.

The first landing view answers: what needs attention today, what was left unfinished, and how to start/reopen a matter. Its counts must derive from authorised records. Loading/error/partial states must not appear as “No matters yet”. NM may offer a brief introduction once; do not repeatedly make an experienced advocate complete a tutorial.

### 5.2 Open or accept a matter — M02

Ask for enough to identify the client, other relevant parties, nature of the instruction, forum/location if known and immediate urgency. Accept a short description and supporting material through the admitted route. A deadline tomorrow or immediate harm is visible at once; intake does not bury urgency under profile completion.

Distinguish the prospective matter shell from an accepted engagement. Explain the actual conflict-screen population and any omissions. A possible name match requires review; no matches in an incomplete registry is not clearance. Where conflict cannot yet be assessed, restrict the affected work while preserving lawful, necessary protective guidance within the product's scope and professional review rules.

Create a commission in ordinary language: “You want an assessment of … for … by …; you have not authorised sending or filing anything.” Record objectives, constraints, desired output, who instructs and who decides. The advocate can correct the summary and mark unknowns. Scope is revisited when the instruction changes.

### 5.3 Take the brief as an interactive loop — M03 and M08

1. Invite the advocate to describe the problem in their own words, paste notes, attach files or record a voice note. Typing is never the only route.
2. Receipt and processing are visible per item. Show exactly which material NM has read and which it has not.
3. Retrieve relevant material already authorised for this matter before asking the advocate to repeat it. Explain if an earlier answer may have changed; do not ask as though it was never given.
4. Reflect a compact understanding of the client, posture, objective and material facts. Separate the advocate's account from NM's inference and unresolved contradictions.
5. Ask the next most useful question or small related group. State why it matters when not obvious. Offer “I do not know”, “I cannot get this”, “Already in the file” and “Come back to this”.
6. If the answer changes a material premise, show the correction and affected work. If it is immaterial, incorporate it without a ceremony.
7. Offer useful interim work while gaps remain: evidence to preserve, questions for the client, provisional routes, or a bounded research task. Do not force a premature opinion.
8. When sufficient for the commissioned task, say what is ready and what is still conditional. Let the advocate continue briefing, narrow the task or move to file work. Never equate a completed questionnaire with a sufficient brief.

Voice input has a clear recording control, timer, pause, stop, cancel and playback. Do not listen continuously by default or infer permission to record third parties. Show the processing location/profile and relevant retention choice before recording. Microphone refusal leaves typing and file upload usable. Keep an editable transcript separate from source playback, label uncertain words/speakers and preserve locators. A recording of a witness is evidence to assess; it is not permission to coach false testimony.

For audio/video, recording-local speaker diarisation is a hypothesis until checked; automatic transcripts and translations are labelled derivatives. A date, amount, party name, negation or material admission with low transcription confidence needs review before it drives advice. A local label such as Speaker 1 separates contributions; a user-confirmed name records an attributed claim, not biometric authentication. NM must not identify or authenticate people from voice or appearance, create or match voiceprints, derive affect/emotion, or infer credibility or truthfulness from voice or appearance. Consent, a model prompt or a provider default cannot override this product boundary.

This does not prevent normal evidence-based legal assessment: the advocate can compare what was said with documents, chronology, contradictions and admissions, retaining the source and explaining the inference. Preserve admitted original evidence even when it contains another person's identity or emotional assertions; do not silently redact or rewrite the evidentiary original to satisfy a ban on NM-generated analysis. Uncertain attribution remains visibly uncertain, and correction preserves the earlier transcript and time locator.

The actual processing route must refuse prohibited operations before any media bytes leave NM, including hidden or inseparable processing in the selected provider configuration. Accept only recursively allowlisted response fields before they can enter storage, caches, logs, the interface or reasoning. The provider's unrelated optional services do not disqualify an otherwise verifiably compliant operation. A blocked route offers an approved transcription route, upload or manual review; it does not invent a transcript. BK-69-AC3 owns the foundation, BK-79-AC3 its served intake integration, and BK-88-AC4 confidential-path proof. EVAL-007/008/027 specify both allowed transcription and the prohibited-operation controls; they remain NOT_RUN specifications.

### 5.4 Work the file — M04 through M07

The default view is a concise case map: client objective and posture, issues, strongest supporting material, adverse facts, missing proof, thresholds/deadlines and competing routes. Open detail on demand. Never require the user to read a visual knowledge graph to work the file; optional graph inspection is a specialist view.

From any material proposition, one action opens its exact page/paragraph or audio/video time range. The inspector distinguishes original, OCR/transcript/translation, advocate correction, and NM interpretation. The user can mark a fact disputed, correct it, relate another document or ask what a contradiction changes. Those actions write attributable changes, not destructive edits to the original.

Research offers a focused question, scope, coverage and budget before a long operation. Results show relevant authority and contrary treatment with precise source references. “Search found nothing” names the searched scope and does not establish that no law exists. Research outside verified Telangana/Union coverage is clearly bounded even though NM operates in India. Saving a research result to a matter records what proposition it supports; simply opening it creates no matter fact.

The reasoning view explains the legal route, material premises, adverse case and practical consequences at a useful level. It need not reveal or store hidden internal model deliberations. Show a checkable decision rationale, evidence and assumptions. Deterministic date/amount calculations expose inputs and rule versions; the underlying legal applicability remains open to challenge.

### 5.5 Advise — M09

Start with the answer to the commissioned question. Depending on the task, show a short oral-style view, a full opinion, a hearing note, options comparison or client explanation. The substance is one versioned advice object rendered differently; separate independent generations must not contradict each other.

Every material advice version makes available: recommendation, objective, basis, strongest counterargument, uncertainty/assumptions, alternatives including not proceeding where relevant, practical cost/time/enforceability considerations, next action/owner/due basis, and what would change the recommendation. Not every short interaction prints all these sections, but a material omission must not be hidden by the format.

Display the existing registry's advice-maturity names: **Immediate protective guidance**, **Preliminary orientation**, **Provisional view**, **Considered advice** and **Action or argument brief** (AM-01–AM-05). Explain the selected level in ordinary language; do not create a new incompatible maturity scale or silently rename levels in the frontend. Separate NM's internal release checks from an advocate's review and external readiness. A polished PDF is not evidence of any of them.

If the advocate rejects the recommendation, record the decision and reasons without modifying the analysis to make the original risk disappear. The advocate can ask NM to challenge its own position or develop another lawful route. NM should be decisive where justified and bounded where not; indiscriminate hedging is not senior-counsel quality.

### 5.6 Prepare, approve and act — M10

Draft from a confirmed brief and the current authorised sources. Show document type, intended audience, forum, objective, version and unresolved drafting choices. Facts not established remain clearly marked for resolution rather than silently invented. Citation and annexure checks operate on the actual export bytes, not just the editor's preview.

Present approval as an exact transaction: document/version, attachments, recipient/destination, purpose, relevant limits and the role authorising it. Default consequential actions to a review screen. Separate **Save draft**, **Approve this version**, **Export reviewed copy**, and any future **Send/File** integration. Do not use one ambiguous “Done” button.

An edit to approved content, recipient or attachment invalidates the affected approval. Double-clicks and network retries must not duplicate external acts. A timeout after sending means the outcome may be unknown; NM checks the receipt and asks for reconciliation instead of offering an unsafe automatic resend.

If a filing integration is not built and authorised, NM prepares the reviewed pack and a checklist; the advocate files through the proper channel and records the receipt. This is useful complete behaviour for a scoped release, not a simulated “Filed” status.

### 5.7 Carry the matter forward — M11

“My work” and the matter's “Actions & dates” show who owns the next step, what must happen, due basis, status, and any review or escalation. A notification is not completion. A court-date source change reopens affected reminders and advice; NM does not silently update a deadline the advocate has relied on.

On re-entry, show a short **Since you last worked here** view: new material, changed instructions, affected advice, completed work and live obligations. The advocate can resume the last activity without rereading the whole conversation. A handover includes the commission, posture, live issues, adverse material, current advice/decisions, source access and unfinished obligations; the receiving person confirms receipt and scope.

Proactivity is bounded by the recorded task and notification preferences. Do not monitor indefinitely, run paid research repeatedly, contact clients, or widen the matter merely because NM has background capacity. External notifications contain generic wording by default and link back to authenticated content.

### 5.8 Close, reopen and leave — M11 and M01

Before closing, show unresolved obligations, pending actions, outstanding receipts, custody/return needs and retention decisions. Closing the engagement is separate from archiving the view and erasing data. The responsible person records the closure basis and any surviving duties.

Reopening preserves the historical file and requires a fresh check of instruction, permissions, conflicts where appropriate, relevant legal currency and outstanding obligations. It does not present old advice as a current opinion merely because the old matter opens.

Sign-out stops protected streams, revokes the current session as specified, clears in-memory protected views/drafts and avoids sensitive browser caching. Warn before intentionally discarding unsaved text where safe; never silently upload an unsaved draft during sign-out. If a network failure prevents confirming server revocation, clear the local view immediately and state that remote revocation could not be confirmed. Downloaded/exported copies remain outside NM's ability to erase; explain that boundary in account security guidance.

## 6. Accessibility and interaction acceptance

Target WCAG 2.2 AA and test actual core journeys, not just an automated score. Requirements include keyboard access, visible focus, focus not obscured, sufficient contrast, text alternatives, reflow, accessible authentication, adequate target size and perceivable status/error messages. The standard includes specific criteria and exceptions; conformance requires the complete applicable assessment, not selecting this list. [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/).

Implementation rules:

1. Use semantic forms, headings, landmarks and labelled controls. A button performs an action; a link navigates. Required/help/error text is programmatically associated with its field.
2. Preserve predictable keyboard order. Opening a modal moves focus appropriately; closing returns it to the initiating control. Source drawers and nonmodal panels do not trap focus.
3. Provide a skip link and keyboard-accessible matter navigation. Keyboard shortcuts supplement visible controls, can be discovered, and do not override common browser/assistive-technology commands.
4. Test at 200% text zoom and 400% browser zoom, narrow mobile width, tablet and desktop. Core controls remain reachable; no information disappears because a side rail was hidden.
5. Provide textual equivalents for recording/playback status, waveform annotations and visual evidence highlighting. Captions/transcripts are available for admitted AV derivatives; neither their presence nor their accessibility proves their accuracy.
6. Use live regions deliberately: announce meaningful state changes, not every token, progress heartbeat or scroll event. Long work retains a stable status and a stop control.
7. Respect reduced-motion preferences. Do not rely on hover-only disclosure, drag-only attachments, colour-only urgency or time-limited recovery-code viewing without a user-controlled acknowledgement.
8. Support password managers and paste. Do not block authentication with unnecessary memory/cognitive puzzles. Validate security and accessibility together instead of treating one as an exception to the other.
9. Test English and the actually supported Indian-language flows with representative content, long names, mixed scripts and date formats. Language support is a measured capability, not an automatic consequence of multilingual model output.

Evidence combines automated checks, keyboard walkthroughs, screen-reader review, zoom/reflow screenshots and observed advocate tasks. A screen-reader test cannot be replaced by a screenshot. Record tested browser/OS/assistive-technology versions and the actual task population.

## 7. Live module visibility: the proof console — M00

Build an authenticated **Build progress** area in the synthetic validation environment. It is for the product owner/reviewers, not routine clients and not an unauthenticated diagnostics endpoint. It can expose technical evidence in a separate restricted detail view without polluting normal advocate UI.

Each module card must show:

- module name and user outcome;
- current registry-derived state: planned, building, ready for demonstration, verified for a named release profile, or blocked;
- which actual capability is enabled in this environment;
- exact deployed commit/build, configuration profile, schema/index identities and synthetic fixture set;
- dependencies and unresolved limits;
- **Open live module**, **Run the permitted rehearsal**, **Inspect evidence**, and **Report a finding**;
- last validation time, population, PASS/FAIL/NOT_RUN/BLOCKED results and reviewer decision;
- whether anything is simulated, which boundary is simulated, and what has not been exercised.

Do not let a frontend flag or manually typed green badge determine readiness. The console reads the registry and fresh execution evidence. A stale server, changed schema, empty test population or disabled dependency makes the relevant proof stale/unavailable. Preserve the prior evidence as history without presenting it as current.

Use synthetic fixture tenants with conspicuously fictitious names, documents and recordings. The fixture banner stays visible, including in exports. Never populate a public demo with real matter data. The reset control may affect only its dedicated synthetic fixture scope and requires confirmation; it is not a production deletion tool.

The console should offer controlled failure demonstrations: processing service unavailable, interrupted network, two simultaneous edits, expired session, inaccessible source, partial extraction and stale advice. Fault injection is authorised only in the synthetic environment. A production operator cannot enable it by visiting a guessed route.

### Live-validation habit

At the close of each small implementation packet:

1. Update the registry's implementation/evidence state, without authoring completion beyond its evidence.
2. Start the named synthetic environment at the exact build under review.
3. Open the module card and verify that it names that build and fixture set.
4. Complete the specified user task through the actual UI and served API; do not edit database state to make the next step possible.
5. Repeat the named failure/abuse case and observe the safe recovery.
6. Save the transcript/screenshot/network/result artefacts permitted by the fixture policy, with the expected and actual results.
7. Record findings as delivery work, fix them, and repeat only the affected/risk-required checks. A later pass can close a fixed defect while retaining the earlier failure history.
8. Accept the module for its named scope only. Do not mark the whole product ready because the module works in isolation.

Model-backed or long-running evaluations retain the repository's explicit bounded-run approval requirement. Opening the proof console is not authorisation to incur arbitrary model/research costs.

## 8. Module rehearsals with observable outcomes

All rehearsals below are specifications, initially `NOT_RUN`. Each requires a declared fixture population and evidence identity. They supplement tests rather than certify themselves.

| Module | User performs | Expected visible result | Required failure rehearsal |
|---|---|---|---|
| M00 Proof console | Open a module; inspect build, fixture and evidence; switch to an older deployed build | Current evidence becomes stale rather than staying green | Empty evidence population cannot pass |
| M01 Access | Accept invitation, sign in, verify workspace, enrol required factor, recover, revoke another session, sign out | Correct identity/context; one-time secrets are not redisplayed; revoked session loses new access | Invalid invitation/recovery stays neutral; browser back and stale tab reveal no protected view |
| M02 Secure matter | Create a prospective matter, record objective/parties, review screening limits, accept/reopen | Explicit admission state and accurate matter cover survive refresh/restart | Conflict service unavailable cannot produce clearance; other tenant cannot open guessed ID |
| M03 Material | Attach a supported document and voice note; inspect receipt, transcript and original locator | Per-item received/read/partial states; source and derivative distinguishable | Corrupt file, uncertain name, blocked processor and interrupted upload remain visible and recoverable |
| M04 Case file | Confirm an account; mark a statement disputed; correct a material date | Provenance and prior version remain; affected work is flagged | Unsupported claim cannot become a documented fact by repetition |
| M05 Legal corpus | Open a held authority and its version/coverage record | Exact source identity and dated scope are visible | Missing/expired/unverified source is not presented as current authority |
| M06 Retrieval | Search an exact citation and a subject question; inspect contrary result and searched scope | Correct identity plus relevant traceable candidates and coverage limits | No hit from a broken index is not labelled absence of law; other tenant sentinel never appears |
| M07 Legal reasoning | Ask a bounded issue; inspect assumptions, elements, countercase and impact of a correction | Reasoned position traceable to current inputs; unresolved applicability is explicit | Attractive but irrelevant authority and an unsupported material premise are rejected/qualified |
| M08 Interactive brief | Give an incomplete mixed-media brief; answer, correct and decline a question | NM remembers answered questions, prioritises useful gaps and permits provisional work | No repeated loop for unavailable material; user interruption does not lose accepted work |
| M09 Advice | Request concise advice; expand rationale; compare another lawful route; record decision | Consistent versioned substance with explicit maturity, risks and next steps | Changed evidence removes current-ready label; insistence does not manufacture certainty |
| M10 Actions | Draft, inspect sources/annexures, approve exact version, export, record receipt | Approval scope/version and actual action outcome are clear | Edit after approval, duplicate click and unknown external response do not lead to unapproved/duplicate action |
| M11 Continuity | Re-enter, hand over, close with an open obligation, reopen, request retention review | Changes, outstanding duties and access scope remain explicit | Closure cannot silently cancel obligation; expired access/deleted source does not reappear after restore |
| M12 Operations | Open a degraded but authenticated session, recover from a representative outage | Saved work remains; availability and limits are honest; authorised recovery is measured | Missing key, stale restore, failed alert and unavailable dependency cannot produce a healthy badge |

## 9. Experience checklists for the registered execution packets

The finite work queue and predecessor outputs are in [packets.json](packets.json).
The A–F checklists below supply interaction detail; they are not a second
dependency graph or delivery-status ledger. A maps to P02/P08/P09, B to
P10/P13/P14, C to P15/P16/P25, D to P17/P18/P24/P28, E to P29–P31 and F to
P32/P33. Each registered packet ends with a runnable slice, not disconnected
screens. Implement the corresponding data/security contracts before presenting
the slice as usable with real client material. Scenario IDs point to the
initially unrun [evaluation specifications](evaluations.json); real execution
and any required human review are separate obligations.

### Packet A: M01 access and workspace

Relevant existing work includes BK-31 and BK-63; verify their current scope and evidence before extending them.

1. Inventory the currently served invitation, login, recovery, identity/workspace, sessions and sign-out flows. Map each visible state to a server state and list contradictory/missing copy.
2. Add the shared unauthenticated shell with semantic forms and no protected data fetch before authentication. Handle password managers, error focus and slow/failed session resolution.
3. Add the server-derived identity/workspace header and explicit multi-workspace switching if enabled; clear previous protected content before fetching the next workspace.
4. Implement the required factor and recovery management screens, including one-time secret acknowledgement and replacement/rotation. Record missing backend operations before pretending a screen implements them.
5. Add session list/revocation and an accessible sign-out route. Distinguish local clearing from confirmed server revocation when offline.
6. Rehearse through real browser sessions for two users: normal arrival, invalid invitation, recovery, changed factor, revoked session, stale tab, browser back and reload.
7. Close only when server/API tests, keyboard/zoom and live privacy checks agree. Register every remaining production assurance gap rather than waiving it in UI copy.

Stop gate: protected content is visible before valid context or after revocation; recovery secrets enter storage/logs; or required production authentication is missing.

#### The first access finishing slice: P02

The normal user sees **Account → Security → Replace recovery codes**, not
credential generations, idempotency keys or provider implementation names.
Explain the consequence before confirmation: “Your old recovery codes will
stop working. Save the new set somewhere safe.” Use the local password
reauthentication route only in the explicitly permitted local profile; the
confidential profile follows its approved strong authentication.

| State | What the advocate sees and can do |
|---|---|
| Ready | Read the consequence, continue to authentication, or cancel without changing anything |
| Authentication required | Complete the approved authentication; no new codes are created merely by opening this screen |
| Replacing | A stable in-progress message; do not invite a second uncontrolled submission |
| Replaced | New codes displayed once with a user-controlled save acknowledgement; old codes are no longer usable |
| Authentication failed | “We could not confirm this change. Try again.” No account-existence or secret detail |
| Account changed | Ask for fresh authentication; never silently use the earlier proof |
| Response not confirmed | “The connection ended before we could confirm the result. Sign in again and replace the set before relying on any codes.” Do not claim the old set still works |
| Leaving or signed out | Remove codes and protected content from the DOM and memory; no browser-history or storage redisplay |

Successful secret issuance is deliberately not replayed as plaintext. After a
lost response, a fresh authorised replacement is the safe recovery path; the
server must not retrieve stored plaintext to make the screen convenient.
The confirmation/control is keyboard accessible, errors receive appropriate
focus, and codes are not sent to analytics or a screenshot-taking proof sink.
Use synthetic codes for permitted evidence. P02's exact command and generation
rules live in the command catalog; EVAL-004 is the shared rehearsal anchor,
while BK-31-AC20's complete criterion and negative control still govern closure.

### Packet B: M02 matter cover and admission

Relevant existing work includes BK-33, BK-62 and admission/conflict journey items.

1. Build matter-list loading, partial failure, empty and authorised content states first. Provide a reachable return path at all target widths.
2. Build the prospective-matter form and commission summary. Use plain questions and unknown options; separate client, instructor and decision-maker.
3. Add immediate urgency capture and honest screening-scope/result display. Ensure missing screening blocks only the work the policy specifies and cannot be bypassed with navigation.
4. Build the matter cover from canonical server data: objective, client side, proceedings, instruction scope, current stage, next obligation and last update.
5. Implement resume/reopen with server version identity, preserving previous work and disclosing any reassessment required.
6. Rehearse fresh matter → incomplete admission → accepted scoped matter → refresh → restart → second-user access refusal.
7. Record whether an advocate can correctly explain who NM is acting for and what it has been asked to do without reading the conversation.

Stop gate: matter count silently omits errors; posture/client side is guessed; acceptance is confused with storage; or scope is not visible before substantive work.

### Packet C: M03 file and voice intake

Relevant existing work includes BK-54 and BK-69.

1. Build a single attachment tray used by new briefs and later turns. It displays file name privately, type, size/duration, progress, admission/read status and removal/cancel action.
2. Publish the tested capability limits before selection, with a supported alternative for refused formats. Do not claim every media type can be read.
3. Add upload interruption/retry around the same operation identity. Cancelling an upload must show whether anything was received and its retention state.
4. Add explicit record/pause/stop/cancel, permission explanation, playback and accessible transcript review. Keep recording permission distinct from third-party processing authority.
5. Build the source inspector and per-page/time processing coverage; show uncertain material fields in context rather than requiring review of every harmless transcription variation.
6. Attach only admitted derivatives to the briefing context; acknowledge unread/partial items without pretending to have used them.
7. Rehearse document+voice+correction in one brief, microphone refusal, mixed script, corrupt page, unavailable processor and interrupted connection.

Stop gate: “uploaded” implies “read”, partial extraction is hidden, or content leaves the approved processing boundary without authority.

### Packet D: M04 and M08 structured file plus conversation

Relevant existing work includes BK-64, BK-65 and the interactive briefing feature/step contracts.

1. Build a shared matter-state store in the frontend that renders server versions; keep unsent text local in memory under the session policy and accepted text on the server.
2. Add source-linked proposition and chronology views with clear asserted/documented/disputed/inferred meanings. Do not use the same badge for source presence and truth.
3. Implement correction and confirmation actions with previewed impact for material changes. Preserve original evidence and prior decisions.
4. Connect the question queue to recorded answers, unknown/unavailable states, objectives and current evidence. Let the user answer out of order or return to an earlier point.
5. Add pause/cancel/resume and changed-file handling. A newer server version cannot be overwritten by an older browser tab.
6. Build the change-impact banner and review task list; click through to affected analysis/advice without erasing unaffected work.
7. Rehearse a realistic evolving brief with documents, interruption, answered question, unavailable source, contradiction and corrected date; use only normal user actions between stages.

Stop gate: repetition, loss of accepted work, silent inference or stale advice on the corrected record. This packet is not professionally complete until the legal-brain and advocate-evaluation contracts also pass.

### Packet E: M10 drafts and consequential action

Relevant existing work includes BK-56, BK-57, BK-62 and BK-63.

1. Define the release's action scope. Start with draft/review/export and manual receipt capture where external integration is not authorised or built.
2. Build a document work surface with source links, unresolved placeholders, version history and an exact export preview.
3. Add explicit review and approval controls tied to authority, destination, content, annexures and limits. Make the consequence of the button unambiguous.
4. Add stale/changed approval states and user-friendly recovery. A material edit requires a new approval; previously sent versions remain history.
5. Show action attempts and receipts separately. Unknown delivery outcome offers reconciliation, not a green success or unsafe resend.
6. Rehearse a full drafting task, edit after approval, missing annexure, wrong recipient, duplicate click, timeout after acceptance and actor revocation.

Stop gate: a user cannot tell what they approved, stale material can be acted on, or export bytes differ materially from the reviewed version without warning.

### Packet F: M11 continuity and closure

Relevant existing work includes BK-39, BK-58 and BK-59.

1. Build the next-actions view with explicit owners, deadline bases, review status and generic notification preferences.
2. Add re-entry change summary from versioned records, not a separately invented model summary.
3. Build handover preview with access scope, missing material, adverse facts and open obligations. Capture acceptance and clarify who now owns each task.
4. Build closure review; unresolved duties must be dispositioned or remain visible after closure. Add archive and retention-request controls as separate actions.
5. Add reopen with current instruction/permission/law review, preserving the old record.
6. Rehearse departure → new event → re-entry → handover → close with a live obligation → reopen → retention hold/deletion review.
7. Verify the user can leave and later resume without reconstructing context from chat, and cannot accidentally erase or abandon the file by clicking “Close”.

Stop gate: a live obligation vanishes, a recipient gets unauthorised material, or closed advice is presented as freshly reviewed.

## 10. Measuring experience quality

Define success before testing and publish denominators. For each named task, record completion, critical mistakes, assistance needed, time, repeated questions, source-navigation success, recovery success and the advocate's explanation of the result/limits. Collect qualitative observations, not only satisfaction scores.

Test with representative advocates and matters of varying complexity, digital comfort, language and accessibility needs. The expert evaluator checks legal/professional adequacy; an advocate completing the interaction checks practical usability; security and accessibility reviewers check their domains. A model judge is not the sole witness for any of these.

Latency should be measured from the user's action to acknowledgement, useful progress and fully checked result, with percentiles, device/network, task size, cache state and concurrency. Separate upload time, queue time, retrieval and analysis. Do not improve the displayed speed by releasing unchecked advice or declaring success before persistence. Cost displays, if shown, distinguish estimated from actual and explain the scope before a long paid task; cancellation shows any already-incurred cost.

An experience is ready for its named release when the representative journey is useful and reliable, critical harms are refused, recovery works, limitations are understood and the evidence is current. “Every component is green” without an end-to-end user rehearsal does not establish that outcome.
