# Start Record — an abbreviation surface for Act identification

**Status:** specified, not built. Needs a `BK-` registration before implementation
(§9). Measured 20 September 2026 against the 1,000-document evaluation set drawn
by `pipeline/acquisition/build_eval_frame.py`.

---

## 1. The defect, measured

`Manifest._named_in` identifies an Act by its full title without the year
appearing in the text, requiring `len(title) > 6`. So `Code of Criminal
Procedure` must appear verbatim.

Indian registry orders and Indian advocates do not write that. Measured across
1,285 prayer windows in the drawn set:

| form written | documents |
|---|---|
| `CPC` | 579 |
| `CrPC` | 114 |
| `BNSS` | 45 |
| `IPC` | 2 |
| `Criminal Procedure Code` (the reversed title) | 11 |

**533 of the 865 documents that name their Act by abbreviation fall through to
keyword scoring**, and 369 of them land on the **Transfer of Property Act,
1882** — scored from the words around *"Petition under Section 151 CPC praying
that in the circumstances stated in the affidavit…"*.

This is CLAUDE.md §5's wrong-Act trap. It is not confined to the evaluation
pipeline: the same `Manifest.resolve` runs at turn time, and an advocate writes
`s.151 CPC` exactly as the registry does.

`ActBasis.INFERRED` means the product discloses the guess, so no advocate is
silently misled today. The cost is that the correct Act is never *named* for the
commonest citation form in Indian practice, and an exact section lookup is
therefore never issued against it.

## 2. The outcome

An advocate who writes the Act the way Indian practice writes it gets
`ActBasis.NAMED` and an exact lookup, not a keyword score. An advocate who
writes something the manifest does not hold still gets `INFERRED` or
`NOT_RESOLVED`, disclosed as now.

## 3. Contract

**DOES** — resolve an Act from an abbreviation or a title variant recorded
against that Act in `pipeline/manifest.yaml`, returning `ActBasis.NAMED` with
the matched form in `Resolution.matched_on`.

**NEVER** —
- read an alias anywhere except the slot immediately following a provision
  reference (§4);
- let an alias outrank a full title match;
- let a shorter alias win over a longer one that also matches at that position;
- resolve to an Act not in force on the governing date, which `in_force_on`
  already owns.

**PRODUCES** — `Resolution(entry, ActBasis.NAMED, matched_on=(alias,))`.

**RECOVERS** — an alias that matches no Act leaves resolution exactly where it
is today: keyword scoring, disclosed as `INFERRED`, with alternatives named.

**EVAL** — the projection in §6, recomputed after the change; plus the three
guard tests in §5.

## 4. Why matching must be positional, and the measurement that decides it

An alias vocabulary matched anywhere in the text would reintroduce the defect
`citation.py` exists to refuse, one level up. The abbreviation namespace in
Indian court documents is **shared between Acts and case types**. Measured over
the same windows:

```
OS 86   CC 48   OP 44   WP 43   AS 31   EP 24   MVOP 21   FCOP 21   IA 14
```

`OS` is an Original Suit, `CC` a Contempt Case, `WP` a Writ Petition. `citation.py`'s
`_NOT_ABBREV` guard was written because `O.S. 442` contains `S. 442`; a flat
alias list would make the same mistake with the Act instead of the section.

**Restricting the match to the slot after a provision reference removes this.**
Measured over 1,187 windows carrying a section reference, case-number prefixes
occupy that slot **4 times** (`CRP` 1, `IA` 3) against hundreds of appearances
elsewhere in the same text.

The slot is defined as: the text immediately following a `citation.SECTION`
match, after an optional **repeated** connector sequence (`of`, `the`, `r/w`,
`read with`, `under`). The repetition is load-bearing — a single optional
connector leaves `the BNS…` after stripping `of`, and the alias no longer sits
at the position. That cost the prototype its BNS match until it was found.

`citation.py` keeps sole ownership of how a provision reference is spelled.
What this change adds is *where to look after one*.

## 5. The guard tests

Two exist and one is new.

**`test_no_act_title_is_a_substring_of_another`** — unchanged in intent,
extended in population. It must cover aliases as well as titles. Verified
against the proposed vocabulary: **no alias sits inside any Act's title.**

