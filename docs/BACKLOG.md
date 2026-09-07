# Backlog

What is known, not done, and not yet a defect row. Opened 6 September 2026.

**The defect register is `spec/plan/build_plan.py` and it stays the record of
things that BROKE.** This holds the other two kinds: work deliberately deferred
with the reason, and findings that need a decision before they can become a
fix. A row here is either closed by a defect row or by a decision recorded
here — it does not simply disappear.

Every entry carries WHY IT IS NOT DONE. "Not done" with no reason is
indistinguishable from forgotten, which is the whole failure this file exists
against.

---

## Open

### BK-29 - sixteen hand-picked token ceilings, and five reads that echo verbatim spans
Opened 7 September 2026, out of the BK-27 fix. **One instance is fixed; the
population is not swept.**

The dispute read ran at `max_tokens=200`. Once it began returning three
verbatim spans the JSON was truncated mid-string at character 827, the read
was lost, and the turn fell back to one thread. Nothing was wrong with the
model or the prompt.

**The shape, without the read that exposed it:** a read that must QUOTE to be
believed has an output roughly the size of its input. A constant ceiling on
such a read is a length limit on the advocate, disguised as a cost control,
and it fails by TRUNCATION - which is a parse error, not a short answer, so
the whole read is lost rather than degraded.

Measured from the code, 7 September 2026:

| | |
|---|---|
| `max_tokens=` literals in `nm/core/` | **16**, every one hand-picked at its call site |
| schemas returning a verbatim span | **7** - cause, dispute, evidence_item, factors, issues, posture, threading |
| of those, returning a LIST of spans | **5** - issues, factors, evidence items, inventory, salvage |

The five list-returning reads are the ones with the same failure available to
them, and their ceilings (400-900) were chosen against briefs nobody recorded.

**What is NOT known and must be measured before this is called safe:** whether
each of those reads FAILS SAFE when truncated. The dispute read now does -
`G-SPLIT` reports `not_assessed` and the advocate is told nobody counted -
but that third state exists only because the `Gate` constructor refused the
row without it. **A truncated read that falls back to an empty list and is
reported as a finding is S1**, and nothing here has checked.

**Why this is a row and not a fix.** The obvious repair - raise every ceiling -
is the patch, not the fix: it moves the cliff without removing it, and sixteen
call sites each choosing a number is the same one-owner question CLAUDE.md §4
asks. The fix is a ceiling DERIVED from the input for reads that echo spans,
with one owner. Sizing that needs the population measured, which is this row.

### BK-27 - one message describing N disputes opened ONE thread - **FIXED**
**FIXED 7 September 2026, and the fix was upstream of where it showed.**

The cause read was the symptom. `Thread` is already *"a dispute inside a
matter"* and already carries `posture` per dispute -- GS-09's rule, *must
never: a single matter-level posture field*. What was never given the same
treatment is the COUNT: `threading.bind` answered WHICH thread a message
belongs to and never HOW MANY it describes. Rule 4, the empty matter, returned
exactly one thread unconditionally, and the engine did not even make the
dispute read there. The justification was written into `turn.py` as a comment:

> with no thread yet, there is nothing to confuse it with

There is: the disputes inside the message, with each other. Measured on the
matter that found it -- **one thread for three disputes**, labelled
`'My client is Ravi Kumar, a retired bank employee'`, carrying one posture,
7 chronology entries spanning 2019/2024/2026, and 3 issues.

| | |
|---|---|
| `nm/core/dispute.py` | the read returns a COUNT. `verdict` is this message against the FILE; `described` is this message against ITSELF, and the second question has no file in it -- which is why turn 1 was never asked. Each item is checked against the advocate's own words and a failing item is DROPPED, because a thread gets created from these |
| `nm/core/threading.py` | rules 4 and 5 open one thread per dispute. Labels come from the read, not from `_label`'s first line. Identifiers land on the first thread only -- a case number belongs to one dispute and nothing here knows which |
| `nm/core/turn.py` | the read runs on turn 1; every thread lands on the matter. One extra model call, skipped only where a number of record decides the binding on a matter that already has threads |
| `G-SPLIT` | the disputes NOT advised on are named and marked NOT ASSESSED |

`tests/test_one_message_many_disputes.py` states the rule and not the
scenario: *a message describing N disputes opens N threads*, parametrised over
N, with nothing about land or cheques in it.

**WHAT THIS FIX DOES NOT DO, said plainly rather than left to be discovered.**
The other threads carry no posture, no chronology and no cause. They exist,
they are named, and the advocate can name one to have it worked. **They are
not advised on.** A turn derives one posture, one chronology and one
limitation; running three of those from one message is a feature and not a bug
fix, and it should be a decision rather than a side effect.

**AND THE SECOND DEFECT IN THIS ROW IS STILL OPEN.** The s.19 pass read the
cheque dishonour of 12 February 2024 as a **part payment**. That is a fact
given a type it does not have, it is independent of threading, and nothing
above touches it.

**Four checkers refused this change before any test I wrote did**, which is
the machinery working:

* `Gate.__post_init__` -- G-SPLIT had two states, and a failed count falls
  back to one thread, which reads exactly like `single`. **S1 inside the fix
  for S7.** It now carries `not_assessed` and `BindResult.counted` records
  whether anyone counted.
* `test_blank_values` -- `Described` accepted whitespace in required fields.
* `test_provider_independence` -- the scripted double could not answer the new
  schema field, so every turn through it fired `G-MODEL unavailable` while the
  model was fine. **19 of 22 failures had that one cause.**
* `Answer.__post_init__` -- the disclosure landed at position 0 and the
  recommendation must lead. `_with_screens` already carried that exact lesson
  in its docstring, so the notice now rides through it rather than beside it:
  one owner for trailing background, three call sites.

Then pylint E0601 caught `names` assigned in one branch and read in another --
correct only because the two conditions happen to agree, CLAUDE.md §6's shape.

**One check had to be repaired rather than satisfied.**
`test_a_blocked_turn_still_says_the_screens_have_not_run` asserted the literal
source text `"_with_screens(elements, screens)"` appeared three times, and
adding an argument broke it while every branch still carried the rows. It now
walks the `ast` and counts CALLS. Matching prose against code has cost this
project five checks.

