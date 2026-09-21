# Open a matter — scoped build and verification, 21 September 2026

**Decision: RETURN TO BUILD / TEST for full B1 acceptance.** This report records
implemented opening functionality and local synthetic evidence, not a full
Class-A PASS, live legal-quality evaluation, counsel approval or release.
BK-93 remains partial / in progress. No commit or push is included.

## Authority and identity

The product owner approved the seven-area Establish the brief form and the
principle-led opening interaction in Before Build, then authorised implementation
and hands-on browser testing. Unknown details, non-contentious matters and a
narrow immediate request are legitimate; opening does not require a full brief.
No approval for paid model evaluation, real client-data processing, legal
retention periods or production release is inferred from that instruction.

Base commit: `b9d4f8482dfbf583fcd21a741a845d89c219c2e6`. Work is an uncommitted
candidate over that base. Pre-existing owner edits to the draft-status placement
and spacing in `frontend/index.html` and `frontend/app.css` were preserved.
`source-manifest.json` records candidate code/test file hashes and evidence
artifact hashes; it is a scoped identity, not the canonical gate fingerprint.

Workbook: `docs/Nyaymalaw_Implementation_Plan.xlsx`, SHA-256
`94fbc732734bbaa7a2beff9beb2b60f0b91d7dfae33e1c36fbf7b641432e323e`.
Only 81 Before Build cells in B:J were revised. All historical descriptions in
column A, Arrive rows 5–70, the 328-row full Implementation Plan and the other
ZIP parts were preserved. Two sheets; 155 Before Build rows. Approved decisions
and acceptance boundaries were rendered and visually inspected. The bundled
artifact library was unavailable; the permitted fallback edited the existing
worksheet XML rather than introducing another canonical plan generator.

## What is implemented

| Contract | Implementation and bounded evidence |
|---|---|
| Open before the first message | One owned matter saves the entire attributed brief, original party roles and immutable request identity. Unknowns are explicit; no facts, conflict clearance, verified authority or legal deadline are fabricated. Store restart and read-back are tested. |
| Seven opening areas | Optional title, multiple clients/type, instruction source and stated authority, other-party state, immediate task, proceeding details, and attributed urgency/date. Details use progressive disclosure rather than a compulsory full intake. |
| Retry and recovery | An uncertain acknowledgement retains the original offer. Changed instructions cannot silently reuse its identity or open another file; restoring and retrying the original reuses the committed matter. Protected draft restore includes all new fields. |
| Re-entry and continuity | Recorded instructions are available on the board and to the turn reader, distinctly labelled unverified. Original parties remain visible. Released conversation inside an explicitly opened file survives reload without becoming a case fact. |
| Contextual conversation | One shared set of professional principles guides turn-engine model calls; current instructions are not silently cut to a prefix. No example dialogue or deterministic greeting classifier was added to the operating guidance. Live model quality remains unmeasured. |
| Originals | Upload controls follow durable opening and show server-declared limits. Explicit storage purpose and retention are recorded. Incomplete uploads can resume from their original receipt. Received, quarantined and unread are visibly distinct from examined material. |
| Workspace safety | Sending stays visibly disabled until the selected file is ready. Existing session, CSRF, provider destination, authority, grounding-withhold and unadmitted-media boundaries remain in force. Local tests cover affected boundaries, not all possible threat models. |

## General fixes found during implementation and browser use

1. **Lost opening instructions:** persist the complete opening at the existing
   creation boundary; do not defer scope/capacity to the first message.
2. **False recovery banner:** clear the consumed intake draft after durable
   opening, not just its visible form controls.
3. **Apparently usable but inert composer:** derive button readiness from the
   selected file's loading state, shared by all re-entry paths.
4. **Shared prompt text confused the scripted adapter:** internal operation
   metadata now selects the test adapter's conversational response; the fake
   no longer infers its task from a word appearing in general guidance.
5. **Upload limit refactor left stale names:** hands-on selection exposed the
   failure. All upload/digest/recording limit checks now use the confirmed server
   limits. A served storage-and-re-entry test guards the complete path.
6. **Party information omitted from the opening display:** render the complete
   original party projection, not only the first client in the board heading.
7. **Keyboard and touch access:** increase composer/menu targets to 44 pixels;
   return focus to the visible attachment trigger when closing its dialog only
   if the original context is still current; focus the message box after the
   asynchronous opening transition, not while it is still hidden.
8. **Immediate opening raced draft protection after sign-in:** all protected
   saves now await the owning session's unlock and recheck account/context
   identity before writing. A deliberately delayed key proves no premature
   opening request; an unavailable key proves the operation stays unsent and
   does not misleadingly suggest the server may already have saved it.

## Test contract changes, not diluted safeguards

- BK-93-AC1 is explicitly refined by the owner's continuity requirement:
  non-matter must not implicitly create a file or establish facts; a released
  conversational receipt may be kept inside an explicitly opened owned file.
  Replay, no-fact/no-clearance and no-implicit-opening tests distinguish these.
- Existing browser helpers expand the new progressive-disclosure controls and
  open a durable matter before inspecting its upload controls. The contrast,
  keyboard, focus, width, error and external-asset assertions remain intact.
- Context tests reselect a file after returning to My work, which intentionally
  shows the file list. A late-history-response test waits for the initial
  automatic history render before capturing its next request; it still requires
  exactly one held response and proves logout prevents late DOM repopulation.
- Literal peer-register assertions now reflect the approved policy: explain
  when requested or material, without presuming the advocate is a junior.
  No grounding, permission, authority or confidentiality test was weakened.
- The full keyboard journey follows the new disclosure order using Tab/Enter
  and still requires an actual committed answer with attributed scope/capacity.
  Reload returns through My work and verifies the particular saved answer,
  rather than waiting on an unrelated hidden rail row on Home.

