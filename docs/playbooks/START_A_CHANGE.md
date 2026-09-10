# Start a change

Use this playbook before code changes begin. Reopen it whenever Build, Test or
Sign-off discovers that scope, authority, contract, state or proof was not
settled.

**Entry:** a requested feature, defect, refactor, control or documentation
change.

**Exit:** a Start Record supports a `READY` decision. `READY` is derived from
the checklist below; it is not a feeling and not a substitute for delivery
status in `docs/backlog/status.yaml`.

## Quick card

1. Find the registered item, its existing contract and linked journey outcome.
2. Choose the applicable scope from `docs/BUILD_GUIDE.md`; reuse unchanged
   decisions and record specific exclusions.
3. State the changed promise, forbidden outcome and recovery behaviour.
4. Inspect the affected source and existing mechanism; for fixes, measure the
   causal family and name the real population and transfer boundary.
5. Name the evidence needed for each changed promise and any critical control.
6. Record resolved decisions and `READY`, or the precise remaining blocker.

The sections below explain these checks. Do not copy every question into a
small change record. A tooling or documentation item can state its enabling
outcome without inventing a matter, forum or client instruction.

## 1. Find the registered work

Start from a `BK-` or `J-` item in `docs/backlog/status.yaml`.

- Read its reason and observations in `docs/BACKLOG.md`.
- Confirm its wave in `docs/backlog/plan.json`.
- Confirm dependencies, priority, affected journey phases and current evidence.
- Find the linked feature in `spec/features.yaml` and journey step in
  `docs/backlog/steps.yaml`.
- Find applicable PA, EW, AM and ROLE objects in
  `docs/backlog/professional.json`.

If no registered item owns deliverable work, register or expand one before
implementation. Do not leave work owned only by a chat, workbook cell, commit
message or issue title.

## 2. State the user and professional outcome

Write a short outcome statement that answers:

- Who is the user and what professional role is active?
- Who instructs and who decides?
- What decision or work product is sought?
- What is the matter, forum, deadline, objective and scope?
- What may NM retrieve, process, store or disclose?
- What does success look like to the advocate?
- What harm must the system prevent?
- What should the user see when work is blocked, uncertain or fails?

Describe an advocate-visible outcome. “Add an endpoint,” “use a new model” or
“create a table” describes an implementation, not the outcome.

## 3. Resolve the governing source

Read only the sources needed for the change, following the ownership table in
`docs/BUILD_GUIDE.md`.

Confirm:

- the PRD's DOES, NEVER, PRODUCES and EVAL obligations;
- the journey entry, action, exit and permitted return transition;
- the typed output contract;
- applicable gate behaviour and scope;
- current corpus or jurisdiction limits;
- relevant recurring defect shapes;
- previous evidence and why it may now be stale.

If two live sources conflict, stop. Classify the conflict, resolve it in the
source that owns the fact, and reconcile downstream views. Do not let the code
choose a product, legal or professional policy through a default.

Pause only the affected decision. Continue independent authorised work while
it is resolved. Routine design choices within the contract are implementation
work; a change to the user's outcome, legal meaning, authority boundary or
required proof must be recorded here before dependent implementation.

## 4. Complete the change contract

The contract must state:

| Part | Required answer |
|---|---|
| Entry | What state, identity, role, authority and prerequisite permits the operation? |
| Does | What user-visible and domain behaviour must occur? |
| Never | What unsafe, misleading or unauthorised outcome is forbidden? |
| Produces | What visible output and persisted typed state must exist? |
| Refuses | Which conditions block, withhold or disclose, and what does the user receive? |
| Recovers | What happens on timeout, cancellation, retry, replay, restart and partial failure? |
| Exit | What state proves this step is complete? |
| Return | Which changed facts, objectives, roles, evidence or law reopen an earlier state? |
| Eval | Which atomic promises and counterexamples prove the contract? |

For an interactive loop, also state pause, stop, escalation and resumption. A
partial contract does not qualify as ready.

For Take the Brief, make question economy observable: what is already known,
what permitted retrieval can answer, which unresolved point could change the
next decision, and when enough is known for a provisional response. Missing
non-material detail must not create an endless questionnaire. Urgency may
require an immediate protective next step while the fuller brief continues.

## 5. Define state, provenance and authority

Name the authoritative objects and version boundaries. For each material value,
decide which of these apply:

- source and immutable source identity;
- page, paragraph, timecode or other locator;
- instruction, allegation, admission, document, testimony, transcript,
  inference, assumption, law or judgment;
- confidence, dispute, authenticity, privilege, admissibility, weight, burden
  and materiality;
- created, checked, effective and stale times;
- dependencies and selective invalidation;
- role, commission and decision authority.

If the system could not later explain why the state or conclusion changed, the
design is incomplete.

## 6. Enumerate impact and risk

Use the code-review graph first, record its source identity and gaps, then
verify every affected caller, writer, reader, renderer, serializer, export and
recovery path in source. An empty or stale graph is not proof of absence. Add
source/registry searches for dynamic dispatch, indirect consumers, background
jobs, cache/index invalidation and non-indexed UI/document paths. Search the
defect register for the same shape and enumerate all similar sites from the
code or registry, not from memory. Record the discovery method and denominator;
a hand-picked list is not a whole-product sweep.