Opened 7 September 2026 from a served browser run, `turn_e92eaa518ed1` on
`mat_0cc673806ea9`, kept in the History tab. Latency 35.7s, 14 model calls,
$0.0036, `outcome ok`, three non-gating violations.

The brief carried three distinct causes on one file: specific performance of a
2019 agreement of sale; two cheques dishonoured on 12 February 2024 with a
demand notice on 20 February 2024; and men entering the plot and breaking a
compound wall on **2 September 2026, five days before the turn**.

The metrics say what happened:

| | |
|---|---|
| `cause_reads` | **1** |
| `chronology_reads` | 1 |
| `route_reads` | 1 |
| issues produced | **3** |

One cause was resolved -- specific performance, routed to Limitation Act
Article 54 -- one limitation was computed from it, expiring 2022-03-01, and
**all three issues came back carrying that verdict**: each reads "it is a
threshold issue, running against the party who has to move, and it cuts
against us." A trespass five days old does not cut against us on limitation,
and neither does a 2024 cheque on its own accrual.

The thread-level line is the same error stated plainly: *"no deadline -- every
deadline on this thread has passed -- the nearest was 2022-03-01"*.

**WHAT WORKED, and it is the reason this is a backlog row and not an incident.**
The product caught its own inconsistency and refused to state the figure:

> I am not putting this figure in front of you: limitation: expires
> 2022-03-01, before events the file already records (2026-09-02). Either the
> accrual is wrong or the chronology is.

That is violation `D1`, and it is exactly right -- the accrual was wrong.
An advocate was told the derivation was inconsistent instead of being handed
a confident wrong date. The gap is that nothing goes on to ASK which of the
two it is, and nothing splits the file.

**THE SHAPE, stated without the facts that exposed it.** A matter carries N
causes; the cause reader returns one; every derivation downstream that is
per-cause -- limitation, accrual, deadlines, elements, the issue verdicts --
silently uses that one for all N. This is defect shape **S7**: a rule applied
outside the case it was derived for. It is not a limitation defect. Limitation
is where it was noticed.

**A second, separate defect in the same turn.** The section 19 reasoning read
the cheque dishonour of 12 February 2024 as a **part payment**: *"the part
payment is dated 2024-02-12 ... Section 19 applies only to one made before
expiry."* A cheque returned unpaid is the opposite of a payment. A fact was
given a type it does not have, and the acknowledgment/part-payment reader then
reasoned correctly from a wrong premise.

**Not yet fixed.** Sizing it needs the per-cause population enumerated from the
code -- every derivation keyed on a single resolved cause -- rather than a
patch at the limitation call site, which is the one place it happened to show.

### BK-28 - runs and golden sets are not in the History tab, and from now on they are
Opened 7 September 2026. **Standing instruction, recorded so it binds: from
here on every run -- served turns, eval runs, golden-set runs -- is saved in
the History tab.** Served conversations already are; nothing else is.

Measured the day this was written:

| artefact | where it lives now | in History? |
|---|---|---|
| served turns | `.nm/matters/transcripts/` (80) | **yes** |
| turn metrics | `.nm/matters/metrics/` (503) | no |
| judged eval runs | `.nm/judged/` (7) | no |
| the eval summary | `.nm/eval_results.json` | no |
| the label audit | `.nm/label_audit/worksheet.md` | no |

`/api/matters/{id}/transcript` is keyed by MATTER, which is why nothing that
is not a matter can appear there. A golden run is a run of many matters and an
eval result is not a matter at all, so this is a shape change and not a
listing change: History needs a second axis -- runs -- beside conversations.

**What must not be lost in doing it.** `pane-history` renders what was SERVED,
and the comment above it in `index.html` is load-bearing: a search hit does
not become a fact on a matter by being looked at. A runs axis that lets an
eval artefact render as though it were a served turn would break exactly that,
so the two axes stay separate surfaces inside one tab.

**Naming, done today.** The tab was "The record" and is now "History", renamed
through `web/index.html`, `web/app.js` and `web/app.css` -- token by token and
not by a blanket rewrite, because `web/` uses the word "record" in four
unrelated senses ("Registration records the Bar Council number", "none
recorded", "source size not recorded", and the design comment about what a
record IS). `pane-record` is now `pane-history`, `loadRecordMatters` is
`loadHistoryMatters`, and nothing points at the old ids.

### BK-25 - the authority need finds a case by scanning a million paragraphs
Opened 7 September 2026, out of the paragraph-labelling work. **Approved: the
case-finding step becomes a search over case SUMMARIES, and the paragraph
index is only read for the cases that step selects.**

Today `AuthorityIndexSearch.search` puts the advocate's query straight at an
FTS5 table over **451,553 attributable paragraphs** and ranks paragraphs. The
question it is actually being asked is *which judgments bear on this*, and a
paragraph index answers that badly in both directions: a case whose holding is
spread over four paragraphs competes against itself, and a case whose relevant
paragraph is labelled `arguments` is invisible - which is the failure the label
audit measured, **14 of 22 adjudicated disputes hid a holding**.

`case_summaries_v3_chunks.json` is the surface that fits the question.
Measured, 7 September 2026:

| | |
|---|---|
| entries | **32,527**, one per case, `case_id` unique |
| `court`, `year` | **100%** populated - the filters `search()` already applies still apply |
| `cited_by_count` | 87.4% non-zero |
| `citation` | **17.9%** - the derived layer dropped it again; read a hit's citation from `identity.db`, never from the summary row |
| cases with NO summary | **1,510 of 34,037 = 4.4%** |

**The shape.** Rank 32,527 summaries, take the top N by relevance and citation
weight, then read the paragraph index **filtered to those `case_id`s** for the
attributable paragraphs that are quoted. Every existing guard stays exactly
where it is: the summary decides only which cases are opened, and a `Finding`
still resolves to a `ratio`/`reasoning`/`order` paragraph or it does not exist.

**Why the type already forbids the obvious mistake.** `SourceKind` has two
members, `PROVISION` and `AUTHORITY`. A summary emitted as a Finding would
have to claim `AUTHORITY`, and `ports/evidence.py` then requires
`para_kind.attributable`, which a summary has no honest way to satisfy. The
summary cannot become a quotation by accident - it can only become one by
someone adding a third `SourceKind`, and that is a change a reviewer sees.

