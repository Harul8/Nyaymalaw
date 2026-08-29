# Working on Nyaymalaw

This repository begins with documents and no code. What follows is carried
forward from a build that reached 217 stories and was then deleted — not the
code, which was the part that failed, but the rules that were learned by paying
for them. Every one exists because the same mistake recurred and cost real time.

---

## The authority chain

`docs/PRD.md` → `docs/JOURNEY.md` → `docs/GOLDEN_SCENARIOS.md` →
`docs/NM_Build_Plan.xlsx` → the code. A change that contradicts a document above
it is wrong, or the document is — decide which before writing either.

`docs/DEFECT_REGISTER.md` holds 164 reproduced defects. **Read the recurring
shapes at the top before designing a control**, because a new control that has
one of those shapes is not new.

---

## What "done" means, and what it does not

**A tenet is not done because the code looks right, and not because a structural
property holds.** The previous build had twelve mechanically-checked properties —
persisted, survives restart, cannot be bypassed, has a production caller — and
every one of them passed on a transcript where the product asked a client who
had said *"yesterday"* for the date twice, dropped an assault into a possession
cause, and analysed a twelve-year limitation on a trespass a day old.

**The twelve measured the plumbing. The client drinks the water.**

So the definition of done is `docs/JOURNEY.md` §5: a stage passes its own rubric
standalone, then the journey portfolio passes end to end with no hand-authored
inter-stage state. Structural checks remain, as a **linter**. They are necessary
and they are not the bar.

---

## Before any code change

### 1. Generalised fixes only — never scenario-specific patches
The test: **can you state the fix without naming the specific Act, section,
case, atom type, or phrase that exposed it?** If not, it is a patch, and the
next unseen input fails the same way.

Worked example worth keeping: an unretrievable Schedule Article looked like a
missing entry in an atom-priors table. The real defect was that `table.get(kind,
0.0)` made *any* unlisted atom type score worse than every listed one. One is a
patch that helps one atom type; the other fixes every atom type that will ever
exist. Prove it by **deleting the patch and re-measuring** — if the number holds,
the fix was general.

### 2. Every fix lands with an invariant test that states the RULE
Not the scenario. The test is what prevents the regression; the fix alone does
not. A test that asserts current behaviour is not an invariant — roughly fifteen
had to be rewritten in one session, **including one that asserted the very defect
it was meant to catch**. When a test breaks on a change, decide which of the two
was wrong before touching either.

### 3. Measure before diagnosing, and say which it is
A cause that has been measured and a cause that sounds right are different
things. Three confident diagnoses in a row were wrong on one retrieval gap, and
each was excluded only by instrumenting the pipeline stage by stage. **Never
report a hypothesis in the voice of a finding.**

### 4. Ask what refuses the second copy
The question is not "where is the other copy" but **"what makes a second copy
impossible?"** A prompt system with two owners meant a change described as
"global" landed in half the product, and it bit twice. If nothing structurally
refuses the duplicate, that is the defect — not the duplicate.

### 5. Renames must be swept, and pyflakes is not enough
A rename left a live call site that raised `NameError` on every matter for
weeks. A conditionally-assigned local crashed every advising turn.

```bash
python -m pylint --disable=all --enable=E0601,E0606 --score=n <package>
```

### 6. A broad `except` must not hide a bug
Failing open is usually right, but `except Exception` that logs a warning made a
`NameError` look like a model failure and silently suppressed a whole feature.
Catch programming errors separately and log them at ERROR with a traceback.

### 7. Verify on the bytes, not the return value
40/40 offline passed while every served turn crashed. **Every defect the first
external review found lived between a correct module and the served path.** A
guard that is right in the core and wrong in the composition root is not a guard.

### 8. An absent input must never read as success
The single most repeated defect, in four separate controls: a screen that could
not run returned the shape of a clean result. Three states, always — held, not
held, **not assessed** — and the third must be visible in the output, not only
in the type.

---

## Standing constraints

- **Never run the golden or e2e evals without explicit per-run approval**,
  including targeted re-runs. One approval covers a bounded batch, not an
  open-ended licence.
- **Never auto-run long pipeline steps** — train, features, predict, backtest,
  index builds. Report and stop; the user runs these.
- **Ask before destructive or irreversible actions.** Deleting corpus rows
  counts. Removing a junction with `Remove-Item` can recurse into the target —
  use `cmd /c rmdir`, which removes the reparse point only.
- Routine model calls use the cheap tier; reserve the expensive one for where it
  changes the answer.
- Do not summarise at the end of a response, and do not narrate before acting.

---

## The corpus

`legal_database/` is **22GB, gitignored, and attached as a directory junction**
(see README). It is scoped to **Telangana and the Union of India** — an answer
about Kerala law out of it is confidently wrong and nothing downstream catches
that.

**Two measured traps, both the same shape — a wrong lookup that answers
confidently:**

1. **Search the right index.** `case_name` holds party names, so a subject
   search against it returns zero and zero reads exactly like "not in the
   corpus". Bail returned **0** by name across all 33,791 cases and **1,452**
   against the summaries. Limitation Act Articles are `schedule_article` atoms
   in the chunks layer, absent from parents. **A zero result must name the index
   it came from** (`B-163`).

2. **Presence is not completeness.** Acts are partially ingested and the
   manifest records only that the Act exists. Specific Relief Act 1963: 13 of 44
   sections. Muslim Women (Divorce) Act 1986: one of seven. BNSS 2023: 162 of
   531 (`B-164`). **State coverage before relying on it.**

---

## Tooling

**Use the Write tool for any script containing escape sequences.** Heredocs
mangle `\n`, `\b` and `\uXXXX` — `\b` became a literal backspace and broke a
regex silently. This recurred four times in one session.

Git Bash converts Windows paths in arguments to native commands, which
corrupts `mklink` targets. Use the PowerShell tool for anything path-shaped.

---

## Pushing

All work goes to **`origin` → https://github.com/Harul8/Nyaymalaw**.

The corpus is gitignored and must stay that way — twelve files exceed GitHub's
100MB hard limit and one is 3.9GB. Never `git add -f` under `legal_database/`.
