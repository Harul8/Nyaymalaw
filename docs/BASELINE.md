# Baseline — what the corpus actually holds

**Every figure here was measured, not carried forward.** Measured 29 August 2026
against `legal_database/vector_store/` at `VERSION` as of that date.

**The rule this file exists to enforce:** *no claim about corpus coverage is made
without naming the store it was measured from.* The corpus holds the same Act
under more than one identifier, in more than one store, at different degrees of
completeness — so "the corpus does not have it" is a statement about a query,
not about the corpus, until the store is named.

**How to use it.** Before relying on any provision, court or period, check it
here. Before adding a figure here, measure it and record the query. A figure
without a store name and a date does not belong in this file.

---

## 1. Judgements

| Court | Judgements | Years held | Post-2018 |
|---|---:|---|---:|
| Supreme Court of India | 29,510 | 1950–2026 | 7,293 |
| High Court of Andhra Pradesh | 4,280 | **1954–2018** | **0** |
| `Supreme Court` *(unnormalised duplicate label)* | 1 | 2017 | 0 |
| **Total** | **33,791** | | |

*Store: `caselaws_v2_parents.json`, one record per `case_id`.*

**The one-row court is a normalisation defect, not a court.** A single judgement
carries `court = "Supreme Court"` where every other carries
`"Supreme Court of India"`. Any code that groups or filters on the court string
will silently drop it. Court names are normalised on read, never trusted as
stored.

### 1.1 DECIDED — every Andhra Pradesh High Court judgement held is binding on Telangana

**Decision, 29 August 2026.** All 4,280 AP High Court judgements in the corpus
are treated as **binding** authority for a Telangana matter, not persuasive.

**This is not a concession, it is what the measurement supports.** The Telangana
High Court was constituted on the bifurcation of 1 January 2019, and the
predecessor court's decisions bind the successor court's territory. Every AP
judgement held predates it — the latest is **2018**, and the post-2018 count is
**exactly zero**. So the rule "AP before bifurcation binds Telangana" and the
rule "all held AP judgements bind Telangana" currently select the same 4,280
rows.

**The tripwire, and it must be a check rather than a note.** The two rules stop
agreeing the instant one post-2018 AP judgement is ingested, and on that day
silence becomes a wrong answer — an advocate told a 2022 Andhra judgement binds
a Telangana court has been misled about the weight of their own authority.

> **CHECK `bind-1`:** on every ingest, count AP High Court judgements with
> `year >= 2019`. If the count is non-zero, this decision is void and binding
> status must be computed from the date against 1 January 2019 before the
> corpus is served. The check fails the build; it does not warn.

**What is still absent.** Zero Telangana High Court judgements, 2019 to date.
Seven years of the binding court's own output is not held, and nothing in the
decision above changes that — it establishes that the AP material we *do* hold
is usable at full weight, not that the gap is closed.

---

## 2. Acts — and the finding that matters most

**There are three stores and they give three different answers. None is
canonical.**

| Act | `snake_case` id | `JURISDICTION_YEAR_N_UPPERCASE` id | `legal.db` |
|---|---:|---:|---:|
| Specific Relief Act 1963 | 13 | **44** | 44 |
| Bharatiya Nagarik Suraksha Sanhita 2023 | 162 | **531** | 453 declared / 513 rows |
| Transfer of Property Act 1882 | 85 | **145** | — |
| Hindu Marriage Act 1955 | 11 | **37** | 31 |
| Protection of Women from Domestic Violence Act 2005 | 12 | **37** | 37 |
| Muslim Women (Protection of Rights on Divorce) Act 1986 | 1 | **7** | 0 rows |
| Gram Nyayalayas Act 2008 | 15 | **40** | 40 |
| Limitation Act 1963 | **169** | — | 32 declared / 169 rows |

