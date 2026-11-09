# Baseline — what the corpus actually holds

**Every figure here was measured, not carried forward.** The initial baseline was
measured 29 August 2026 against `legal_database/vector_store/` at `VERSION` as
of that date. Later measurements carry their own date and store.

**The rule this file exists to enforce:** *no claim about corpus coverage is made
without naming the store it was measured from.* The corpus holds the same Act
under more than one identifier, in more than one store, at different degrees of
completeness — so "the corpus does not have it" is a statement about a query,
not about the corpus, until the store is named.

**How to use it.** Before relying on any provision, court or period, check it
here. Before adding a figure here, measure it and record the query. A figure
without a store name and a date does not belong in this file.

---

## 0. The library as it stands now — measured 8 November 2026

**Stores named: the judgment store searched is `judgments_v4` (swapped in 8 November 2026; record
`.nm/retrieval/judgments.lineage.json`); the Acts store searched is `acts_v5` (record
`.nm/retrieval/bare_acts.lineage.json`).** Sections 1–5 below were measured earlier, from earlier
stores, and say so; where this section gives a figure for the same thing, this one is the figure for
the library now. Queries and scripts: read-only counts over each store's own database, judgment list
and catalogue; nothing was sampled except where it says so.

### 0.1 Judgments — `judgments_v4`

| | |
|---|---:|
| Judgments | **34,037** |
| Passages | **990,668** (median 20 a judgment, most 2,162) |
| Judgments that print paragraph numbers | 20,745 (60.9%) |
| Judgments that print none | 13,292 (39.1%) |
| Judgments not in the earlier store (every kind unknown) | 249 |
| Passages over the search model's reading limit after the cut | 2 |

| Court (as the product shows it) | Judgments | Years held | After 2018 |
|---|---:|---|---:|
| Supreme Court of India | 29,748 | 1950–2026 | 7,477 |
| High Court of Telangana (filed as the Andhra Pradesh High Court: 4,280 as "High Court of Andhra Pradesh", 9 as "Andhra HC (Pre-Telangana)") | 4,289 | **1954–2018** | **0** |

**Check `bind-1`, run on this ingest (§1.1): Andhra Pradesh / Telangana High Court judgments with
`year >= 2019` = 0.** The decision that every held Andhra Pradesh High Court judgment binds Telangana
stands. The unnormalised one-row court label of §1 is gone: the court is read from the filing and
named once.

**How a passage is called (locator), by a sample of every 20th passage (49,534):** the court's
printed paragraph number 61.8%; "passage N", for what the court never numbered, 33.8%; "opening of
the judgment" 4.4%. Every part of a long paragraph carries its paragraph's number.

**Kinds of passage (all 990,668).** Attribution to a court (§3) needs the kind to be known; 28.9% are
still unknown.

| Kind | Passages | Share | Attributable to the court? |
|---|---:|---:|---|
| unknown | 286,433 | 28.9% | not yet named |
| reasoning | 243,934 | 24.6% | yes |
| arguments | 146,990 | 14.8% | **no — counsel's submission** |
| ratio | 146,241 | 14.8% | yes |
| facts | 123,352 | 12.5% | recited, not held |
| order | 38,901 | 3.9% | yes |
| headnote | 4,817 | 0.5% | no — not the court's |

**What the judgments cite** (read from their own words; the build left 3,890 notes on how a judgment
was read — a paragraph that runs on and was cut, a judgment the earlier store did not hold): the
reporter citation of the judgment itself found in 26,785 judgments; 207,029 citations of other cases
in 24,146 judgments; **301,804 citations of a section, by what the Act resolved to:** held
237,556 (78.7%), the Act named but not held 28,670 (9.5%), not decided 33,353 (11.1%), ambiguous
(two Acts of that name in force that year) 2,225 (0.7%). The Acts were named by exact name or by the
59 short names the owner checked (115 ways of writing, `pipeline/act_aliases.json`); nothing was
guessed.

**Vectors and word index:** 990,668 vectors of 1,024 dimensions made by `BAAI/bge-large-en-v1.5`,
4,057,776,173 bytes; a word index of the same 990,668 passages; at recording, 60 of 60 sampled
passages encoded again matched their stored vector.

