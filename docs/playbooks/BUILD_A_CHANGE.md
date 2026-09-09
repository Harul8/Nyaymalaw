# Build a change

Use this playbook only after Start is closed. It governs implementation, not
scope discovery. If implementation reveals a missing contract, policy,
authority or acceptance decision, reopen Start.

**Entry:** a closed Start Record with a `READY` decision.

**Exit:** a Build Record supports `BUILT`: the smallest complete vertical
outcome is implemented, reviewed and ready for independent verification.
`BUILT` does not mean verified, conformant, done or releasable.

## 1. Reconfirm the boundary

Before editing:

- read the Start Record and current registered state;
- confirm no dependency, source, decision or evidence changed;
- inspect existing mechanisms for the same rule or defect shape;
- map the exact domain, orchestration, persistence, adapter and interface paths;
- preserve unrelated user changes in the working tree.

If the Start Record is stale or the boundary has materially changed, return to
Start before proceeding.

## 2. Implement one vertical outcome

Make the user path complete across every layer it needs:

1. accept only permitted input;
2. validate identity, role, authority and applicable gates;
3. convert input into typed, attributable domain state;
4. derive or retrieve through explicit ports;
5. validate model or external output before accepting it;
6. apply state transitions and selective invalidation;
7. commit atomically before substantive output;
8. render truthful state and recovery to the user;
9. retain audit and evidence needed to explain the result.

Horizontal infrastructure may be built as a prerequisite, but it does not close
Build until the named vertical outcome uses it.

## 3. Keep deterministic mechanics outside the model

Enforce these in code and typed state, not only in prompts:

- authentication, role and permission;
- matter, party, thread, source and authority identity;
- dates, arithmetic, limitation and deadline status;
- validity windows, binding relationships and coverage states;
- gates, readiness, advice maturity and transition rules;
- idempotency, concurrency, persistence and audit;
- source existence, locators and required fields.

Models may interpret narrative, generate candidates, compare plausible legal
positions and assist judgment. Treat their output as proposed input to
validation. Never let a model's fluency become permission, fact or proof.

## 4. Preserve legal and evidential distinctions

Do not collapse instruction, allegation, admission, document, testimony,
transcript, inference, assumption, law and professional judgment. Preserve the
source and locator across ingestion, extraction, retrieval, state, reasoning,
display and export.

Changed input must invalidate only dependent work. Unrelated work should remain
current. The resulting record must show what changed, what became stale and why
the revised position differs.

**Taking the brief is a loop, not a form.** Refuse a fixed intake questionnaire
that asks what the file already holds or what retrieval could answer. Rank the
next question by the decision it unblocks, use what is already known or
retrievable first, and let a changed objective reopen the questions that rested
on it.

## 5. Make unsafe and unknown states impossible to misread

Use explicit states for positive, negative and not assessed. Add partial,
blocked, stale or low-confidence when they change user action.

- An unavailable screen is not a clean screen.
- Nothing found is not automatically nothing held.
- An empty population is not automatically a passing population.
- An attempted transmission is not a confirmed action.
- A provisional view is not considered advice.
- A warning appended after unsafe content is not a gate.

Refusal and degraded behaviour must name what could not be established, the
effect on the task and the next safe step.

## 6. Commit before emit

The accepted turn and resulting state commit atomically before substantive
bytes leave the composition root. Prove the following where applicable:

- a replayed logical operation is not applied twice;
- opening a matter is idempotent even before a matter ID exists;
- a concurrent stale version is re-derived or rejected deliberately;
- a commit failure cannot yield apparently successful output;
- retry and restart recover the same truthful state;
- audit-write failure remains visible;
- the reopened file agrees with what the user received.

Do not infer served-path correctness from a core return value.

## 7. Apply one mechanism across the population

For a feature or defect mechanism:

1. state the general rule without naming the example that exposed it;
2. reuse an existing mechanism if one owns that rule;
3. enumerate every applicable site from code or registry;
4. apply one mechanism across them;
5. remove superseded point guards;
6. make the proof enumerate the same population.

A general explanation with a one-site implementation is still a patch.

## 8. Keep one owner for every truth

Put policy in its authoritative domain object or registry. Keep adapters behind
ports. Keep orchestration explicit enough to audit order. Generate views and
exports from authoritative state.