**Three things this must carry, none of them optional:**

1. **The 4.4% is disclosed, not absorbed.** A case held with no summary is
   unreachable through this path, and B-163's rule applies exactly - a zero
   names the index it came from. `Coverage.NOT_ASSESSED` for the summary
   stage, never an empty hit list.
2. **An absent `cited_by_count` is not zero citations.** 12.6% carry no count,
   and ranking them last on that basis is S1 wearing a sort key. Rank on
   relevance where the count is absent and say so.
3. **The summary stage is a RANKER.** It never decides that the corpus does
   not hold an authority; only the paragraph read can say that, and only about
   the cases it was given.

**What it replaces, and what it costs.** A 451,553-row FTS scan becomes a
32,527-row rank plus a `case_id in (...)` fetch. That is the cheap direction,
but it is not the argument - the argument is that the question and the index
finally match.

### BK-26 - the Act summaries are DECLINED, and the gap they would have filled stays open
Opened and decided 7 September 2026. **Decision: the case summaries are used
(BK-25); the ACT summaries are not used at all.**

`act_summaries_v3_chunks.json` holds 1,628 entries, one per Act - `act_id`,
`act_name`, `year`, `total_sections`, and a model-written summary. 1,658 bare
Acts are held, so it covers 98.2% of them. It was surveyed as a possible
widening of Act resolution and **refused**.

**Why.** The one field in it that could be checked against something else
disagreed with everything:

| Act | `legal.db` declares | `legal.db` holds | summary says |
|---|---|---|---|
| The Limitation Act, 1963 | 32 | **169** | 32 |
| The Specific Relief Act, 1963 | 44 | 44 | 44 |
| The Transfer of Property Act, 1882 | 131 | 145 | **127** |
| The Delimitation Act, 1972 | 8 | 11 | **7** |

Three of four wrong against what is held, and two of four not even agreeing
with the other declaration. **To be exact about what that does and does not
prove:** it condemns `total_sections`, which is a metadata field, and it says
nothing directly about the summary PROSE, which nothing here checked. The
decision stands on the harder ground rather than the wider claim - **the only
part of this artefact anybody could verify failed, and nothing else in it is
verifiable at all.** An unverifiable input deciding which statute is read is
CLAUDE.md section 5 exactly: fuzzy may RANK, never IDENTIFY, and never an Act.

**The gap does not close by declining this, and must not be recorded as if it
had.** `spec/manifest.yaml` carries **22 Acts**. Those are the only Acts
keyword routing can offer, so an advocate whose matter turns on any of the
other **1,636 held Acts** gets `ActBasis.NOT_RESOLVED` - not a wrong Act, but
no candidate at all, and nothing to correct in four words.

That is a real, measured hole with no owner. It stays open here, and the
answer to it - when there is one - is exact and curated, the way
`spec/manifest.yaml` already is, not a ranked read of prose nobody has
checked. `total_sections` is not evidence for any coverage figure either;
those stay in `docs/BASELINE.md`, measured, with the store named.

**A drift found on the way.** CLAUDE.md says the citation checks hold "for
today's 17 Acts". The manifest carries 22. The checks are enumerated from the
manifest and so are not wrong - the sentence is - but it is a document
disagreeing with the code about the code, which is the S4 shape and the
cheapest possible instance of it to leave standing.

### BK-24 - the citation filter excludes exactly the years the corpus needs
Opened 7 September 2026, from the first real run. **The ingestion is stopped
and is to be resumed once this is fixed.**

| year | candidates | kept, cited by >= 2 |
|---|---|---|
| 2018 | 100 | 88 |
| 2019 | 100 | 52 |
| 2020 | 120 | 51 |
| 2021 | 100 | 53 |
| 2022 | 100 | 50 |
| 2023 | 110 | **10** |
| 2024 | 120 | **0** |

**Citation count is a LAGGING INDICATOR, so filtering on it is a filter on
AGE.** A judgment delivered in 2024 has had no time to be cited; one from
2018 has had six years. The criterion does not select important judgments,
it selects old ones - and 2025 and 2026 would have returned zero for the
same reason.

**Which defeats the purpose the fetch exists for.** RG-01 fails because the
corpus holds no output of the Telangana High Court, constituted 1 January
2019, and `RG-01b` wants **a binding High Court judgment dated 2021 or
later**. The gap is RECENT binding output. A citation filter delivers old,
well-cited authority - which the corpus already holds 34,037 of.

**So the filter needs replacing, not tuning.** `--min-cited-by 1` would let
in more of 2024 and still rank 2018 above it. Candidates worth considering:

- **a per-year quota** - take the top N of each year by citations, so recency
  competes within its own cohort rather than against 2018;
- **citations per year since delivery**, which is the same correction stated
  as a rate;
- **no citation filter at all for years after 2022**, on the ground that the
  binding court's recent output is wanted whether or not anyone has cited it
  yet - which is what RG-01b actually asks for.

**What is already staged and is NOT lost:** 304 judgments, 22 MB, 2018-2023,
in `.nm/staging/judgments/`. Nothing has entered the corpus. Whatever filter
replaces this one, those files stand.

**And a second finding from the same run:** the search endpoint 429s after
10-13 pages every time, so `--pages-per-year 15` is never reached. The tool
stops that year rather than retrying, which is right. But the document
endpoint's 429 handler does `continue` where the search handler does
`break` - so if documents ever start limiting, the tool would keep firing at
a server asking it to stop. That is the one thing its own docstring says it
must not do, and it is unfixed.

### BK-23 - the web scrape is a ONE-TIME EXCEPTION, not the new route
Recorded 7 September 2026, on the advocate's instruction and in their words:
*this is a one time exception*.

`tools/fetch_judgments.py` deliberately excluded the scrape path:

> ONLY API MODE IS IMPLEMENTED. The scrape path is deliberately absent: the
> sanctioned route exists, the previous build flagged the other as ToS-bound,
> and a product that advises advocates should not acquire its corpus in a way
> it would have to explain.

**That policy still stands.** `tools/scrape_judgments.py` is a bounded
exception to it, not a replacement for it.