### 0.2 Acts — `acts_v5`

| | |
|---|---:|
| Acts | **1,621** (Union of India 1,259; Telangana 362) |
| Passages | **351,184** (one vector each; 351,182 until the Limitation Act's two missing Articles were added, 9 November 2026) |
| Standing, as India Code gives it | in force 1,174; not stated 242; not in force 205 |
| Instruments the search keeps (the one-copy register) | 1,587 kept; 44 copies not searched; 2 excluded |

Passages by kind: sub-section 110,343; clause 109,419; section head 66,190; sub-clause 40,640;
proviso 18,733; explanation 5,339; illustration 383; schedule article 137 (135 before 9 November 2026).

**Principal Acts now (sections as the store numbers them).** An Act is held once, under the name its
text now carries.

| Act | Sections | Standing (India Code) |
|---|---:|---|
| Code of Civil Procedure, 1908 | 882 | in force |
| Indian Penal Code, 1860 | 574 | not in force |
| Bharatiya Nagarik Suraksha Sanhita, 2023 | 537 | in force |
| Code of Criminal Procedure, 1973 (filed 1974) | 606 | not in force |
| Bharatiya Nyaya Sanhita, 2023 | 358 | in force |
| Bharatiya Sakshya Adhiniyam, 2023 | 170 | in force |
| Indian Evidence Act, 1872 | 180 | not in force |
| Negotiable Instruments Act, 1881 | 166 | in force |
| Limitation Act, 1963 | 32 sections + **137 Articles of the Schedule** (135 until 9 November 2026) | in force |
| Transfer of Property Act, 1882 | 149 | in force |
| Unified Waqf Management, Empowerment, Efficiency and Development Act, 1995 (the Wakf Act, 1995, as renamed in 2025) | 126 | in force |
| Registration Act, 1908 | 97 | in force |
| Indian Easements Act, 1882 | 64 | in force |
| Guardians and Wards Act, 1890 | 55 | in force |
| Specific Relief Act, 1963 | 48 | in force |
| Hindu Marriage Act, 1955 | 37 | in force |
| Family Courts Act, 1984 | 23 | in force |
| Muslim Women (Protection of Rights on Divorce) Act, 1986 | 7 | in force |

The six provisions of §2.2 are held in `acts_v5`: Specific Relief Act s.6 (7 passages), Muslim Women
Act s.3 (12), Negotiable Instruments Act s.138 (6), Indian Evidence Act s.65 (8), Limitation Act
Article 65 (1), and the Wakf Act s.51, now s.51 of the Unified Waqf Management Act ("Alienation of
waqf property without sanction of Board to be void").

**Two findings of this measurement.**

1. **Two Articles of the Limitation Act's Schedule are not held.** Of Articles 1–137, 105 ("By a
   Hindu for arrears of maintenance", three years) and 127 ("To set aside a sale in execution of a
   decree", sixty days) are in the Act's source text
   (`legal_database/raw_data/BareActs/Union of India/1963_0_The Limitation Act, 1963.txt`) and are
   not among the 135 held. Articles 54 and 65 are held. Why these two were dropped is not established;
   the source prints the first period as "Three yean" and the second as "5[Sixty] days", which a
   reader expecting a clean period may have refused. Until they are held, a search for the period for
   arrears of maintenance or for setting aside an execution sale finds nothing, which reads as no
   such rule (the confident-zero shape of §2.1). **The reader is repaired (8 November 2026):** on the
   real text it now reads all 137 Articles, takes the editor's mark out of "5[Sixty] days", reads
   "Three yean" as "Three years" (changed 9 November 2026; first it kept the misprint as printed) and says
   so in the Act's schedule notes, and names any Article it leaves out.
   **The held store was corrected on 9 November 2026 (the owner ran the job, server stopped).** The
   Act's 280 held passages stayed word for word unchanged and 2 were added (351,182 → 351,184
   passages), at positions 80717 (Article 105) and 80739 (Article 127). Checked afterwards, reading
   only: the passage store, the vector index and the word index each hold 351,184; positions run
   without a gap; the lineage record agrees (index bytes, word-index parameters, passage count); the
   Act has 137 Articles; the Act that follows it starts at 80750. The earlier files are kept beside
   the live ones as `.before-20261109T041124` (about 2.4 GB: the passage store, the vector index and the word index; the
   owner's to remove). Article 105's
   period is **still stored as the text prints it, "Three yean"**, so a word search for "three years"
   does not match it; the meaning search can. The reader now reads it as "Three years" (a dry run
   finds 281 of the Act's 282 passages unchanged and only this one changed); the store changes when the
   owner runs the correction for the Limitation Act a second time, server stopped.
2. **The Wakf Act 1995 is held only under its 2025 name.** A plan that names "the Wakf Act" matches
   no held name and is told it is not held; the owner's checked short names (59) do not include it.

### 0.3 Not re-measured here

The Acts' vectors in the store searched are those made from each passage as shown (its first line
included). Vectors made from each passage's own wording (plan AN.45, D91) were built beside them on
8 November 2026 (351,182 vectors, 60 of 60 sampled matched, `acts_v5_wording.index`; the store now
holds 351,184 after the 9 November correction, so that candidate is two vectors short and its index
stage would be run again before any swap) and **not swapped in**: the owner's comparison tool, run on its 80 composed questions over a sample library of 21,460
passages of 57 Acts, finds them modestly worse in the product's whole search (first place 65 of 80
against 68; 79 questions found against 80; mean 1/rank 0.873 against 0.900; 9 worse, 4 better, 67
the same) and worse alone (first place 57 against 66; 18 worse, 6 better), most for questions that
name the Act; the word search is the same by construction. The questions are composed, not sampled
(`docs/GOLDEN_SET.md` §7), and the sample is not the whole library. Sections 1–5 below keep their
dates and stores. The defects and their causes (§4) are history
and still describe how those stores went wrong.

---

## 1. Judgements

> **Superseded for the library now by §0.1.** The figures below are those of 29 August 2026,
> measured from `caselaws_v2_parents.json`.

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

**What is still absent, stated correctly.** The corpus holds **4,280 High
Court judgements binding on Telangana**, running 1954–2018, and **none dated
later than 2018**. That is a *recency* gap in binding High Court authority,
not an absence of it.

The distinction is not pedantry, and it cost something. This paragraph used
to read *"zero Telangana High Court judgements"* — literally true of the
court LABEL, and false of the product's own decision above, under which every
one of those 4,280 is a Telangana judgement. `pipeline/releasegate.py` was
written from this sentence: RG-01 counted the label, got 0, blocked the
release, and made G-COVERAGE tell the advocate on every authority turn that
*no High Court output is held for this jurisdiction.* See defect **B-044**.

The two statements lead an advocate to different next moves — *"I have
nothing for you"* against *"check whether anything has moved since 2018"* —
so they are now separate release rows: **RG-01** (binding-court output held)
and **RG-01b** (that output is current).

Supreme Court output is continuous and binds throughout: 29,511 judgements
running to 2026.

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

### 2.3 Bare-act search artefacts, measured 29 September 2026

> **Superseded for the library now by §0.2:** the Acts store searched is `acts_v5`, 351,184 passages
> of 1,621 Acts, one copy of each instrument; the 414,710 passages and `bareacts_v3` below are the
> store of 29 September.

The bare-act search set contains **414,710 passages** in `chunks.db`
(`doc_type='bare_act'`, positions 0–414,709), **414,710 vectors** in
`bareacts_v3.index` (1,024 dimensions, inner product on normalised vectors),
and **414,710 documents** in `bareacts_v3_bm25s`. The recorded embedding model
is `BAAI/bge-large-en-v1.5`. The lineage job encoded 60 sampled passages and
compared each with the vector at its own position: 60/60 met its threshold;
the lowest similarity was 0.9391 and the mean was 0.9981. These figures are
recorded in `.nm/retrieval/bare_acts.lineage.json` and read from the three
members under `legal_database/vector_store/`.

The product now combines word and vector search over those passages, reranks
the merged results, and reads candidate sections through the provision reader.
Ranking does not establish which Act governs. The append job has passed offline
tests but has not been run on a new real Act. A new Act also needs a reviewed
curated-manifest entry before the product will read its sections as candidates.

---

## 3. Case paragraphs — what may be attributed to a court

> **Superseded for the library now by §0.1:** the judgment store searched is `judgments_v4`, 990,668
> passages cut on the courts' own paragraphs. The 1,015,780 chunks and their kinds below are those of
> the earlier store, cut by size.

1,015,780 case-law chunks, by `atom_type`:

| Type | Count | Share | Attributable to the court? |
|---|---:|---:|---|
| `reasoning` | 266,744 | 26.3% | yes |
| `ratio` | 144,739 | 14.3% | yes |
| `order` | 40,065 | 3.9% | yes |
| `arguments` | 149,960 | **14.8%** | **no — counsel's submission** |
| `facts` | 139,677 | 13.8% | no |
| `headnote` | 3,551 | 0.3% | no |
| `unknown` | 271,020 | **26.7%** | **cannot be vouched either way** |

**Attributable total: 451,548 — 44.5%.** Roughly one retrievable case paragraph
in seven is something a losing advocate said, and one in four cannot be
classified at all.

> **Re-measured 7 September 2026, against the corpus.** The `ratio` row said
> **144,744** and the corpus holds **144,739**, so the attributable total was
> 451,553 and is 451,548. The table was internally consistent and wrong at the
> source — which is the harder kind to catch, because adding the rows up
> confirms it.
>
> TWO INDEPENDENT SOURCES AGREE ON THE NEW NUMBER: a direct count of
> `paragraph_type` over the 1,015,780 case-law chunks, and the built index's
> own `indexed_paragraphs`, which is 451,548. `CLAUDE.md` and
> `docs/BACKLOG.md` had both copied the old total.

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

Three claims carried in `development_environment/archives/` were re-measured and did not hold. They
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
lives in `nm/legal_brain/common/citation_contracts.py`, and `tests/test_citation_patterns.py` fails
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
> by `pipeline/releasegate.py`. A ratio of two set sizes is never reported as
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

> **CHECK `rg-01`:** these figures are measured by `pipeline/releasegate.py`
> against `assurance/specification/release.yaml`, written to `assurance/specification/coverage.yaml`, and **read at
> turn time** by `nm/legal_brain/retrieve/coverage_sources.py`. The release decision and the
> advocate-facing disclosure rest on ONE measurement, so they cannot disagree.

---

## 5.1 Standing gaps — real, and measured

| Gap | Size | Consequence |
|---|---|---|
| Binding High Court authority since 2018 | 0 judgements *later than 2018*; **4,280 held in total** | Recent High Court authority is not held. It is **not** the case that no High Court output is held — that framing was measured, shipped and wrong (**B-044**). Supreme Court output runs to 2026 and binds throughout |
| Unclassified case paragraphs | 271,020 (26.7%) | A quarter of the case corpus cannot carry a proposition |
| Duplicate Act identifiers | present across the corpus | Coverage is a union query, never a lookup (`act-1`) |
| `legal.db` `case_section_links` | **0 rows** | The judgement→section table is empty. The chunks layer's own `sections_cited` covers **4.9%** of attributable paragraphs, so *which authorities interpret this provision* is not answerable today except for the Constitution, the IPC, the CrPC and the CPC |
| Subsequent treatment | **≤14.5%** of judgements have any citator entry | Treatment is `NOT_CHECKED` on a miss, and a `NOT_CHECKED` authority cannot carry a proposition alone. **The product may not claim to verify that an authority is still good law** |
| The authority index | **built 30 Aug 2026** — 451,548 paragraphs in 32s, 1.1GB, 564,232 excluded as non-attributable | Judgment retrieval uses lexical FTS5. It matches words rather than meaning: a question naming the provision rather than the subject returns generic results until the query is seeded from the resolved provision's marginal note (`_subject_of`). Semantic judgment retrieval has not been built; the bare-act search set in section 2.3 is separate |

---

*Measured 29 August 2026 · `legal_database/vector_store/` · queries reproducible
from `chunks.db`, `legal.db` and `caselaws_v2_parents.json`.*