## Hands-on browser observations

The actual served UI at `http://127.0.0.1:8092/` was exercised through the
in-app browser using a synthetic account and synthetic information only.
Its visible rehearsal banner states that answers are scripted, not legal advice.

- Opened with all details unknown; found the saved file in My work and reopened
  it before giving any substantive brief. Unknown states remained visible.
- Sent a greeting; the released conversation survived reload and re-entry.
  This proves persistence, not natural-language judgment quality.
- Entered a non-contentious, multiple-client advisory brief, stated representative
  authority as unverified and recorded a source-attributed review date.
- Reloaded before submission, recovered the protected draft, inspected hidden
  details, then saved and read back the complete opening on the board.
- Uploaded a synthetic original for **storage only**. After an interrupted
  attempt, reselected it and resumed the same receipt rather than creating a
  duplicate. The completed receipt remained quarantined/unread and disclosed
  that OCR, transcription, scanning and page/time assessment had not run.
  Receipt `upload_7182258b53a4`; original SHA-256
  `051c2bb1fcb31821da17359de9cd15d4683f9408e36f2264671a080c48e2b10f`.
- Inspected desktop and 390 × 844 phone layouts; the phone DOM reported
  `scrollWidth=390` and `innerWidth=390`. No horizontal overflow was observed.
- First attempted normal sign-out. The product displayed its unsent-draft-discard
  confirmation; the browser connector then stopped exposing the dialog and
  timed out. That particular attempt is not counted as successful.
- Restarted the review server on the focus-corrected candidate and used a fresh
  tab. Opened another unknown-details matter: focus visibly reached the message
  box. Opened the material dialog and pressed Escape: focus returned to the
  attachment button. Signed out from this saved, empty-draft workspace; the
  page confirmed server-side closure. Reload still showed sign-in and no matter.
  Automated browser logout and late-response isolation are reported separately.
  No real microphone permission was granted and no real recording was made.

The subsequently identified draft-unlock race is covered by the deliberately
delayed/unavailable-key browser witnesses and final combined browser rerun;
the earlier hands-on observations are not relabelled as having tested that fix.

The browser file chooser took unusually long to return; that tool delay is not
an application upload-latency measurement. The observed final receipt, not the
chooser's return alone, established upload completion.

## Automated evidence

| Final run | Executed population | Passed | Failed/errors | Skipped |
|---|---:|---:|---:|---:|
| Opening, memory, turn contract, original intake, Arrive, protected drafts, peer register and provider independence (`focused.xml`) | 209 | 208 | 0 | 1 |
| Model/destination boundaries, token ceilings, withholding, receipts, ownership, capacity, scope, emergency admission, unadmitted media, CSRF and non-phrase routing (`impact.xml`) | 303 | 303 | 0 | 0 |
| Opening, context isolation, responsive light/dark design and login-to-logout journey (`browser.xml`) | 57 | 57 | 0 | 0 |
| **Total** | **569** | **568** | **0** | **1** |

The final browser run took 188.91 seconds as reported by pytest. Its population
includes six new opening witnesses, 21 context/recovery witnesses, six visual
width/theme cases and 24 existing login-to-logout cases. Six screenshot/JSON
capture pairs are preserved alongside the XML and the 42-file source manifest.
The initial failures remain in explicitly superseded XML reports; none was
hidden by a skip or an expected-failure marker.

Ruff on the changed Python implementation/tests passed; JavaScript syntax checks
passed; layercheck passed across 178 modules; `git diff --check` passed. Code
graph impact review was used to select affected tests; its semantic lookup
fell back to FTS, not embedding-backed semantic retrieval.

Focused runs use synthetic models and local stores. The one skipped test is
the paid live-provider witness in `test_provider_independence.py`, requiring
`NM_APPROVE_PAID_EVAL=1`; approval has not been received. It is not a PASS.
Existing dependency deprecation warnings remain (Starlette/httpx, AnyIO and
pytest-bdd fixture registration); no warning filter was added to conceal them.

No canonical Class-A evidence is promoted from these scoped runs. Backlog lint
examined 105 rows / 44 features / 47 steps and returned **20 problems**: one
BK-76-AC2 named-test reference, stale Class-A evidence and 18 stale historical
browser references. No new registry-structure problem was reported.

## Remaining work and acceptance limits

1. **BK-93-AC2 / P25 admitted media:** storage and quarantine are not extraction.
   Document-only/mixed-media intent interpretation needs actual permitted,
   attributable extraction, correction and multi-matter separation. This report
   does not claim that capability is built.
2. **Real judgment:** run the separately requested, bounded paid synthetic
   evaluation only after owner approval; assess question economy, immediate
   intent, mixed substantive input, uncertainty, refusal and risk handoff.
   Then obtain the required qualified review. Synthetic replies cannot close it.
3. **Selective restrictions:** the existing security/authority controls remain;
   full action-by-action reconciliation against the revised opening contract is
   still open. Unknown details must constrain dependent acts, not file access.
4. **Voice and media operation:** real microphone capture, transcription,
   multilingual/noisy input, video modalities and provider failure need their
   own permitted integration and live proofs. No real client material was sent.
5. **Retention and independent sign-off:** exact legal retention exceptions,
   qualified review and independent technical sign-off remain outstanding.
6. **Cumulative gate:** existing global evidence is stale on this changed tree.
   Backlog lint also reports an unresolved legacy BK-76-AC2 named-test reference.
   Neither is papered over or certified by this local verification.

The next safe step is to complete the admitted-media and scoped-action work,
then run authorised model/professional evaluation. Do not release or mark the
whole opening phase complete from this report.