| the exception | |
|---|---|
| scope | Telangana, 2018-2026, 15 pages/year, cited by >= 2 |
| size | ~135 search pages, ~1,350 documents, ~1,485 requests, ~74 minutes |
| authorised | 7 September 2026, for one run |

**Why the cost is what it is, and why the API would not be cheaper.**
*Cited by N* is not a search filter on Indian Kanoon by either route - the
count lives on the DOCUMENT. So every candidate must be opened whichever way
it is acquired, and the filter cannot be pushed to the server.

**What the tool refuses rather than merely configures:** `robots.txt` is read
every run and obeyed with no override; an unreadable `robots.txt` is a
REFUSAL, because the file exists so that silence is not consent. Three
seconds between requests, one at a time, a User-Agent naming the project so
it can be asked to stop, and a hard request cap so a bug cannot make a
bounded job unbounded.

**A page that does not state a citation count is NOT treated as zero.** It is
counted and reported separately - filtering it out silently would drop
exactly the judgments a parser change had blinded the tool to.

**Still to decide, and the reason this row stays open:** whether anything
staged is promoted into `legal_database/`. Nothing enters the corpus by
running this. If the answer later is *yes, and routinely*, then the policy
above needs revisiting properly rather than by accumulation.

### BK-22 - signing in depended on a key that is meant to rotate - **CLOSED**
Closed 7 September 2026, on the advocate's challenge: *if the email and
password match, they should be able to log in, nothing else.*

**They could not, and the reason was a layer below where anyone was looking.**
The password is an scrypt hash with its salt and cost - exactly what a stored
password should be, and scrypt exists so that such a hash can sit in the
open. But the record HOLDING it was sealed with `NM_MATTER_KEY`, so verifying
a password meant first opening a file. Hand the server the wrong key and the
comparison is never reached at all.

That coupling bought almost nothing and cost exactly the failure it caused.

**The directory is now in the open**; client material is not, and none of it
lives there. Matters, transcripts and metrics keep the matter key and always
did. What is readable on disk is an advocate's OWN name, enrolment number and
firm, beside a hash that is safe in the open.

**Proven with a server started on a completely unrelated key:** *"that
password is not right for this email address"* - the record was read and the
password compared.

**The migration had to go in the READ, and unsealing the writer alone did
nothing.** `enrol` is the only other writer and it refuses to overwrite, so
every existing record would have stayed sealed forever - measured on the one
account that existed, which did not change until the read was taught to
rewrite. It converts only where the decrypt SUCCEEDED, so a record it cannot
open is left exactly as it is.

**What this does NOT fix: BK-21.** Matters are still sealed with a key that
is also the OpenAI credential, so rotating that still makes them unreadable.
It no longer locks anyone OUT of the product, which was the urgent half.

### BK-21 - the matter encryption key IS the OpenAI API key
Opened 7 September 2026. `NM_MATTER_KEY` and `NM_MODEL_API_KEY` in `.env`
hold **the same value** - an `sk-proj-...` credential - so one secret is
doing two unrelated jobs.

**Why that is a trap and not just untidy.** Rotating the API key is a
routine, expected act: it leaks, a laptop is lost, a provider forces it. Do
that and **every stored matter becomes permanently unreadable**, because the
same string was sealing them. The advocate would discover it the way this one
did on 7 September - *"this account exists and could not be opened"* - except
with no wrong key to swap back.

**It has already been demonstrated at zero cost.** `start.ps1` supplied a
different `NM_MATTER_KEY`, `load_dotenv` documents that *existing environment
variables win*, and the real key was shadowed. The account was never damaged;
it was being opened with the wrong key. That is exactly the shape of an API
key rotation, and the only difference is that the old value still existed.

**And the value is now in a session transcript.** It was printed while
diagnosing the login failure - a `grep` that displayed the line rather than
counting it. That is the reason rotation is not hypothetical.

**The order matters and it is not the obvious one.** Rotating first destroys
the matters. The sequence is:

1. generate a NEW, independent `NM_MATTER_KEY`;
2. re-key every sealed file - matters, transcripts, advocate records,
   sessions - decrypting with the old and writing with the new;
3. only then rotate the OpenAI credential.

**Step 2 needs a tool that does not exist.** It must back up before it
writes, refuse to start if anything fails to decrypt with the old key, and
verify every file reopens with the new one before removing the backup - a
half-re-keyed store is worse than either end of the operation.

**A guard is also missing:** nothing refuses `NM_MATTER_KEY` being equal to
any other credential in the environment. It is a one-line comparison at the
composition root and it would have made this impossible to configure.

**BK-21, BK-23 and BK-24.** BK-14 to BK-20 were found by the forensic audit below and
**all six were fixed on 7 September** - the audit is kept in full because
its measurements are the evidence, not the headings.

BK-20 was the recorded COST of a change the advocate asked for, and it
closed when the half it needed - the login rate limit - was built.

### BK-20 - sign-in names which of three things failed - **CLOSED, with its pair**
Opened 7 September 2026.

A1 collapsed every sign-in failure into one sentence so a stranger could
not use the form to discover which addresses are enrolled - the same
reasoning as the timing note in `authenticate`, which pays for a password
derivation on an unknown advocate so the stopwatch cannot answer either.

**That trade is now made the other way, on instruction**, and the reason is
good: three different problems were reading as one.

| state | what the advocate is told |
|---|---|
| `unknown` | no advocate is enrolled with that email address |
| `wrong_password` | that password is not right for this email address |
| `unreadable` | the account exists and was sealed with a different `NM_MATTER_KEY` - retyping will not fix it |

**The third is why it was worth doing, and it happened the same day.**
`p14lrahul@iima.ac.in` was enrolled under one key, `start.ps1` supplied a
different one, and the advocate was told their credentials were wrong on
credentials that were correct. No amount of retyping fixes that and nothing
on the screen pointed anywhere. `start.ps1` now generates a key ONCE and
reuses it, so an account survives a restart.

**And the pair is built.** `nm/domain/attempts.py` holds the policy - times
in, verdict out, no clock and no I/O of its own - and the door consults it
BEFORE the password is derived, because the point of a limiter is that the
expensive part stops happening.

**TWO COUNTERS, because one does not imply the other.** Five wrong answers
for one address in fifteen minutes, twenty from one source across all
addresses. A directory sweep tries each address ONCE and never trips a
per-account counter - so limiting per account alone would have left
enumeration exactly as cheap as before, which is the whole reason this row
existed.