**`test_no_keyword_is_claimed_by_two_acts`** — mirrored for aliases:
`test_no_alias_is_claimed_by_two_acts`. Verified: **no collisions**, once
alias forms are normalised (strip non-alphanumerics, upper-case) so that `CPC`
and `C.P.C.` are recognised as one form of one Act rather than two claimants.

**New — `test_an_alias_that_contains_another_is_still_distinguished`.**
This one is required, because the vocabulary contains a genuine substring pair:

```
BNS  (Bharatiya Nyaya Sanhita, 2023)
      is a substring of
BNSS (Bharatiya Nagarik Suraksha Sanhita, 2023)
```

Both must exist and both are in force from 1 July 2024, so neither the
substring guard nor the in-force filter can separate them. **Plain substring
matching is unsafe here and the test must prove the matcher is not doing it.**

It is a *behavioural* guard rather than a string guard — it calls `resolve` on
a probe for each side and asserts the right Act comes back — because the
property that matters is that the matcher distinguishes them, not that the
strings differ. Verified on the prototype:

| probe | resolved |
|---|---|
| `section 329 of the BNS for trespass` | Bharatiya Nyaya Sanhita, 2023 |
| `section 482 of BNSS for pre-arrest bail` | Bharatiya Nagarik Suraksha Sanhita, 2023 |
| `section 151 CPC praying that` | Code of Civil Procedure, 1908 |
| `section 482 of Cr.P.C praying that` | Code of Criminal Procedure, 1973 |

The mechanism that makes it hold is **longest match at the position**. That is
the same rule `_named_in` already applies to titles, so the two paths share one
tie-break rather than acquiring a second.

## 6. Predicted effect, measured on the drawn set

| | |
|---|---|
| Act `NAMED` today | **65** of 1,000 |
| would resolve by alias | 454 |
| newly `NAMED` (were `INFERRED` or `NOT_RESOLVED`) | **446** |
| projected `NAMED` total | **~511** of 1,000 |

Gold-eligible documents in the evaluation set would rise from **64** to roughly
**500**, since gold eligibility is `NAMED` Act plus a read section.

## 7. The decision this change forces, and it is not cosmetic

**Eight documents currently resolve `NAMED` and would resolve to a different
Act.** Seven are `Indian Penal Code, 1860` → `Code of Criminal Procedure,
1973`; one is `Negotiable Instruments Act, 1881` → the same.

They are not errors in either direction. A criminal petition says both *"for
the offence punishable under Section 420 IPC"* and *"filed under Section 482
Cr.P.C"* — **two Acts and two sections in one window**. The title path finds
the IPC because the full title `Indian Penal Code` is written out; the
positional path finds the CrPC because that is the Act attached to the section
the matter was *filed* under.

For the label *"what was this filed under"* the positional answer is the
correct one. For *"which Acts does this matter engage"* both are. This change
therefore needs an explicit decision:

- **(a)** the positional match wins and the label means *the provision filed
  under*; or
- **(b)** the full title continues to win and aliases only fill the gap where
  no title matched, leaving those eight unchanged.

**(b) is the smaller change and the one to take first** — it is purely
additive, cannot regress any case that resolves today, and still delivers 446
of the 454. (a) is a change to what the field means and should be argued on
its own, not carried in on the back of an abbreviation list.

## 8. Out of scope, and worth its own item

Three Acts appear in the Act position in these documents and are **not in the
manifest at all**: Motor Vehicles Act (42 documents), Land Acquisition Act
(14), Workmen's Compensation (10). They resolve `NOT_RESOLVED`, which is
correct behaviour for an Act the manifest does not hold.

But `MACMA` — motor accident claims — is **2.7% of the Telangana docket** and
carries 34 documents in the drawn set. This is a corpus-scope finding, not a
matching defect, and it belongs in a separate item.

## 9. Blocker to `READY`

No `BK-` item owns this work. `docs/playbooks/START_A_CHANGE.md` §1 is explicit
that work must not be owned only by a chat or a commit message. Registering it
needs an entry in `docs/backlog/status.yaml`, a wave in
`docs/backlog/plan.json`, and a record in `docs/BACKLOG.md`. Next free
identifier at the time of writing is **BK-97**.

Everything else in this record is settled.