**The thin copies are not merely incomplete — they are scattered.** The Hindu
Marriage Act's `snake_case` copy holds sections 6, 11, 13A, 15, 17, 21, 21C,
23A, 27, 28A and 30: no s.9, no s.13, no s.24. An advocate asking about divorce,
restitution or interim maintenance gets nothing from it, and nothing-found is
indistinguishable from no-such-remedy.

*Stores: `chunks.db` (`doc_type='bare_act'`, distinct `section_number` per
`act_id`); `legal.db` (`acts.section_count` declared, `sections` rows actual).*

Three consequences, each of which has already produced a wrong answer:

1. **A thin copy reads exactly like a gap.** The Specific Relief Act's
   `snake_case` copy holds sections 4, 5, 9, 24, 25, 29, 30, 32, 35, 36, 39, 43
   and 44 — scattered, no s.6. Query it and the summary-possession remedy does
   not exist. Query the uppercase copy and all 44 sections are there, s.6
   included, verbatim.
2. **`legal.db` disagrees with itself.** `acts.section_count` is a declared
   number, not a count of what is held: the Limitation Act declares 32 and holds
   169 rows; BNSS declares 453 and holds 513. Never read `section_count` as
   coverage.
3. **The year in an uppercase id is not the Act's year.** The Muslim Women
   (Protection of Rights on Divorce) Act **1986** is held as
   `UNION OF INDIA_1980_27_...`; the Wakf Act **1995** as
   `UNION OF INDIA_1980_9_...`. Any code parsing the year out of the identifier
   is reading a filing number.

> **CHECK `act-1`:** coverage for an Act is the **union across every store and
> every identifier convention**, and the answer names which store supplied each
> section. A coverage figure derived from one store is refused, not reported.

> **CHECK `act-2`:** where two identifiers resolve to the same Act, the
> discrepancy is reported as an ingestion defect. Two copies of one Act at
> different completeness is not a fact about the law.

### 2.1 Principal Acts, measured — union across stores

| Act | Sections held | Store carrying the full copy |
|---|---:|---|
| Code of Civil Procedure 1908 | 826 | snake_case |
| Indian Penal Code 1860 | 574 | snake_case |
| Bharatiya Nagarik Suraksha Sanhita 2023 | 531 | uppercase |
| Code of Criminal Procedure 1973 | 509 | snake_case |
| Bharatiya Nyaya Sanhita 2023 | 358 | snake_case |
| Negotiable Instruments Act 1881 | 261 | snake_case |
| Indian Evidence Act 1872 | 175 | snake_case |
| Limitation Act 1963 | 169 + **137 Schedule Articles** | snake_case |
| Transfer of Property Act 1882 | 131 | snake_case |
| Wakf Act 1995 | 118 | uppercase |
| Registration Act 1908 | 96 | snake_case |
| Indian Easements Act 1882 | 65 | snake_case |
| Guardians and Wards Act 1890 | 54 | snake_case |
| Specific Relief Act 1963 | 44 | **uppercase only** |
| Hindu Marriage Act 1955 | 31 | snake_case |
| Family Courts Act 1984 | 24 | snake_case |
| Muslim Women (Divorce) Act 1986 | 7 | **uppercase only** |

Totals across the whole corpus: **3,207** distinct `act_id` values in
`chunks.db`; **1,592** acts and **69,681** sections in `legal.db`; **414,710**
bare-act chunks.

**The Limitation Act's Schedule is a separate atom type.** All 137 Articles are
`atom_type='schedule_article'` with `section_number` of the form `Article_65`.
They are absent from the parents layer entirely, so a search that looks only at
sections finds none of them and returns a confident zero.

### 2.2 Provisions verified readable back

Each of these was retrieved verbatim on 29 August 2026, with its locator:

| Provision | Store / id | Status |
|---|---|---|
| Specific Relief Act 1963 **s.6** — suit by person dispossessed | `UNION OF INDIA_1963_1_THE SPECIFIC RELIEF ACT, 1963` | HELD |
| Muslim Women (Divorce) Act 1986 **s.3** — mahr and provision at divorce | `UNION OF INDIA_1980_27_...` | HELD |
| Wakf Act 1995 **s.51** — alienation without Board sanction void | `UNION OF INDIA_1980_9_THE WAKF ACT, 1995` | HELD |
| Negotiable Instruments Act 1881 **s.138** with provisos (a)–(c) | `the_negotiable_instruments_act_1881` | HELD |
| Indian Evidence Act 1872 **s.65** — secondary evidence | `the_indian_evidence_act_1872` | HELD |
| Limitation Act 1963 **Article 65** | `the_limitation_act_1963`, `schedule_article` | HELD |

---

## 3. Case paragraphs — what may be attributed to a court

1,015,780 case-law chunks, by `atom_type`:

| Type | Count | Share | Attributable to the court? |
|---|---:|---:|---|
| `reasoning` | 266,744 | 26.3% | yes |
| `ratio` | 144,744 | 14.3% | yes |
| `order` | 40,065 | 3.9% | yes |
| `arguments` | 149,960 | **14.8%** | **no — counsel's submission** |
| `facts` | 139,677 | 13.8% | no |
| `headnote` | 3,551 | 0.3% | no |
| `unknown` | 271,020 | **26.7%** | **cannot be vouched either way** |

**Attributable total: 451,553 — 44.5%.** Roughly one retrievable case paragraph
in seven is something a losing advocate said, and one in four cannot be
classified at all.

> **CHECK `attr-1`:** a proposition attributed to a judgement resolves to a
> paragraph of type `ratio`, `reasoning` or `order`. An `unknown` paragraph may
> be quoted with its status disclosed, and may not carry a proposition alone.

**Labels are noisy, and the noise runs both ways.** In
`HC_1998_PAVAN_KUMAR...` the sentence *"It is now settled law that in a case
falling under Article 65, the burden lies on the defendants…"* is labelled
`arguments`; in `HC_2007_MOHAMMEDIA...` paragraphs labelled `order` recite the
trial court's decree. The label is taken at face value because the alternative
is inventing an attribution — but a scenario must not be built on a single
paragraph whose label is doing all the work.

---

## 4. What the archive got wrong

Three claims carried in `docs/Archives/` were re-measured and did not hold. They
are recorded here because the *shape* of each error is more instructive than the
correction, and every one of them is the same shape.

| Archived claim | Measured | Why it was wrong |
|---|---|---|
| `B-164` — "Acts are partially ingested." Specific Relief Act 13 of 44; BNSS 162 of 531; Muslim Women 1986 one of seven | All three are **complete**, under the uppercase identifier | Measured from one store. The thin `snake_case` copy was read as the corpus |
| `GOLDEN_SCENARIOS §8b` — SRA s.6, Muslim Women 1986 s.3 and Wakf 1995 s.51 struck as ABSENT, and three scenarios cut | All three retrieved **verbatim** | Same single-store query. Three scenario expectations were struck for a defect that was in the lookup |
| `D3A` / `C2` — AP judgements need date-relative binding status | True in principle, inert in fact: **0** AP judgements post-2018 | The rule was written against a risk the corpus does not yet contain. It is now `bind-1`, a check that fires when it becomes real |

**All three are `B-163`'s shape — an empty result from the wrong index,
indistinguishable from absence.** The register named that shape and the register
itself then fell to it. That is the argument for `DEFECT_SHAPES.md`: a shape
written down is not a shape defended against. Only a check is.

### 4.1 It fired again, during the verification pass built to avoid it

On 29 August 2026, while verifying authority for the expanded golden set, four
provisions came back **NOT HELD**: Hindu Marriage Act s.13, Transfer of Property
Act s.53A, and Domestic Violence Act s.17 and s.19. **All four are held.** The
query had hit the thin `snake_case` copy of each Act.

