# Offline passage/output pressure test

The checks prevent the exercised ownership, target, completion and persistence
errors, but **do not prevent every false claim or false rejection**. A wrongly
accepting semantic reviewer can release false prose, and repeated empty
inapplicable review metadata can withhold a substantively correct response.
No production code or prompts were changed in this pressure-test milestone.
Before Build remains the queue and status owner.

## What ran

At base HEAD `2236020`, 79 distinct user-passage/fabricated-output scenarios ran
in forward, reverse and fixed shuffled order: **237 passing test executions**,
with identical observed projections in all three runs. There was one recorded
case per test, with actual inputs, fabricated outputs, attempts, code outcomes,
expected outcomes and qualifications. The packet hashes production source,
the tests, fixture helpers and the repeat runner.

The final combined affected-flow regression run passed **246 tests** (the 79
new cases and 167 existing tests). Ruff passed for all six new test/helper/runner
files. **Zero real-model API or browser calls** were made.

| Boundary | Distinct cases | Fabricated dispatches in one pressure run |
| --- | ---: | ---: |
| Source classification and downstream source-role gate | 20 | 28 |
| Material extraction and bounded correction | 20 | 33 |
| Independent material verification and coverage | 20 | 31 |
| Authenticated `/api/turn`, reopened records and final release | 19 | 199 |
| Total | 79 | 291 |

Dispatches include initial conversation setup, extraction, checks and conditional
correction. They are synthetic calls, not latency, token or cost measurements.
Exact delivery replay and stale/conflicting request admission add zero calls in
the tested paths. Repetition does not enlarge the distinct scenario set.

Case dispositions were 21 admitted, 19 recovered, 26 blocked and **13 gap
demonstrations**. These are constructed-case categories, not population error
rates; several gap cases exercise the same unfinished invariant. All assertions
passed, including assertions deliberately proving an error remains possible.

## Concrete passage/output observations

| User passage or context | Fabricated model output | Actual observation |
| --- | --- | --- |
| Correct northern carton arrival from 17 April to 19 April. | Corrects the owned carton entry and selects its actual effect. | Reopened active record holds 19 April; the saved reply and exact code-rendered revision agree. `release_01_actual_date` |
| Correct northern carton date, preserving the rig account. | Changes the southern rig instead and claims the carton task is fulfilled. | Wrong-target success is withheld; the requested correction remains unfinished. The actual rig change is accurately disclosed. `release_02_wrong_target` |
| Ensure carton entry says 17 April, which it already does. | Selects the current owned entry with `already_current`. | Useful reply accepted without an invented write operation. `release_05_already_current` |
| Read a substantial correction passage. | Returns empty proposals; the Judge reports missing account coverage. | Partial coverage is explicit, but no extraction reread recovers the omission. `material-03-empty-date-omission-no-recovery` |
| Genuine caretaker/key account. | Source classifier wrongly labels it examination material; candidate Judge supports the original account. | Genuine proposal blocked, with no semantic source-owner reconsideration. `source-pressure-16-semantic-mislabel-false-rejection` |
| A greeting with no record-change request. | False prose says the date was changed and saved; the Judge wrongly accepts. | False prose released beside the true no-changes footer. `release_08_prose_accept_gap` |
| Correct carton date, with empty extraction. | Typed result truthfully says unresolved, but prose says corrected and saved; Judge wrongly accepts. | Task stays unfinished and old record remains, yet false prose is released. `release_18_unresolved_prose_gap` |
| A normal greeting. | Correct reply, with repeated empty retention fields on the accepted review shape. | Useful reply withheld after two review attempts. Substantive false rejection caused by a schema defect. `release_17_repeated_empty_metadata_gap` |
| Same greeting. | Same empty metadata first, correct shape second. | Reply delivered after one additional reviewer call. This is avoidable formatting friction. `release_11_split_empty_metadata` |
| Two independently supported extraction proposals. | One malformed sibling, then a complete replacement containing only its repair. | Earlier sound sibling can disappear. `extractor-15-repair-drops-valid-sibling`; strict variant `extractor-20-strict-hidden-sibling-gap` |
| Actual carton date correction. | Valid checked correction, followed by injected save failure. | HTTP 503/unconfirmed status; reopened record remains 17 April; no prepared success reply released. `release_13_failed_save` |
| Same actual correction, acknowledgement lost after durable commit. | Valid checked correction. | Durable lookup recovers the exact reply; one revision only; repeat delivery uses zero calls. `release_14_lost_ack_replay` |

Additional cases exercised mixed instructions/account, tentative and opposing
positions, unadopted quoted drafts, earlier NM analysis, authorised repair from
earlier advocate evidence, long meaningful content, foreign/missing references,
contradictory accept/support decisions, source and target coverage, restoration
successor dependencies, unread siblings, partial useful work, turn-ID conflict,
stale versions, duplicate owned selectors and bounded retry exhaustion.

## Transport and semantic limits

Source and extraction tests distinguish permissive transport followed by actual
Brain validation from strict adapter rejection using production `require_schema`.
In strict rejection, Brain receives no rejected object; correction preserves
the original input but `rejected_output` is `None`. Material-verification tests
use strict whole-envelope schema validation. Public-release tests use the
explicit offline/legacy transport, with live-shaped metadata cases; they do not
qualify real provider transport behavior.

Scripted correct rejection proves wiring, not that a real reviewer recognises
the error. Scripted incorrect acceptance demonstrates the consequence of a
wrong semantic decision. Exact quotation and owned IDs do not establish meaning.
No measured false-positive/false-negative rate, semantic accuracy or exhaustive
legal correctness follows from these runs. Real-model/browser qualification
remains deliberately deferred by the user.

## Remaining work under existing owners

- **LB-178/179:** bounded semantic source-owner reconsideration; candidate-specific
  and verdict-applicable material/dispute schemas. These remain unimplemented.
- **LB-175/178/179/182:** recover detected omissions and preserve sound extractor
  units across correction; strict whole-envelope rejection can hide peers.
- **LB-179/182/193:** remove harmless accepted-review metadata rejection without
  dropping populated contradictory content or weakening grounding.
- **LB-176/188/193:** false unrestricted effect prose is still a semantic-review
  dependency; the correct footer and typed outcome do not make it truthful.
- **LB-183:** actual model retries, useful delivery, tokens, latency, cost and
  independently labelled false acceptance/rejection evaluation remain unverified.

## Reproduce and inspect

Run `.venv/bin/python development_environment/one_off_tools/brain_pressure_test_20261006.py --output /tmp/nm-pressure-new-run --rounds 3`
from the repository. Use a fresh output directory. The runner refuses empty or
incomplete evidence, failed/skipped tests, changing source and order-dependent
observations.

The [case packet](evidence/brain-pressure-test-20261006.json) contains every paired
passage/output and the three rounds' observed projections. The
[verification record](evidence/brain-pressure-verification-20261006.json) links
JUnit evidence and source hashes. The
[workbook change record](evidence/brain-pressure-workbook-20261006.json) preserves
changed cells before/after and verifies unaffected workbook values/styles.
