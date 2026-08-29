# Defect shapes — and the check that refuses each one

**164 defects were reproduced in the previous build. They are not 164 different
mistakes.** They are eleven shapes, each recurring across unrelated components,
because the shape is a property of the problem rather than of any one author.
The full entries are in `docs/Archives/DEFECT_REGISTER.md` and stay there.

---

## Why this file exists, and why the register was not enough

**The register already listed its own recurring shapes, at the top, in bold.**
Then, on 29 August 2026, three of its own measured claims were checked and all
three had fallen to the shape sitting first in that list — an empty result from
the wrong index, read as absence. The Specific Relief Act was recorded as
holding 13 of 44 sections. It holds all 44. Three golden-scenario expectations
were struck on the strength of it.

> **A shape that is written down is not a shape that is defended against. Only a
> check is.**

So every shape below carries a `CHECK` — a rule that structurally refuses the
defect, stated so it can be run. A shape with no runnable check has not been
understood well enough to be in this file yet, and says so.

**The test for whether a check is real:** it must be able to fail. A check that
has never rejected anything is not evidence of health; it is an unexercised
claim. Every check below ships with a **counterexample it must reject** — a
concrete input that, if the check passes it, means the check is broken.

---

## S1 · An absent input reads as success

**The most repeated defect in the register — four separate controls.** A screen
that could not run returned the shape of a clean result. A conflict screen that
was incomplete still cleared the matter. A candour pass that failed reported the
same as one that found nothing. A posture that was never established defaulted
to *our client is the aggrieved party*, and the whole analysis inverted while
staying internally consistent.

*Instances: B-06, B-131, B-137, B-150, B-155, B-161, B-112.*

> **CHECK S1.** Every screen, gate and derived value has **three** states —
> held, not held, and **not assessed** — and the third is visible in the output,
> not merely representable in the type. `unknown` is a value, never a null and
> never a default. An enumerated field rejects an out-of-vocabulary value by
> blanking it, never by accepting it.

**Counterexample it must reject:** a matter where the conflict registry was
unreadable, and the output says the screen is clear.

---

## S2 · A guard with no production caller

Correct in the type, consulted by nothing. Eight class-B invariants existed and
nothing on the served path called them. A `blocks_merits` field existed and
nothing read it. A readiness object was built as *the* gate and the served path
consulted one of its five permissions.

*Instances: B-94, B-154, B-160, B-132, B-133.*

> **CHECK S2.** Every guard is proven by a test that drives the **served path on
> the wire** — not the module that defines it. A guard with no production caller
> fails the build. Where a scripted port stands in for a real one, it must
> implement the same entry points as the real one, or the path it fronts is
> untested by construction.

**Counterexample it must reject:** a green suite on a build where the streaming
entry point does not exist, so no test ever reached the advice path.

*This is the scar behind `40/40 offline passed while every served turn
crashed`.*

---

## S3 · A zero result from the wrong index

`case_name` holds party names, so a subject search against it returns zero — and
zero reads exactly like *not in the corpus*. Bail returned **0** by name across
33,791 cases and **1,452** against the summaries. Acts are held under two
identifier conventions at different completeness. A native index served 411,797
documents against the source's 414,710, silently, through every query.

*Instances: B-163, B-05, B-19, B-47, B-57, B-56. **And the register's own
B-164.***

> **CHECK S3.** A zero result **names the index it came from**. Coverage is a
> **union across every store and every identifier convention**, never a lookup
> in one. A three-state answer — answered / not held / **held but not found** —
> is computed from a curated manifest, never inferred from a hit count, and the
> third state is a defect that escalates rather than a gap that is disclosed.

**Counterexample it must reject:** a query for Specific Relief Act s.6 that
returns nothing from the `snake_case` store and reports the remedy as
unavailable.

---

## S4 · State that dies with the turn, or with the process

An emergency found on one turn vanished on the next. Every turn was a first
meeting. A streamed turn wrote its whole opinion and then died on a context
reset. Making matters durable wrote them to disk in plaintext.

*Instances: B-103, B-106, B-145, B-135, B-158.*

> **CHECK S4.** Anything the advocate can rely on **survives a process
> restart**, and is proven by a test that actually restarts the process. State
> that is carried in memory across turns is a defect even when it works, because
> nothing distinguishes it from state that does not.

**Counterexample it must reject:** an urgency raised at turn 1, still live, and
absent from the file after a restart.

---

## S5 · Model prose escapes before the screen that guards it

The professional-duty screen ran *after* the advice it guards had been shown.
The candour lead carried model prose out before the duty screen. The urgency
actions are model text and the lead printed them first, unscreened. Both times
the type was structured — **a type constrains shape, not content.**

*Instances: B-125, B-136, B-157, B-162.*

> **CHECK S5.** No model-generated text reaches the transport before every
> screen that governs it has returned. Ordering is asserted at the composition
> root, on the bytes leaving the process — not in the module that composes the
> answer. A screen that runs correctly in the core and late at the edge is not
> a screen.

