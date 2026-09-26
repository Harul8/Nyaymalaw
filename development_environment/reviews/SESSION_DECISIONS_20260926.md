# Session decisions, checked against the plan -- 26 September 2026

Every item discussed and settled in the session on the autonomous legal brain (from "what makes Claude good" to the build-status pass), checked against the Before Build sheet of `docs/Nyaymalaw_Implementation_Plan.xlsx`. Each item names the rows that must carry it and a phrase that must appear there; the check is `development_environment/one_off_tools/session_decisions_check_20260926.py` and can be re-run.

**First run: 52 of 60 present.** One report was a false alarm (the header says "rather than fixed rules"). Seven were real gaps, closed by `legal_brain_session_gaps_20260926.py`:

1. the five loops, named as a set (L.2 header)
2. the corpus is the ceiling (L.4 header)
3. the legal reasoning order as guidance, including remedy (LB-163)
4. the answer shows the sections finalised in the scratch pad, and the relief sought (LB-165)
5. how the owner reviews what is built (new LB-167)
6. build status re-measured at each slice close (LB-167)
7. the slice list brought up to everything now planned, marked as a proposed order (LB-138)

**Second run: 60 of 60 present.**

## Second cross-check -- how NM reads the matter, decomposes disputes, retrieves, asks, and what the board and scratch pad show

Built from the session transcript itself, not memory. 25 more items were added to the check (85 in all). 83 were present; 2 gaps, one point: the statute and case-law tool rows (LB-156, LB-157) did not say they report the candidates they returned and the model's keep / set-aside decision on each, which the scratch pad shows. Closed by `legal_brain_retrieval_events_20260926.py`. **Third run: 85 of 85 present.**

## Raised in the session but never settled -- NOT added as rows

From the 25 September review of the legal brain. The owner accepted only the practice layer (LB-120..125); these were proposed or observed and not answered. They are open, for the owner to decide:

1. Choose about ten legal-brain rows that define "great", each bound to a golden conversation with a check that can fail; fold or defer the rest.
2. Name the reviewer for LB-40: practising Telangana advocates, with a scoring rubric agreed before release, not after.
3. Telugu-language material in Telangana records (1 mention in the plan).
4. Pleadings craft: Order VII / Order VIII drafting (drafting appears only as generic persuasion, LB-23).
5. CPC state amendments and the Telangana High Court rules (0 mentions).
6. The expert-practice research leans on UK and Australian sources; only 4 of 8 are Indian and none is the Bar Council of India Rules.

## Latest run

