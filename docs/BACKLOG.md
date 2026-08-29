# Nyaymalaw — Engineering Backlog

Living document. Add items as they surface; update status in place; never delete
a shipped item (move it to SHIPPED with the commit, so the reasoning survives).

Status: `TODO` · `IN PROGRESS` · `BLOCKED` · `SHIPPED` · `WONTFIX` · `DECIDED`

---

## Model tiering — `DECIDED / SHIPPED`

### M1. Which model runs what — **settled 2026-08-22 after a live A/B**

**FINAL (in `infra/llm.py`):**

| Tier | Model | Why |
|---|---|---|
| light / medium / heavy (conversation, classifiers, extraction) | **gpt-4o-mini** | proven, prompts tuned for it, supports `temperature`, cheapest |
| deliver + every `force_strong` (charge resolution, verification, re-grounding, advice-critique, final opinion) | **gpt-5.1** | reasoning over supplied text under high stakes — where it demonstrably wins |

**The hypothesis was wrong, and the evidence says why.** The migration to
gpt-5.1 + gpt-5.6-luna was reverted for the conversation tiers:

1. **Temperature.** luna and gpt-5-mini REJECT an explicit temperature and run
   at a fixed 1. NM sets `temperature=0.0` on every classifier, gate,
   charge-resolution and grounding call *because* those must be reproducible.
   Running them at 1 injects variance where determinism is the point — a
   functional loss, not just cost.
2. **The model was never the bottleneck.** The failures chased during the
   migration were *starvation*, not reasoning: an issue that got ZERO retrieval
   (R1) and a governing section outside the resolver's window. No model can cite
   what it was never shown. Where the task IS reasoning over supplied text,
   gpt-5.1 measurably won — which is why it keeps `force_strong`.
3. **Fit.** The prompt corpus was tuned for months against gpt-4o-mini; the
   empathy regression on gpt-5.1 was partly prompts leaning on mini's register.
4. **Cost.** ~13× per turn for the above.

**What the migration was still worth:** it EXPOSED R1 — a latent retrieval bug
that had been silently costing charges on every complex matter regardless of
model — and left behind the temperature shim, cached-token pricing,
`cache_hit_pct` telemetry, and the model selector.

**Kept for reference — pricing (fetched 2026-08-22, per 1M tokens):**

| Model | Input | Cached | Output |
|---|---|---|---|
| gpt-4o-mini | 0.15 | — | 0.60 |
| gpt-5.6-luna | 0.20 | 0.02 | 1.20 |
| gpt-5.1 | 1.25 | ~0.125 | 10.00 |
| gpt-4o | 2.50 | — | 10.00 |
| gpt-5.6-terra | 2.00 | 0.20 | 12.00 |
| gpt-5.6-sol | 4.00 | 0.40 | 20.00 |
| gpt-5.5 | 5.00 | 0.50 | 30.00 |

**Blocking sub-tasks:**
- [x] **M1a. Temperature compatibility shim** — `SHIPPED`, and still load-bearing
  (gpt-5.1 runs every `force_strong` call). Measured: `gpt-5.6-luna` and
  `gpt-5-mini` reject any temperature but the default; `gpt-5.1` accepts one — so
  it is NOT a clean family rule. `get_llm` omits the parameter for models known
  to reject it, seeded from measurement plus a runtime learner.
- [x] **M1b. Pricing table + cached-token rates** — `SHIPPED` — full gpt-5.x table
  with cached rates; `usage_snapshot` reports `cache_hit_pct`. Longest-match
  lookup so "gpt-5" cannot swallow "gpt-5.6-luna".
- [x] **M1c. UI model map + dropdown** — `SHIPPED` — selector now offers
  Standard / GPT-5.1 / GPT-5.6 Luna / GPT-4o Mini (legacy), defaulting to
  **Standard = send no override** so the server's per-task tiering applies.
  Previously the dropdown always sent `tier:gpt4o_mini`, silently overriding
  every tier — it would have defeated the whole migration.
- [x] **M1d. Measure the delta** — `DONE — this is what drove the revert.`
  Findings (both registers, live):
  - **Legal substance improved markedly.** gpt-5.1 named three distinct matters
    and, on "can they throw me out?", correctly *refused to answer
    definitively* — stating what it turns on (title/tenancy, established
    residence, the precise steps threatened). More genuinely lawyerly than
    mini's flat "he cannot simply force you out".
  - **The case-brief defect is FIXED.** On mini a brief fabricated "the court
    ruled that a cheque issued by a builder…". On gpt-5.1 the K. Prema S. Rao
    brief states a real ratio — *gifts associated with a marriage are not by
    that fact alone enough; proof they were given pursuant to a demand is
    material.* Grounded and accurate.
  - **Cost measured: ~$0.053/turn** (2 turns, $0.1065) — above the ~$0.017
    estimate because cache hit is 0% (C1) and background steps generate a lot.
    ~13× gpt-4o-mini. Closing C1 is what brings this down.
  - **Not reasoning-token waste** — verified: luna returns 5 output tokens with
    `reasoning_tokens=0` on a classifier. (`reasoning_effort` accepts
    `none`/`low`, rejects `minimal`.)
  - **Still to check:** concision (C2) — ~400 words on a peer turn, needs a
    client-register read; and whether empathy holds on gpt-5.1 for clients.

**Smoke-test results (2026-08-22):**

| Model | Basic | temperature | Structured output | Latency |
|---|---|---|---|---|
| gpt-5.1 | ok | ok | ok | 1.4–2.2s |
| gpt-5.6-luna | ok | **rejects** | ok | 1.2s (fastest) |
| gpt-5-mini | ok | **rejects** | ok | 2.3–3.5s |

luna beats gpt-5-mini on both price axes *and* latency → luna wins the light tier.

**Watch:** losing temperature control means `_generate_intake_turn`
(deliberately `temperature=0.7`, so turns don't read templated) runs at fixed
temp 1. May be fine or better; if turns drift, move that one call to gpt-5.1.

---

## P0 — Cost & latency

### C1. Prompt caching — `SHIPPED (partial)` — **0% → 10.2%**
**Fixed 2026-08-22.** `_narrow_prompt` (the most-called generation path) was
reordered so every STATIC block leads and every per-turn VARIABLE block follows.
`_register_instruction` no longer takes `grounding_text` (that list varies every
turn and is appended separately), and the RESPOND-FIRST *rules* — which are
static; only the quoted message varies — moved into the head, with the quote
itself emitted later, just before the goal.

Stable prefix went **915 → 1517 tokens**, clearing OpenAI's 1024-token minimum.

| | before | after |
|---|---|---|
| cache hit | 0% (0 / 76,030) | **10.2% (4,188 / 41,138)** |
| cost/turn | ~$0.053 | **~$0.029** |

**Still to do (raises the hit rate further):** only `_narrow_prompt` has a
qualifying head. The other ~20 background prompts (`classify_client_turn`,
`_EVIDENCE_MAP_PROMPT`, `_CHARGES_PROMPT`, `_score_issues`, …) still have static
heads of ~400–900 tokens, under the threshold, so they never cache. Giving the
hot ones a stable ≥1024-token head is the next increment.

### C1-history. Prompt caching — original diagnosis (0% hit rate)
**Measured 2026-08-22, live, 2-turn DV matter on the new tiers:**

```
cache_hit_pct: 0.0    cached 0 / 50,660 input tokens    35 calls    $0.1065
  gpt-5.6-luna        in=34,339  cached=0  out=25,630  calls=27
  gpt-5.1             in=16,321  cached=0  out= 4,848  calls= 8
```

**The meter is NOT blind — verified against the raw API.** Same >1024-token
prefix sent three times: call 1 `cached=0`, calls 2 and 3 `cached=1837/1840`
(**99.8%**). So caching works and `prompt_tokens_details.cached_tokens` is read
correctly; NM genuinely gets **zero** benefit today.

**Why (diagnosis):** OpenAI caches only a byte-identical prefix of **≥1024
tokens**. NM's per-call prompts mostly don't qualify:
- The big static block (`_CONSULT_PROMPT` + `core`, ~4–5k tokens, correctly
  first at `orchestrator.py:4179`) is **not used on intake turns at all** — the
  structured-intake path builds a bespoke `_narrow_prompt` whose static head
  (operating mode + register) is only ~150–200 tokens, far under the threshold.
- Background/light calls are 27 *different* prompts; they cannot cache each
  other, and each static head is small.
- `_CHARGES_PROMPT` does lead with ~700–900 static tokens — near, possibly
  under, the 1024 line.

**Fix direction:** make each hot prompt lead with a static block that clears
1024 tokens and is byte-identical run to run — chiefly `_narrow_prompt` (the
most-called generation path) and the charge/evidence prompts. Then re-measure.

### C1-orig. Prompt caching — background
Cached input is **10× cheaper**. NM is near-ideal for it: every advising turn
sends a large, near-identical prefix (`_CONSULT_PROMPT` + `_CORE_*` ≈ 5–8k
tokens of static text) before anything matter-specific. Caching is automatic
for prompts ≥1024 tokens with a byte-stable prefix — no API flag.

- [ ] Verify cache hits are actually happening (`usage.prompt_tokens_details.cached_tokens`)
- [ ] Log + price cached tokens separately so cost tracking is honest
- [ ] **Extend the stable prefix.** Assembly already starts well
      (`system_parts = [_CONSULT_PROMPT, core]`, `orchestrator.py:4143`) but
      everything after varies per turn. Making the **evidence block stable within
      a matter** (it is re-retrieved and can reorder each turn) would grow the
      cached prefix from ~8k to ~16k and roughly halve cost again.

Estimated effect (~20k in / ~1k out per advising turn):

| Model | No cache | Cached prefix |
|---|---|---|
| gpt-5.6-luna | ~$0.005 | **~$0.002** (cheaper than today) |
| gpt-5.1 | ~$0.035 | **~$0.017** |

### A5-part. Empathy regression on gpt-5.1 — `SHIPPED`
**Found by the client-register A/B, 2026-08-22.** Switching the brain to gpt-5.1
*regressed* empathy — proving audit finding A5 (empathy was never modelled; it
was borrowed from mini's natural register, and a more precise model does not
supply it).

| | opening line, same distressed DV client |
|---|---|
| gpt-4o-mini | "Your situation is quite serious, and it's clear that **you are in a lot of pain and fear right now**." |
| gpt-5.1 (before fix) | "**The hot-oil attack and the threat of worse violence are serious and time-sensitive.**" — law-first, D1 fail |
| **gpt-5.1 (after fix)** | "Being beaten for two years, burned with cooking oil, and then threatened with worse harm is **frightening and deeply humiliating; you should not have to face this as though it were an ordinary family disagreement**." |

**Fix:** a SPEAK TO THE PERSON BEFORE THE CASE rule in the client
`operating_mode`, stated as a generalized principle with its consequence —
naming the wrong is *analysis, not acknowledgement*; a frightened client who
does not feel heard withholds the very facts the case needs. Client register
only; the peer/advocate register is untouched.

**Note:** this does NOT close A5. Empathy is now instructed more sharply, but
still not *modelled* — nothing in state carries "she is frightened" into turn 4.

### C2. Output-token discipline — `SHIPPED` — 590 → 279 words
**Landed 2026-08-22.** ECONOMY principle in `_CONSULT_PROMPT`; counsel stage no
longer expands per-option pros/cons in chat; assessment turn is spoken-length.

**Gotcha worth remembering:** the first ECONOMY edit had NO effect on intake
turns, because the structured-intake path never uses `_CONSULT_PROMPT` — it
builds its own `_narrow_prompt`. (Same root cause as the caching miss.) A LENGTH
rule had to be added there too; only then did turn length drop 590 → 279 words.
Deliver-mode memo templates remain untouched — detail belongs there.

### C2-orig. Output-token discipline — background
Output is the expensive axis (gpt-5.1: $10/1M out vs $1.25/1M in). Conversation
turns should be **crisp** — which is also better advocacy; a senior advocate is
concise, not verbose. Detail belongs at the **deliverable** (opinion / draft),
not in every intake turn.

- [ ] Tighten conversation prompts for concision (intake + consult turns)
- [ ] Keep full detail for `deliver` mode and the drafter only
- [ ] Measure tokens/turn before → after

**DECIDED — do NOT use a small model to expand accumulated output into the final
legal document.** That inverts the risk: the filed document is the
highest-stakes artifact in the system, and a small model expanding a summary is
exactly where subtle legal error enters. The economics don't justify it either —
drafting happens ~once per matter, while cost is driven by dozens of
conversation turns.
*The good version of the idea:* the drafter is already section-by-section
(`draft_one_section`), so tier **per section** — cheap model for mechanical /
boilerplate sections (cause title, verification clause, formatting), strong
model for substantive ones (grounds, averments, prayer). Tracked as D1.

### D1. Per-section model tiering in the drafter — `WON'T DO 2026-08-23`
The idea was to run mechanical sections (parties, annexures, verification) on a
cheaper tier and keep the strong model for reasoning sections.

Not implemented, deliberately. There is **no generalizable per-section signal**
for "this section needs no legal reasoning": `_scoped_outline_for_section`
deliberately passes `statute_map`, `precedent_map`, `charges`, `key_dates` and
`prayer` to EVERY section, precisely so any section that turns out to need a
citation can find one — its docstring calls trimming those a real correctness
risk. So the only available implementation is a hardcoded section-key -> model
table, which is exactly the situation-specific rule
`docs/PROMPT_GUIDELINES.txt` P4 forbids, applied to the highest-stakes output
the product has.

The cost case is weak too: the drafter runs ONCE per matter, at the end, so it
is not the hot path — C2 already took the per-turn output tokens from 590 to 279
words. Reopen only if drafting cost is ever measured to matter, and then with a
data-driven signal rather than a key list.

---

## P1 — Behaving like a renowned advocate
*(from the forensic audit, 2026-08-22)*

### A1. No deliberation — single-pass generation — `SHIPPED`
**Landed 2026-08-22** as the `advice_critique` graph node, between
`grounding_guard` and `grounding_audit`.

Everything else in the pipeline checks whether the reply is GROUNDED (is the
section real, is it in evidence, is the figure supported). Nothing asked whether
**the advice is any good**. This is that pass: the strong model reviews the
finished answer as the senior in chambers — missed or mischaracterised issue,
conclusion the cited law does not support, unflagged defence/risk/limitation, a
better route not recommended, oversold confidence — and either confirms it or
returns a complete revision.

Safety design (a quality pass must never become a way to smuggle in bad law):
- **Advising turns only** (`_is_advising_turn`: deliver, consult counsel stage,
  or intake assessment) — fact-gathering pays nothing.
- The revision is **re-validated with the same deterministic checks
  grounding_guard uses** (`_ungrounded_sections`, `_ungrounded_pairs`,
  `_content_mismatched_sections`, repealed-code regex) and **reverted** on any
  failure.
- Reverted too if the revision collapses the reply (<50% of the original).
- Prompt forbids introducing any Act/section/case not already in the evidence.
- Fail-open on any error; kill-switch `AGENTIFIED_NM_DISABLE_CRITIQUE=1`.
- Problems found are kept on `state["critique_problems"]` for observability.

**Follow-ups:** surface `critique_problems` in the UI (an advocate would want to
see what the review caught); consider running it on the drafter's substantive
sections too.

### A1-orig. No deliberation — background
The reply is one `llm.invoke()`, after which `grounding_guard` repairs
*citations only*. Nothing evaluates the answer **as advice**. A senior advocate
forms a theory, tests it, runs the opponent's best case, revises, *then* speaks.
`build_case_theory` / `_search_adverse_authority` exist but run **before**
generation as advisory inputs, and only on counsel turns.

**Proposal:** a self-critique pass before the reply ships — "what would a senior
silk say is wrong or missing here?" — gated to advising turns so it costs one
extra call only where it matters.

### A2. Corpus stores passages, not knowledge — `SHIPPED`
Ratio distillation, lazy + cached, distilled **from the case SUMMARY** rather
than an arbitrary retrieved chunk.

**Ratio decidendi** = the principle the court actually decided on, which binds
later courts. Distinct from *obiter* (passing remarks), the *record* (this
case's parties/amounts/dates), and the *issue framing* (the question, not the
answer). A case is cited FOR its ratio.

**Why the source changed (measured, 400-case sample):**

| Signal in the summaries | Coverage |
|---|---|
| States a holding ("court held" / "held that") | **84%** |
| Uses the literal phrase "ratio decidendi" | 17% |
| Average length | 1,367 chars, structured |

A retrieved chunk is an arbitrary paragraph — often the issue-framing — so
distilling from it produced the QUESTION, not the answer. Summaries follow a
structure (core dispute → what the court examined → what it HELD → often an
explicit ratio clause), so they are much the better source.

**DECIDED — no batch regeneration.** The obvious next step looked like
regenerating all 32,526 summaries from full judgments (the raw text exists:
`caselaws_v2_chunks.json`, ~1.02M chunks; cost ≈ $15 on 4o-mini). **Measured
first and it is unnecessary:** distilling from the existing summaries yielded a
usable ratio on **25/25 sampled cases (100%)**, with **0/25** phrased as the
issue. The 17% figure measures only whether the summary uses that *phrase* — the
84% that say "the court held" distil just as well. Pre-computing ratios for
32,000 cases that will never be cited would buy nothing.

**Code guarantees (P2), because the prompt alone leaked):**
- Distilled ratios have section AND article references stripped
  (`_strip_statutory_refs`). This is not cosmetic: a brief naming a provision
  the turn is not citing would trip `_has_citation_leak` and discard the WHOLE
  turn. Measured leaks: "under Section 138 of the ... Act, 1881",
  "under Article 32 of the Constitution".
- Enactment-year patterns cover **16xx–20xx**, not just 19xx/20xx — Indian
  statutes are routinely 19th-century (NI Act 1881, Evidence Act 1872, IPC
  1860), and the narrower pattern silently failed on all of them.
- The output is re-checked with the renderer's own recital test, borrowed rather
  than copied so the two cannot drift.

**Follow-up (small):** the sample surfaced mojibake in at least one case name
("Sanjay Singh & Anr. Ã Petitioners") — a corpus encoding artifact, tracked as
B12.