**Not a lockout.** Nothing is disabled and no state is set on the account;
the window ages out. A real lockout hands an attacker a denial-of-service:
send five wrong passwords for an advocate's address and they cannot work.
The refusal says so in terms, and says WHEN - *"Try again in about 15
minute(s). Nothing is locked and no account has been changed."*

**The pause is measured from the OLDEST attempt in the window**, not the
newest. Counting from the newest would extend the pause every time the
attacker knocked, and extend it for the advocate - who is the one reading
the message.

**It fails OPEN and says so.** If the attempt log cannot be read the door
opens, because refusing every sign-in over an unwritable file is a
self-inflicted outage on a product used under time pressure. Allowing them
SILENTLY would be S1, so `/api/health` reports `rate_limiting` and shows
**NOT RUNNING** when it cannot.

Verified live: five 401s naming the failure, then 429 with the retry time.

### The forensic audit, 7 September 2026
Run by SWEEP rather than by reading: one mechanical pass per defect shape,
each drawing its population from the whole product. Six findings, and the
list of what was checked and found sound is below them - an audit that
reports only problems misrepresents the tree.

Each row says whether it is **measured** or **reasoned from the code**.

---

### BK-14 - the date came from the server's clock - **FIXED**
**MEASURED.** `nm/edge/api.py:389` takes `today=req.today or date.today()`,
and **`web/app.js` never sends `today`** - grep returns nothing. So every
served turn dates itself by whatever clock the server happens to keep.

**Nothing in `nm/` mentions a timezone.** No `ZoneInfo`, no `Asia/Kolkata`,
no `tzinfo` outside `utcnow()` for credentials. The product is scoped to
**Telangana**, which is UTC+5:30.

**What it reaches:** `limitation.days_remaining` (`expires_on - today`),
`Deadline.status`, `deadlines.passed`, `deadlines.upcoming`, and
`ours.expired(turn.today)` - the branch that decides whether the salvage
pass runs at all. A limitation date is the most consequential number this
product produces.

**The failure:** a server keeping UTC is on the previous day from 18:30
UTC onward - 00:00 to 05:30 IST. A turn taken in that window computes
every period one day short, and a claim that expires today reads as
expiring tomorrow. Silently: there is no third state for "which day is
it", because the question has never been asked.

**And no test pins the clock.** Every suite passes `today=date(2026, 9, 4)`
explicitly, so the defect is invisible to all of them by construction.

### BK-15 - six owners for the jurisdiction - **FIXED**
**MEASURED.** `"Telangana"` is a literal default in six modules:
`adapters/evidence/corpus.py:92`, `bootstrap/composition.py:133`,
`core/turn.py:188`, `edge/api.py:192`, `knowledge/jurisdiction.py:133`,
`ports/evidence.py:367`.

S9, and CLAUDE.md supplies the failure mode itself: *an answer about Kerala
law out of it is confidently wrong and nothing downstream catches that.*
Change one default and the binding computation uses a different
jurisdiction from the retrieval, with no disagreement surfaced.

### BK-16 - the matter cipher downgraded silently - **FIXED**
**MEASURED, and less bad than it first looks.** `_Cipher.__init__` catches
`ImportError` on `cryptography` and sets
`scheme = "xor-keystream(NOT-SECURE)"`. The live scheme here is **fernet**
(`cryptography` 46.0.5), and `/api/health` discloses
`"encryption": store.scheme` - so the third state IS visible.

**What is still wrong is that nothing refuses it.** A deployment without
`cryptography` starts, serves, and writes privileged client material under
a scheme the code itself labels NOT-SECURE. Keystream XOR under a reused
key is trivially broken: two ciphertexts XORed cancel the keystream.

**Its own neighbours take the opposite line.** A missing `NM_MATTER_KEY`
is a HARD FAILURE - *never a silent no-op* - and the authority index
refuses to fall back to a scan with different recall because *a fallback
swapped in silently is the three-stores defect wearing a helpful face.*
The same argument applies here and was not applied. The class docstring
even says *"Raised loudly. Never degraded into writing plaintext"* - true
of plaintext and not of this.

### BK-17 - three load-bearing guards vanished under `-O` - **FIXED**
**MEASURED.** Every `assert` in `nm/` is a guard, and `-O` removes all
three:

| where | what stops being checked |
|---|---|
| `core/turn.py:1160` | that `may_admit_substance` still REFUSES an unscreened matter. Without it substance is admitted with every screen outstanding and nothing says so |
| `domain/spoken.py:81` | that every enum member has a phrase |
| `domain/spoken.py:88` | that no phrase outlives its member |

**The second and third were written on 7 September and their docstring is
wrong under `-O`.** It says *a member with no phrase is an ImportError, not
a surprise in a served turn.* Under `-O` `complete()` is a no-op and `said`
raises `KeyError` mid-turn - precisely the outcome the sentence promises is
prevented. S11: a check that cannot fail because it is not there.

### BK-18 - the session cookie had no `secure` flag - **FIXED**
**MEASURED.** `response.set_cookie(name, value, httponly=True,
samesite="lax", max_age=..., path="/")`. The comment beside it reasons
carefully about `httponly` and `samesite` and does not mention `secure`,
which reads as overlooked rather than decided. Without it the session token
travels in clear over HTTP or a downgrade.

**THE COOKIE HALF IS FIXED**: `secure` is derived from the connection -
`request.url.scheme` plus `X-Forwarded-Proto`, trusted only upwards. The
first attempt defaulted to `secure=True` with an env-var opt-out, and a
secure cookie on a plain connection is DROPPED: six served-path tests went
401 and local development would have too.

**THE RATE LIMIT IS FIXED TOO**, with BK-20, which it pairs with.

**The rate limit was already admitted, in the wrong place.** `advocate.py`
refuses a short password with *"this is the only thing standing between one
advocate's client file and another's, and the product has no rate limit
yet"* - a known gap declared in a message the ADVOCATE reads rather than in
a row anyone tracks.

### BK-19 - a missing identity count read as zero - **FIXED**
**MEASURED.** `adapters/search/authority.py:64`: `int(rows.get(key, 0))`
over the index identity, so an identity missing `indexed_paragraphs`
reports **0 indexed** - indistinguishable from an empty index.