Do not create another copy of:

- gate behaviour;
- status, wave or dependency;
- model or prompt policy;
- role permissions or authority;
- corpus coverage or binding identity;
- UI labels that independently decide domain state.

If a boundary requires duplication, add blocking reconciliation in both
directions.

## 9. Build security, privacy and usability into the path

Apply matter isolation, least privilege, encryption, purpose limitation,
retention, deletion and auditable support access wherever relevant. For media,
preserve original bytes and hash, scan and quarantine, control processors,
retain page/timecode and confidence, and support correction and deletion.

In the interface, use user language. Preserve keyboard operation, focus,
semantics, visible progress, cancellation, responsive layout and recovery.
Test with realistic long and adverse content while implementing; do not defer
all usability work to Sign-off.

**A recommendation is never authority to act.** The advocate decides and the
advocate acts. NM may prepare, draft, rank and advise; it may not concede,
settle, file, serve, transmit or bind, and no output may read as though it
has. Every external or irreversible step passes through an explicit,
recorded authorisation naming who gave it and for what — the boundary the
whole senior-counsel relationship rests on, and the one this playbook set
lost when the guide was split.

## 10. Check continuously while building

- Run the narrowest useful invariant after each coherent change.
- Plant the planned negative control and assert that the mutation changed real
  input before interpreting the result.
- Sweep every affected site after a rename, rule or schema change.
- Check the persisted state and served bytes together when crossing a boundary.
- Keep known limitations explicit; do not turn them into quiet fallback.
- Update implementation mapping and work notes as the real boundary becomes
  known.

These checks guide implementation. Test owns the independent evidence verdict.

## Stop here when

- implementation requires new scope, policy or professional judgment;
- a gate would need weakening or bypassing;
- provenance, authority or a typed distinction would be lost;
- safe failure or recovery cannot be represented;
- the mechanism applies at unenumerated sites;
- a second source of truth is being introduced;
- a P0 security, confidentiality, grounding, persistence or legal-correctness
  risk appears;
- the vertical outcome cannot be completed within the authorised scope.

Return to Start or record a blocker. Do not hide it behind partial code.

## Close Build

Build is closed only when all applicable statements are true:

- [ ] The Start Record is still current.
- [ ] The complete vertical path is implemented.
- [ ] Domain rules remain independent from adapters and model selection.
- [ ] Deterministic rules are enforced outside prompts.
- [ ] Provenance and legal/evidential distinctions survive every layer.
- [ ] Unknown, failed and stale states cannot read as success.
- [ ] Commit, idempotency, concurrency and recovery boundaries are implemented.
- [ ] The general mechanism covers the enumerated population.
- [ ] No new second truth was introduced.
- [ ] Security, privacy, accessibility and user recovery are implemented.
- [ ] Narrow invariants and planned negative controls pass locally.
- [ ] Known limitations and deliberate exclusions are recorded.
- [ ] The change is small enough to review and maps to the registered item.

### Build Record

```text
Item / Start Record:
Implemented advocate-visible outcome:
Files/components changed by layer:
Authoritative state and mechanism:
Model/external boundary and validation:
Persistence/concurrency/recovery behaviour:
Population enumerated and swept:
Security/privacy/accessibility behaviour:
Local invariants and negative controls run:
Known limitations / exclusions / follow-up items:
Material deviations from Start:
BUILT: yes / no, with reason:
```

**Handoff to Test:** provide the closed Start and Build records plus a clean,
reviewable change. Test independently decides whether the required claims are
proved.

---

<!-- THE RULES THIS PLAYBOOK CARRIES. `docs/backlog/build_rules.json`
     is the registry; this manifest is how the card CLAIMS its rules.
     Dropping one now means deleting an id here, which lint refuses --
     because two rules were lost when the guide was split and nothing
     noticed. Do not edit by hand except to add a genuinely new rule
     to the registry first. -->
<!-- BUILD_RULES: BG-002 BG-004 BG-005 BG-006 BG-007 BG-008 BG-009 BG-010 BG-012 BG-013 BG-014 BG-050 BG-051 BG-052 BG-060 BG-062 BG-063 BG-064 BG-065 BG-066 BG-067 BG-068 BG-069 -->
