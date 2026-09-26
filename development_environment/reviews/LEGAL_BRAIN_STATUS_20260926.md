# HANDOVER -- read this first (session of 25-26 September 2026)

You are continuing work on **Nyaymalaw (NM)**, an AI legal assistant for Indian advocates (Telangana and Union law). The previous session ran out of usage; this section is everything you need to pick up. Read `CLAUDE.md` at the repo root before anything else -- its rules bind (generalised fixes only, invariant tests, measure before diagnosing, no fuzzy Act identification, three states, verify on the served path).

## Where things are
- Repo `Harul8/Nyaymalaw`, branch **`claude/defect-shapes-review-q843ph`**, head at or after **`b5e25f6`** (this handover), pushed, working tree clean.
- **The plan:** `docs/Nyaymalaw_Implementation_Plan.xlsx`. Sheet **Before Build** holds the requirements (10 columns per row); sheet **Implementation Plan** mirrors every LB/OM row and holds build state (col 39 Build status, 41 Evidence, 43 Test date, 44 Remaining gaps). `assurance/control_plane/plan_scenarios.requirement_problems()` must return `[]` after any edit. Workbook edits are made by one-off tools in `development_environment/one_off_tools/legal_brain_*_20260926.py`, which snapshot every cell, write only intended cells, and prove the rest unchanged on the saved file before replacing the source. Copy that pattern; never hand-edit cells.
- **Decision record for this session:** `development_environment/reviews/SESSION_DECISIONS_20260926.md` (85 settled items, all verified present in the rows; re-run `development_environment/one_off_tools/session_decisions_check_20260926.py`).
- **Build status of every legal-brain row:** the table below this handover.

## What was built in code this session (all pushed, tested, mutation-checked)
The **Indian practice layer**, each a curated table in `backend/nm/knowledge/`, a port in `backend/nm/ports/`, an adapter in `backend/nm/adapters/knowledge/`, wired in `backend/nm/bootstrap/composition.py` and `backend/nm/core/turn.py`:
- LB-120 governing code by date (IPC/BNS, CrPC/BNSS, Evidence/BSA) -- built but deliberately **unwired** (no criminal cause in the closed vocabulary).
- LB-121 pre-institution conditions (NI Act s.138/142 notice, CPC s.80, TPA s.106) -- names engaged conditions; does not read whether done.
- LB-122 which authority binds (bench/court ranking through `identity.supersedes`).
- LB-123 interim relief on its own test (Order XXXIX, XXXVIII r.5, XL; SRA s.41 bar; limbs NOT ASSESSED).
- LB-124 procedural periods (Order VIII r.1 ordinary/commercial, XXXVII, s.148A) -- entered on the deadline register undated; track never inferred.
- LB-125 forum/valuation/court fee -- honest measured gap (Telangana schedules not in `pipeline/manifest.yaml`).
Full suite at that point: only the 21 pre-existing `tests/test_current_plan_view.py` failures (they need a runtime absent from the cloud container).

## The direction the owner set (the heart of this session)
1. **No model training.** Use frontier models as they are (Opus 5.5, Fable, or an OpenAI model), provider-neutral.
2. **The model works autonomously in a loop** -- decide, act through tools, verify, decide again -- guided by **principles, not fixed rules** that work against its capabilities.
3. **A strong harness checks everything the model produces**; a failed check goes back to the model with its reason (**repair**), bounded; still failing is withheld with the reason. **Zero invention / hallucination is non-negotiable**: every answer is a set of **claims tied to retrieved passages or the advocate's own words**.
4. The existing gates were sorted: **18 output checks** (keep, run after the loop), **6 professional boundaries** (fixed), **13 judgment gates** -- owner to decide floor or principle (LB-134; recommendation recorded).
5. **Build beside the current pipeline, behind a switch; switch on a golden-set comparison** (LB-138). Never run golden/e2e evals without the owner's per-run approval.

## The plan structure (Before Build)
**A Arrive** (unchanged) -> **L Legal brain**: L.0 entry, L.1 guiding principles, L.2 the reasoning loop, L.3 tools, L.4 retrieval and grounding, L.5 the harness, L.6 context and memory, L.7 legal reasoning and advice, L.8 Indian practice layer, L.9 models, evaluation and build discipline -> **U** interface -> **P** later phases -> **X** diagnostics.