The atom-priors trap in miniature, and CLAUDE.md's worked example is the
same shape: `table.get(kind, 0.0)` made every unlisted atom type score
worse than every listed one. Low severity today because the builder always
writes the key; the defect is that nothing would notice if it stopped.

---

### What was checked and found SOUND
Reported because an audit listing only faults misrepresents the tree.

| swept | result |
|---|---|
| **Route authorisation** | every route derives the advocate from the SESSION (`Advocate = Annotated[str, Depends(signed_in)]`), never from a parameter, and every matter route checks `m.advocate_id != advocate_id`. A past defect - *it came from the body, which means the caller asserted it* - is recorded at `api.py:184` |
| **Encryption at rest** | matters AND transcripts are sealed with the same key; a missing key is a hard failure; the transcript is keyed by matter so attribution never depends on decrypting |
| **Broad `except`** | all 12 carry `# noqa: BLE001 -- ERROR, never a warning`, and each logs at ERROR with the type. §7 is held |
| **Mutable default arguments** | none |
| **Bare `except:` / silent `pass`** | none |
| **Set iteration reaching output** | none - no ordering nondeterminism in what the advocate reads |
| **Client text in metrics** | `domain/metrics.py` carries counts and ids only |

### The phases - **ALL SECTIONS CARRY**

| phase | what it is | state |
|---|---|---|
| **1** | the thread REMEMBERS what it concluded | **done** - six fields persist |
| **2** | the summary CARRIES those, with a third state | **done** (B-130) - 10 blockers to 6 |
| **3** | the register and the queue survive the turn | **done** (B-134) - 6 to 4 |
| **4** | the screens and the authorities | **done** (B-135) - 4 to 2 |
| **5** | the engagement and the reservations | **done** (B-137, B-138) - **2 to 0** |

`CARRIES` is **14 of 16** - the other two are `handover_complete` and
`handover_blockers` themselves, which are derived. **`handover_blockers`
is empty.**

**And emptying it exposed the defect the whole contract existed to
prevent (B-139).** `handover_complete` was `not handover_blockers`, so it
went TRUE for a matter with no client, no thread and no fact. That is
`handover_blockers`'s own counterexample one level up, and it was
invisible for as long as any section was unbuilt: the first half was
doing the second half's job by accident.

So the summary now makes both claims, which is the distinction this whole
sequence of work kept apart at every level below the top one:

| | |
|---|---|
| `handover_blockers` | sections this PRODUCT does not build - **none** |
| `not_assessed_here` | sections nothing computed **on this file** |

An empty matter reports **10 unassessed** and `handover_complete: False`.

**What is genuinely still slice 10 and untouched:** `G-SCOPE`, `G-CONFLICT`,
`G-COMPETENCE`, `G-CAPACITY`, `G-EMERGENCY`. The screens SECTION carries
five `not_run` states; RUNNING the checks is B2-B6 and R-8 still binds.
---

## Closed

### BK-13 - the product spoke in its own identifiers - **CLOSED**
Closed 7 September 2026 as **B-132**. An enum now reaches the advocate
only through a phrase it owns.

`nm/domain/spoken.py` holds the mechanism: the phrases live ON the enum
and `complete()` asserts every member has one AT IMPORT. No fallback to
`.value` - a fallback is what makes a missing phrase invisible. Seven
enums speak: `Holder`, `Form`, `Standard`, `IssueKind`, `Effect`, `Side`,
`Binding`.

The three bracket-notation findings are sentences:

| before | after |
|---|---|
| `{pos.element} [burden ours; balance_of_probabilities; held on X]` | *The burden is on us, on the balance of probabilities. It is held on X.* |
| `{i.statement} [substantive; runs against defending; opposes our case on posture v2]` | *It is a substantive issue, running against the party defending, and it cuts against us. Read on the posture as it stood at v2.* |
| `{item.what} - held by third_party, certified_copy` | *a third party has it, and what exists is a certified copy.* |

**The structure did not change, and that was the point.** The element
kinds are load-bearing: `Answer.__post_init__` refuses an answer that
leads with background, the gate matrix hangs off `disclosure`, and B-128
was five days earlier. The previous build produced advice that read
beautifully and hid what it could not establish. Better sentences INSIDE
the structure, never instead of it.

**`Element.feature` came out of it**, and its own docstring had predicted
it: the issues suite filtered findings by searching for the words *runs
against*, said so, and named the fix in the same sentence. Rewording the
findings turned three tests red - all three keyed on prose rather than on
the rule. They read `feature == "D9"`, `Effect.SUPPORTS.said`, a version
TOKEN, and `concluded["proof"]` now. **A product whose tests break when
its English improves does not improve its English.**

### BK-12 - the fold rule is asserted behaviourally - **CLOSED**
Closed 7 September 2026, and it found **B-133** on the way.

`tests/js/render_turn_partition.mjs` executes the real `renderTurn` under
plain `node` against a forty-line stub DOM and walks the tree. No npm
install: jsdom to hold one rule is R-6 apparatus, and a check that needs
a toolchain nobody maintains is a check that stops running. An absent
`node` reports **NOT ASSESSED** in those words rather than passing.

**And it was useless until a mutation said so.** Deleting `!el.disclosure`
from the partition - the exact two-character edit this exists to refuse -
left it GREEN, because the fold's renderer hard-coded `el ground` and
stripped the `disclosure` class at precisely the moment it mattered. The
partition would have been wrong AND every trace of it gone, from the
screen and from the check looking for it.

The fold now shares the class and label expression with the open half,
and the same mutation fails loudly.

### BK-11 - G-MODEL proven at one read of fifteen - **CLOSED**
Closed 7 September 2026 as **B-131**. All fifteen structured reads are
driven and each is asserted to appear IN the disclosure line.

One owner - `TurnEngine._refused_reads`, wired at both assembly sites,
drawing from `TracedModel.refused_reads`, the sibling of
`empty_decisive`. The nine `except ModelError` branches keep firing
G-MODEL and keep their degraded return; only the disclosure moved.

**Three measurement mistakes, and the tests caught the last two.**

1. The sweep that opened this row searched for any phrase the product
   uses when it is short of something. All fifteen *said something*, under
   a proxy too generous to tell a named read from an unrelated disclosure
   on the same turn.