```
OK  No model training; open models (Opus, Fable, OpenAI) used as they are
OK  Models work in a loop: decide, act, verify, decide next
OK  Guiding principles, not fixed rules that work against the model
OK  Principles distilled from OM-P01-14, the D16 tenets and CLAUDE.md; owner edits without code
OK  Strong harness checks every output; the model acts on the result
OK  Zero invention / hallucination is non-negotiable
OK  Answers as claims tied to sources, so zero invention is checkable
OK  18 output checks kept and strengthened
OK  6 professional boundaries fixed
OK  13 judgment gates: floor or principle, owner decides, with recommendation
OK  The pipeline (fixed reads, closed lists as a cage, fixed retrieval rounds) is what holds the model back
OK  Closed lists only at the tool's door
OK  Build beside the pipeline behind a switch; switch on golden comparison
OK  Golden set is the improvement signal instead of training; every defect becomes a golden case
OK  Show the work live; the advocate can correct mid-turn
OK  Arrive first, then the legal brain holding loop, context and scaffolding; retrieval part of it
OK  Tools as their own section after the loop
OK  Five loops: turn, research, opposing counsel, matter, improvement
OK  Research sub-loop with fresh context returns findings with spans
OK  Opposing-counsel loop sees claims and sources, never the reasoning
OK  Independent verifier on a cheaper tier, never the author
OK  The matter written only through checked tools
OK  Checks before and after every tool call; step log as process evidence
OK  Every number and date from a tool
OK  Context tagged with source and status; retrieved text never an instruction
OK  Record, replay, compare providers
OK  Every check keeps a planted-violation control
OK  Corpus is the ceiling: measured gaps close by acquisition, not by the model
OK  Legal reasoning method as guidance: facts, issues, statute, authority, application, procedure, remedy, risk, next step
OK  Cost: nested loops cost more; budgets; cheaper tier for checks
OK  Stable prefix, append-only history (cache and the model's own reasoning)
OK  LB-145 'built fresh each turn' refined: assembled once, appended, rebuilt only at compaction
OK  Detail on demand: tool search and practice playbooks
OK  Spent results cleared, large results paged, re-fetchable by locator
OK  Compaction rebuilds the brief from the checked file, not a chat summary; native compaction must pass the same check
OK  Advocate's own memory, apart from matters, with consent
OK  Freshness: versioned reads, stale writes refused, change notices
OK  Harness owns context policy on every provider; budget visible; one model per loop
OK  Ten tool rules, the envelope, the registry
OK  Tool families: matter read/write, statutes, case law, computation, practice tables, checking/delegation, advocate/action, discovery
OK  Deliberately not tools: open web search, command line, direct database access
OK  External acts are proposals the advocate approves
OK  About 25 of ~40 tools wrap existing code; build order core first
OK  Scratch pad closed by default, openable, live, grouped by dispute
OK  Scratch pad shows understanding, disputes, Acts, sections considered/kept/set aside, judgments and relevant passages, needs
OK  Scratch pad shows the tools called
OK  Interim marked as working, not advice; set-aside reasons labelled as NM's judgment
OK  Decision: scratch pad saved with the matter
OK  Decision: order guided by principles; final sections required
OK  Guided method per message
OK  Final answer per dispute: Act passages, case-law passages, evidence, case, arguments, other side, strengthen
OK  Final answer shows the sections finalised in the scratch pad
OK  Matter board: disputes listed; questions per dispute from passages, each saying why
OK  Decision: opposing counsel in three passes (early per dispute, full per dispute after details, across matter at end)
OK  Pass 1 shapes the board's questions
OK  Guardrails: every defence backed by a passage; only questions that change the position; re-run only on change
OK  Open: what counts as a dispute's key details for pass 2
OK  How the owner reviews what was built: behaviour first, legal tables, rules, mutation, code by risk, PR per slice
OK  Build status recorded per row and re-measured at each slice close
OK  Slices cover everything now planned (loop foundation, tools, harness, scratch pad, answer and board, opposing counsel, context, switch)
OK  Each message: the understanding is stated first, shown first in the scratch pad
OK  The matter is read from the checked file through tools, not loaded wholesale
OK  The advocate's own words kept verbatim and retrievable
OK  Disputes identified per message, new or existing; each kept distinct
OK  Everything after identification is done per dispute and grouped by dispute
OK  Two disputes' analysis never merged
OK  Per dispute: Acts retrieved, sections considered, relevant, finalised
OK  Statute tool reports candidates considered and which were kept or set aside, with reasons
OK  Per dispute: case law retrieved and the relevant portions identified
OK  Case-law tool reports which passages were found relevant, with reasons
OK  Finalised sections and relevant passages are what the answer shows
OK  What each dispute needs is worked out from the Act and case-law passages
OK  Questions per dispute come from the passages and elements, each saying why
OK  Pass 1 anticipated defences shape the questions
OK  Only questions whose answer changes the position; never asked twice
OK  Answers from the board or the conversation go through checked writes and reopen the dispute
OK  Unobtainable details are marked so and the analysis proceeds with the limit
OK  Matter board on the left lists every dispute with its status
OK  Scratch pad is the live stream of what the loop does, and it is streamed
OK  Scratch pad works on phone and desktop
OK  Each pass of the other side is labelled in the scratch pad
OK  Final answer: other side from pass 2, cross-matter risks from pass 3
OK  Final answer: questions outstanding listed
OK  Unsupported items left out or stated as a limit
OK  Streaming does not exist today (stated as a dependency)

85 of 85 present; 0 gaps
```