Owner-directed rows added this session, **LB-126 to LB-167** (drafts for owner review):
- L.1: LB-126 principles document the model reads every turn.
- L.2: LB-127 tool calling across providers; LB-128 the loop with budgets and a step log; **LB-140 opposing counsel in three passes**; LB-163 the guided method per message; LB-164 typed step events (streamed and saved); **LB-139 the scratch pad**.
- L.3 Tools: LB-129, LB-154 (envelope, 10 tool rules, registry, build order) to LB-162 (matter, statute, case-law, computation, practice-table, checking/delegation, advocate/action tools incl. **`submit_answer` -- the answer is a tool call**; discovery; deliberately not tools: open web search, command line, DB access).
- L.4: LB-130 claims tied to sources; LB-137 model-chosen retrieval with exact Act identity; LB-144 every number from a tool.
- L.5: LB-131 18 checks; LB-132 6 boundaries; LB-133 repair; LB-134 13 gates; LB-141 independent verifier; LB-143 checks before/after each tool call.
- L.6 (modelled on how Claude manages context): LB-135/136/142/145, LB-147 stable prefix + append-only conversation, LB-148 on-demand tools and practice playbooks, LB-149 clear spent results / page by locator, **LB-150 compaction rebuilds the brief from the checked file**, LB-151 advocate memory, LB-152 freshness, LB-153 one context policy on every provider.
- L.7: **LB-165 the answer dispute by dispute** (Act passages finalised, case-law passages, evidence to collect, case to prepare incl. relief, arguments, what the other side will say, how to strengthen); **LB-166 matter-board questions per dispute**, each naming the passage or anticipated defence behind it.
- L.9: LB-138 build beside and switch (with the proposed slice order), LB-146 record/replay/compare, **LB-167 owner review and keeping status true**.

## Decisions the owner made (recorded in the rows)
- Order of work is **guided by the principles; the final sections are required**, not enforced step by step (LB-163).
- **Each turn's scratch pad is saved with the matter**; closed by default; interim lines marked as working, not advice; reasons for setting a section aside labelled as NM's judgment (LB-139).
- **Opposing counsel in three passes**: pass 1 anticipated defences early per dispute (shape the board's questions); pass 2 full attack per dispute once its details are in; pass 3 once across the matter; every defence backed by a passage; re-run only when what it rested on changes (LB-140).

## Open -- the owner has not decided
1. Confirm the **slice order** in LB-138 (proposed: loop foundation -> envelope/registry/core tools -> harness after the loop -> streaming + scratch pad -> per-dispute answer + board questions -> opposing counsel -> context work -> document extraction -> golden comparison and switch).
2. **LB-134**: floor or principle for each of the 13 judgment gates.
3. **LB-140**: what counts as a dispute's "key details" before pass 2 (proposed: the elements' required facts answered or marked unobtainable).
4. **LB-148/LB-167**: the first practice-area playbooks, and who does counsel review of the curated legal tables (none has been counsel-reviewed).

5. **Raised in the 25 September review, never answered** (not in the plan): ten rows that define "great" bound to golden conversations; practising Telangana advocates as the LB-40 reviewers with a rubric agreed before release; Telugu-language material; Order VII/VIII pleadings; CPC state amendments and Telangana High Court rules; Indian sources (Bar Council of India Rules) for the expert-practice research. See `development_environment/reviews/SESSION_DECISIONS_20260926.md`.

## Next step (was about to start)
**Slice 1, as a pull request for the owner's review:** tool calling in `backend/nm/ports/model.py` + OpenAI, Anthropic and scripted adapters (LB-127); the loop runner with step/token/cost/time budgets (LB-128); typed step events and a saved step log (LB-164); the append-only conversation (LB-147); record-and-replay so the loop is testable without an API key (LB-146). Built beside the existing `TurnEngine`, behind a switch.