Consider at least:

- absent, empty, malformed and partial input;
- stale, concurrent and out-of-order state;
- retry, replay and duplicate delivery;
- timeout, cancellation, restart and unavailable dependencies;
- wrong role, matter, party, thread, version or recipient;
- low-confidence extraction and contradictory sources;
- hostile file/media and cross-matter leakage;
- long content, keyboard use and narrow layouts;
- logs, metrics, support access, export and residual data;
- false success caused by a check that did not run or parsed nothing.

Name deliberate exclusions and the item that owns them. Out of scope is a
recorded decision, not an edge discovered at release.

### 6.1 For a fix: establish the causal and transfer contract

**A causal fix contract precedes implementation.** Retain a reproducible
privacy-safe original witness: input/source identity, entry point, expected
rule, observed failure and measured failing boundary. Record diagnosis as a
hypothesis until evidence distinguishes it from plausible competing causes.
An unavailable reproduction is an open diagnostic limitation, not permission
to declare the guessed fix proved.

State the invariant and defect family without the name, phrase, Act, section
or scenario ID that exposed it. Look up prior occurrences and the mechanism
that owns them. Distinguish a shared implementation defect from incorrect
source-backed rule data: correcting a specific legal rule is legitimate when
its provenance and applicability are established, not when it supplies a
memorised answer for the incident.

Before tuning the implementation, name the original witness, distinct or
held-out contexts, and transformations expected to preserve the rule. Also
name boundary changes that **must** change the result or remain refused, and
unrelated behaviours that must stay correct. Party role, jurisdiction, date,
authority, privilege or source-version changes are not presumed equivalent.
Record why each transformation is legally and technically valid. Reuse
existing witnesses where they exercise the required behaviour.

## 7. Design proof before implementation

Break the outcome into atomic acceptance criteria. For each criterion, name:

- required evidence types;
- exact test, scenario, evaluation, review or measurement;
- population and denominator;
- a counterexample for every critical control;
- the expected failure when the counterexample is planted;
- evidence that must be marked stale if this change lands.

Ask whether the proof could pass without executing the affected population,
served path, return loop or failure. If yes, redesign it.

## Stop here when

- the work has no registered owner or active wave;
- a hard dependency is unresolved or scheduled later;
- role, commission, authority or jurisdiction is undecided;
- the feature or journey contract is partial;
- provenance, invalidation or persisted state is unclear;
- a P0 risk has no safe design;
- a critical acceptance promise has no proof or counterexample;
- a product or counsel decision is being smuggled into implementation.
- a fix has only an incident-specific answer, an unmeasured causal claim or no
  justified boundary between equivalent and materially different contexts.

Record the blocker and next decision in the authoritative work item. Do not
start Build around it.

## Close Start

Start is closed only when all applicable statements are true:

- [ ] One registered item and active wave own the change.
- [ ] Dependencies permit work to begin.
- [ ] User, role, commission, authority and outcome are clear.
- [ ] Journey step, feature and professional standards are linked.
- [ ] DOES, NEVER, PRODUCES and EVAL are complete.
- [ ] Entry, refusal, recovery, exit and return rules are stated.
- [ ] State, provenance and invalidation are defined.
- [ ] Whole-product impact and recurring defect shapes were swept.
- [ ] Security, privacy, accessibility and operational risks were considered.
- [ ] Atomic criteria, evidence and counterexamples are named.
- [ ] Required product and counsel decisions are resolved.
- [ ] Deliberate exclusions have owners.

### Start Record

Keep this in the work item's plan or implementation record:

```text
Item / wave:
Change scope / applicable obligations / exclusions with reasons:
User / role / commission:
Advocate-visible outcome:
Journey step / feature:
PA / EW / AM / ROLE:
Governing sources:
Contract — entry / does / never / produces / refuses / recovers / exit / return:
Authoritative state and provenance:
Dependencies and invalidation:
Affected population and code/data paths:
Fix only — original witness / measured cause vs hypothesis / defect family / invariant:
Fix only — graph/source inventory identity / discovery method / population / gaps:
Fix only — transfer, distinguishing boundaries and unrelated-behaviour witnesses:
Material risks and deliberate exclusions:
Acceptance criteria and required evidence:
Negative controls:
Decisions made / still blocking:
READY: yes / no, with reason:
```

**Handoff to Build:** link the closed Start Record. Build must return here if it
needs to invent scope, policy, authority, state or acceptance during
implementation.

---

<!-- THE RULES THIS PLAYBOOK CARRIES. `docs/backlog/build_rules.json`
     is the registry; this manifest is how the card CLAIMS its rules.
     Dropping one now means deleting an id here, which lint refuses --
     because two rules were lost when the guide was split and nothing
     noticed. Do not edit by hand except to add a genuinely new rule
     to the registry first. -->
<!-- BUILD_RULES: BG-001 BG-003 BG-019 BG-020 BG-021 BG-022 BG-023 BG-024 BG-025 BG-026 BG-027 BG-028 BG-029 BG-030 BG-046 BG-047 BG-048 BG-049 BG-053 BG-061 BG-078 -->