That is **three separate occasions** on which this one shape has produced a
false gap in this project — in the previous build's register, in the first
golden-set verification, and in the pass whose stated purpose was to avoid it.
The lesson is not that more care is needed. It is that **care does not survive
repetition and a check does**:

> **`act-1` is not advice. It is a build-failing check.** A coverage figure
> derived from a single store is refused rather than reported, and every
> provision lookup queries the union across identifier conventions.

---

## 4.2 A fourth time, in the code rather than the corpus

On 30 August 2026 the **second-copy** shape (S9) produced the same class of
false gap, from the other direction. Two modules each held a pattern for
reading a provision reference; one was hardened against `O.S. 442/2023` parsing
as *section 442* and the other was not. A realistic brief retrieved
**Specific Relief Act s.442**, found nothing, and reported a corpus gap in an
Act the corpus holds in full.

**The lesson is the same one and it is now enforced the same way.** The pattern
lives in `nm/domain/citation.py`, and `tests/test_citation_patterns.py` fails
the build if a second one appears anywhere in `nm/`.

---

## 4.3 A FIFTH TIME — and this one was the biggest

**Measured 30 August 2026.** Every figure below about case identity was taken
from `vector_store/`, the DERIVED layer, and reported as a fact about the
corpus. `legal_database/raw_data/` — **34,037 source judgment files, 1.1GB** —
was never opened.

The immediate cause: `find legal_database -iname "*CaseLaws*"` returned
nothing, and **Git Bash `find` does not traverse Windows directory junctions**,
which is how `legal_database` is attached. An empty result was read as absence.
That is defect shape S3 exactly, against the corpus, for the fifth time in this
project — and this occurrence was mine, in the pass that had just finished
writing the previous four up.

**Three claims were wrong, and each was wrong in the same direction: the
derived store's poverty was reported as the corpus's.**

| Claimed, from `vector_store/` | Measured, from `raw_data/` |
|---|---|
| Bench composition: **7.5%** of cases, 0.7% for the AP High Court. "A hierarchy rule would answer *cannot tell* for 92.5% of judgments" | **`Bench:` header on 30,710 of 34,037 files — 90.2%** |
| Reporter citations: **17.9%** of judgments addressable | **`Equivalent citations:` on 27,977 — 82.2%**, 299,965 distinct citation keys |
| Party names: corrupt, 13.1% truncated, unrecoverable | `PETITIONER:`/`RESPONDENT:` on 13,625 — **40.0%**, clean |

**Every source file carries a structured header**: cites/cited-by counts, court,
title with date, `Equivalent citations:`, `Bench:`, `Author:`, and for 40% the
party blocks. The derived layer dropped all of it.

> **CHECK `raw-1`:** a claim about what the corpus holds names the LAYER it was
> measured from — `raw_data/` or `vector_store/` — and a claim of absence must
> be measured against `raw_data/`. The derived store is an artefact of one
> extraction, not the corpus.

> **CHECK `raw-2`:** never conclude absence from a `find` over
> `legal_database/`. It is a directory junction and Git Bash `find` does not
> follow it. Use PowerShell `Get-ChildItem -Recurse`, or Python `pathlib`,
> both of which do.

### 4.2.1 ONE FORMAT DOES NOT FIT SEVENTY YEARS — the rejects table

The files run from 1955 to 2026, and the header format drifts across them. A
single parser silently produces a partial record, and an undifferentiated NULL
cannot say whether a field is ABSENT from the judgment or merely written
differently in that era.

So every field that cannot be established is recorded in a `rejects` table with
a **reason** and an **era**. Measured on the first run, and the drift runs in
*opposite directions by field*:

| Era | bench missing | citations missing | parties missing |
|---|---:|---:|---:|
| 1950s | 267 | 0 | 415 |
| 1960s | 530 | 0 | 814 |
| 1970s | 550 | 0 | 1,263 |
| 1980s | 376 | 0 | 1,124 |
| 1990s | 608 | 0 | 1,787 |
| 2000s | 523 | 2 | 1,977 |
| 2010s | **14** | 758 | 6,807 |
| 2020s | 377 | **5,300** | 6,225 |