## Facts to keep in mind
- Today the turn engine (`backend/nm/core/turn.py`, ~7,200 lines) is a **fixed pipeline** of ~22 model reads; only evidence retrieval loops (max 3 rounds). The model port has `complete`, `structured`, `embed` -- **no tool calling**. `/api/turn` returns one finished answer -- **no streaming**.
- **Uploaded documents are stored but never read** (no PDF/OCR/media extraction). Retrieval is **keyword (FTS) only**; semantic support is mostly "not assessed".
- The cloud container has **no model API key** and **no corpus** (`legal_database/` is a Windows junction on the owner's machine). Live runs happen on the owner's machine with approval.
- Status legend below: **Built** = works on the served path with tests for its acceptance criteria; **In progress** = partially built; **Not started** = none of the row's behaviour exists. Verification columns were deliberately left "Not verified".

---

# Legal brain -- build status, 26 September 2026

Every legal-brain row in `docs/Nyaymalaw_Implementation_Plan.xlsx`, assessed against the code. Recorded in the Implementation Plan sheet's Build status, Evidence references, Test date and Remaining gaps columns.

**Built** -- works on the served path, acceptance criteria have tests. **In progress** (partially built) -- a real part is in production code; acceptance not met. **Not started** -- none of the row's specific behaviour exists.

Verification status is unchanged: building is not acceptance, and no acceptance criterion was run as written for this pass.

**Totals:** 13 built, 147 in progress, 29 not started, of 189 (LB-167 added after the pass).

## L.0  (11 built, 26 in progress, 2 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| OM-Q01 | Brief form and matter naming | Built | Live unscripted browser review with unknowns and several parties (AC) not recorded. |
| OM-Q02 | Screening boundaries and restricted results | In progress | Each screen across positive/unknown/unavailable/stale/negative states is not demonstrated as a population; restriction of conflict-match detail to authorised recipients not evidenced. |
| OM-Q03 | Media capability and limits | In progress | Uploads are received, typed and contained, but no document extraction, OCR or media transcription exists, so nothing uploaded is read for meaning. |
| OM-Q04 | Interrupted work, retries and cost | In progress | Tab close/reopen, logout and wrong-matter late results are not all exercised. |
| OM-Q05 | Retention of recordings and derived text | In progress | Backups and processor copies are not accounted for before certifying erasure. |
| OM-Q06 | Opening completion and onward journey | In progress | Live model judgment on the first contribution needs approved live evaluation. |
| OM-I01 | Input methods remain distinct | In progress | Typing, dictation and upload exist; uploaded documents and media are not extracted or transcribed. |
| OM-I02 | Saving, submitting and requesting analysis | In progress | Store-only is enforced; an explicit request to examine an upload cannot proceed because nothing extracts it. |
| OM-I03 | Flexible judgment with enforced boundaries | In progress | Today's pipeline runs a fixed sequence of reads; the free, principle-guided choice of next action is the loop in L.2 (LB-128), not yet built. |
| F-B-01 | Start a new matter from Home | Built | None recorded. |
| F-B-02 | The matter board beside the chat | Built | None recorded. |
| F-B-03 | My work lists the matters, and opening one resumes it | Built | None recorded. |
| F-B-04 | The matter's own tools sit in its header | Built | None recorded. |
| F-B-05 | The three ways a matter opens, after the form | In progress | Upload, mic and typing are offered; uploaded material is not understood (no extraction). |
| F-B-06 | Conflict screened as soon as the parties are known | Built | No executable scenario for this feature yet. |
| F-B-07 | Who the client actually is, and who instructs | In progress | Who instructs versus who the client is, with stated authority, is not held as its own record. |
| F-B-08 | Capacity and authority to instruct | In progress | Capacity is recorded; authority to instruct is not separately assessed. |
| F-B-09 | Forum and jurisdiction, stated or inferred | In progress | Forum is carried where stated; an inferred forum is not proposed and confirmed. |
| F-B-10 | A matter outside what is held is declared at opening | Built | No executable scenario for this feature yet. |
| F-B-11 | The dates that kill a matter, captured at opening | In progress | Urgency is recorded at opening; limitation is computed only once the cause and accrual are read. |
| F-B-12 | Two matters between the same parties are not one matter | In progress | Disputes within a matter are separated; two matters between the same parties are not detected. |
| F-B-13 | A matter's state is visible and moves | In progress | Matter state moves are not modelled as a lifecycle. |
| F-B-14 | My work at scale | In progress | My work lists matters; behaviour at scale (search, paging) is not built. |
| F-B-15 | Protected identities are never printed | Not started | No protected-identity handling exists; the cited test concerns internal identifiers only. |
| F-B-16 | Open a matter from a document | In progress | A matter can open from original files; nothing extracts parties, forum or dates from them. |
| F-C-01 | Add documents, media or a voice note from the plus button | Built | None recorded. |
| F-C-02 | Dictate the brief with the mic, transcribed on this installation | Built | None recorded. |
| F-C-03 | Live words while the advocate speaks | Built | None recorded. |
| F-C-04 | Understand the message, then answer or ask | In progress | The message is read by fixed reads; the loop that decides to answer or ask is LB-128. |
| F-C-05 | The model decides what to say; the checks decide what may leave | In progress | The checks decide what may leave; the model deciding freely awaits the loop (LB-128). |
| F-C-06 | Nothing binds until the advocate confirms it | In progress | Premises need confirmation; extracted values from documents (OCR) do not exist to confirm. |
| F-C-07 | A summary never loses a fact | In progress | Verbatim retention of critical values in summaries is not proved across compression. |
| F-C-08 | The client's own language is kept | Not started | No translation or original-language transcript handling exists. |
| F-C-09 | The matter's memory: atoms, the recent window, and a cited digest | In progress | Atoms and a recent window exist; the cited digest is not checked against the file. |
| F-C-10 | A matter's memory never reaches another matter | Built | None recorded. |
| F-C-11 | Resuming rebuilds the context from our own store | In progress | Context is rebuilt from the store; resumption after an abrupt stop mid-turn is not exercised. |
| F-C-12 | What is kept, and for how long | In progress | The 30-day audio rule is moot until voice notes are transcribed. |
| LB-02 | Typed contribution from composer to record | In progress | Long input with critical detail at its end, and switching matter mid-processing, not exercised. |
| LB-37 | Typed-first delivery and future media parity | In progress | Typed journey works; no medium beyond typing and dictation is extracted. |

## L.1  (0 built, 18 in progress, 1 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| OM-P01 | Professional relationship | In progress | Encoded in reads; held-out live evaluation not run. |
| OM-P02 | Purpose and scope | In progress | Encoded in reads; held-out live evaluation not run. |
| OM-P03 | Relevant listening | In progress | Questions already answered are not re-asked; held-out live evaluation not run. |
| OM-P04 | Non-leading enquiry | In progress | Held-out live evaluation not run. |
| OM-P05 | Proportionate questions | In progress | Questions are ranked by what they block; held-out live evaluation not run. |
| OM-P06 | Knowledge and evidence | In progress | Held-out live evaluation not run. |
| OM-P07 | Useful bounded assistance | In progress | Held-out live evaluation not run. |
| OM-P08 | Independent judgment | In progress | Held-out live evaluation not run. |
| OM-P09 | Urgency and priorities | In progress | Held-out live evaluation not run. |
| OM-P10 | Purposeful retrieval | In progress | Held-out live evaluation not run. |
| OM-P11 | Authority and instructions | In progress | Enforcement is tested; held-out live evaluation not run. |
| OM-P12 | Confidentiality in use | In progress | Boundaries are tested; synthetic-marker breach evaluation not run. |
| OM-P13 | Expression and meaning | In progress | Held-out live evaluation not run. |
| OM-P14 | Continuity and stopping | In progress | Held-out live evaluation not run. |
| LB-04 | Professional conversation | In progress | Blinded review of register and praise not run. |
| LB-17 | Independent merits assessment | In progress | Preference/pressure invariance not evaluated. |
| LB-39 | Independence and generalisation evaluation | Not started | No pressure-invariance or held-out generalisation evaluation exists; the golden set is the starting population. |
| LB-113 | Converse with judgment, not a joined-up audit report | In progress | Multi-dispute transcript judging with negative controls not run. |
| LB-126 | Guiding principles the model reads every turn | In progress | A shared reasoning discipline is composed in code; no owner-edited principles document with its version recorded per turn. |

## L.2  (0 built, 13 in progress, 5 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-127 | The model calls tools, whichever provider serves it | Not started | The model port has complete, structured and embed only; no tool calling. |
| LB-128 | The reasoning loop: decide, act, verify, decide again | Not started | The turn engine is a fixed pipeline; only evidence retrieval loops (at most 3 rounds). |
| LB-140 | Opposing counsel, in three passes | In progress | Adverse, attack and cross-file reads exist; the three passes as grounded nested loops do not. |
| LB-163 | How each message is worked: the guided method | Not started | The guided method depends on the loop (LB-128) and the principles document (LB-126). |
| LB-164 | Step events: every step recorded, streamed and saved | Not started | Model calls are kept; no typed step events, no step log, no streaming. |
| LB-139 | The scratch pad: the loop's work, shown live and kept with the matter | Not started | No streaming endpoint and no scratch-pad panel; /api/turn returns one finished answer. |
| LB-01 | One continuing assessment loop | In progress | Stage-free choice of next action awaits the loop. |
| LB-03 | Objective, instruction and authority | In progress | Objective and scope are recorded; client constraints versus instruction are not held separately. |
| LB-05 | Material, non-leading questions | In progress | Needless-repetition and burden measurements not run. |
| LB-35 | Proportionate latency and cost | In progress | Latency and cost by task type are not recorded. |
| LB-36 | Sufficiency and completion of the immediate task | In progress | Distinct stop reasons (sufficient, awaiting, no-progress, budget) not all modelled. |
| LB-61 | Let the model propose the next useful investigation | In progress | Bounded investigations can be proposed; a general next-action choice awaits the loop. |
| LB-64 | Run adaptive loops with measurable progress and honest stops | In progress | No-progress stops and resume triggers not all modelled. |
| LB-69 | Control total effort without weakening quality conditions | In progress | No whole-task budget across children and retries. |
| LB-70 | Make the reasoning loop understandable to the advocate | In progress | Progress, stop and resume reasons are not shown; the scratch pad is LB-139. |
| LB-110 | Work through the whole matter | In progress | As previously recorded. |
| LB-116 | Distinguish my missing information from NM unfinished work | In progress | As previously recorded. |
| LB-118 | Update the checklist from ordinary replies | In progress | As previously recorded. |

## L.3  (0 built, 0 in progress, 10 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-129 | What NM can already do becomes tools; closed lists only at the tool's door | Not started | No tool layer; the capabilities it would expose exist and are tested. |
| LB-154 | How every tool is shaped: the envelope, the rules and the registry | Not started | No envelope, registry or tool rules exist yet. |
| LB-155 | Matter-file tools: read and write the file | Not started | The matter model exists; no read or write tools over it. |
| LB-156 | Statute tools: identify the Act, read the provision as it stood | Not started | Exact Act resolution and provision fetch exist; not exposed as tools. |
| LB-157 | Case-law tools: find, read, resolve, weigh | Not started | Search, expand, passage, resolve, treatment exist; not tools; no find_contrary_authority. |
| LB-158 | Computation tools: every figure computed, never estimated | Not started | Limitation and deadlines exist; no date-arithmetic or interest tool. |
| LB-159 | Practice-table tools: the curated Indian practice layer, as tools | Not started | The curated tables exist and are wired into the pipeline; not tools; no playbooks. |
| LB-160 | Checking and delegation tools: check the work, research deeply, argue the other side | Not started | Consistency check exists; no verify_support, research or oppose tools. |
| LB-161 | Advocate and action tools, and the answer itself as a tool | Not started | Question record and action paths exist; no submit_answer claim structure. |
| LB-162 | Discovering tools on demand, and what is deliberately not a tool | Not started | No tool discovery exists. |

## L.4  (0 built, 20 in progress, 0 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-130 | Every answer is a set of claims, each tied to its source | In progress | Propositions are checked against retrieved spans; the answer is not submitted as typed claims. |
| LB-137 | Retrieval chosen by the model, identification kept exact | In progress | Exact Act identity is enforced; retrieval rounds are still decided by code, not chosen by the model. |
| LB-144 | Every number and date comes from a tool | In progress | Figures are computed deterministically; no check that every number in an answer maps to a computation. |
| LB-11 | Material inventory and examination limits | In progress | Examined ranges and extraction records do not exist (no extraction). |
| LB-13 | Retrieve applicable Indian legal material | In progress | Adverse-proposition search and recorded stopping basis not complete. |
| LB-14 | Authority status and contextual fit | In progress | Binding, treatment and bench are weighed; factual analogy and distinction are not assessed. |
| LB-25 | Assessment-to-case-and-law explorer | In progress | No readable basis view linking conclusions to premises and passages. |
| LB-26 | Evidence viewer and reverse dependencies | In progress | Reverse dependencies are recorded; not navigable from a source in the browser. |
| LB-27 | Legal source viewer and application explanation | In progress | Applicability explanation shown separately from the text is not complete. |
| LB-57 | Ground every material claim in the authorised record | In progress | Semantic support is mostly reported not assessed (see LB-141). |
| LB-59 | Represent claims, legal application and inference dependencies | In progress | Claim types and inference premises are not one recorded structure. |
| LB-100 | Published source withdrawal | In progress | As previously recorded. |
| LB-101 | Exact case scope | In progress | As previously recorded. |
| LB-102 | Search outcomes and limits | In progress | As previously recorded. |
| LB-103 | Retrieved candidate versus assessed support | In progress | Support is carried as true/false/not assessed; it is rarely assessed. |
| LB-104 | Faithful literal query handling | In progress | As previously recorded. |
| LB-105 | Honest bounded research loop | In progress | As previously recorded. |
| LB-106 | Measured hybrid retrieval and contextual reading | In progress | Lexical (FTS) retrieval only; the dense leg was refused (S11) and no fusion or reranking exists. |
| LB-107 | Qualified provision identity at grounding | In progress | As previously recorded. |
| LB-108 | RAG validation and accountable claims | In progress | As previously recorded. |

## L.5  (0 built, 16 in progress, 2 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-131 | The harness checks every answer: the eighteen output checks | In progress | The eighteen output checks run on every pipeline answer; the loop they must follow does not exist. |
| LB-132 | Professional boundaries stay fixed | In progress | The six boundaries are enforced on answers; tool calls do not exist to be gated. |
| LB-133 | Repair: the model is told why a check failed and revises | In progress | A bounded, constrained retry exists for structured reads; failed answer checks withhold without feedback to the model. |
| LB-134 | Thirteen judgment gates: principle or floor -- the owner decides | Not started | Awaiting the owner's floor-or-principle decision for each of the thirteen gates. |
| LB-141 | An independent verifier: does the passage support the claim? | Not started | No independent verifier; G-GROUND discloses semantic support as not assessed. |
| LB-143 | Checks before and after every tool call, and on the step log | In progress | Admission exists for delegated specialist tasks; no per-tool-call checks or step-log process evidence. |
| LB-31 | Human decisions and recorded disagreement | In progress | Reconsideration on material change not evidenced. |
| LB-32 | Enforced permissions and confidential retrieval | In progress | Revocation during tool execution cannot be tested until tools exist. |
| LB-33 | Untrusted content and tool results | In progress | Injection into each supported source channel not exercised (uploads are not read). |
| LB-38 | Checks before consequential assessment release | In progress | Qualified semantic review not run. |
| LB-60 | Use focused, versioned model task contracts | In progress | Versioned per-call policy identity not recorded on each request. |
| LB-62 | Enforce capability and permission checks before action | In progress | No shared admission for model-chosen tools (they do not exist). |
| LB-63 | Accept candidate results through one controlled writer | In progress | Candidate versus accepted results are separated for delegation only. |
| LB-66 | Record layered verification and its limits | In progress | Checks record state and detail; not inputs, performer and versions as one verification record. |
| LB-67 | Guard the final user-facing content on every channel | In progress | Streaming, exports and drafts are not all under one release service. |
| LB-71 | Qualify models and preserve the same contract across providers | In progress | No per-role model qualification on held-out behaviour. |
| LB-114 | A selected event is not an established legal trigger | In progress | As previously recorded. |
| LB-119 | A blocked assessment has an accessible correction path | In progress | As previously recorded. |

## L.6  (1 built, 13 in progress, 5 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-135 | Context: the file on demand, the advocate's words verbatim, summaries checked | In progress | The advocate's words are kept; summaries are not re-checked against the file; file is not read on demand by tool. |
| LB-136 | Research sub-loop with its own clean context | In progress | Research and delegation exist; not a fresh-context nested loop returning spans. |
| LB-142 | The matter is written only through checked tools | In progress | Facts and premises carry quotes and corrections supersede; writes are made by reads, not by checked tools. |
| LB-145 | Context built fresh from the file, every item tagged with source and status | In progress | Facts carry their source; the layered, tagged context assembly is not built. |
| LB-147 | A stable prefix and an append-only conversation | Not started | No stable-prefix or append-only conversation handling; each read builds its own prompt. |
| LB-148 | Detail loaded on demand: tools and practice-area playbooks | Not started | No tool discovery and no playbooks. |
| LB-149 | Spent results cleared, large results paged, everything re-fetchable by locator | In progress | Expand and passage page by locator; nothing clears spent results. |
| LB-150 | Compaction regenerates the brief from the checked file | Not started | No compaction. |
| LB-151 | The advocate's own memory, kept apart from every matter | Not started | No advocate memory. |
| LB-152 | The file in context is never staler than the file | In progress | Stale writes are refused at commit; no change notice to a running model. |
| LB-153 | One context policy on every provider; the budget visible; one model per loop | In progress | The port is provider-neutral with a shared context budget; no context policy in the harness yet. |
| LB-08 | Critical extraction and confirmation | In progress | Premise confirmation and correction exist; document extraction does not. |
| LB-10 | Shared matter memory and connected issues | In progress | Cross-thread exposure and snapshot display partial. |
| LB-12 | Retrieve relevant private material | Not started | No search over the matter's own material; uploads are not read. |
| LB-29 | Corrections and impact propagation | Built | Drafts as dependants not exercised in the journey. |
| LB-30 | Versioned assessments and resumption | In progress | Compare/export versions not built. |
| LB-34 | Failure, cancellation and concurrent work | In progress | Cancellation during generation not exercised. |
| LB-58 | Reason against a versioned, durable matter snapshot | In progress | Each run does not name its snapshot. |
| LB-68 | Reopen affected work when its basis changes | In progress | Access withdrawal across caches and exports not exercised. |

## L.7  (1 built, 26 in progress, 3 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-165 | The answer, dispute by dispute: passages, evidence, case, arguments, the other side, how to strengthen | In progress | Proof, theory and relief exist per dispute; the seven-section per-dispute answer does not. |
| LB-166 | What each dispute needs, asked on the matter board | In progress | The board shows a need per dispute; questions derived from passages and anticipated defences do not. |
| LB-06 | Urgency and protective prioritisation | In progress | Justified reprioritisation not evaluated. |
| LB-07 | Attributed assertions and evidential status | Built | None recorded. |
| LB-09 | Chronology, identities and quantities | In progress | Units, currencies and alias handling partial. |
| LB-15 | Cross-validation and respectful challenge | In progress | Respectful-challenge behaviour not evaluated. |
| LB-16 | Corroboration, authenticity and proof limits | In progress | Authenticity versus admissibility versus weight not modelled. |
| LB-18 | Alternative theories and strongest opposing case | In progress | Disconfirmation conditions not recorded per theory. |
| LB-19 | Issues, elements, burdens and proof | In progress | Burdens and presumptions partial; elements curated for few causes. |
| LB-20 | Procedural and numerical dependencies | In progress | Forum, valuation and fee not assessable (LB-125). |
| LB-21 | Realistic prospects and calibrated uncertainty | In progress | No fabricated-percentage control evidenced. |
| LB-22 | Practical options and recommendation | In progress | Sequence and option-loss explanation partial. |
| LB-23 | Candid advice and persuasive drafting | In progress | Advocacy drafting from the brief partial. |
| LB-28 | Coverage, gaps and unresolved limitations | In progress | Coverage display against actual execution partial. |
| LB-45 | Frame the decision that can actually be made | In progress | Decision-maker, source of power and permitted record not modelled. |
| LB-46 | Master the operative record, not just the document collection | In progress | No operative-record map of pleadings, orders and their status. |
| LB-47 | Find the decisive issue and explain the argument structure | In progress | Necessary premises versus independent routes not represented. |
| LB-48 | Turn a material gap into a lawful proof-development plan | In progress | Custodian, preservation and acquisition plan partial. |
| LB-49 | Protect the integrity of recollection and witness preparation | In progress | Recollection versus refreshed account not recorded. |
| LB-50 | Sequence strategy and preserve valuable options | In progress | Irreversible-consequence and preclusion analysis not built. |
| LB-51 | Use principled concessions without surrendering authority | In progress | Concession boundaries exist in hearing preparation only. |
| LB-52 | Assess resolution by interests and executable outcomes | Not started | No resolution-by-interests or settlement-terms analysis. |
| LB-53 | Know when legal analysis needs specialist knowledge | Not started | No specialist-referral or expert-report review capability. |
| LB-54 | Prepare to answer the difficult question directly | In progress | Answering a changed question against the brief not evaluated. |
| LB-55 | Apply the same brain to advisory and transactional work | Not started | No advisory or transactional instrument review. |
| LB-65 | Challenge material hypotheses and prepare credible scenarios | In progress | Raised versus anticipated versus speculative arguments not separated. |
| LB-109 | Keep each dispute distinct | In progress | As previously recorded. |
| LB-112 | Pre-filing advice without a fictional proceeding | In progress | As previously recorded. |
| LB-115 | Opposing arguments must not invent facts or law | In progress | As previously recorded. |
| LB-117 | A source-backed checklist within the conversation | In progress | As previously recorded. |

## L.8  (0 built, 6 in progress, 0 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-120 | Apply the law in force on the date that governs it | In progress | The table and port are built and tested but deliberately unwired: no criminal cause exists in the closed vocabulary. |
| LB-121 | Mandatory steps before a proceeding can be instituted | In progress | Engaged conditions are named on the served turn; whether the file shows them done is not read; s.12A not curated (Act not held). |
| LB-122 | Weigh a precedent by what binds this court | In progress | Bench and court ranking reaches the answer; references to a larger bench and per incuriam are not detected. |
| LB-123 | Assess interim relief on its own test | In progress | The test is set out; limbs are not assessed against the record. |
| LB-124 | Time limits that run inside a proceeding | In progress | Periods are engaged and entered undated; no trigger date is read, so none is computed; the track is never established. |
| LB-125 | Whether a filing will be accepted: forum, valuation and court fee | In progress | The gap is measured and named; no forum, valuation or fee is computed (Telangana schedules not held). |

## L.9  (0 built, 9 in progress, 1 not started)

| Row | Title | Status | Remaining |
|---|---|---|---|
| LB-138 | Build beside the pipeline, compare, then switch | Not started | The loop does not exist to be built beside the pipeline. |
| LB-146 | Record, replay and compare: the loop tested on every commit | In progress | Model calls are kept and a scripted model exists; no replay adapter from recordings, no provider comparison. |
| LB-167 | The owner's review of what is built, and a status that stays true | In progress | Added after this pass; the first status pass is recorded, no review step has begun. |
| LB-40 | Qualified review and realistic quality measures | In progress | No qualified Indian reviewer rubric has been run. |
| LB-43 | Plan reconciliation and delivery ownership | In progress | This status pass is part of it; delivery owners per clause not mapped. |
| LB-44 | Decisions required before implementation and release | In progress | Decisions open: LB-134 gates, LB-148 playbooks, pass-2 key details, thresholds and budgets. |
| LB-56 | Learn from review without hindsight or private-data leakage | In progress | De-identified reusable evaluation material not separated. |
| LB-72 | Evaluate behaviour and prove that controls can reject defects | In progress | Held-out multi-turn model evaluation not run. |
| LB-73 | Evolve the architecture with one owner for each control | In progress | The cutover and migration for the loop are not specified. |
| LB-74 | Build and validate the harness in complete, accountable slices | In progress | Slices defined in LB-138; none started. |