**Counterexample it must reject:** a streamed turn whose first token is model
prose and whose duty screen returns after it.

---

## S6 · A clean verdict from an input known to be incomplete

An incomplete conflict screen still cleared the matter. The manifest reconciled
presence and called it coverage. A screening note counted the matter against
itself. The proof-coverage gate certified itself.

*Instances: B-155, B-56, B-144, B-128, B-90.*

> **CHECK S6.** Incompleteness is **contagious**. A verdict computed from an
> input marked incomplete inherits the mark and cannot be reported as clean. A
> component may never be its own witness — the thing that certifies coverage is
> not the thing that produced it.

**Counterexample it must reject:** a coverage report that passes because the
step that produced it also decided it was complete.

---

## S7 · A test pinned to behaviour instead of to a rule

About fifteen had to be rewritten in one session, **including one that asserted
the very defect it was meant to catch.** A layering test asserted its own
membership list rather than the rule. A runtime assertion had a condition that
could not fail. A confirmation gate recorded a violation every time it worked.

*Instances: B-73, B-68, B-67, B-71, B-69, B-70.*

> **CHECK S7.** A test states the **rule**, not the incident — it must be
> writable without naming the Act, section, case, atom type or phrase that
> exposed it. Every test ships with a **counterexample it must reject**. When a
> test breaks on a change, decide which of the two was wrong before touching
> either.

**Counterexample it must reject:** a test that passes on the current output and
would also pass on the output the rule forbids.

---

## S8 · A patch wearing a fix's clothes

An unretrievable Schedule Article looked like a missing row in an atom-priors
table; the real defect was that an unlisted atom type scored below every listed
one. The citator matched phrases to labels, and lengthening the list improved
none of the three unknowns it was collapsing. A closed list with no legitimate
outside is a funnel, not a classification.

*Instances: B-04, B-17, B-110, B-121, B-122.*

> **CHECK S8.** State the fix **without naming the specific instance that
> exposed it**. If you cannot, it is a patch and the next unseen input fails the
> same way. Prove it by **deleting the specific entry and re-measuring** — if
> the number holds, the fix was general. A growing vocabulary list is a growing
> patch list.

**Counterexample it must reject:** a treatment classifier that handles every
phrasing on its list and misses *"we see no reason to depart from"*.

---

## S9 · Two owners for one truth

A prompt change described as global landed in one of two prompt systems and
silently applied to half the product — **and it bit twice.** The answer and the
case summary were built from separate state and disagreed. The board cited
Article 66 while the answer reasoned from Article 65. The build report disagreed
with the graph it described.

*Instances: B-10, B-85, B-98, B-52, B-82.*

> **CHECK S9.** The question is never *where is the other copy* but **what makes
> a second copy impossible.** Exactly one component owns each prompt, each piece
> of state and each derived projection; a second path calls the owner rather
> than copying it. If nothing structurally refuses the duplicate, **that is the
> defect** — not the duplicate.

**Counterexample it must reject:** a change to shared instruction text that a
grep finds in two files.

---

## S10 · A broad `except` that hides a programming error

`except Exception` logging a warning made a `NameError` look like a model
failure and silently suppressed a whole feature. `guard()` defaulted to catching
`Exception`. A named `KeyboardInterrupt` was swallowed. An outage in the urgency
step took the whole turn down.

*Instances: B-29, B-30, B-33, B-75, B-147, B-02, B-01.*

> **CHECK S10.** Programming errors are caught **separately** from expected
> failures and logged at ERROR with a traceback — never merged into a
> fail-open branch. Failing open is usually right; failing open *silently* never
> is. Renames are swept with a checker that finds undefined and
> conditionally-defined names, not with a linter that only sees unused imports:
>
> ```bash
> python -m pylint --disable=all --enable=E0601,E0606 --score=n <package>
> ```

**Counterexample it must reject:** a `NameError` on a live call site that
surfaces to the advocate as a degraded answer rather than as an error.

---

## S11 · A derived artefact trusted without its source identity

A stale BM25 index served old results silently. The coverage roll-up went stale
across partial updates. A summary generated from a superseded section reads
fluently and is invisible in a way a stale index is not.

*Instances: B-05, B-31, B-52.*

> **CHECK S11.** Every derived artefact — index, embedding store, summary,
> citator, manifest — records the identity of what it was built from and is
> **refused on mismatch**, not used with a warning.

**Counterexample it must reject:** an index whose document count differs from
its source's and which still answers queries.

---

## How a new control is designed

Before writing one, read the eleven headings. **A new control that has one of
these shapes is not new.** Then state, in one line each:

1. which shape it could take;
2. what structurally refuses that shape — not what discipline avoids it;
3. the counterexample the control must reject, written before the control.

If (2) is a convention rather than a structure, the control is not finished.

---

*Distilled 29 August 2026 from `docs/Archives/DEFECT_REGISTER.md` — 164 entries,
129 fixed, 15 open, 3 withdrawn, 17 answered.*