**Bench parsing fails in the old era and is clean in the 2010s. Citations and
parties fail in the modern one.** No single format assumption survives that.

**The table paid for itself on its first run.** 49% of the citation rejects
carried a NEUTRAL citation instead — `2025 INSC 407` — which the modern Supreme
Court stamps in place of an `Equivalent citations:` line. Adding it lifted
citation coverage from **82.2% to 90.9%** and halved the citation rejects,
recovering 2,973 judgments in exactly the era an advocate is most likely to be
citing.

**What is deliberately NOT recovered.** 2,222 of the 3,245 bench rejects carry
an inline `Name, J.` after the JUDGMENT heading. That names the judge who WROTE
the judgment, not the bench that heard it. Counting it would lift bench coverage
from 90.5% to about 97% and **silently demote every Division Bench whose author
signed alone** — and bench size decides which authority governs. The gap stays
open and named.

> **CHECK `rej-1`:** an ingestion pass over a corpus spanning decades records
> what it could not establish, with a reason and an era. A field that is merely
> NULL cannot be worked, and a parser with no rejects is a parser that is
> guessing.

---

### 4.2.2 What the correction unlocks, measured

Building a citation index from the 299,965 `Equivalent citations:` keys and
scanning every source file for blocks carrying a treatment verb:

| | |
|---|---:|
| Blocks containing a treatment verb | 45,509 |
| Reporter citations inside those blocks | 40,843 |
| Resolving to a held judgment | **18,629 — 45.6%** |
| **Distinct judgments reachable as a treatment target** | **6,710 of 34,037 — 19.7%** |

**0.83% → 19.7%, deterministic, no model call.** And that is a floor: it
matches on reporter citations only, over crude paragraph splits, requiring an
exact normalised key. Party-name matching against the clean `PETITIONER:` /
`RESPONDENT:` fields is not yet used.

**The bench data is real and usable.** 30,710 benches with a plausible
distribution — 4,646 single-judge, 17,645 two-judge, 6,263 three-judge, 1,087
five-judge, and benches of 7, 9 and 11. The larger-bench-supersedes rule is
buildable against that; it was declined on a measurement taken from the wrong
layer.

**`bind-1` and RG-01 survive the correction unchanged.** The source folder is
named `Telangana HC`, but the files inside label themselves *"Andhra HC
(Pre-Telangana)"*, run 1954–2018, and hold **zero** post-2018 judgments. The
folder is named for the jurisdiction served, not the deciding court — and the
source's own label independently confirms these are predecessor-court
judgments, which is the whole basis of the standing decision.

---

## 5. Measured 30 August 2026 — what slice 2 needed to know

| What | Measured | Store |
|---|---:|---|
| Provision coverage against the manifest, **union across identifier conventions** | **99.8%** of 3,038 intended sections | `chunks.db` |
| Attributable case paragraphs (`ratio`, `reasoning`, `order`) | **451,548** of 1,015,780 — 44.5% | `chunks.db` |
| Paragraphs carrying a structured `sections_cited` link | **22,127** of 451,548 attributable — **4.9%** | `chunks.db` |
| Citator entries | 4,894 — but see below | `citator.json` |
| Held judgments the citator actually reaches | **278 of 33,529 — 0.83%** | intersection, resolved through `citation_graph.json`'s 79,952 name variants |
| Held judgments with NEGATIVE treatment | **75** | `citator.json` ∩ parents |
| Citator keys naming cases the corpus does not hold | **94.3%** | Privy Council, English and older Indian authorities |
| `interprets` edges — provision → judgment | **27,164**, 100% pointing at held cases, 13,371 cases, 1,079 sections | `citation_graph.json` |
| Contamination denylist, applied on read | 44 chunk ids | `contamination_denylist.json` |