2. The follow-up asked `read in said` - a SUBSTRING - and reported 14 of
   15 named. `"cause" in said` matches *cause of action*.
3. Nothing was being disclosed at all: the shared `build` fixture does not
   wrap the model in `TracedModel`, so `refused_reads` did not exist on it.

Two of those were fuzzy matching deciding rather than ranking, on the same
day, in the same file. The third is CLAUDE.md S8 arriving at the TEST
rather than at the edge - a guard absent from where it is exercised.

### BK-10 - the handover contract was 4 of 16 - **CLOSED**
Closed 7 September 2026 as **B-130**. `CARRIES` is **8** and
`handover_blockers` returns **6**.

The four lifted - `issues`, `theory`, `proof`, `decisions` - each carry a
STATE and not just a value: `held`, `none`, or `not_assessed`. That third
state is why this was not a rename. Every one of those fields persists as
an empty tuple until written, so empty meant both *computed and found
nothing* and *never computed* - and lifting them as they were would have
moved S9 from the turn, where an empty section is a small ambiguity, to
the handover, where it is the dangerous one.

`Thread.assessed` carries it, drawn from the KEYS of the derive phase's
`concluded` dict. One field rather than four flags: the fifth section
would have arrived without its copy.

**The six that remain are genuinely unbuilt** - `screens` is B2-B6 at
slice 10, `authorities` waits on BK-4, and `engagement`, `deadlines`,
`reservations` and `gaps` have no writer at all. The set is pinned by NAME
in the test, so it cannot drift in either direction without a deliberate
edit.

### BK-9 - five disclose gates nothing proved the advocate sees - **CLOSED**
Closed 7 September 2026. `tests/test_disclosure_reaches_the_advocate.py`
now stands at **thirteen of thirteen PROVEN** on the advocate's own bytes,
and `NOT_PROVEN` is empty and kept - an exception table that has been
deleted cannot record the next exception.

The five are in `tests/test_a_disclosure_is_served_not_recorded.py`, one
file because they are one shape rather than five topics. Each drives a
served turn, reads `out.answer.elements`, and names its gate so a rename
cannot separate the matrix row from the bytes. **Each was verified RED**
by removing its disclosure phrase from the product and re-running - BK-5's
lesson, where a served-turn assertion I was sure of passed with the fix
reverted.

`_Fails` refuses exactly one read by its `x-nm-read` name. One double, not
five: the schema already carries the read's name, so nothing had to be
invented to select on.

**It found a product defect on the way, which is the point of writing the
test rather than the note.** There was no clean-state sentence to assert
on for G-ADVERSE, because there was none - **B-129**. Three declared
states, audible on two.

**Three things corrected themselves during the work, all worth keeping:**

- The first fixture put two disputes in one message and got ONE thread, so
  the exposure read was never reached and it looked like a product defect.
  The existing suite's guard - `assert len(out.matter.threads) >= 2` - is
  now in the helper.
- The G-MODEL test asserted `"found none"` was absent. B-129's clean-state
  line ends with those words, correctly, and the assertion broke the day it
  landed. **An assertion on a fragment is an assertion on a coincidence**;
  it names the exposure pass's own sentence now.
- The accounting check could not see through `_served(out)` and called five
  correct tests proof of nothing. It follows the module's own helpers now -
  one level, and `metrics` still fails at either.

**B-077 was NOT closed by this**, though its status line reads like it.
*"Fixed - unverified on a served turn"* needs the DIFFERENTIAL judge E-073:
the defect was an asymmetry, the recommendation softening the finding
against our own client, and no assertion on the bytes can see that. Matching
a row on its status and not its substance turns a real gap into a closed one.

### BK-1 — E-102 still fails, and the verdict has moved — **CLOSED**
Fixed as **B-122** and judged: **E-102 PASS** on `mat_bf1b5f744dbc`, with the
control failing first. `nm/domain/register.py` now holds one clause and every
prompt whose words reach the advocate carries it.

The useful part was the verdict MOVING. After B-078's two structural fixes the
judge stopped quoting the recommendation and the bare Act — both fixes
confirmed — and started quoting the theory and the adversarial reads, which is
how it became visible that the rule had been applied at one site out of six.

### BK-5 — the cascade fires on an ordinary turn — **CLOSED**
Fixed as **B-123**. `_record` counted FINDING elements while B-120 had
narrowed rendering to what CHANGED, so the inventory held two items, rendered
none, and the turn announced them lost — two lines above the answer's own "2
item(s) already on the file are unchanged".

The count comes from what the thread HOLDS now. `cascade.lost`'s docstring was
false too: it named four things as re-derived every turn that are all
persisted. The check itself was right and stays.


### BK-6 — the evidence bound is reached on a four-turn matter — **CLOSED**
Measured: **every turn spent 2 of its 3 rounds re-fetching Limitation Act
s.18 and s.19** — the same two sections — leaving one round for the advocate's
actual question and none on a turn that also wanted authority.

The bound was not the problem. `MAX_EVIDENCE_ROUNDS` limits how far a turn may
WANDER, and those two sections are named by number before the turn starts —
the case `exploratory=False` was built for. Wandering fell from 3/3 to 1/3.
The number was not raised: raising a limit until it stops complaining is how a
bound becomes a formality.

The section list also had **two owners** — `factors.SECTION_FOR` and a literal
`("18", "19")` in `turn.py`. `factors.sections_needed()` owns it now.


### BK-2 - the screens are stated to the advocate - **CLOSED**
Closed 7 September 2026 as **B-128**, and the defect was sharper than
"unbuilt".

`nm/core/screens.py` had been complete since slice 6 - four states, an express
emergency exception, `unscreened` drawing its population from `ScreenKind` -
and NOTHING CONSTRUCTED A SCREEN. That is B-079's shape and B-116's shape for
the third time: a module that is right and has no production caller.

**What made it worse than unbuilt.** `_run_screens` fired `G-UNSCREENED` under
a comment claiming *"the output says so rather than reading as though it had
passed"*, and measured on 7 September the advocate saw **zero** screen-related
lines. The gate was in the metrics; the answer carried none of it. CLAUDE.md
S9 exactly - the third state must be visible in the OUTPUT, not only in the
type.