### A2-orig. Corpus stores passages, not knowledge — background
411,797 bare-act chunks + ~32.5k case summaries, but the model sees only **16
chunks** (`_selected_evidence(limit=16)`), retrieval finds *provisions* not
*doctrine*, and case law arrives as raw chunks.
Confirmed live: Basalingappa's retrieved chunk was the **trial court's
issue-framing** (another case's cheque number and amount), not the ratio — it
had to be suppressed to avoid reciting the wrong record.

**Proposal:** pre-compute a distilled **ratio / principle** per judgment as its
own indexed field, so briefs are grounded in the holding rather than whatever
paragraph retrieval happened to hit.

### A3. Precedents ranked by authority, not helpfulness — `SHIPPED`
`_attach_precedents._rank` now buckets on `_prop_fit` (fit to the charge's
FACTUAL proposition) BEFORE authority weight, so a squarely-fitting High Court
case outranks a loosely-fitting Supreme Court one. Verified wired 2026-08-23.
Original diagnosis:
`_attach_precedents` ranks by `(court_weight, cited_by_count, score)` — never by
whether the holding actually *helps this client's position*. The subject-match
gate (shipped) stops off-topic cases but doesn't select *useful* ones.

### A4. Conversation is a state machine, not a mind — `SHIPPED (conservative)`
`merge_new_issues` scores issues that arrive mid-conversation, and an urgency-2
issue overrides the phase plan in `advance()` — a running clock or someone at
immediate risk takes the turn regardless of which phase the machine is in.
Deliberately narrow: it does not let any turn abandon the plan, only an urgent
one. Verified wired 2026-08-23. Original diagnosis:
`triage → ingredients → strength → assessment` with per-turn
`classify → gate → plan → generate`. Orderly, but not responsive — the tell is
that "answer the client's question before gathering" had to be bolted on as a
prompt block (`RESPOND-FIRST`) because the machine's default is to pursue its
own agenda. Allow a turn to abandon the phase plan when the client's message
demands it.

### A5. Empathy is instructed, not modelled — `SHIPPED`
`ClientTurnClassification.client_state` MODELS how the client is coping and
renders a HOW THEY ARE COPING block, instead of relying on a register borrowed
from whichever model happened to be answering (which is why it regressed on
gpt-5.1 — see A5-part). Verified wired 2026-08-23. Original diagnosis:
Empathy lives in prompt adjectives ("warm", "steadying") and a forbidden-openers
list. **Nothing in state models the client's emotional condition** —
`_score_issues` rates *legal* urgency/consequence, never "this person is
frightened". So it is unreliable across turns: nothing carries "she is scared"
into turn 4.

### A6. Cross-matter memory is shallow — `SHIPPED`
Matters now record what they CONCLUDED, not just what they started with:
`_session_summary_input` builds an `outcome` from the settled charges, the
issues the corpus could not answer, and what the deliberation pass caught
before the answer went out; `agents/memory.py` persists it (migrated column)
and reads it back. Verified end-to-end 2026-08-23. Original diagnosis:
`memory_update` persists regex-extracted section numbers and case names;
`get_user_memory` returns the last 5 session summaries. NM remembers *what it
cited*, never *what worked* — no accumulating judgment.

---

## P0 — Multidisciplinary-matter audit (2026-08-23)

Method: one seven-turn client conversation, run end-to-end through the real
graph and instrumented at every turn (issues, charges, era, key dates,
checklist, intake threads, reply). The matter deliberately spans five bodies of
law a client would not separate — matrimonial cruelty and dowry, forgery of a
sale deed over her own land, criminal breach of trust by a business partner, a
dishonoured cheque, and an ongoing safety situation — and straddles 1 July 2024
(2019 forgery, 2025 cheque). Saved to chat history so the whole conversation can
be read in the UI.

Measured against how a senior advocate actually works a matter of this shape:
triage for danger and clocks FIRST, establish what the client actually wants,
treat the five threads as ONE strategy rather than five files, sequence the
remedies, and end with a written opinion.

- [x] **M1. `opinion` is not a deliverable — so the written opinion cannot be
      produced at all.** Turn 7, "Please prepare the full written opinion
      covering everything", returned **19 words**: *"I cannot find authoritative
      material in the indexed corpus to answer this question."* `deliverable`
      was `None`, so the drafter sub-graph never ran and the request fell through
      to the consult path.
      Root cause: `_DELIVERABLE_PATTERNS` covers ten document types
      (legal_notice, plaint, written_statement, writ, interim_application,
      petition, complaint, rejoinder, reply, affidavit) — **all pleadings, none
      advisory**. Verified directly: "prepare the full written opinion", "draft
      the legal opinion", "give me the full opinion" and "prepare an opinion
      note" ALL return `None`.
      This is worse than a missing feature: `_CONSULT_PROMPT`'s own ECONOMY rule
      tells the client "the detailed treatment belongs in the written opinion...
      prepared separately when the matter is ready". **NM promises, every single
      turn, a document it structurally cannot produce.**
      An opinion is also the natural home for M5 and M6 below — its "Recommended
      course of action" section IS the synthesis and sequencing that is missing,
      and it is the only place that would consume the charge sheet, case theory,
      key dates and checklist together.

      **FIXED 2026-08-23.** `opinion` added as a deliverable AND made the
      DEFAULT: `_detect_draft_request` now returns "opinion" when a draft verb
      carries no deliverable noun, plus `_HANDOVER_OPINION_RE` for "give me the
      full opinion" (handing over is not drafting, so those verbs are not draft
      verbs — but paired with an unambiguous opinion phrase they plainly ask for
      the written product). 13/13 detector cases, including the negatives that
      matter: "what is your opinion", "in my opinion he was lying" and "I want to
      understand every issue" all stay `None`.
      Drafter side: `_DEFAULT_SECTION_KEYS["opinion"]` — matter_summary,
      instructions, issues_for_opinion, applicable_law, analysis,
      limitation_and_urgency, **recommended_action**, documents_required,
      caveats — deliberately the shape of what the pipeline already computes and
      had nowhere to put. The unrecognised/empty deliverable fallback moved from
      `plaint` to `opinion`: producing a court pleading when we do not know what
      was wanted asserts a forum, a cause title and a decision to file that the
      client may not have taken. `drafts/templates/opinion/template.jinja` added
      (no cause title, no prayer, no verification).
      `renderer._supported_deliverables()` was a HARDCODED list duplicating the
      outliner's table, and had already drifted — it is now derived from
      `_DEFAULT_SECTION_KEYS`, removing the second source of truth rather than
      adding an entry to it.
      Register follows the deliverable: `section_system_for()` gives an opinion
      an advisory head ("advice, not averments... say plainly where the law is
      against them") while the GROUNDING RULES stay byte-identical between
      registers, so an advisory document can never be held to a weaker standard
      than a filed one.
      Verified end-to-end on the same charge sheet that produced the failure:
      **9 sections, 3,707 words**, fact-tagged throughout, against 19 words of
      "I cannot find authoritative material" before.
- [x] **M2. Repealed law applied to CURRENT conduct — regression from B14.**
      Turn 2 introduced ONE explicit date, 12/08/2019 (the forged deed).
      `_conduct_era` returned `"old"` for the WHOLE matter and
      `_prefer_era_provisions` moved every charge to the repealed code:

        cruelty       BNS §85(1)  -> IPC §498A     (conduct was "last month")
        causing hurt  BNS §115(1) -> IPC §321      (conduct was "last month")
        breach trust  BNS §316(1) -> GAP           (lost entirely)

      Two distinct causes:
        - **relative-recency is invisible.** `_dated_events` reads only explicit
          calendar dates, so "last month", "just found out", "since the wedding"
          contribute nothing. A matter with one old date and everything else
          described relatively reads as uniformly OLD. Verified in isolation.
        - **era is matter-level, conduct is issue-level.** A multidisciplinary
          matter has a different date per thread; one era cannot be right for all.
      Note the straddle logic DOES work once both dates are explicit — by turn 4
      (2019 + 2025 present) it correctly abstained. The failure window is exactly
      "one explicit old date + everything else relative", which is how clients
      actually talk. This is the inverse of what B14 was built to prevent.

      **FIXED 2026-08-23, and re-done to be structural rather than lexical.**
      First attempt added `_describes_recent_conduct()` — a list of relative-time
      phrases. That works, and a relative expression genuinely is a dated event,
      but a phrase list drifts ("the other day", "over Diwali") and is exactly
      the growing-patch shape this project rejects. It is kept only as a
      SUPPORTING signal.
      The load-bearing rule is now an **asymmetric burden of proof** in
      `_prefer_era_provisions`: moving a charge BACKWARD cites a repealed
      provision and so asserts that this conduct predates commencement — a
      positive claim that must be shown for THAT charge. Moving it FORWARD
      asserts nothing extra, since the current code governs undated conduct
      anyway. So a backward move now requires either a single-charge matter
      (where the matter's dates can only concern that charge) or dating evidence
      in the charge's OWN facts; forward moves stay unconditional.
      Verified on the exact failure: a 7-charge matter with one 2019 date moves
      ONLY the forgery back to IPC §463, while cruelty and hurt stay on BNS
      §85(1) and §115(1) — and it does so without the phrase list carrying any of
      the weight. Single-charge matters still swap, so B14's benefit is intact.
- [x] **M3. An expired deadline was computed and never mentioned.** At turn 6
      `_compute_key_dates` correctly derived the §138 chain from the 03/03/2025
      dishonour — notice by **2025-04-02**, payment by **2025-04-17**. Today is
      2026-08-23, so that window closed **sixteen months ago** and the cheque
      route is time-barred. The reply said nothing about it, and went on
      recommending a police complaint. A senior advocate leads with "that one is
      gone, here is what is left instead". Computing a deadline, knowing it has
      passed, and staying silent is worse than not computing it.

      **FIXED 2026-08-23.** Whether a date has passed is arithmetic, so code
      decides it — the same division of labour that computes the date. Each
      entry in the KEY DATES block is now compared against today and marked
      "THIS DATE HAS PASSED", and an expired deadline adds a block instructing
      that it be stated FIRST for that issue, with what is still open instead,
      and that no step whose window has closed may be recommended.
      Generalised: no statute is named, it applies to any deadline the pipeline
      computes.
      The same gap existed in the DRAFTER and was worse — the opinion invented
      "you must act before 12/08/2022" from memory, on a matter being advised in
      2026: a date that was never computed, already impossible, and stated as
      settled. `_SECTION_RULES` (shared by both registers) now forbids computing
      any period or deadline, requires stating supplied `key_dates` verbatim or
      writing `[GAP: exact date not computed]`, and requires flagging a passed
      deadline. Re-drafted the section to verify: the invented 2022 date is gone
      and the reply now works from the supplied 02/04/2025 and 17/04/2025.
- [x] **M4. The advising turn was discarded — on the turn that mattered most.**
      Turn 5 was the explicit ask: "tell me now what I can actually do. What are
      my options and what do you recommend I do first?" It returned **118 words**
      — the shortest reply of the conversation — as `_limited_authority_reply`,
      with a request for more documents, on a matter that had **8 settled
      charges**. B17's salvage did not fire. (B17's honesty fix did work: the
      wording was the accurate "I have the governing provision, but I could not
      tie every point back to source" rather than the old false "no authority".)
      Turn 6 then produced a decent sequenced plan — but only because the client
      volunteered documents, not because they asked for advice.

      **FIXED 2026-08-23.** The gate that discarded the draft is correct — a
      reply carrying citations that cannot be tied to source must not ship. What
      was wrong is what it fell back to. The settled charge sheet is produced by
      a DIFFERENT path and has already been verified against each provision's own
      text, so it is not in doubt and there was never a reason to withhold it.
      `_limited_authority_reply` now states the settled provisions —
      "What is already settled on your facts, and does not change:" — rendered
      from data, so nothing in it can be ungrounded, and gapped charges are
      excluded. A client who asks "what are my options?" on a matter with eight
      settled charges now at least learns what those eight are.
- [x] **M5. No cross-issue synthesis — five threads, five parallel analyses.**
      Nothing in the pipeline asks "given ALL of these together, what is the one
      strategy?". `build_case_theory` does merits (strong points / defence /
      counters) for the matter as a whole but never how the threads INTERACT —
      that the forged deed is simultaneously a standalone offence, evidence of
      cruelty, and grounds to set aside the sale; that the DV route is the
      fastest interim protection; that the cheque has a hard clock the others do
      not. That interaction is most of what a senior advocate is for.

      **LARGELY ADDRESSED by M1, 2026-08-23.** The opinion's
      `recommended_action` section is the synthesis, and the drafted opinion did
      cross-reference threads and sequence them ("this action can be pursued
      concurrently with..."). M6 supplies the ordering signal mid-conversation.
      What remains unbuilt is a synthesis step DURING the consultation rather
      than at the end — deliberately not added, because it is an extra LLM call
      per turn for a benefit the opinion and the urgency ordering now largely
      provide. Revisit only if a later end-to-end run shows the mid-conversation
      turns still reading as parallel mini-analyses.
- [x] **M6. No remedy sequencing, though urgency is already measured.**
      `_score_issues` produces urgency 0-2 per issue with the definition "a clock
      is running or someone is at immediate risk", and it drives intake ORDERING
      and the A4 focus override — but it **never reaches the answer**. So no turn
      ever says what to do FIRST. Turn 1: the client says she was hit last month
      and (turn 4) is still living in that house — the senior-advocate response
      is a protection/residence order this week, before any evidence-building.
      NM asked her for incident details instead. The signal exists and is unused,
      the same shape as B12 and H5.

      **FIXED 2026-08-23.** `_score_issues` already scores every issue 0-2 on
      exactly the right question ("a clock is running or someone is at immediate
      risk"); the score simply never left the intake agenda. A TIME-CRITICAL
      block now carries the urgency-2 issues into the answer with the
      instruction to deal with them FIRST and as ACTION rather than analysis —
      protective or preserving steps before merits, and never to open a turn with
      fact-gathering on a matter just described as urgent.
      Generalised: it names no remedy, no statute and no kind of matter —
      whatever the scorer marked urgent is what leads. The signal was already
      paid for; this only stops discarding it.
- [x] **M7. A superseded issue is never retired, and it takes focus.** Turn 1
      framed "my husband sold my land" as **criminal breach of trust** —
      defensible on turn 1, wrong by turn 2 once the forged signature appeared
      and `forgery` + `fraudulent transfer of property` were spotted correctly.
      The wrong thread was never retired: it survived all seven turns, its charge
      sat as a GAP, and it **took the focus at turn 3** and still appeared in the
      turn-5 document request. `merge_new_issues` appends; nothing supersedes.
      A senior advocate revises out loud — "forget breach of trust, this is
      forgery" — and drops the discarded theory.

      **FIXED 2026-08-23.** Not by retiring the thread — a gapped charge can
      mean the corpus is missing the provision rather than the issue being unreal
      (cf. B6), so destroying it would lose real information. Instead the agenda
      is now ordered by (urgency, HAS A SETTLED CHARGE, consequence): a thread we
      have no legal theory for no longer out-ranks one we can name the law for,
      but it stays on the agenda and in the checklist.
      Two supporting fixes were needed. `merge_new_issues` returned early when a
      turn brought no new matter, which is most turns — that early return is what
      FROZE the ordering at triage. It now always re-derives each thread's
      settled-theory flag from the CURRENT charge sheet and re-sorts, so a thread
      whose provision settles later can rise and one whose charge decays to a gap
      can sink.
      Verified: the superseded "Breach of Trust" thread now yields focus to
      `forgery`, while an URGENT gapped thread still goes first — safety is not
      traded for a settled citation.
- [x] **M8. The client's objective is never captured.** `matter_frame.relief`
      was `None` on every one of the seven turns. `_want_frame` extracts the
      frame for a CLIENT audience only while `posture` is still unknown — i.e.
      on turn 1, the one turn where the client has said "I don't know where to
      start" and cannot yet state an objective — and never re-extracts after.
      Two clients with identical facts who want different things (safety /
      the land back / a divorce / the money) should get different advice; NM
      cannot tell them apart.

      **FIXED 2026-08-23.** `_want_frame` now also extracts while `relief` is
      unknown, for every audience, instead of only while `posture` is unknown.
      The objective decides the advice as much as the facts do — two clients with
      identical facts who want safety, the property back, a divorce or the money
      are owed different answers — and asking only on turn 1 asked at the one
      moment a distressed client cannot answer. It stops of its own accord once
      known, so the cost is one light call per turn only while we genuinely do
      not know.
- [x] **M9. One legal insight per intake turn on an 8-issue matter.**
      `_render_legal_insight` renders exactly ONE citation per structured intake
      turn. With 8 spotted issues and 8 settled charges, the client learns their
      case at roughly one issue per turn and never sees its shape. The checklist
      DOES cover every thread (verified — that part works), so the breadth exists
      internally and is simply never voiced.

- [x] **M11. A straddling matter got NO era correction at all** — `FIXED
      2026-08-23`, found while verifying M2 on the re-run. Matter-level
      abstention is right when the dates disagree, but abstaining for EVERY
      charge throws away the ones that can be placed: a sale deed dated
      12/08/2019 is pre-commencement conduct whatever else the matter contains.
      And a straddling matter is the NORMAL shape of a multidisciplinary brief,
      so this blind spot applied to exactly the matters that need era handling
      most. When the matter cannot be dated as a whole, each charge is now judged
      on its OWN facts and left alone if those do not date it — the same evidence
      standard as M2, applied per charge instead of per matter. This is the
      per-issue era the audit asked for.
      Verified on a straddling matter: cruelty ("last month") stays on BNS
      §85(1), the 2019 forgery moves to IPC §463, and the NI Act §138 charge is
      untouched because it has no successor code.

- [x] **M12. `is_allowed_source` is a looser duplicate of the real gate.**
      `retrieval/enricher.py` enforces its source allowlist through
      `is_blocked_source` and `ALLOWED_TIERS = ("tier3_legal_portal",)`. Sitting
      beside them is an unused `is_allowed_source()` that admits tier2 AND tier4
      — i.e. newspapers — into what is supposed to be a legal corpus. Not a live
      defect: nothing calls it. It is a trap, because the name reads like the
      gate and wiring it would silently widen what can be ingested. Delete it or
      rename it to say it is not the gate. Found by the never-called sweep.

      **REMOVED 2026-08-23, and the concern turned out to be bigger.** The
      looser predicate is gone, replaced by a note naming the real gate
      (`is_blocked_source` + `ALLOWED_TIERS = ("tier3_legal_portal",)`).
      But `retrieval/enricher.py` **cannot be imported at all** — it imports
      `BARE_INDEX_V2`, `BARE_CHUNKS_V2`, `CASE_INDEX_V2` from `config`, which
      carries the v3 names now. Swept every module under `agents/`,
      `retrieval/`, `infra/`, `api/` and `prompts/`: **it is the ONLY one that
      fails to import**, and nothing outside it references it. So the whole
      web-enrichment subsystem, source allowlist included, is dead code — see
      M25.
- [x] **M13. The matter frame only ever saw turn 1** — `FIXED 2026-08-23`,
      found on the re-run when `relief` was STILL None on all seven turns despite
      M8 asking for it every turn. `_matter_facts` was
      `state["client_statement"]`, which is set once when the matter opens and
      never accumulates — so `extract_matter_frame` re-read the OPENING message
      on every later turn. M8 made it ask repeatedly and always about the same
      stale words; a client almost never states their objective in the first
      message. Now uses `_all_client_text(state)`.
      Verified: on the accumulated account the extractor returns
      `relief='recovery of land and safety from husband'`, where it returned
      nothing before. A worked example of a fix that "shipped" and did nothing —
      the same shape as B12, and only the re-run caught it.

- [x] **M6-intake. The urgency rule reached only HALF the product** —
      `FIXED 2026-08-23`. M6 put the TIME-CRITICAL block in the consult path;
      the structured-intake path builds its own prompt and never saw it, so from
      turn 2 onward intake went back to gathering ingredients however urgent
      something else was. Observed on the re-run: turn 4 said "your safety is the
      priority" and then asked for injury details rather than naming a protective
      step. This is **PD3 exactly** — a rule applied in one prompt system only —
      and it happened to me while PD3 was already documented.
      Now `_urgency_directive()` is carried on EVERY intake plan (not just
      triage) and appended by all four gathering intents, and it deliberately
      includes an urgent issue that IS the current focus: that is precisely when
      the turn should lead with action instead of questions.
      `eval/drift/test_prompt_parity_offline.py` now asserts the rule exists on
      BOTH sides, so it cannot regress into one again. Suite: 26 passed.

- [x] **M14. A drafted document never checks whether a cited case still stands.**
      `agents/verification/agent._verify_draft` runs exactly two checks —
      citation-resolvable and fact-trace. The other five are declared and
      `_NOT_IMPLEMENTED`: `citation_not_overruled`, `ingredient_coverage`,
      `party_complete`, `limitation_pleaded`, `relief_mapped`. They are
      non-blocking and honestly marked, and `overall_ok` is judged only over the
      checks that actually ran, so nothing is being faked.
      `citation_not_overruled` is the one that matters most now that M1 makes the
      written OPINION the default output: the consult path already has
      `_search_adverse_authority`, and the drafter — the higher-stakes surface,
      because its output is a document the client keeps and acts on — does not
      use it. A drafted opinion can therefore rest on a judgment that has since
      been overruled without anything noticing. The machinery exists; only the
      wiring is missing, which is the same shape as B12 and H5.
      Verified by inspection: no reference to adverse authority anywhere under
      `agents/verification/` or `agents/drafter/`.

### Second matter (advocate register) — run 2026-08-23

A deliberately unalike matter: industrial death + factory regulation + tenancy +
consumer + a dishonoured cheque, advocate audience, its own straddle of the
cutover. Run so a fix could not be tuned to one scenario. Saved to chat history.

Matter A (client) after the M1-M13 fixes: T5 advising 1,932 words with the
objective captured and the key dates computed; T7 **3,945 words, deliverable
`opinion`** — against 118 and 19 words before. Matter B then exposed one root
cause behind two failures:

- [x] **M18. The advising trigger was a phrase list, and it did not
      generalise** — `FIXED 2026-08-23`. `_advising` decides whether a turn gets
      the case theory, companion provisions, precedents, adverse authority and
      the deterministic KEY DATES. It was decided by `_WANTS_ADVICE_RE`.
      Measured across the two matters:
        "what are my options and what do you recommend I do first?"  -> matched,
        1,932-word advising turn with key dates.
        "what is the exposure across all of this, and what would you move
        first?" -> DID NOT match: **99 words about one issue**, ending in a
        request for more evidence, on a matter with **14 settled charges**.
      Same question, different words. Widening the regex would be the growing
      patch this project rejects, so the decision now comes from the model's own
      reading of the turn: a new `wants_analysis` field on
      `ClientTurnClassification` — "is this asking me to ASSESS the matter
      rather than RECORD facts about it" — taken on the classification call that
      ALREADY runs every turn, so it costs nothing extra. The regex stays as a
      fast path.
      It needed its own prompt block: placed under the existing
      `wants_direct_guidance` text — fifteen lines teaching that exactly these
      questions are FALSE — it had no examples of its own and sat beneath
      contrary instruction. QUESTION 1B now states that the same message is
      routinely `wants_direct_guidance=false` AND `wants_analysis=true`, with
      worked examples. 7/7 on both phrasings and on fact-supplying turns.
      The classification is also hoisted so it applies to THIS turn rather than
      the previous one, and the intake block reuses the result — it needs only
      the prior focus and the message, not this turn's charges.
      **Measurement note:** the first reading of this field showed "always
      false" and was a TEST BUG — `classify_client_turn` returns a dict and the
      probe used `getattr`, which silently defaulted. The restructure stands on
      its own reasoning; it was never shown to be fixing a live failure.

- [x] **M19. No key dates on a matter with a live §138 clock** — `FIXED by M18`.
      **Verified on the re-run:** key dates went 0 -> 1-2 per turn from T3
      onward, on the same matter that had none at all.
      Matter B had a cheque dishonoured 20/05/2026 with notice not yet sent —
      the §138 chain was live and decisive — and `key_dates` was **0 on every
      turn**, while the same computation worked on matter A. Not a date bug:
      `_compute_key_dates` runs only inside `if _advising:`, so the phrase-list
      miss above meant it never ran at all. One root cause, two symptoms, and
      the more dangerous symptom was the silent one.

- [x] **M20. Amending Acts were being settled as governing law** — `FIXED
      2026-08-23`. Matter B settled a consumer claim on **§8 of the Consumer
      Protection (Amendment) Act, 2002**, whose entire content is *"Substitution
      of new section for section 12"*. A provision of an amending Act governs no
      conduct at all — the change it makes is read into the PRINCIPAL act, which
      is what a charge must cite. Two independent guards, both structural:
        - `_NON_GOVERNING_RE` now covers amending mechanics (substitution of new
          section, amendment/insertion/omission of section, "shall be
          substituted/omitted"). Verified it still passes real offences —
          "Punishment for causing death by negligence" and "Striking gear and
          devices for cutting off power" are untouched.
        - a charge resolved onto an act whose `_statute_kind` is `amendment` is
          gapped outright, with the reason recorded on the charge.
      Fixing that exposed a second bug in `_statute_kind` itself: it tested for
      `_amendment_` with underscores, so it saw
      `the_indian_evidence_amendment_act_2002` but missed
      `UNION OF INDIA_2002_8_THE CONSUMER PROTECTION (AMENDMENT) ACT, 2002` —
      the same two-naming-schemes split as M15/B18. It now matches "amendment"
      as a word whatever separates it (and NOT with `\b`, since `_` is a word
      character and there is no boundary in "amendment_act" — the very shape
      being caught). Corpus-wide the count of correctly-classified amending acts
      went **141 -> 268**: nearly half were being read as canonical statute, and
      therefore as firm statutory footing.

- [x] **M26. The checklist vanished from saved runs — my saver, not the
      product** — `FIXED 2026-08-23`. Reported as "the checklist seems to have
      disappeared".
      **The pipeline was never at fault.** Checklist sections per turn across the
      saved runs: A `[2,5,6,6,7,7,7]`, A-v3 `[2,4,5,5,6,6,6]`, B-v1
      `[1,5,8,10,11,11]`, B-v4 `[3,6,8,10,10,10]` — built correctly and growing
      monotonically every time.
      What broke was `scripts/save_run_to_history.py`. The runner flattened the
      checklist for its own reporting — a bare list, items as plain strings — and
      that flattened form was handed straight to `save_run` and persisted. The
      frontend requires `checklist && Array.isArray(checklist.sections)` and
      **explicitly nulls it otherwise** (`App.jsx` 2793 / 2853 / 3626), so the
      panel disappeared. Worse, opening such a chat made the frontend sync its
      own normalised (null) version back, destroying the stored copy — which is
      how one chat ended up with `checklist: null` outright.
      `intakeState` had the same problem: issues persisted as
      `["Negligent Death", 2, true]` tuples where dicts were required.
      Fixed at the saver, which is the last thing between a good run and what the
      user sees, so it now REPAIRS the shape rather than trusting its caller:
      `_normalise_checklist` and `_normalise_intake_state` accept dicts, tuples
      or bare strings, preserve a real checklist untouched (including item
      status), and return None for anything unrecognisable so the key is dropped
      — an absent panel is recoverable, a corrupt one that overwrites good data
      is not. Unit-tested.
      All seven saved runs repaired in place and verified to render: 7, 7, 6, 11,
      9, 11 and 10 sections.
      Lesson worth keeping: a reporting convenience in a throwaway runner reached
      the product's own database and looked like a product regression.

- [x] **M27. Drive the checklist to a terminal state before advising** —
      `SHIPPED 2026-08-23`. Requested: iterate the checklist, mark each item
      completed / not available / pending, gather the rest from the client, do a
      final check, then produce the opinion.
      Most of the machinery existed — items already carried `done` / `missing` /
      `open`, mapped from the gate's `provided` / `absent` / `pending`. Two
      things were missing, and the first was a correctness bug:
        - **An item the gate never judged was marked `done`.** The renderer
          defaulted to done whenever the ISSUE was covered, so an issue closed on
          one supplied document displayed ALL of its items ticked, including ones
          never mentioned. Measured: 1 of 3 items actually supplied, 3 of 3 shown
          complete. The honest default is `open`; `nothing_more` is the one case
          where unjudged means genuinely unavailable.
        - **Nothing drove the remaining items to a conclusion.** Working an issue
          to "covered" never guaranteed its items had been raised at all.
      Added two phases between gathering and assessment:
        `sweep` — puts the outstanding items to the client in ONE grouped
        question (batches of 5, at most 3 sweeps), explicitly inviting "I don't
        have it" as a real answer that records the item unavailable. The gate had
        to learn to judge across issues for this: in a sweep there is no focus
        issue, so `classify_client_turn_for_state` passes the batch, and
        `_apply_sweep_gate` routes each judgment back to the issue that owns the
        item — without that the client's answer was heard and discarded and the
        sweep re-asked the same things.
        `review` — reads the record back once ("N in hand, N could not be
        obtained, N outstanding"), names what is missing and what its absence
        costs, and asks whether to proceed. It runs ONCE, so it is a checkpoint
        and not a loop, and a client can still override it by asking for the
        advice directly.
      `_item_status` is now the single definition shared by the renderer, the
      sweep and the review, so the three can never disagree — the checklist
      cannot show an item as supplied while the sweep is still chasing it.
      Both new intents got structured goals (`_STRUCTURED_INTENTS`) as well as
      guidance-path renderers; without the former they would have fallen through
      to the full consult agent, which answers at length instead of asking the
      one grouped question these turns exist for.
      Order is now `ingredients -> sweep -> strength -> review -> assessment`,
      and the Actions block still appears only at assessment.
      **The deliverable gate — added after a live run showed the close-out
      never firing.** The first live test produced the opinion with SIX items
      still open and no sweep at all. Cause: `query_planning` RETURNS EARLY for a
      drafting request (line ~469, when charges already exist), skipping the
      whole intake block — so a check placed inside that block could never run.
      Two wrong guesses were eliminated by measurement first (`short_response`
      and `wants_analysis` both classified correctly on the actual turns), and
      `advance()` was proved correct in isolation against the run's own saved
      state before looking further up.
      The gate now sits at that early return: if a document is requested while
      items are open or the record has not been read back, the request is HELD
      (`pending_deliverable`, carried on state so the client asks once), the
      intake phase is forced to `sweep`/`review`, and the turn closes the list
      instead. Verified live — turn 2 answered "Please prepare the written
      opinion" with: *"Before I prepare the written opinion, let's finalize a
      few details… I need to confirm whether you have a copy of the bounced
      cheque, the bank memo…"*, and items moved 0/0/4 to 2 done / 1 unavailable /
      1 open as the client answered.
      Only the DELIVERABLE waits. An advising turn still answers immediately —
      "what should I do" gets told, and the answer now carries the checklist's
      honest state anyway.
      `eval/drift/test_checklist_closeout_offline.py` (6 tests) covers all of it,
      including the two ways it could trap a conversation: a client who never
      answers the sweep (capped, remainder recorded unavailable) and a matter
      with no gaps (sweep skipped, review still runs). Offline suite 26 -> 32.

- [x] **M28. Browser run of a new multi-dispute matter — close-out verified,
      one defect found and fixed** — `2026-08-23`. Driven through the real UI at
      :8080 as a user would, on a matter unlike the earlier two: a Kukatpally
      flat-owners association with a hidden mortgage and an auction notice,
      undelivered common areas and OC, and the builder renting out the parking.
      **What the live product got right**
        - Checklist rendered **0/7 with every item open** — the honest-status fix
          (M27) visible in the product; nothing falsely ticked.
        - Triage named the three distinct matters and flagged them as
          time-sensitive (the urgency wiring, M6).
        - Matter board filled in: forum "Telangana High Court — Writ", stage
          "pre-litigation", **relief "injunction restraining auction of the
          property"** — M8/M13 working, where relief had been None on all seven
          turns of the previous audit.
        - Grounding honesty unprompted: *"There is no directly-retrieved statute
          that lays down the exact remedies for your hidden-mortgage fact
          situation… I will mark clearly where I am generalising from principle
          and where the corpus is silent"*, then cited Ishwar Dass Jain v. Sohan
          Lal for what the court actually analysed.
        - **The close-out gate held the document.** "Please prepare the full
          written opinion" was answered with one grouped question closing off the
          checklist, explicitly inviting "I don't have them or can't get them" as
          an answer and offering to explain how each is normally obtained. Items
          moved 2/12 -> 4/12 as answers landed.
      **The defect, and it was mine.** The client then said *"That is everything
      we have. Please go ahead with the opinion now"* — and was asked ANOTHER
      round. Two causes compounding: spotting new issues GREW the agenda (12 ->
      17 items), so the sweep kept finding fresh gaps; and the gate set
      `_client_said_stop = False`, which overrode the client's explicit
      instruction to proceed. A client must always be able to override.
      Fixed with a bounded hold (`_CLOSEOUT_HOLD_CAP = 2`) rather than
      phrase-matching "go ahead": a document asked for twice is a document the
      client wants on the record they have, and the outstanding items are carried
      into the opinion as gaps — which is what its "could not be obtained"
      section exists for. Structural, so it cannot be defeated by phrasing.
      **Not yet re-verified in the browser** — the fix is unit-covered and the
      offline suite is green (32), but the live re-run is outstanding.

- [x] **M29. The close-out gate was blind to any issue it had not yet worked
      up** — `2026-08-25`. Found by running a four-dispute matter (partner
      siphoning firm funds, an 18-lakh cheque dishonoured on 4 Aug 2026, an
      employee's illegal-termination claim, and CAD drawings walked out of the
      door) through the real UI. The client asked for the written opinion and
      **got it**, with three of the four issues never having had a single
      question put on them.
      **Root cause, and it was general.** An issue that has been SPOTTED but not
      yet worked up carries `needs = []`. The renderer synthesised a placeholder
      row for it ("establish the facts and evidence for this issue") and showed
      it open — but `_open_needs`, `checklist_summary`, `_apply_sweep_gate` and
      `_mark_unresolved_as_missing` each re-derived their own item list by
      iterating `needs`, found nothing, and concluded the record was closed. So
      the UI said three issues were untouched while every engine-side caller
      said the matter was ready to advise on. Five callers, five enumerations.
      Measured on the live state: renderer 3 open, `_open_needs` **0**.
      **Fix**: one shared enumeration, `_issue_items(iss)`, returning
      `(label, status)` and owning the placeholder — which is now a REAL item the
      gate can judge and the sweep can close. All five callers read through it,
      exactly as they already shared `_item_status`. The one deliberate
      exception is the back-fill sweep, which asks a model whether the client
      supplied each named thing: a placeholder is not something anyone can hand
      over, and a guessed "provided" there would silently close an issue nobody
      had asked about. Commented in place so it is not "fixed" into consistency.
      Replaying the exact live state through the fix: 3 open, gate holds.
- [x] **M30. The hold set the phase on the wrong branch, so it held the
      document and produced it anyway** — `2026-08-25`. `_es0["phase"] = "sweep"`
      sat on the cap-REACHED branch instead of the branch that holds. So a held
      turn fell through with the phase still at `assessment`, `advance()`
      returned `assess`, and the assessment reply read as the very opinion the
      client had asked for — the hold was cosmetic. On the release branch the
      same line was worse than useless: it sent the matter back to gathering
      after the document had already gone out. Moved to the hold branch. The
      release now logs at WARNING, not INFO — a client receiving a document
      built on a record NM knows is incomplete is worth seeing in the log.
      **Verified live, end to end** (Warangal succession matter — forged will,
      mutation, and an evicted eleven-year agricultural tenant):
        - T2 "Please prepare the full written opinion" -> **held**. State:
          `pending_deliverable='opinion'`, `deliverable=None`, `phase='sweep'`,
          `closeout_holds=1`. NM asked one grouped question naming all six
          outstanding items and invited "say if you don't have something".
        - T3 client answers and says *"That is everything we have. Please go
          ahead with the opinion now"* -> **held once more** (`closeout_holds=2`,
          the cap). Checklist moved to 3/6 with honest marks: the will they have
          never seen recorded ✗, mutation records and witnesses ✓.
        - T4 -> **released**, without the client having to ask a third time.
          Log: `closeout: hold cap reached — producing opinion with 2 item(s)
          still outstanding`. The Opinion rendered, 7/7 traceability checks.
      The client is still asked once after saying "go ahead" — that is the
      bounded trade-off, and the cap is what guarantees it ends.

- [x] **M31. The delivered opinion leaks internal identifiers to the client**
      — `2026-08-25`, from the same live run. Three separate leaks, all visible
      in the rendered document a client is invited to download as DOCX:
        - **Retrieval chunk ids as citations.** Every authority reads
          `[SC_1961_RANI_PURNIMA_DEVI_AND_ANOTHER_VS_KUMAR_KHAGENDRA_NARAYAN_DEV_AND_ANOTHER_P018_C01]`
          and `[bharatiya_nyaya_sanhita_2023_SECTION_338]`. The consult path
          renders the same authorities cleanly (a linked `§336`, "Urmila Devi vs
          Balram"), so the drafter is missing the citation rendering the consult
          path already has.
        - **`[[GAP: ...]]` markers.** "[[GAP: expert opinion on handwriting]]",
          "[[GAP: evidence of eviction]]", "[[GAP: specific counterclaims not
          identified]]" — an internal marker for "the record does not cover
          this", printed raw.
        - **"Relevant Case Laws: Result 1, Result 2, Result 3, Result 4"** —
          placeholder labels where the case names belong.
      Each is a rendering defect, not a reasoning one, and none is
      scenario-specific: they appear on every deliverable.
      **Fixed** `2026-08-25`. Same two-owners shape as M29: `_strip_trace_tags`
      already stripped bare chunk ids, but it ran only on the DOCX/markdown
      path — and the chat is what the client actually reads. The chat path was
      separately converting `[[case:<chunk_id>]]` to a bare `[<chunk_id>]`, on
      the theory that the frontend resolves it; it only does so when that chunk
      is in the turn's authority list, and on a deliver turn it often is not.
      Now the renderer owns what a trace tag becomes: `humanise_trace_tags`
      resolves against the OUTLINE, so `[[stat:…]]` reads "[Bharatiya Nyaya
      Sanhita §338]" and `[[case:…]]` reads the case name. That degrades the
      right way — with the authority list present the readable form still
      linkifies (the frontend keys its map by "act §section" and case name too),
      and without it the client still reads the case name. A tag naming a source
      the outline cannot vouch for is dropped rather than printed. Doubled
      `[[GAP: …]]` is normalised here too, not just on the repair path.
      "Result 1 … Result 4" was one titling site in the frontend that read
      `title || act_name || source` and not `case_name`, which every other
      titling site there reads.

- [x] **M32. Every opinion section prints its own heading twice** —
      `2026-08-25`. "Facts as Instructed / Facts as Instructed", "Issues for
      Opinion / Issues for Opinion", and so on for all nine sections: the
      outliner emits the heading and the section body opens by restating it.
      One of the two owners should stop.
      **Fixed** `2026-08-25`. The heading is ours and styled; the echo is the
      model's and is not — so the echo goes. `_drop_heading_echo` matches on
      normalised text and only at the very top of the body, because a heading
      phrase recurring later in the prose is ordinary writing.

- [x] **M33. A buildings rent-control Act was applied to an agricultural
      tenancy — wrong law, confidently reasoned** — `2026-08-25`. The most
      serious finding of the run, and a live instance of the M21 lexical
      collision landing on the merits rather than in a citation label.
      The matter: a tenant who had farmed agricultural land for eleven years,
      evicted, now claiming occupancy rights. The opinion analysed it under
      **§10(1) of the Telangana Buildings (Lease, Rent and Eviction) Control
      Act, 1960** — a statute whose own title says *Buildings* — and built the
      analysis on buildings-tenancy authorities (Majati Subbarao; P. J. Gupta,
      which is about sub-letting *premises*). The controlling instrument for
      agricultural occupancy rights is the Tenancy and Agricultural Lands Act.
      It then asserted a limitation rule the cited provision does not contain
      ("a tenant can challenge an illegal eviction within one month").
      Nothing objected, because "tenant / eviction / occupancy" matches the
      rent-control corpus strongly on the words. What is missing is any check
      that the SUBJECT an act governs matches the subject of the matter — here,
      land against buildings. The grounding guard verifies that a cited
      provision exists and is quoted correctly; it never asks whether it is the
      right provision to be quoting.
      **Do not re-apply the M21 subject-gate as written** — that version
      destroyed correct charges (measured 2/3, then 2/4) and was reverted. This
      entry is the strongest evidence yet for solving the problem, not a licence
      to reapply the fix that failed.
      **Fixed** `2026-08-25` — and the measurement changed the diagnosis
      entirely. This was never a semantic-similarity failure.
        - The RIGHT Act is in the corpus and richly so: the Telangana (Telangana
          Area) Tenancy & Agricultural Lands Act, 1950 carries 580 chunks.
        - The Act NM used holds **ten sections in total** (16-18, 23, 25-29, 31).
        - **There is no §10 of it in the corpus at all.** Zero chunks.
      So NM cited a provision nobody retrieved, quoted what it requires and
      stated a limitation period from it, out of parametric memory — and the
      traceability verifier reported 7/7, because the chunk it was tagged to was
      real and the act name was real. Nothing compared the section the charge
      NAMED against the section of the chunk it rested on.
      That comparison needs no model and no judgement about subject matter, so
      that is the fix: `_verify_cited_sections` demotes a charge whose claimed
      section is not the section of its own chunk. It FAILS OPEN — only an
      affirmative mismatch, both sides parsing and differing, demotes anything;
      a prefix either way (§10(1) against a chunk numbered 10, §10 against 10A)
      is the same section. The M21 attempt fired when it could not confirm and
      destroyed correct charges; a check that acts only on positive evidence of
      fabrication cannot.
      **Measured before shipping: 240 matters, 722 comparable charges, 5
      demoted (0.7%), zero false positives.** All five are the same real defect
      — the CrPC's FIRST SCHEDULE, which is a table of *IPC* offences, being
      cited as sections of the CrPC: "§420 of the Code of Criminal Procedure,
      1973" against chunk `Schedule_FIRST_SCHEDULE_420`. §420 CrPC does not
      exist; §420 is IPC. Also caught §386, §467, and §92 of the NI Act against
      its Schedule I.
      **What this does NOT fix**, and M21 stays open for it: why a
      thinly-ingested buildings rent-control Act outranked a 580-chunk
      agricultural tenancy Act for an agricultural tenancy in the first place.
      The wrong citation is now caught; the wrong ranking is not. The designed
      answer there is to judge an Act by its OWN scope clause (§1 application,
      §2 definitions) rather than by vocabulary overlap — the corpus carries a
      §1 or §2 for essentially every Act, so the data exists — and to fail open
      the same way. Worth noting for whoever picks it up: it would NOT have
      helped here, because this particular Act's §1 and §2 are among the
      sections missing from its ten.

- [x] **M36. Live run of a five-issue school matter — the render fixes hold, the
      law does not** — `2026-08-25`. Driven through the real UI on a matter with
      four unrelated disputes: a contractor who took 35 lakh and abandoned a
      school building in Nov 2025, a partner who forged the client's signature on
      a bank loan in **January 2023**, a school bus driver who killed a
      pedestrian in **February 2026**, and a landlord trying to evict against a
      registered lease running to 2029.
      **Verified working in the product**
        - Close-out: held the opinion twice and released on the third turn —
          `closeout: hold cap reached — producing opinion with 9 item(s) still
          outstanding`. Checklist 0/12 -> 3/17 -> 5 done / 1 missing / 9 open.
        - **M31/M32 confirmed on a fresh 25,939-character opinion**: chunk ids 0,
          `_SECTION_` ids 0, doubled `[[GAP:` 0, raw `[[stat/case/fact:` tags 0,
          duplicated headings none. Citations now read
          "[Bharatiya Nyaya Sanhita, 2023 §336(1)]" and
          "[Surjit Singh & Ors vs Balbir Singh, Supreme Court of India, 1996]".
        - Grounding honesty, unprompted: *"The retrieved corpus here does not
          actually reproduce §17 of the Limitation Act, 1963, so I cannot quote
          its text"*, and it declined to advise on bail or FIR procedure because
          the corpus lacked those provisions.
        - `_verify_charge_provisions` demoted BOTH culpable-homicide charges to
          gaps on the element check — it is doing its job.
      Everything below was found by the same run and is NOT fixed.
- [x] **M37. `conduct_era` is inert — it resolves for 4 matters in 250** —
      `2026-08-25`. Measured across every matter on record: `conduct_era` is
      `None` for **246 of 250**, `''` for 2, and an actual value (`'new'`) for
      **2**. So the whole era apparatus — `_conduct_era`, `_dated_events`,
      `_prefer_era_provisions`, the asymmetric backward/forward burden — almost
      never has an era to act on, and the rule it exists to enforce cannot fire.
      Live consequence, on the standing instruction that conduct before July
      2024 is governed by the old codes: a forgery committed in **January 2023**
      was charged under **§336(1) and §340(1) of the Bharatiya Nyaya Sanhita,
      2023**, which did not commence until 1 July 2024. The correct provisions
      are IPC §§463/465/471. The opinion mentions the BNS repeatedly and the IPC
      not once.
      This is the highest-value open item: it is a correctness rule the owner has
      stated explicitly, the machinery to enforce it already exists, and it is
      simply not being fed. Start by finding why `_conduct_era` returns nothing
      on a matter whose facts carry four clearly dated events.
      **Fixed** `2026-08-25`, and the earlier reading of it was wrong: `None`
      for 246 matters is HISTORICAL — the field predates them. All four recent
      matters carry it, and `''` on a multi-date matter is the resolver
      abstaining exactly as designed. The real defect was in two places.
      Upstream, `_ISSUE_PROMPT` said "Use the law IN FORCE in 2026 … NEVER use
      repealed IPC / CrPC / Evidence Act names", so BNS-only search wording was
      settled before any charge existed and no era swap could recover a
      provision that was never retrieved. That instruction now follows the DATE
      of the wrong, and asks for both codes where the date is unstated or the
      matter spans 1 July 2024.
      Downstream, the per-charge fallback — the one that matters precisely when
      the matter-level era abstains — re-derived an era from `issue` + `why`,
      which are labels. Measured: `_dated_events` returned `[]` for every charge
      of every recent matter, so it could never fire. Issues now carry `when` in
      the client's own words, `_stamp_conduct_when` copies it onto the charges
      and `_charge_era` reads it. On the live example the January 2023 forgery
      dates as `old` and the February 2026 accident as `new`, on one matter.

- [x] **M38. One checklist section bundled two unrelated issues from different
      eras** — `2026-08-25`. The agenda opened with a section titled **"Forgery
      and Culpable Homicide Incident"**, merging the January 2023 loan forgery
      with the February 2026 fatal road accident — different parties, different
      forums, different codes, three years apart. Its checklist items sat
      together ("copy of the forged loan application" beside "police report of
      the accident"), and the sweep asked about them in one breath.
      Beyond being confusing, the bundling is causally linked to M37: an issue
      carries ONE era, so merging conduct from either side of a commencement
      date forces one of the two onto the wrong code. Later turns did split the
      agenda into five issues, so the defect is in the FIRST pass of issue
      spotting, before any charge is settled.
      **Fixed** `2026-08-25`. The issue prompt now forbids merging two wrongs
      into one issue, naming date, wrongdoer and forum as the things that keep
      them apart, and carries the live example.

- [x] **M39. A key date was fabricated, in the client's own diary** —
      `2026-08-25`. The matter board carried:
      `{"label": "Eviction compliance period", "date": "2023-10-01",
      "period": "30 days", "from_event": "eviction notice received",
      "from_date": "2023-09-01"}`.
      The client said the eviction notice arrived **last month** — July 2026.
      Nothing in the conversation mentions September 2023. The 30-day period was
      taken from §5(2) of the Act NM had wrongly picked (see below) and anchored
      to an invented date three years off.
      This is worse than a wrong citation, because a key date is exactly what a
      client acts on. A date must be derived from an event the client actually
      dated, or not shown at all.
      **Fixed** `2026-08-25`. The PERIOD a rule applies was already corroborated
      against the provision's own text; the ANCHOR date was taken from the model
      on trust, and it invented one. An anchor now has to trace to something the
      client wrote — the year appears in their own words, or they dated it
      relatively and the anchor lands within about a year of today. Anything
      else is dropped with a warning rather than shown.

- [x] **M51. The ingestion list for the three launch practice areas** —
      `2026-08-26`, from `scripts/area_gap_report.py`. Every governing statute
      and landmark authority for land & revenue, matrimonial and bail checked
      against the corpus. **Nine items missing in total** — a small, bounded job,
      not the corpus-wide problem earlier entries described.
      **Statutes (7)**
        - Registration Act, 1908 — §17, §49, §22A. The single most valuable one:
          unavoidable in land work, and the corpus holds only Rules made under
          it whose numbering collides with the Act's (see M50).
        - Indian Stamp Act, 1899 — §35, impounding and admissibility.
        - Indian Easements Act, 1882 — rights of way, prescription.
        - Guardians and Wards Act, 1890 — custody, and the procedural companion
          to the Hindu Minority and Guardianship Act, which IS present.
        - Indian Divorce Act, 1869 — Christian matrimonial.
        - Muslim Personal Law (Shariat) Application Act, 1937.
        - Parsi Marriage and Divorce Act, 1936.
      The last four together mean NM can currently only answer HINDU matrimonial
      matters properly. Muslim Women (Protection of Rights on Marriage) 2019 and
      on Divorce 1986 are present, so the gap is the personal-law framework
      rather than the whole subject.
      **Judgments (2)**: Vidyadhar v. Manikrao (proof of a sale deed and the
      presumption of consideration), and Amardeep Singh v. Harveen Kaur (waiver
      of the six-month cooling-off under HMA §13B(2)) — a case cited in almost
      every mutual-consent divorce.
      **Everything else is present**, including the whole bail statute set (BNSS,
      CrPC, NDPS, PMLA, UAPA, POCSO, SC/ST, JJ, PC Act, Arms) and 22 of 24
      landmark judgments checked.
      **The script's own history is the warning.** Three separate false readings
      before the numbers above could be trusted: `act_id` uses underscores so a
      LIKE missed the CrPC entirely; the Rules made under an Act satisfy both a
      name match and a section-number probe, which is how the Registration Act
      read as present three times; and a single party name is not identification
      — "Arnesh Kumar" matched "KARNESH Kumar Singh", "Rajnesh" matched a dairy
      federation's case, "P. Chidambaram" a 1960s partition. The script now
      excludes subordinate instruments and requires BOTH parties to match.
      **Closed** `2026-08-26`. All seven Acts ingested from Indian Kanoon
      (`scripts/fetch_acts_ik.py`), 1,422 chunks, with act summaries written and
      the bare-act BM25 rebuilt. Retrieval probe on the provisions each practice
      area turns on: **8/8 found, 6 at rank 1**, the other two at 2 and 3 behind
      genuine competing provisions (Limitation Act s.25 for prescriptive
      easements, Hindu Minority and Guardianship s.13 for welfare of the minor).
      **The two judgments were not two.** Amardeep Singh v. Harveen Kaur was
      already in the corpus, ingested earlier and never noticed. Vidhyadhar v.
      Manikrao was already there too, as
      `SC_1999_VIDHYADHAR_VS_MANIKRAO_ANR` with all 63 paragraphs — **the fifth
      false gap** this entry's own warning predicted, and this time I ingested a
      duplicate on top of it before catching it. The duplicate has been removed
      and the corpus is back to 1,015,780 case chunks.
      Three defects were found by doing this and are fixed generally, not for
      these documents:
        - **A judgment ingested live was unreachable.** `search_case_laws` gates
          on the case-summary index before it reads a paragraph, and the
          incremental path seeded that entry with the case TITLE while the
          32,526 bulk cases carry a written summary. Both live-ingested
          judgments were retrievable by nothing, not even both party names.
          `scripts/ingest_case_summary.py` now writes a grounded summary, wired
          into BOTH owners of the ingest path. Amardeep went from absent at any
          depth to **gate rank 1 and 3**. This is the same bug
          `ingest_act_summary.py` was written to fix for bare acts, on the half
          of the corpus that was left behind.
        - **Dedup compared case_id, which is a SOURCE key.** The same judgment
          from a different feed always read as new. `case_identity()` compares
          parties and year instead. It finds 54 pre-existing duplicate
          identities in 33,737 judgments (0.16%, all bulk spelling variants like
          "Bhagwandas"/"Bhagwan Das") — left alone, since deleting them is a
          call for the corpus owner, not a side effect of this work.
        - **Indian Kanoon marks up the tables at the back of an Act with the
          same class as its sections.** The Parsi Act's schedule of prohibited
          degrees contributed a "32. Brother's son's wife." colliding with s.32,
          "Grounds for divorce" — M50's failure in a new place. A number already
          taken, on an element with no structure, is now rendered as a list item
          rather than a section: 69 impostors removed across the seven Acts,
          and the 24 genuine cross-part duplicates and 5 genuine one-line
          sections kept.
      Remaining and NOT fixed: s.22A of the Registration Act is a state
      amendment and is not in the central Act; and Amardeep still ranks 16-20 on
      its own subject, behind Manish Goel and Anil Kumar Jain, which is ordinary
      ranking competition rather than the unreachability this closed.

- [x] **M50. The Registration Act, 1908 is not in the corpus — only Rules made
      under it, and their numbers collide** — `2026-08-26`. Found by the land
      slice of the new benchmark, which scored 57% until this was separated out.
      What the corpus holds is "Andhra Pradesh Rules under the Registration Act,
      1908" (242 records) and "Registration (Andhra Pradesh Amendment)". The
      parent Act is absent. So **§17** (documents of which registration is
      compulsory) and **§49** (effect of non-registration) — two of the most
      cited provisions in Indian property practice, and unavoidable in land
      work — cannot be retrieved.
      Worse than absence: the Rules are numbered 1..242, so a query for "section
      17 of the Registration Act" lands on **Rule 17**, a different instrument
      saying something else entirely. An absent Act produces an honest gap; a
      colliding one produces a confident wrong answer.
      It also defeated my own label validator, which matched the act name as a
      substring and reported 44/44 labels present. The validator now prints
      WHICH record satisfied each label, which is what made this visible.
      **This is a small, precise ingestion job** — one central Act, about 90
      sections — not the corpus-wide problem M17 was written up as. It is the
      highest-value single ingestion for the land and revenue practice area.
      Until then the benchmark marks these expectations `blocked` and excludes
      them from the score, so an ingestion gap cannot be mistaken for a pipeline
      failure: land reads 4/5 (80%) scored, with the two Registration Act
      expectations reported separately.
      **Closed** `2026-08-26`. The Registration Act, 1908 is in the corpus: 96
      sections, 403 chunks, ingested from Indian Kanoon. A query for "documents
      of which registration is compulsory" now returns
      `the_registration_act_1908 s.17` at **rank 1**, and "effect of
      non-registration of a sale deed" returns **s.49 at rank 1**. The collision
      this entry was written about — s.17 of the Act answered by Rule 17 of the
      AP Rules — no longer decides the query.
      The assumption that blocked this was that a person must download the PDFs,
      because India Code 403s automated fetchers and a general web fetcher
      returns a model's RENDERING rather than the bytes. Indian Kanoon is
      neither: it serves the real text as **Akoma Ntoso**, so sections,
      subsections, clauses and provisos arrive already delimited instead of
      being recovered from PDF whitespace — strictly better than the corpus's
      existing bare-act sources. See `ingestion/acts_indiankanoon.py`.

- [x] **M48. CORRECTION — the 38.5% was wrong, and so was closing M21** —
      `2026-08-26`. Three findings in this file rested on joining `legal.db`'s
      `acts` table to `chunks.db` on `act_id`. That join is invalid: the corpus
      records the same Act under several act_ids, so an Act reads as empty under
      one while its full text sits under another.
      **Corrected coverage.** Of the 613 Acts that looked empty by id, **570
      have their text under a different record of the same Act**. The real
      figure is **43 of 1,592 (2.7%)**, not 38.5%, with a further 4 Acts (0.3%)
      below 75%. Matching records to Acts is done on the normalised name, so
      even 2.7% is a ceiling rather than a floor. Corpus coverage is therefore
      NOT the launch blocker it was written up as.
      **M21 was real and I closed it wrongly.** I reported 0.0% cross-record
      duplication in retrieval pools and read it as "the act gate collapses
      duplicates correctly". It is equally consistent with only ONE record
      surviving — and the surviving one being the wrong one, which is what was
      happening.
      **M33 was mis-diagnosed too.** §10 of the Telangana Buildings (Lease, Rent
      and Eviction) Control Act is in the corpus, in full: "Eviction of tenants:
      (1) A tenant shall not be evicted whether in execution of a decree or
      otherwise except in accordance with the provisions of this Section", under
      a 38-section record of 264 chunks. Beside it sit TWO 10-section records of
      10 chunks each, and retrieval landed on a stub. So NM was not citing a
      provision nobody had; it was reading a crippled copy of an Act whose
      complete copy was one record away. (The `_verify_cited_sections` guard is
      still right to fire — the charge cited §10 while grounded on a §26 chunk —
      but the framing "not in the corpus" was wrong.)
      **Fixed.** `_act_ids_by_gate_key` now drops a record that is badly thinner
      than the best record of the same Act (below 40% of its section count, and
      only where the best is substantial). A stub is strictly worse than the
      full record — everything it holds, the full record holds — so it is
      removed rather than reranked. **719 stub records dropped**, 2,481 act_ids
      retained across 1,614 gate keys. A search for "eviction of tenants from a
      building under rent control" now returns §10 from the full record at rank
      1; before, the stubs competed and §10 was unreachable.
      Recall benchmark still 6/6, offline suite still 40.
      **The lesson worth keeping**: 0% of something bad is not evidence of
      health until you have checked it is not 0% because the population is
      already gone. And any measurement keyed on `act_id` in this corpus is
      wrong until it is collapsed by Act.

- [x] **M45. Case-law paragraph classification existed and was thrown away** —
      `2026-08-25`. Every case chunk carries `paragraph_num` AND
      `paragraph_type`, classified as ratio / reasoning / arguments / facts /
      order / headnote (measured over 600 sampled chunks: 179 reasoning, 169
      ratio, 116 arguments, 63 facts). `_ATOM_TYPE_PRIORS_CASE` already
      expressed the right preference — ratio above all — and was **completely
      inert**, because it read `atom_type`, which is a bare-act field and is
      `None` on every case chunk. Its vocabulary (holding, obiter, issue) also
      did not match the corpus's, so most of the table described nothing.
      Fixed in three places: the prior reads `atom_type or paragraph_type`, the
      table now speaks the corpus's own vocabulary, and the case-result builder
      carries `paragraph_type` through (the OTHER case-result builder already
      did, so the same chunk described itself differently depending on which
      path returned it).
      **`arguments` is now scored BELOW zero, deliberately.** An arguments
      paragraph records what counsel submitted, not what the court held, and
      quoting one as authority is citing the losing side's case as the law — the
      one paragraph type that is actively misleading rather than merely
      unhelpful.
      Measured before/after on a Hindu-succession query: `paragraph_type` was
      `None` on every result; it is now 6 ratio + 2 reasoning + 0 arguments.
      Precedents attached to charges now carry the paragraph and its type, and
      the AUTHORITATIVE CHARGES block renders "Mangal Singh v. Rattno (Supreme
      Court of India, 1967) para 17.2 [ratio]" — a citation an advocate can use
      without re-reading the judgment to find the passage NM already held.
- [x] **M46. Advocate-only: the client register is gone** — `2026-08-25`, on the
      owner's decision. Advising a lay client in the first person is what raises
      questions under the Advocates Act and the Bar Council rules, so the
      product no longer offers it.
      Pinned in depth rather than defaulted: `_select_audience_and_template`
      normalises ANY incoming audience to `advocate`, the intake turn does the
      same, every `(state.get("audience") or "client")` fallback across the
      orchestrator and the intake engine now falls back to `advocate`, and the
      UI toggle is replaced by a static label that also clears the persisted
      `nm_audience` key. So a stale browser setting, a stored matter replayed
      from history, or a request posted straight at the API cannot reopen client
      mode. Verified: `client`, `auto`, `advocate`, `None` and `nonsense` all
      resolve to `advocate`.
      Landing copy changed with it — "Your senior advocate, on call" was a claim
      made to a client; it now reads as what the product is to counsel.
- [x] **M47. "I do not have that Act" is now the answer, not a hedge** —
      `2026-08-25`, on the owner's decision to leave the corpus as it stands.
      A gap used to render as "governing provision did NOT surface in retrieval
      — say you'll confirm the exact section", which invites the model to fill
      the space from memory. It now renders as **NOT IN THE CORPUS**, with the
      instruction to say in one plain sentence that the governing Act or section
      is not held and so the law on it cannot be stated, to say what it WOULD
      look at, and explicitly not to reason from memory of what the Act probably
      says. The turn-level rule carries the same words: *"I do not have the Act
      that governs this, so I cannot state the law on it."*
      With 38.5% of Acts holding no retrievable text (M17), this is the
      behaviour that makes that survivable: saying so costs an advocate nothing
      and guessing costs them the point.

- [x] **M44. The controlling provision is in the corpus and is not retrieved —
      the failure that matters most for selling this** — `2026-08-25`, from the
      pre-production audit. A Hindu woman died intestate in April 2026 leaving a
      flat; her husband claims a will nobody has seen; gold her mother had given
      her for safekeeping was taken from a locker; her employer will release
      gratuity and PF only to the husband.
      NM split the three issues correctly and asked sensible questions. What it
      cited was **§46C of the Code of Civil Procedure** — a real section, which
      is why `_verify_cited_sections` did not fire, and which sits in the
      EXECUTION chapter (§§46-46E, precepts and attachment). It has nothing to
      do with wills. `_verify_act_subject` did not fire either, correctly: the
      CPC is a general code and is exempted by design.
      **What it never mentioned is the provision the whole matter turns on.**
      §15 of the Hindu Succession Act, 1956 — "General rules of succession in
      the case of female Hindus" — and specifically §15(2), under which property
      a female Hindu inherited from her mother devolves on her MOTHER'S heirs,
      not on her husband. On these facts that is close to dispositive for the
      gold, and it shapes the flat and the PF too.
      **The Act is in the corpus and complete**: 31 of 31 sections under
      `UNION OF INDIA_1956_1_THE HINDU SUCCESSION ACT, 1956`, §15 among them,
      with full text. So this is not M17 and not a coverage problem. It is
      RECALL: the governing section was there to be found and was not found.
      (Note the second record, `the_hindu_succession_act_1956`, holds 14
      sections and does NOT include §15 — the same split-record shape as M21,
      though here the good record exists and should have won.)
      Why this one matters more than the rest: every guard built so far checks
      that what NM SAYS is grounded. None of them can notice what NM never said.
      A confident, fluent, well-cited answer that omits the controlling
      provision is the product's worst failure mode, it is invisible to every
      check in the repo, and it is the exact thing a paying client would be
      harmed by. Nothing in `eval/` measures it either: the gold sets score
      behaviour (issues spotted, risk acknowledged, retrieval fired), never
      whether the right law was found.
      Fixing it needs a controlling-provision recall benchmark with
      lawyer-labelled answers — see the production-readiness plan.
      **Fixed** `2026-08-26`, by the facts-driven issue spotter and the
      unanchored-issue rescue rather than by anything aimed at this matter.
      Re-run on the exact failing facts: the spotter now returns "succession to
      property" as a merits issue and **HSA §15 comes back at rank 1**. Where it
      previously produced only "disputed will" and searched "execution of will",
      it now reaches the provision the matter turns on.

- [x] **M40. Two more wrong-Act citations on the merits — M21, restated with
      fresh evidence** — `2026-08-25`. Both survived every existing check,
      including `_verify_cited_sections` (the sections are real and match their
      chunks — it is the ACT that is wrong for the subject):
        - A contractor who abandoned a school building was analysed under
          **§31(2) of the Andhra Pradesh Forest Contract (Disposal Of Forest
          Produce) Rules, 1977** — matched, presumably, on "contract" and
          forfeiture of advance.
        - A **private** landlord evicting a school on a registered lease was
          analysed under **§5(2) of the Andhra Pradesh Public Premises (Eviction
          Of Unauthorised Occupants) Act, 1968** — a statute for evicting
          unauthorised occupants from GOVERNMENT premises, and the source of the
          fabricated date in M39.
      Same shape as the buildings-versus-agricultural-land error: the words match
      and the subject does not. It is now three independent live instances, which
      makes this the strongest-evidenced open defect after M37.
      **Partly addressed** `2026-08-25` — and the limit matters more than the
      fix. `_verify_act_subject` asks one narrow question, batched per Act:
      *is there ANY dispute in this matter that this statute governs?* Framing it
      per-matter instead ("is this Act about what the matter is about?") made it
      reject the penal code on a land matter, so the framing is the fix.
      **It FLAGS; it does not demote.** Measured over repeated runs, a single
      sample is not stable enough to destroy anything with: one run left an
      ordinary cheque matter untouched and the next rejected the penal code and
      the Specific Relief Act on it. So two independent samples must agree
      before anything is said, and even then the charge survives carrying a
      `subject_warning` that the answer must voice. A wrong charge a reader can
      see questioned is a much smaller harm than a right charge silently
      deleted, which is what the previous attempt did.
      Measured, 3 runs per scenario (`eval/drift/test_act_subject_live.py`):
      the buildings-Act-on-agricultural-land error flagged 3/3; across 14
      correctly-matched Acts in two controls — including the risky
      subject-limited ones, PWDVA, Dowry Prohibition, RERA, Consumer Protection
      — one false flag at 1/3, and **zero charges destroyed in any run**.
      **Still open**: the Public Premises (Eviction of Unauthorised Occupants)
      Act on a private landlord is NOT caught — a school reads as public
      premises to the model. And this catches the citation after the fact; it
      does nothing about why a ten-section stub outranked a 580-chunk Act in
      retrieval, which is the M21 half that remains.
      **Closed** `2026-08-26`. The remaining miss — the Public Premises (Eviction
      of Unauthorised Occupants) Act applied to a private landlord — is caught,
      and the check is now cleaner than when this entry was written.
      The fix is to stop reasoning from an Act's NAME. `_act_scope_text` feeds
      each subject-limited statute's own §1 and §2 into the question, so "public
      premises" is decided by the Act's definition of a corporate authority
      rather than by whether a school sounds public. Measured: **0/3 flagged
      before, 3/3 after**, with the right reason given.
      Two regressions were introduced and measured out on the way, which is the
      only reason the final numbers are trustworthy. Attaching scope text to the
      GENERAL codes worked against the exemption they already had — the penal
      code went from a false flag on 1 run in 3 to 3 in 3 on a domestic-violence
      matter — so scope text is withheld from them. Leaving the "decide from
      §1/§2" instruction in when no scope text was attached primed rejection on
      its own, so that instruction is now conditional on some Act actually
      carrying it. And the general-code exemption was too soft to hold, so it is
      now categorical: answering NO for a code of general application is always
      a mistake.
      Full control suite: **3/3 scenarios clean, zero false flags across 14
      correctly-matched Acts, zero charges destroyed in any run** — better than
      the 1-in-3 false flag this check shipped with.

- [x] **M41. Two sweep rounds cannot clear a seventeen-item checklist** —
      `2026-08-25`. `_SWEEP_BATCH = 5` and the close-out cap is 2, so at most ten
      items can be put to a client before the document is released. This matter
      released with **9 of 15 still open**. The cap is deliberate and the client
      must always be able to get their document (M28/M30) — but the opinion
      should then say plainly, in its own words, how much of the record is
      missing. Worth checking whether the "documents required" section actually
      reflects the nine, or reads as though the file were complete.
      **Fixed** `2026-08-25`. `build_outline_from_state` now carries
      `outstanding`, read through `_open_needs` so it is the SAME list the
      checklist shows and the close-out gate chases. The comment at the top of
      `outliner.py` always claimed `documents_required` was checklist-driven; it
      never was, which is why an opinion released with nine items open mentioned
      none of them. The drafter rules now require every outstanding item to be
      named, with its issue, and the opinion to say it is written without them.

- [x] **M42. Cosmetics in cited references** — `2026-08-25`. `§Order_XXXIX_Rule_2
      of The Code Of Civil Procedure` — an Order and Rule does not take a §, and
      the underscores are the corpus's internal section-number token showing
      through. Also `[(d)(i) of The Limitation Act, 1963 §17(1)]`, where the
      sub-clause has been split off in front of the act name. Both are in the
      section-number field rather than in prose, so they need normalising where a
      citation is formatted, not in the model output.
      **Fixed** `2026-08-25`. `_section_display` is the one place that decides
      how a section number is shown: a Schedule, an Order-and-Rule and an
      Article are not sections and take no §. Anything unrecognised is returned
      as-is rather than dressed up, so a new token shape shows through as itself.

- [x] **M43. A quarter of the new-code sections have no predecessor, so the era
      rule cannot move them** — `2026-08-25`. Found by the live run that
      verified M37. The era machinery now works end to end: the charge carried
      `conduct_when = 'August 2022'`, `_charge_era` returned `'old'`, and IPC
      provisions appeared in an answer for the first time. But one charge stayed
      on **§340(1) of the Bharatiya Nyaya Sanhita for August 2022 conduct**,
      because `_code_equivalent` returned `("", "")` — `predecessor('BNS','340')`
      is `None`. Nothing is wrong with the swap; there is nowhere to swap to.
      Measured across the corpus against `legal_database/succession_map.csv`
      (766 rows):
        - **BNS  — 105 of 358 sections unmapped (29%)**
        - **BNSS — 149 of 531 sections unmapped (28%)**
        - **BSA  —  44 of 170 sections unmapped (26%)**
        - **298 of 1,059 in total (28%)**
      So roughly one pre-July-2024 charge in four cannot be put on the code that
      governs it, however well the rest of the chain works. §340 BNS is "forged
      document or electronic record, and using it as genuine" — IPC §§470-471 —
      an ordinary provision, not an exotic one.
      This is a DATA job, not a code one: extend the succession map. The
      `era-swappable` check in `eval/audit_invariants.py` now counts the gap, so
      progress on it is measurable rather than anecdotal. Worth doing by
      marginal heading against both bare acts rather than by hand, and worth
      marking `verified` honestly — 258 of the existing BNS rows are
      `auto-heading` rather than confirmed.
      **Mostly closed** `2026-08-25` by `scripts/extend_succession_map.py`,
      which derives the mapping from data instead of memory: both codes are in
      the corpus with their marginal headings, and the sanhitas mostly reworded
      rather than renamed. **109 rows added, 766 -> 875, and the gap fell from
      298/1,059 (28%) to 189/1,059 (18%)** — BNS 14%, BNSS 19%, BSA 21%.
      Conservative by construction, because a wrong predecessor would move a
      charge onto the wrong old section and cite it confidently: exact or >=0.88
      heading match, unique on both sides, and where two old headings are both
      near, the best is taken only if it beats the runner-up by a clear margin
      (that is what resolves BNS §41 *property* against IPC §100 *body* / §103
      *property*). Every one of the 109 was read before it was written.
      **What is left is not fixable by matching.** Of the ~50 unmapped BNS
      sections, about 13 are MERGERS — BNS §340, the one from the live failure,
      is "forged document or electronic record **and using it as genuine**",
      which answers to both IPC §470 and §471, and this schema holds one
      predecessor per section. About 43 have no near counterpart at all and are
      genuinely new offences, correctly unmapped. Expressing a merger needs a
      schema change, not more matching.

- [x] **M34. The §138 notice deadline could not be stated — M17 biting at the
      worst possible place** — `2026-08-25`. In the four-dispute run the corpus
      copy of §138 had its **proviso truncated**, so NM could not give the one
      fact that mattered most to that client: the notice window running from the
      4 August 2026 return memo. Its handling was exemplary — it said plainly
      that the text it held was truncated, refused to quote a day-count it could
      not source, and told the client to have the full section verified before
      despatch. But a client who came for the deadline did not get the deadline.
      Concrete, high-value evidence for M17 (stub chunks): the gap is not evenly
      spread. It lands on provisos and time limits, which is exactly where an
      advocate is most relied on.
      **Fixed** `2026-08-26`, and the diagnosis recorded above was wrong. §138 is
      NOT truncated in the corpus: it holds 6 chunks and 1,794 characters — the
      head, clauses (a), (b) and (c), the proviso and an explanation — and TWO of
      them carry the thirty-day and fifteen-day periods.
      What retrieval returned was the 190-character section HEAD and nothing
      else. `_neighbor_expand_bare` skipped it deliberately: "section_head atoms
      are NOT expanded — they are already the coarsest unit and have no
      meaningful siblings". True of siblings, false of CHILDREN, and the children
      are where the operative text lives.
      A second defect sat underneath it. Walking the parent link from a head
      finds nothing either, because the head is `..._SECTION_138` while its
      children hang off `..._SECTION_138_OCC2` — an occurrence suffix the chunker
      adds when a section number appears more than once in an Act. So
      `_section_children` looks them up by (act_id, section_number), which is
      immune to the id shape.
      Measured on the query that failed live — "notice period after dishonour of
      cheque before filing complaint": **1 chunk carrying 0 periods, now 6 chunks
      carrying 2**. Recall benchmark unchanged at 85%, offline suite 40.
      This is general: any section head that wins a slot now arrives with its
      operative text, which is the same shape as B15.

- [x] **M35. A compound checklist item ticks done when half of it was
      supplied** — `2026-08-25`. "invoices and delivery challans showing what
      goods this cheque was issued against" went to `done` on a turn where the
      client said, in terms, *"I have the invoices too but not the delivery
      challans"* — and the missing half was never chased. Either such items
      should be split when generated, or a partial answer should hold the item
      open. Low severity alone; it quietly erodes the meaning of the checklist,
      which the whole close-out now depends on.
      **Fixed** `2026-08-25`. At both ends, and neither is a string-splitting
      hack: the charge resolver is now told each `needs` entry names ONE thing
      to obtain, and the per-item gate is told that an item naming more than one
      thing, only some of which the client has, is `pending` rather than
      `provided`.

- [x] **M24. The length budget counts NM's own replies, so better answers end
      the consultation sooner.** `token_count` is the cumulative character count
      of the entire transcript, NM's own output included, against a 50,000
      limit. A written opinion is ~25,000 characters — half the budget in one
      turn — and the M18/M18b advising fixes moved the cutoff from turn 7 to
      turn 5 purely by answering better. A real matter routinely runs past
      50,000 characters.
      The silent-failure half is fixed (M23); the SIZING is a cost decision and
      is deliberately left to the owner. Three options, in increasing order of
      change: raise `AGENTIFIED_NM_TOKEN_BUDGET_CHARS` (it is already an env
      var); count only what is actually sent to the model per turn rather than
      the cumulative transcript, since prompt size is already bounded elsewhere
      by the retrieval windows; or exclude NM's own long deliverables from the
      count. Do not raise it silently — it exists to stop runaway spend.
      **Fixed** `2026-08-25`, by the owner's choice of the narrowest option: a
      deliverable NM produced no longer counts against the budget. Ordinary
      replies still count — they are conversation, and the next turn reads them
      back, so exempting those would remove the cap rather than correct it.
      The limit itself is unchanged.

- [x] **M25. `retrieval/enricher.py` is dead code that cannot import.** ~1,300
      lines importing v2 config names (`BARE_INDEX_V2`, `BARE_CHUNKS_V2`,
      `CASE_INDEX_V2`) that no longer exist; `config.py` moved to v3. Verified
      the only failing module in the repo, and nothing outside it imports it, so
      nothing in the running product is affected. It carries the web-enrichment
      and source-tiering logic, which is therefore not live.
      Not deleted unilaterally — 1,300 lines is the owner's call, and the
      subsystem may be intended for revival. Either fix the imports and wire it
      up, or delete it; leaving a module that cannot load is the one option that
      helps nobody, because it reads as working infrastructure.
      **Deleted** `2026-08-25` on the owner's decision. Recoverable from git
      history if the web-enrichment and source-tiering logic is ever wanted.

- [x] **M21. Lexical collisions still produce confidently wrong charges.**
      Same matter: "cutting off power supply to force eviction" (a landlord
      cutting electricity) settled on **§24 of the Factories Act, 1948** —
      *"Striking gear and devices for cutting off power"*, a mechanical
      power-transmission safety device. Pure lexical collision on "cutting off
      power", and it survived `_verify_charge_provisions`' ingredient check.
      Also "eviction without due process" -> §19 Slum Areas (Improvement and
      Clearance) Act, which is real law but applies only to declared slum areas,
      not a fabrication unit in Medchal.
      This is the hard residual: the provision is real, the words match, and only
      knowing what the Act is FOR rejects it. Not attempted — it needs a
      measured approach (does the act's own subject-matter contradict the
      matter's?), not another pattern.

      **ATTEMPTED AND REVERTED 2026-08-23 — the fix was worse than the bug.**
      Diagnosis first, and it holds: `_element_check` works element-by-element on
      the PROVISION's own text and never asks whether the provision addresses the
      wrong the ISSUE names. It even instructs "do NOT invent an element from the
      issue label and then mark it missing", which actively discourages that
      comparison. So a provision whose elements are all satisfiable on the facts
      passes, even when it regulates an unrelated subject.
      Added a SUBJECT MATCH gate ahead of the elements. Measured on four charges
      from the real matter:
        - strict wording: collision correctly rejected, but "unguarded
          machinery" -> "Fencing of machinery" ALSO rejected (2/3).
        - softened to "unrelated matters only, related subjects pass": collision
          still rejected, but now TWO correct charges rejected — "Fencing of
          machinery" and a Consumer Protection "Deficiency" definition (2/4).
      Both directions destroy correct charges, and a gapped correct charge costs
      the client more than one wrong citation the reply-side guards may still
      catch. **Reverted.**
      What this rules out: fixing it by instruction inside `_element_check`. What
      is left to try, in order of cost: compare the ISSUE against the ACT-SUMMARY
      embedding (the summaries exist, 1,621 of them, and this needs only the
      local embedder — no API spend); or give the check the act's own summary as
      context so "what is this Act for" is data rather than recall. Measure any
      candidate against at least the four charges above before shipping — the
      false-negative rate is the number that matters, not whether the collision
      is caught.
      **RE-OPENED then fixed — see M48.** Closing this was my error: 0%
      cross-record duplication meant only one record survived, not that the
      right one did. Original note follows.
      **Closed as mis-stated** `2026-08-25` — the measurement does not support
      the theory. The premise was that a thin duplicate record outranks the
      properly-ingested copy of the same Act. Measured across 261 stored
      retrieval pools and 17,794 statutory chunks: **cross-record duplication is
      0.0%**. The act gate already collapses the duplicate records of one Act, so
      two copies never compete for slots. (11.9% of slots are several atoms of
      the SAME section — a head plus its sub-sections and provisos — which is
      the retriever working, not waste.)
      And in the case that prompted this, there was no fuller copy to prefer:
      the Telangana Buildings (Lease, Rent and Eviction) Control Act is ingested
      at **10 of its 37 sections**, and §10 is in none of them. The record that
      looked fuller exists only in the section INDEX, with no text behind it.
      So this was never a ranking defect. It is M17 — the corpus does not hold
      the provision — and the work belongs there.

- [x] **M18b. Asking for analysis did not move the conversation to counsel** —
      `FIXED 2026-08-23`, the second half of M18 and only visible after the
      first half landed. `wants_analysis` correctly made `_advising` true (key
      dates started computing, M19), but the REPLY still came from the narrow
      intake generator, because ROUTING is a separate decision:
      `should_move_to_counsel` read `wants_direct_guidance` alone, which is
      deliberately narrow and requires INSISTENCE.
      So the depth of the answer depended on the client's TONE rather than on
      what they asked: "what are my options and what do you recommend I do
      first?" -> 1,932 words, while "what is the exposure across all of this,
      and what would you move first?" -> 199 words and another question.
      `should_move_to_counsel` now also honours `wants_analysis`. Answering on
      thin facts is recoverable — the consult prompt already qualifies such an
      answer — whereas refusing to answer the question actually asked is not.

- [x] **M23. A deliverable request produced the PREVIOUS turn's reply verbatim.**
      Matter B v4, T6: "Please prepare the written opinion for the client's
      file." returned **byte-identical text to T5** (1,845 words, the answer to
      "what is the exposure...") with `deliverable=None`. The turn produced
      nothing and the stale `final_reply` carried through.
      `_detect_draft_request` is NOT the cause — it returns `opinion` for that
      exact sentence, verified in isolation, and matter A's T7 with the same
      shape produced a 3,945-word opinion in the same run series. So the
      difference is STATE, not wording: in v4 matter B had already moved to
      counsel/assessment by T3 (T3-T5 all long), and matter A had not.
      Hypothesis to test: once intake reaches `assessment`, a later turn takes a
      path that neither regenerates a reply nor reaches `_route_after_planning`'s
      drafter branch, leaving the previous `final_reply` in state. A turn that
      silently re-serves the last answer is worse than an error — nothing
      surfaces it.
      **Test first:** instrument which node produces `final_reply` per turn, and
      assert in the runner that consecutive replies are never identical. That
      assertion belongs in the harness permanently.

      **ROOT-CAUSED AND FIXED 2026-08-23 — the TOKEN BUDGET was ending turns
      silently.** `rate_limit` sets `token_count` to the cumulative character
      count of the WHOLE conversation, and `_route_after_rate_limit` returns
      `END` above `TOKEN_BUDGET_CHARS` (50,000). END without a `final_reply`
      leaves the PREVIOUS turn's reply in state, so the client is served the last
      answer again, word for word, with nothing to indicate it happened.
      Measured on the failing run: T1 ~1.7k chars, T3 ~26.9k, T4 ~41.8k,
      **T5 ~57.2k — over** — so T6 ("prepare the written opinion for the
      client's file") returned T5's answer verbatim with `deliverable=None`. The
      detector was never at fault; it returns `opinion` for that exact sentence.
      Fixed: the over-budget path now returns an explicit, honest reply saying
      the matter has hit its length limit, that nothing is lost, and how to
      continue. Verified under and over budget.
      `eval/regression/run_e2e.py` now HARD-FAILS a turn whose reply is identical
      to the previous turn's — nothing else in the harness could see this, and
      that is what let it through.
      **Note the perverse interaction, logged as M24:** the budget counts NM's
      OWN replies, so the better the answers get the sooner the consultation
      dies. The advising fixes (M18/M18b) lengthened replies and pulled the
      cutoff forward from turn 7 to turn 5.
- [x] **M22. Advising DEPTH is erratic across turns, and the counsel move fires
      on the wrong ones.** Matter B measured across four runs (words per turn,
      T1..T6):

        v1  248 · 212 · 140 · 104 ·  99 · 3710      (baseline)
        v2  233 · 279 · 195 · 196 · 199 · 4213      (after M18/M19)
        v3 2621 · 742 · 238 · 1846 · 253 · 3810     (after M18b)
        v4  193 · 709 · 2542 · 1907 · 1845 · 1845   (after the opening guard)

      M18/M19 are real and hold: key dates went 0 -> 1-2 per turn and the
      deliverable is produced every time. But the advising DEPTH is not landing
      where it should. In v3 the long turns are T1 (a briefing that supplies
      facts) and T4 (more facts), while **T5 — the explicit "what is the exposure
      across all of this, and what would you move first?" — is still 253
      words.** The opening over-trigger is now guarded (turn-1 gate), but that
      does not explain T5.
      Hypothesis to test, NOT yet acted on: once the intake engine has moved to
      `assessment`, later turns may take a different path that does not rebuild
      the full advising context, so the depth depends on WHEN the move happened
      rather than on what was asked. Instrument the routing decision per turn
      (intent + which node produced the reply) before changing anything else —
      three behavioural changes have now been made to this path and the result is
      less predictable, not more, which is the signal to stop and measure.

### Retrieval / corpus quality — measured 2026-08-23

Corpus: **1,429,044 chunks** — 1,015,756 case law, 413,288 bare act.

      **RE-READ 2026-08-23 — largely an artefact, and the evidence was
      contaminated.** Two of the data points that made this look erratic are now
      explained:
        - the v4 tail "1845 · 1845" was **not** two turns of equal depth; T6 hit
          the character budget and re-served T5's reply verbatim (M23).
        - the wild v3 numbers (2621 · 742 · 238 · 1846 · 253) came from the
          PRE-GUARD code, where the counsel move fired on the opening brief.
      Under the current code matter B reads sensibly: **193 · 709 · 2542 · 1907 ·
      1845** — a short listening opening, then substantive advising turns that
      grow with the record. That is the shape it should have.
      Not re-run to confirm, deliberately: a full matter costs real API spend and
      the two anomalies are individually accounted for. Re-assess on the next
      end-to-end run rather than paying for one now. If depth still wanders after
      M23's fix, instrument which node produced `final_reply` per turn before
      changing behaviour again — three changes were made to this path and the
      lesson was to measure, not to keep adjusting.
- [x] **M15. `_act_gate_key` merged acts of DIFFERENT YEARS** — `FIXED`, and it
      was my own B18 bug. The key stripped the trailing year, so the **Companies
      Act 1956 and the Companies Act 2013 normalised to the same act**, as did
      all eleven Finance Acts. Latent rather than live (B19 retired the inferred
      gate, so the key currently serves only explicit whitelists) but a landmine
      for anyone re-enabling it, and exactly the over-generalisation this project
      rejects. The year is now captured and re-appended instead of discarded.
      Verified: Companies 1956 ≠ 2013 and Finance 2012 ≠ 2021, while true
      duplicates (`UNION OF INDIA_1961_0_THE INCOME TAX ACT, 1961` vs
      `the_income_tax_act_1961`) still merge. Summary resolution is 1,553/1,621
      (95.8%) year-aware, so B18's headline number was sound.

- [x] **M16. The same act is indexed under multiple ids, and it costs real
      retrieval slots.** Year-aware measurement: **1,506 of 1,614 acts** appear
      under more than one `act_id`, covering **374,876 chunks = 90.7%** of the
      bare-act corpus — e.g. the Income Tax Act 1961 as both
      `UNION OF INDIA_1961_0_...` (10,362 chunks) and `the_income_tax_act_1961`
      (468). Not identical copies: different ingests at different granularity.
      **Measured cost, which is the part that matters:** across five realistic
      queries, **20% of the top-10 slots went to repeats of the same
      (act, section)** — 0/10 on two queries, 5/10 on a tenancy query. That is
      window that should have gone to a different provision.
      A result-level collapse on (normalised act, section) is the cheap fix and
      is generalized, but it must not flatten genuinely different SUB-SECTIONS of
      one section, which are legitimately distinct. Establish which of the two
      the repeats actually are before building — the measurement to do that was
      started and deferred (it needs the embedder, which could not be loaded
      while two end-to-end runs held the GPU).

      **RESOLVED 2026-08-23 by content-level dedup.** The open question was
      whether the repeated slots were cross-record duplicates or genuinely
      different sub-sections. Measured: across five queries, **5 duplicate slots
      were CROSS-RECORD** (one act, two `act_id`s) and **5 were the SAME record's
      different sub-sections** — so the (act, section) collapse I had sketched
      would have destroyed real content, exactly half the time.
      `_drop_textual_repeats` therefore matches on normalised TEXT with the
      act/section header stripped, since two records of one act carry the same
      body under different headers. Identical text cannot be distinct content, so
      it is safe by construction: it can only free a slot that was carrying a
      copy. Verified — same body under different headers collapses, different
      sub-sections both survive, and empty-text results are never collapsed.
      The underlying corpus duplication (1,506 of 1,614 acts) is untouched; this
      stops it costing retrieval slots, which was the measured harm.
- [x] **M17. 18.3% of embedded statutory chunks are stubs.** Bare-act chunk text
      length, 4,000-chunk sample: p10=158, median=341, p75=535, max=14,887.
      **18.3% carry under 200 characters** and 0.3% under 80 — largely act and
      section header with little operative text. Every one of those is an
      embedded vector competing for the same window, and a short generic vector
      is a weak discriminator. This is the same root as B15 (the §138 chunk in
      the pool was 74 characters while the real section is 1,806), which was
      fixed at ANSWER time by widening; retrieval still ranks against the stub.
      Re-embedding 413k vectors is expensive and risky, so measure first: does a
      stub actually win slots it should not, or do the section's atoms carry the
      match anyway? Do not re-ingest on the strength of the percentage alone.

**Good, and worth not breaking:** empathy on the opening turn is genuine and
tone-matched; the economy rule holds (252-278 words, exactly one question per
turn); citations are grounded and carry plain-language case briefs; the checklist
grows monotonically and covers every thread; `_compute_key_dates` arithmetic is
correct; the straddle abstention works when both dates are explicit; and B17's
honest fallback wording is a real improvement over the old false claim.

## P2 — Known defects (observed live, not yet fixed)

      **NOT A DEFECT ON RE-EXAMINATION, 2026-08-23.** Logged as "the client
      learns their case at one issue per turn". The checklist DOES render every
      thread with its own requirements, and it is a live panel in the UI, not
      buried — verified in the run. A senior advocate does not recite eight
      citations a turn either; one worked issue per turn with the full agenda
      visible alongside is the right shape. The genuine version of this concern
      was that nothing ever SYNTHESISED the threads, which is M5/M1.
      Changing `LegalInsight` to carry several citations would be a schema change
      for unclear benefit, so it is closed rather than built.
      **FIXED 2026-08-23.** `citation_not_overruled` is implemented and no
      longer `_NOT_IMPLEMENTED`. The treatment label is known when a precedent is
      attached during the consult but was unrecoverable by draft time, so it is
      now carried on the precedent record and through `precedent_map`, and the
      verifier fails the draft when a case marked OVERRULED / REVERSED /
      PER_INCURIAM / DISAPPROVED / DOUBTED is actually CITED in it.
      DISTINGUISHED is deliberately excluded — that is a caution for the
      advocate, not a disqualification. The check reports
      `skipped_no_precedents` honestly when there is nothing to check, so it is
      never a vacuous pass.
      Verified: an overruled case cited in a draft fails with the case named; a
      clean draft passes; no precedents skips.
      Still `_NOT_IMPLEMENTED`, and honestly marked as such:
      `ingredient_coverage`, `party_complete`, `limitation_pleaded`,
      `relief_mapped`.
      **BLOCKED ON A MEASUREMENT THAT NEEDS THE EMBEDDER 2026-08-23.** The
      deciding question — do stub vectors actually WIN slots they should not, or
      do the section's atoms carry the match anyway — needs a local embedding
      run, and the embedder (bge-large) could not be loaded: the machine is
      running NM's own uvicorn server plus other work, and it fails with "the
      paging file is too small". No API cost is involved, only memory, so this
      is worth redoing when the machine is quiet.
      Do NOT re-embed 413k vectors on the strength of the 18.3% figure alone —
      B15 already fixed the consequence that was actually observed (a 74-char
      §138 chunk in the answer window) by widening at answer time.
      **Measured and instrumented** `2026-08-25`. **The headline figure here is
      WRONG — see M48.** It joined on `act_id` and so counted duplicate
      records as missing Acts; the real gap is 2.7%, not 38.5%, and this is
      not a launch blocker. The script is fixed and reports both figures. `scripts/corpus_coverage.py` compares what `legal.db` says an
      Act contains against the text `chunks.db` can actually retrieve. Across
      **1,592 Acts with a declared section count**:
        - **613 (38.5%) have NO retrievable text at all**
        - **141 (8.9%) are under 25% ingested**
        - **592 (37.2%) are 25-75%**
        - **246 (15.5%) are 75% or better**
      This single fact sits underneath M33 (a §10 cited that is not in the
      corpus), M34 (the §138 proviso truncated, so the notice deadline could not
      be given) and much of M40 (the Act that governs may simply be unreadable,
      so a worse one wins). It is a re-ingestion job, not a logic fix, and it is
      not something to start unattended.
      **What now protects the client meanwhile**: `_flag_thin_coverage` warns on
      any charge resting on an Act ingested below 60%, and the AUTHORITATIVE
      CHARGES block requires that warning to be voiced once, plainly — "only 10
      of this Act's 37 sections are in the corpus (27%), so a provision that
      governs may not have been read". Two cached COUNT queries, no model call,
      and it warns rather than withholds: a partly-ingested Act is still usually
      the right Act. The `act-readable` check in the invariant sweep tracks it —
      currently **5 of 240** settled charges rest on an Act below that line, so
      the corpus-wide gap reaches an actual charge rarely.
      **Closed by measurement** `2026-08-26` — `scripts/stub_impact.py`, which is
      the measurement this entry itself asked for and which had never been run.
      The percentage was never the question; whether short chunks WIN slots is.
      Over 262 stored retrieval pools and 17,815 retrieved statutory chunks,
      against a 6,000-chunk corpus sample, body length measured with the
      boilerplate header excluded:
        - corpus:    p10=71,  median=245, p90=723, **41.0% under 200 chars**
        - retrieved: p10=108, median=327, p90=748, **24.8% under 200 chars**
      Stubs are **under-represented in results by a third**. Ranking already
      discounts them, so re-embedding 413k vectors would buy nothing — exactly
      the conclusion this entry warned against reaching from the percentage
      alone, now with the evidence to settle it.
      (The 18.3% figure above counted the header; excluding it gives 41%. The
      absolute number moved, the verdict did not, because what matters is the
      ratio between the two distributions.)
      What DID matter was M34: not that stubs rank too high, but that a head
      arrived without its children. That is fixed, and it is the real content of
      this concern.

- [x] **B1.** **Consult prose under-voices the authoritative charges** —
      `ROOT CAUSE FOUND + FIXED 2026-08-23`. Documented in `RUBRIC.md` as the
      Stage-5 "adherence gap" and assumed to be a prompt-adherence problem. It
      was not. `grounding_guard`'s advocate-counsel gate DISCARDED the entire
      answer whenever it cited no firm **Supreme Court** authority, replacing it
      with `_limited_authority_reply` — even when the statutory footing was
      settled, fact-checked and correctly cited. Reproduced on a March 2019
      cheating matter whose charge was settled on IPC §420: the reply read *"I do
      not yet have enough grounded authority to advise conclusively"* while its
      own ACTIONS line cited §420. The note also contradicted the snapshot it was
      handed — `reason='firm_authority'` is not a key in
      `_limited_authority_reply`'s lookup, so it fell through to that default
      string. Now: when the answer is otherwise grounded (no ungrounded /
      mislabeled / mismatched / repealed citations) and the authority floor is
      firm, the missing case law becomes an appended `_authority_caveat` instead
      of a replacement — the rule `_authority_caveat`'s own docstring already
      stated, applied to the case it was not reaching. Bad citations are still
      replaced outright by the definitive gate below it.
- [x] **B2.** **`§351` sub-section wobbled between turns ((3) → (2))** — `FIXED
      2026-08-23`. `_merge_charge_lists` did `out[i] = c`: a fresh resolution
      wholly overwrote the settled one. The resolver re-runs on later turns and
      picks the severity-matched sub-section afresh from a window that has
      shifted, so on a borderline matter it moved between turns on facts that had
      not changed. Sub-section IS the charge to an advocate, and a client
      watching it move loses confidence in both readings. Now a **fact-checked**
      determination is not overwritten by an **unverified** re-run of the same
      question, within the same section (`_same_section`, act+section compared
      with sub-section ignored). A different SECTION is a genuine re-assessment
      on fuller facts and is still taken — this stabilises the sub-section, it
      never freezes the charge. Verified: `_same_section` distinguishes
      §351(3)/§351(2) BNS (same) from §352 BNS and from §351 BNSS (different act,
      same number).
- [x] **B3.** **Citations render doubled in consult prose** — `FIXED
      2026-08-23`. `_CITATION_TAGS_INSTRUCTION` tells the model not to type the
      Act name or section itself and to emit a bare `[[cite:N]]`; it does anyway
      often enough to matter, and the tag then renders the same words again:
      *"…under §420 of The Indian Penal Code §420 of The Indian Penal Code
      [chunk_id]"* (observed live twice). Whether the model obeys is not
      something a prompt can guarantee (P2), so the duplicate is now removed at
      `_resolve_citation_tags` — the ONE place a tag becomes visible text, and
      where the B9 separator fix already lives. `_already_cited()` compares the
      text running into the tag against the label with the enactment year both
      present and absent, because the model writes "§420 of the Indian Penal
      Code" where the corpus label carries ", 1860". Verified: doubling
      suppressed with and without the year; the label still renders when the
      model obeyed; the B9 separator case and a *different* citation later in
      the same sentence both still render in full.
- [x] **B4.** **Quantum check flags the client's own supplied figures** —
      `FIXED 2026-08-23`. Not over-eagerness: `_append_quantity_caveat` was
      handed `_last_human_query_text(state)` — the LATEST message only — so a
      figure the client stated on turn 1 was invisible by turn 2 and the guard,
      which treats a figure absent from both the client's words and the evidence
      as invented, flagged it. Reproduced live in the B14 validation run: client
      opened with "12 lakh rupees", asked for advice on the next turn, and the
      reply was caveated with `['12 lakhs']`. Both call sites now pass
      `_all_client_text(state)` — the whole account, newest last.
      `_last_human_query_text` still answers "what did they just ask", which is
      correctly the latest message. Verified: with the whole account "12 lakhs"
      clears while an invented "3 years" limitation period is still flagged.
- [x] **B5.** **Drafter repeats the demand across sections** — `FIXED
      2026-08-23`. The drafter DID get a view of its earlier sections, but as
      `body[:400]` — and in a notice or a plaint the operative demand, prayer or
      relief is the LAST paragraph of its section. The one thing being duplicated
      was the one thing the truncation cut off, so the instruction "do NOT
      restate their content" was being given to a model that could not see what
      it had already said. `_condense_drafted` now shows each prior section's
      HEAD and TAIL (the middle is what a later section least needs), and
      `_prior_sections_block` keeps the whole thing inside a budget by degrading
      the OLDEST sections to headings only — enough to prevent duplication
      without carrying their bodies. The prompt also now states the general rule:
      the operative ask belongs to exactly one section. Verified: a demand
      trailing 1,600 characters of background is visible in the condensed view
      and was invisible under `[:400]`; an 8-section memo stays in budget with
      every heading present and the newest tails intact.
- [x] **B17.** **The grounding gate discards a settled charge along with the
      bad citations** — `FIXED 2026-08-23`. `_salvage_grounded_reply` now runs
      before every fallback to `_limited_authority_reply` in `grounding_guard`
      (the code graph confirms that is the ONLY caller, so the change is
      complete). `_drop_ungrounded_claims` removes the sentences and list items
      carrying an objected-to citation and keeps the grounded advice around them
      — line-wise, because these replies are markdown, so a bullet is dropped
      whole while a prose paragraph loses only the offending sentence.
      Deliberately conservative: the salvage is used ONLY if what survives
      re-passes every check that rejected the original, still carries at least
      one grounded citation, and retains >=35% of the reply; otherwise the
      limited-authority note is returned exactly as before. At the definitive
      gate it falls THROUGH rather than returning, so a salvaged reply still gets
      the advocate note, citation sanitisation and quantity caveat. Verified on
      the observed shape — a §138 reply that also reached for §118, §142 and
      Schedule I cl. 30: all three removed, §138 and the practical steps
      retained, honest note appended. Original finding: Observed 2026-08-23 on the cheque matter (CLIENT audience, so
      a different gate from B1's advocate one). §138(1) NI Act was settled and
      fact-checked on both turns, but the drafted counsel turn also reached for
      §30, §118 and a mismatched §142; two repair passes failed, and the
      definitive gate correctly refused to ship bad citations — by replacing the
      WHOLE answer with `_limited_authority_reply`. So a client with a settled,
      grounded governing provision got a no-authority note whose own ACTIONS line
      cited that provision. Replacement IS right for bad citations (the codebase
      says so, and B1 deliberately left that path alone). The question is whether
      the failure mode should be *strip the ungrounded citations and keep the
      grounded advice* rather than discard everything. Bigger than a wording fix
      — it changes what the definitive gate does — so it is logged, not
      attempted. **Partially mitigated 2026-08-23**: `firm_authority` was missing
      from `_limited_authority_reply`'s reason map, so these turns fell through to
      the default and told the client "I do not yet have enough grounded
      authority" while a verified citation sat below. The note now says what is
      actually true. Saying the opposite of what the snapshot found is worse than
      saying nothing — it teaches the client to distrust a correct citation.
- [~] **B6.** Corpus gaps — **INGESTION DONE, SURFACING NOT** `2026-08-23`.
      Two of the three original claims were wrong on re-measurement: BNS §318 is
      present (15 chunks) and the Dowry Prohibition Act 1961 is present (74
      chunks) — both were ranking misses, not absences, the same class as B14.
      The third was real.

      **Telangana/AP Land Grabbing (Prohibition) Act, 1982 — INGESTED.** Fetched
      verbatim from Indian Kanoon, reflowed whitespace-only (asserted: no
      non-whitespace character changed) so the 21 sections start their own lines,
      section list cross-checked against the source — 1–17B including 7A/10A/17A/
      17B, complete. FAISS 413,267 → 413,288, legal.db 21 rows, and **both B13
      pipeline fixes fired automatically**: chunks.db synced 21 rows and the act
      summary was created and re-embedded. BM25 rebuilt (413,288 docs). Verified
      searchable through the GATED path: a verbatim §3 sentence returns
      §3 top, then §2 and §4.

      **What is NOT closed — it does not surface from a real matter.** On a
      lay-worded Hyderabad land-grab account ("occupied my vacant plot without
      any title, put up a compound wall, now claims he bought it") the Act
      contributed ZERO chunks and the charges settled on generic BNS trespass
      §329(3) and forgery §336(1) — missing the governing special law with its
      Special Court, reversed burden of proof (§10) and its own penalties.
      Measured cause: the coarse act-summary gate does not rank the Act in the
      **top 25** for those facts (only its 1988 RULES, at rank 3), and scores
      across all 1,621 summaries are bunched **0.626–0.652** — the gate has
      little discriminative power on this corpus. Rewriting the summary in
      fact-shaped language (shipped, see below) did NOT move it.

      Two things came out of the attempt and are shipped:
        - `search_bare_acts` **ignored `plan.act_ids` in fast mode**, so an
          explicit act whitelist from the caller was silently inert. Fast mode
          buys the skipped HyDE call and the skipped ungated compensation pass;
          the gate itself is a set lookup and costs nothing. Now honoured.
        - `_SUMMARY_PROMPT` now asks for the FACT SITUATIONS that bring someone
          to an act, in the words the affected person would use, as well as the
          statutory subject areas. The gate is matched against a client's own
          account, so a summary written only in statutory register is
          unreachable from the matter that needs it. Improves every future
          ingest; regenerating the existing 1,621 summaries is an LLM cost that
          needs approval and is unproven — see B18.

      **Re-measured after B19 retired the gate (2026-08-23): still zero.** The
      non-fast path now returns the Telangana Rights in Land and Pattadar Pass
      Books Act and the Hyderabad Record of Rights — topically adjacent LAND
      acts — and the sweep pool still holds 0 Land Grabbing chunks. Root cause is
      now precise and is NOT the gate: the client's own words lead with the
      documents they hold ("registered sale deed", "pattadar passbook"), which
      pulls the land-RECORDS acts, and those acts field thousands of chunks
      against this Act's 21, so it is outnumbered in the candidate pool on plain
      semantic similarity.

      The remaining levers are both bad: teaching the issue-spotter that state
      special laws exist is the situation-specific rule P4 forbids, and boosting
      "specialised" acts needs a definition of specialised that nothing in the
      data supplies. **Not fixed, and not guessed at.** What is true today: the
      Act is in the corpus, correct and citable, and reachable the moment a
      matter's own words name the wrong rather than the paperwork.

      A `_seed_specialised_acts` step (coarse-gate the matter once, seed absent
      acts) was built and **reverted**: it added 2 chunks from gate-ranked acts
      but did not fix the motivating case, which makes it unmeasured benefit at
      real per-matter cost. Not shipped.

- [x] **B18.** **The act-summary gate matched almost nothing** — `FIXED
      2026-08-23`. Opened as "weakly discriminative"; measurement found something
      worse and much more concrete. The gate tests `chunk.act_id in act_ids`,
      an EXACT string match, but the act-SUMMARY store and the CHUNK store were
      built by different pipelines with different naming schemes:

        summary : `ABDUCTED_PERSONS_RECOVERY_AND_RESTORATION_ACT_1949_1949`
        chunk   : `TELANGANA_1948_0_THE ANDHRA PRADESH HOME GUARDS ACT, 1948`

      **Only 3 of 1,621 summary act_ids (0.2%) equalled any chunk act_id.** So
      for 99.8% of acts the gate whitelisted an act and resolved to an EMPTY
      position set: the gated pass returned nothing and only the ungated recall
      pass ever produced results. The coarse gate was a no-op that still cost an
      extra search, and had been for as long as the two stores disagreed. It was
      invisible because the issue sweep runs `fast=True` and skips the gate
      entirely, and because the non-fast path always compensates with the
      ungated pass.

      Fixed by matching on a normalised act NAME rather than the raw id
      (`_act_gate_key`), with the two state names aliased — Telangana re-adopted
      the Andhra Pradesh acts under its own name, so "The Telangana Home Guards
      Act" and "THE ANDHRA PRADESH HOME GUARDS ACT" are one act here. Measured
      lift: **0.2% -> 67% (name) -> 96.2% (with the alias)**. On a land matter
      the gate now resolves 10 acts / 354 positions instead of 21. Falls back to
      the summary's own act_id when a key does not resolve, so it can never
      whitelist FEWER acts than before, and the ungated recall pass still runs —
      the change is purely additive to the candidate pool. Verified: offline
      suite 23/23, golden `cheque_bounce` still PASS.

      **Honest scope:** the main pipeline's issue sweep uses `fast=True` and does
      not consult the gate, so this improves the agent tool path and
      `lookup_section_with_succession`, not the primary retrieval route. Whether
      the sweep should now use a gate that actually works is a real question and
      a behaviour change — logged as B19, not slipped in here.

- [x] **B19.** **Should the issue sweep use the (now working) act gate?** —
      `MEASURED: NO — and the gate is retired as a restrictor. 2026-08-23`.
      Measured against the golden matters instead of reasoned about: the coarse
      gate whitelists the act a matter MUST cite in only **1 of 4** cases. A
      cheque-dishonour brief was gated to *sales tax settlement, lotteries and
      revenue recovery* rather than the Negotiable Instruments Act. Top-5 scores
      are bunched (margins **0.009 / 0.029 / 0.047**), so there is no confidence
      signal to gate on either — abstaining above a margin threshold, the
      `_conduct_era` move, is not available here.

      So gating the sweep would GATE OUT the governing statute. The answer is no,
      and the existing `fast=True` decision to skip the gate was right for a
      better reason than latency.

      It followed that the gate should not restrict the non-fast path either.
      Retired: an INFERRED gate no longer sets `allowed`; an EXPLICIT
      `plan.act_ids` still does, because that is a caller's instruction rather
      than a guess. The ungated RECALL PASS went with it — it existed solely to
      compensate for the brittle inferred gate, and merging a full-corpus search
      back in would defeat the one case that now sets `allowed`. Net for the
      non-fast path: ONE ungated search instead of a near-empty gated search plus
      an ungated one — same results, less work, and an explicit whitelist is now
      genuinely strict.

      Verified: a cheque query on the non-fast path now returns NI Act §138 as
      its top hits (the gate would have excluded that act entirely); an explicit
      plan returns only the named act; offline 25/25; golden `cheque_bounce`
      still PASS.

      This supersedes half of B18: making the gate MATCH (0.2% -> 96.2%) was a
      real bug fix and is what made the gate's ranking measurable at all — the
      no-op had been hiding it. The matching fix stays and now serves explicit
      whitelists.
- [x] **B15.** **Statutory clocks fall outside the provision window** — `FIXED
      2026-08-23`. Measured: the §138 chunk sitting in the evidence pool is a
      **74-character stub**; the real section is 1,806 characters and carries the
      "fifteen days" and "thirty days" periods the reply said it could not find.
      `_widen_charge_sections` now pulls the WHOLE section for every settled
      charge AND its companions (the filing clock spans both — §138 holds the
      15-day notice period, §142(b) the month to file, so widening only the
      principal charge recovers one end of the chain). The assembly is the one
      `_compute_key_dates` already used, now extracted to `_whole_section_text`
      and shared, so the date arithmetic and the prose can never read different
      texts. LLM-free, capped at 2,000 chars, and applied only to stubs
      (<600 chars) of provisions a charge actually settled on, so the window
      grows exactly where the governing text is. Idempotent — verified across two
      passes. Original finding: On the
      B8 re-run the reply said the §138 timelines were "not fully set out in the
      snippets you have provided" — the proviso's 15-day/one-month clocks live in
      sibling sub-chunks that the window did not reach, so `_compute_key_dates`
      had no period rule to corroborate. A deadline is the single most damaging
      thing to get wrong or omit. Look at whether a settled charge should always
      pull its WHOLE section (the `_section_text` assembly `_compute_key_dates`
      already does) into the evidence window, not just the matched chunk.
- [x] **H4.** **`_EXCLUDED_ACTS_RE` was dead code that read as live policy** —
      `RETIRED 2026-08-23`. `_excluded_act` is now an explicit `False` with the
      history recorded above it — kept rather than deleted so the four call sites
      read as a considered decision instead of a forgotten check. Original
      finding:
      `retrieval/retriever.py:84` excludes the IPC/CrPC/IEA "WHOLE from retrieval
      / lookup / document reconstruction" — but it matches SPACES ("indian penal
      code") while every ingested act_id uses UNDERSCORES
      (`the_indian_penal_code_1860`), so it currently excludes **nothing**:
      measured 2026-08-23, all three old codes reachable (2,670 / 1,008 / 462
      chunks). It survives only by that accident. Either delete it or re-scope it
      to the contaminated legacy act_ids it was actually written for — as it
      stands, a future ingest that spells an act_id with spaces would silently
      vanish from the corpus.
- [x] **B7.** **Pre-1 July 2024 conduct** — `CLOSED 2026-08-23` by B13 + B14
      together. The corpus now holds all three predecessor codes (IPC 1860, CrPC
      1973, IEA 1872 — 1,008 / 2,670 / 462 chunks, all reachable), `_conduct_era`
      recognises pre-commencement conduct from the client's own dates,
      `_prefer_era_provisions` moves the charge onto the code in force, and
      `_cites_repealed` stands down so the citation survives to the reader.
      End-to-end on a March 2019 cheating matter: charge settles on §420 IPC and
      the reply cites it. NM no longer has to answer "the predecessor governs but
      I cannot show you its text".

---

## P1 — Verification debt (owed from the model migration)

### R1. **A spotted issue could receive ZERO retrieval** — `FIXED` **(was P0)**
Surfaced as a golden failure on the new tiering, but the root cause was a
long-standing retrieval bug that had nothing to do with the model change.

**Diagnosis (each step measured, not assumed):**
1. `spot_issues` on luna worked perfectly — it spotted *"Making and publishing
   false imputations that the client stole from the firm"* with the search
   phrases `['Defamation', 'Punishment for defamation']`.
2. The index worked perfectly — `search_bare_acts('defamation')` returns
   **BNS §356** as a top hit.
3. Yet `retrieve_for_matter` returned 114 statute chunks with **§356 absent**.

**Root cause:** `retrieve_for_matter` truncated its search phrases
**positionally** — `uniq = uniq[:20]`. This matter spotted **9 issues** × 2–3
phrases = 27, so the tail was silently dropped and defamation's phrases **never
ran at all**. The issue was named, given zero retrieval, and could then only be
gap-flagged by the resolver. Reproduced in isolation: the old cap covered 7 of 9
issues; defamation was not searched.

**Why it looked like a model regression:** gpt-4o-mini simply spotted fewer
issues, so everything fit under 20. The cap made retrieval quality depend on how
many issues were spotted and in what ORDER — a latent trap for any richer
issue-spotter.

**Fix:** issue-fair round-robin instead of positional truncation — every issue
gets its FIRST phrase before any issue gets a second (the same balancing
`_format_provisions_for_charges` already applies to provisions), with the cap
raised 20 → 28 (`_QUERY_SWEEP_CAP`). A crowded matter now loses *depth* on each
issue rather than losing *whole issues*, which is the right trade: a missed issue
is a missed charge.

**Verified — golden `partnership_forgery_multi` now PASSES.** All MUSTs resolve:
§336(1) forgery, §340(2) using-forged-document, **§351 criminal intimidation**,
**§356 defamation**, NI §138. Pool grew 114 → 172 chunks.

Fixing R1 exposed a second, downstream cap: with retrieval no longer the
bottleneck, the resolver's fixed 28-provision window became one (§351 was in the
pool but outside it). That window now scales ~4 per issue (28–48). **Both caps
had the same shape of bug** — a fixed budget shared across a variable number of
issues.

**Note this bug was NOT caused by the model migration — it was EXPOSED by it.**
It would have hit gpt-4o-mini identically on any matter spotting 8+ issues. The
migration's real return was surfacing a latent correctness bug that had been
silently costing charges on complex matters.

**Lesson for the guidelines:** a positional cap over a per-issue workload is
silently unfair. Prefer round-robin whenever a budget is shared across items
that must each be covered.

### R1-orig. Original symptom (kept for the record)

```
[FAIL] partnership_forgery_multi
    !! MUST missing: bharatiya nyaya sanhita §356
    defamation -> GAP   "governing provision not in retrieved evidence"
```

This matter passed **3/3 on gpt-4o-mini**. Two things are true:
- The charge resolver behaved **correctly** — it spotted defamation as an issue
  and honestly gap-flagged it rather than inventing a section (P1.3 working).
- But **BNS §356 (Defamation) is in the corpus — 29 chunks, verified** — so this
  is a **RETRIEVAL** failure, not a corpus gap.

**Prime suspect:** `spot_issues` generates the statutory search phrases and now
runs on **gpt-5.6-luna** instead of gpt-4o-mini. Different phrases → different
retrieval → §356 never surfaces. The rubric already records spot_issues as one
of "the two moves to watch" in eval.

**Next step:** run `staged_probe.py issues` / `retrieval` on this matter and
compare luna's search phrases against gpt-4o-mini's for the defamation issue. If
luna's phrasing is the cause, either put `spot_issues` back on a stronger tier
or sharpen `_ISSUE_PROMPT`'s search-phrase guidance.

**Do not conclude the migration is bad on one failure** — 5/6 matters passed and
the case-brief/judgment quality improved markedly. This is one fixable retrieval
regression.

### V1. Re-run the eval suites — `DONE (limited run, approved) 2026-08-23`
Run after this session's 15 fixes, on the scope the user approved.

**Golden 3/3 PASS** — `cheque_bounce`, `partnership_forgery_multi`,
`dowry_cruelty`, chosen to exercise the fixes (B15/B4/B17, B11/B2, B14/B12).
ALL MUST / MUST-NOT held on every one, so none of the 15 changes regressed the
citation path.

**E2E 2/2 hard checks held** — `cheque_bounce_complainant`,
`accused_cheating`.

Observed in passing, both logged rather than fixed here:
  - `dowry_cruelty` settled on BNS §118(1) / §351(3) / §127(1), all
    fact-checked, with §351(3) STABLE across turns — B2's fix holding on the
    exact provision that used to wobble.
  - two soft misses on `dowry_cruelty` (`domestic violence §3`, `BNS §115`) and
    one on `cheque_bounce_complainant` (opening asked 3 questions where ~1 was
    expected — a concision point, see V5). Soft checks are reported, not failing.

Not covered: the other 3 golden matters and the 3rd e2e scenario. A full pass is
still the stronger check and remains available on request.
**Owed, and substantial**: everything below this line in the P2 defect list was
fixed and validated with targeted probes and unit tests, NOT with the golden or
e2e suites, which are only run on explicit per-run approval. A full pass is the
right next step and needs a go-ahead. Original note:
**Golden `--runs 1` done (2026-08-22):** 5/6 PASS, 1 FAIL (R1 above). Soft
`want` misses: BNS §125 + MV §164 (road accident), Money Lenders §2A + BNS §124
(acid threat) — all also missed on gpt-4o-mini, so not new.

**Harness bug found:** `run_golden.py` crashes with a Windows `charmap`
UnicodeEncodeError when printing the final verdict (a `‑` in the output), so
the "ALL MUST/MUST-NOT HELD" summary line never prints and the process exit code
is unreliable. Run it with `PYTHONUTF8=1`, or fix the harness to force UTF-8
stdout. Per-matter PASS/FAIL lines are still correct.

### V1-orig. Re-run the eval suites on the new tiering — background
Every prior eval result was produced on **gpt-4o-mini / gpt-4o**. The migration
to gpt-5.1 + gpt-5.6-luna invalidates all of them as evidence about today's
behaviour. Owed:
- `eval/regression/run_golden.py --runs 3` — citation regression
- `eval/regression/run_e2e.py --runs 3` — conversational invariants (includes
  the `evidence_coaching_stuck` scenario)
- Stop the uvicorn server first (concurrent FAISS mapping segfaults).
- **Never run without the user's approval** (guideline D.5).

### V2. `_narrow_prompt` reorder needs repeat verification — `MEASURED 2026-08-23`
Re-measured on a fresh 2-turn client conversation through the full graph:
**8.3% overall cache hit (27,752 input tokens, 2,304 cached) — 9% on gpt-4o-mini across 16 calls, 0% on gpt-5.1 across 5**

The reorder is holding — the static head still leads the prompt and the cached
rate is in the band C1 reported (0% -> 10.2%) rather than having silently
regressed to 0, which was the specific worry. The remaining headroom is C1's
open half, not this item: ~20 background prompts still sit under the 1024-token
minimum a cache prefix needs.

### V3. Case-brief enrichment never live-verified — `VERIFIED 2026-08-23`
Observed live in this session's graph probes, rendering exactly as designed —
the citation, then a plain-language statement of what the court decided:

  "Jugesh Sehgal vs Shamsher Singh Gogi — The court determined that if a cheque
   is fundamentally flawed, such as being drawn on an account not maintained by
   the issuer, it could invalidate the dishonour claim..."

Also seen on the dowry and cheating matters (Panchram, Tholan, Veer Prakash
Sharma, S.W. Palanitkar, Dalip Kaur). The code-gate holds too: a brief is only
rendered when the grounded `case_context` was actually supplied, so the model is
never summarising a judgment it was not given.

### V4. Empathy holds across a full conversation — `PARTIAL 2026-08-23`
Verified on OPENING turns, which is where A5 regressed. Live example:

  "I see you've been dealing with a frustrating situation regarding the cheque
   that bounced, and it's understandable how this could feel concerning,
   especially given the amount involved."

and, on the 2019 cheating matter, an opening that named the loss before the law.
**Not** verified across a LONG conversation — the probes ran 2 turns, and the
original worry was drift over many. Needs a 6-8 turn client-audience run scored
against the rubric, which is a live-run cost and needs approval.

### V5. Concision on advising turns — `MEASURED, NOT HELD 2026-08-23`
The limited eval flagged it as a SOFT check on `cheque_bounce_complainant`:
**"opening asked 3 questions (expected ~1)"**. So the miss is on the INTAKE
opening, not on advising turns as the item assumed — and it persists even though
both prompt systems now carry an economy rule and the intake prompt says "ask
ONLY ONE question (never more)".

That is the interesting part: an explicit, unambiguous instruction is being
under-followed, which per P2 means the constraint belongs in code, not in the
prompt — the same move that fixed citation integrity (structural `[[cite:N]]`
tags) and the conduct-date choice (`_conduct_era`). A deterministic
one-question check on the rendered intake turn is the natural fix and is not yet
built. Advising-turn length itself was not the failure; it was not flagged.

## P2 — Prompt-architecture debt

- [x] **PD1.** **`_CONSULT_PROMPT` <-> inline consult `core` overlap** —
      `CLOSED 2026-08-23 by enforcement, not consolidation`. The overlap is
      low-severity (the blocks agree, no drift measured) and consolidating it was
      flagged as flagship editorial work needing 3-5x live verification — a
      budget that buys little here, since the risk is not that the blocks
      disagree today but that a future "global" edit lands in only one owner.
      That risk is now caught mechanically: see PD3.
- [~] **PD2.** `semantic_search_nodes` degrades **silently** to keyword
      matching — the graph has 0 embeddings, and it answers anyway rather than
      reporting that it cannot do semantic search. Procedure now recorded in
      `CLAUDE.md`; the command is one line. **Blocked on an action only the user
      can take**: it must run with Claude Code CLOSED, because the running MCP
      server holds `code-review-graph.exe` open (the install completes the
      dependencies then fails to replace the entrypoint, `os error 32`), and
      calling the embed tool against a live server whose env just changed hangs
      it for the full idle timeout — measured twice, an hour lost. Not retried
      in-session by deliberate choice.
- [x] **PD5.** **The code graph accumulates a stale duplicate of every file it
      touches** — `WORKAROUND DOCUMENTED 2026-08-23`. Upstream's bug and it
      recurs, so it cannot be "fixed" from this repo — what it needed was for the
      symptom and the recovery to be written down where they will be read.
      Both are now in `CLAUDE.md`: the tell is a `query_graph` result coming back
      `ambiguous` or line numbers that do not match the file, and the recovery is
      to delete `.code-review-graph/graph.db` and rebuild (~2s). Recorded
      explicitly that **`full_rebuild=True` makes it worse** — it reports
      `stale_files_removed` while adding a second full copy (measured: a 133-file
      repo went to 233 files / 2,589 nodes) — because that is the option anyone
      would reach for first.
- [x] **PD3.** **Two parallel prompt systems** — `CLOSED 2026-08-23`. The
      structured-intake path never uses `_CONSULT_PROMPT` and builds its own
      `_narrow_prompt`, so a "global" change lands in half the product. Bitten
      twice before (an ECONOMY edit, the caching prefix).
      Re-checked both concrete instances: **both systems now carry an economy
      rule** — `_CONSULT_PROMPT` as "ECONOMY", `_narrow_prompt` as "LENGTH", worded
      differently, which is exactly why a grep for the rule's NAME found only one
      and the debt looked live.
      Closed by making the invariant executable rather than by unifying the
      systems: `eval/drift/test_prompt_parity_offline.py` asserts that each rule
      meant to be global is present in BOTH owners, and fails naming the one that
      is missing. Add a row to its `INVARIANTS` table when a rule is meant to
      hold across both. Deliberately narrow — it lists only invariants VERIFIED
      to hold today, so a failure is a regression and not an aspiration.
      UNIFYING the two systems remains possible but is no longer urgent: the
      failure mode it was meant to prevent is now caught by a test.
- [x] **PD4.** **`code-review-graph` install is not pinned or documented** —
      `CLOSED 2026-08-23`. Installed as a `uv` tool; the exact command, the
      `--native-tls` requirement (corporate cert) and the file-lock trap are now
      in `CLAUDE.md` alongside the embedding procedure, since they are the same
      operation and the same constraint.
- [x] **H5.** **Dead-code sweep after B12** — `DONE 2026-08-23`. B12 turned out
      to be a fix that was fully written, correct in isolation, and never called.
      Swept all 435 module-level functions in `agents/`, `retrieval/` and
      `infra/` for the same shape. One more real instance:
      **`_learn_fixed_temperature_model` + `_is_temperature_error` were never
      wired in** — the runtime learner for models that reject an explicit
      temperature did not exist in the product. Only the static MEASURED list
      worked, so a NEW model with that behaviour would have 400'd on every call,
      forever, with the diagnosis sitting unused. Now both `call_llm` and
      `call_structured_llm` go through `_invoke_learning_temperature`: one
      rejection teaches the process and every later call omits the parameter.
      Verified — rejection detected, model learned, retry succeeds; a
      non-temperature error still propagates on the first attempt; live call
      unaffected. The other 22 hits were either genuinely unused utilities or
      false positives from module-qualified calls (`_ie.merge_new_issues`), so
      **A4 did ship** despite showing up in the sweep.


- [x] **H1.** `tmp/` — `DONE 2026-08-23`. Gitignored rather than deleted: it
      holds PDFs pulled during ingestion runs (3.8 MB) that no project code
      references, so it is scratch, but deleting someone's source documents is
      not a tidy-up decision to make unilaterally.
- [x] **H2.** `frontend/dist` is gitignored, so any frontend change needs
      `npm --prefix frontend run build` before the backend serves it, and a
      cache-busted reload in the browser (a stale bundle silently served old
      behaviour once this session). **Still open**, and the build step is
      recorded nowhere but here — it belongs in the README or CLAUDE.md, since
      the failure it causes (old behaviour served from a stale bundle) looks
      exactly like a code change that did not work. **DONE 2026-08-23** — both
      the build step and the stale-`:8080`-listener trap are now in `CLAUDE.md`,
      where they are read before the work rather than after the confusion.
- [x] **H3.** **Legacy model ids** — `CLOSED 2026-08-23`, and the premise was
      wrong. The item said they must stay "for backward compatibility with any
      stored client state". Verified: the frontend does **not** persist the model
      choice anywhere — `selectedModel` is `useState("")` and `model_override` is
      rebuilt per request, while `model_used` on a stored message is a display
      field that is never sent back as an override. **No stored client state can
      carry a legacy id.** (An earlier note in this session repeated the wrong
      claim in a code comment; both comments are now corrected.)
      The three dead entries in the frontend's `MODEL_TIER_LABELS` are removed —
      unreachable, since `selectedModel` can only hold a value the selector
      offers. The backend aliases in `resolve_model_from_ui` are KEPT, for the
      one real case left: a browser still running a STALE cached bundle, which
      would otherwise resolve to `None` and quietly drop to the default tier
      instead of the model it asked for. That is transient and has a definite
      expiry, unlike the permanent blocker the item claimed.

---

## SHIPPED

- **2026-08-22 · `06232bd`** — Evidence Strategist: per-charge proof-and-
  elicitation map (why / how-to-obtain incl. legal mechanism / fallback), wired
  into intake coaching. Verified live: a fully-stuck client is guided to a
  certified copy from the sub-registrar, with a handwriting-analysis fallback.
- **2026-08-22 · `4181c6a`** — Case-law citations hyperlinked to their source;
  in-chat verbatim dropped in favour of the model's explanation + the source
  behind the link. Precedents merged into the `case_laws` payload so they
  resolve.
- **2026-08-22 · `117cc67`** — In-process end-to-end conversational regression
  harness (`eval/regression/run_e2e.py`), complementing the citation golden set.
- **2026-08-22** — Full prompt audit across all stages (issue/charge, intake,
  consult, grounding, drafting, research): 13 prompt fixes + `answer_gate`
  deletion, validated by golden (3×), e2e harness, and live browser runs.
  Guidelines captured in `docs/PROMPT_GUIDELINES.txt`.

---

## UNCOMMITTED / IN TREE

_Nothing._ Case-brief enrichment (`agents/intake_engine.py`,
`agents/orchestrator.py`) was the last entry here: it is committed, and **live-
verified 2026-08-23** — see V3. The working tree is clean.