### The citator figure was reported wrongly first, and the correction matters

This file initially recorded **≤14.5%, an upper bound** — 4,894 citator entries
divided by 33,791 judgments. **That is a ratio of two set sizes, not a coverage
measurement**, and calling it an upper bound made it sound careful without
making it useful. The measured intersection is **0.83%**. Wrong by a factor of
seventeen, because 94.3% of citator keys name cases this corpus does not hold.

> **CHECK `cit-1`:** coverage is an INTERSECTION against what is held, computed
> by `tools/releasegate.py`. A ratio of two set sizes is never reported as
> coverage, whatever it is labelled.

**What follows for the product, stated plainly.** NM does not verify whether an
authority is still good law. It can answer that for 278 judgments and for 75 in
the direction that matters. For the other 33,251 it is silent, and silence is
recorded as `NOT_CHECKED` rather than read as clearance — so **no
recommendation this product makes rests on case law.** Statute carries the
advice; judgments are shown as reading material with the limit stated.

**The `interprets` edges are the more useful artefact, and they are skewed.**
27,164 provision→judgment links, all pointing at held cases — but 17,361 are
Constitution, 7,182 IPC, 1,521 CrPC and 636 CPC. The Evidence Act has 57, the
NI Act 34, the Hindu Marriage Act **2**, and the Specific Relief, Limitation
and Transfer of Property Acts **none**. Excellent for constitutional and
criminal work; absent for the property, contract and family matters this
product is aimed at. Building on it would look like it works and then silently
not.

**The `sections_cited` figure supersedes nothing and closes nothing.**
`legal.db.case_section_links` holds 0 rows, and the chunks layer's own links
cover 4.9% of attributable paragraphs, concentrated on the Constitution
(33,444), the IPC (13,472), the CrPC (3,121) and the CPC (1,224). *Which
authorities interpret this provision* is **not** answerable today for the
Evidence Act (66 links), the NI Act (63) or the Hindu Marriage Act (4).

> **CHECK `rg-01`:** these figures are measured by `tools/releasegate.py`
> against `spec/release.yaml`, written to `spec/coverage.yaml`, and **read at
> turn time** by `nm/knowledge/coverage.py`. The release decision and the
> advocate-facing disclosure rest on ONE measurement, so they cannot disagree.

---

## 5.1 Standing gaps — real, and measured

| Gap | Size | Consequence |
|---|---|---|
| Telangana High Court, 2019 → | 0 judgements | The binding court for every matter has no output held. `bind-1` governs what we may say meanwhile |
| Unclassified case paragraphs | 271,020 (26.7%) | A quarter of the case corpus cannot carry a proposition |
| Duplicate Act identifiers | present across the corpus | Coverage is a union query, never a lookup (`act-1`) |
| `legal.db` `case_section_links` | **0 rows** | The judgement→section table is empty. The chunks layer's own `sections_cited` covers **4.9%** of attributable paragraphs, so *which authorities interpret this provision* is not answerable today except for the Constitution, the IPC, the CrPC and the CPC |
| Subsequent treatment | **≤14.5%** of judgements have any citator entry | Treatment is `NOT_CHECKED` on a miss, and a `NOT_CHECKED` authority cannot carry a proposition alone. **The product may not claim to verify that an authority is still good law** |
| The authority index | **built 30 Aug 2026** — 451,548 paragraphs in 32s, 1.1GB, 564,232 excluded as non-attributable | Lexical FTS5 only. It matches WORDS, not meaning: a question naming the provision rather than the subject returns generic results until the query is seeded from the resolved provision's marginal note (`_subject_of`). Semantic retrieval would need embeddings and is not built |

---

*Measured 29 August 2026 · `legal_database/vector_store/` · queries reproducible
from `chunks.db`, `legal.db` and `caselaws_v2_parents.json`.*