Now `_run_screens` builds five `NOT_ASSESSED` screens from the vocabulary,
asks `may_admit_substance` (which refuses, and the turn asserts that it does),
and returns `screens_mod.unscreened(outstanding)` as rows. `_with_screens`
appends them at **all three** Answer sites, blocked branches included - a turn
that stopped to ask a question has still not screened the matter, and that is
exactly when it matters.

**Two things the type caught before a test had to.** `Answer.__post_init__`
refuses a leading GROUND (PRD S6.2 S3: the answer leads with the action, never
with background), so the note is appended LAST. And the first attempt appended
to `head`, which is reassigned `list(elements)` further down - a SNAPSHOT, not
the list - so the rows were discarded silently. The measurement that found the
defect is what found the fix not working.

**The deferral reason was wrong, and that is the lesson.** B2-B6 (conflicts,
competence, engagement) remain slice 10 and R-8 still binds. But *telling the
advocate the screens have not run* is not slice 10 work - it is the disclosure
that makes the deferral honest, and it had been deferred along with the thing
it discloses. **The cost recorded here still stands:** when B3 is built, a
blank `firm_id` must read `NOT_ASSESSED` and never `CLEAR`.

### BK-3 - a served-path judged run needs a credential - **CLOSED**
Closed 7 September 2026. The premise was wrong: the password was never the
advocate's to supply, because the scenario advocate is a FIXTURE.

`tools/run_scenario.py` now mints its own - `_mint_scenario_advocate` enrols
`adv_scenarios` with a generated password held for the run and never written
down, and **refuses to re-enrol an advocate that already exists** rather than
resetting a credential it does not own. `NM_SCENARIO_PASSWORD` still wins when
it is set, so a real deployment is unaffected.

CLAUDE.md S8 was the argument for closing it rather than living with it: every
defect the first external review found lived between a correct module and the
served path, and a judged run that never crosses authentication, serialisation
and the web rendering is the weaker evidence by exactly that gap.

---

### BK-4 - the authority index - **CLOSED, and it had been done for eight days**
Closed 7 September 2026 as **B-141**, by looking at the file instead of at
this row. Measured:

| | |
|---|---|
| `.nm/authority.db` | 1,097 MB, `built_at 2026-08-30T07:51:38` |
| `partial` | **no** |
| indexed | **451,548** of 1,015,780 |
| `readiness("authorities")` | `readable` |
| a live search | **ANSWERED**, 40 binding findings, ratio and reasoning |

The row said *has never been run*. It had been run on **30 August**, and
every statement resting on it since was wrong - including a phase table
written the same morning as this correction, saying `authorities` *waits on
the index build (BK-4)*.

**The count was wrong too, and in the harder way.** `BASELINE.md`'s `ratio`
row said 144,744 where the corpus holds 144,739, so the attributable total
was 451,553 and is **451,548**. The table was internally consistent and
wrong at the source, which adding the rows up CONFIRMS rather than catches.
`CLAUDE.md` and this file had both copied the total.

**The rule it earns:** a document's claim about an artefact is a claim about
the filesystem, and it is measured there.
`tests/test_the_docs_do_not_outlive_the_artefact.py` fails the build on a
live document saying the index is unbuilt while it sits on disk.

**What is still true:** nothing in the repo triggers the build, and it stays
that way. A rebuild needs the file deleted deliberately - the tool refuses
to overwrite, because a half-written index replacing a good one is worse
than a build that would not start.

---
## Observed on GS-14, 6 September 2026 — worth a decision, not yet a defect


### BK-7 — thresholds repeated every turn — **CLOSED**
Forty words naming nine thresholds, identical on all four GS-14 turns. The
full list is given when the set CHANGES and one short clause when it has not —
the B-120 move, never silence: §9 requires the third state to be visible in the
output and not only in the type. `Thread.thresholds_told` carries what the
advocate has already been given, which is history and not a derivation.

### BK-8 — the phrase lists — **CLOSED as B-126**
Not by trimming the lists. Both are gone, with both length rules, and
`nm/core/route.py` reads the route. "bail" is one word and a case fact; "hi"
is one word and a greeting; a count cannot tell them apart.


---

## The hard-coding audit, 7 September 2026

Population from the code: every module-level literal collection in `nm/`, and
every string literal appearing in more than one module. Four kinds, and only
two were defects.

**Fixed** — `_ABOUT_NM` discarding matters (**B-124**), `_WANTS_AUTHORITY`
missing silently (**B-125**), the duplicated section list (**BK-6**).

**Correct by design, and must not be "fixed":**

| what | why it is hard-coded |
|---|---|
| `LIMITATION_ARTICLE`, `ELEMENTS`, `SECTION_FOR` | CLAUDE.md §5 mandates it — exact match decides which Act, fuzzy may never identify. These are curated legal facts with a recorded source. |
| every `_SCRIPTED_*` in `adapters/model/scripted.py` | the test double. Being scenario-shaped is what a double IS. |
| feature ids (`D5`, `C7`…), enum values, format fragments | vocabulary owned by the enums and checked by `trace`. |

### BK-8 - the phrase lists that survive, and why - **RE-MEASURED 7 Sept**
Two remain in product code, not three. **`_MATTER_SIGNALS` and `_ABOUT_NM` are
gone** (B-126) along with both length rules, so the hole recorded in the first
version of this row - a message of three words or fewer with no signal routing
to NON_MATTER, making "he absconded" a greeting - no longer exists. Measured
from the code, not from this file: `grep -rn` finds both names only in prose
explaining their removal.

The rule the survivors satisfy is B-124's: each ROUTES and neither DECIDES.

- **`chronology.CORRECTING`** (15 phrases) - documented and deliberate
  (B-088): it detects that a correction is being *attempted* and decides
  nothing, raising a question with both dates in it.
- **`limitation._WORDS` / `_DAYS`** - parsing "three years" out of retrieved
  statutory text. Not a heuristic on the advocate's message; it reads the
  corpus, and a miss leaves the period uncomputed and says so.

**Why this row was rewritten rather than left standing.** It named a list the
product no longer holds, which is a document disagreeing with the code about
what the code does - CLAUDE.md S4's shape, and the cheapest possible instance
of it to have missed.
