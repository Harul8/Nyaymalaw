# Sign off a change

Use this playbook after Test is closed and before claiming that work is
conformant, done, releasable or released.

**Entry:** closed Start and Build records plus a current Evidence Pack.

**Exit:** a Conformance Record states the exact derived claim, reconciles the
control plane and, where applicable, records the release or return decision.

## Quick card

1. Name the exact item, feature or deployment claim being requested.
2. Inspect current evidence and unresolved failures against that claim.
3. Check substantive professional behaviour with the required qualified reviewer.
4. Reconcile the owning registry, forensic record and generated views.
5. For deployment only, verify release authority, operational gates, recovery and
   controlled exceptions for the named environment.
6. Record the earned decision and its decision-maker; never promote a weaker
   result into a stronger claim.

## 1. Check that the evidence pack is current

Confirm that source, configuration, provider, model, prompt, corpus,
jurisdiction and environment identity match the build being signed off. Check
that no later edit can affect a required result.

Return to Test if evidence is missing, failed, not run or stale. Return to Build
if the implementation must change. Return to Start if scope, authority,
contract or acceptance was wrong.

Use the identity relevant to each evidence type, and inspect what the runner
actually validates. Current structured review records and browser binding do
not yet enforce every validity check in this playbook; BK-80 owns those gaps.
Until those controls exist, record the manual comparison and its limits.

## 2. Use the exact claim the evidence supports

Keep these statements separate:

| Claim | Meaning |
|---|---|
| Implemented | The code or document exists in the mapped layers |
| Verified | Required named evidence ran and currently passes |
| Feature conformant | The feature contract and every blocking item affecting it pass |
| Done | All acceptance evidence required by the item passes and the registry derives completion |
| Releasable | All cumulative release gates for the intended deployment pass |
| Released | An authorised release decision was made and deployed with monitoring and recovery |

Do not promote one claim into another. Never author `done`; it is derived from
the acceptance evidence in `docs/backlog/status.yaml`.

Technical sign-off records an implementation/evidence judgment within the
reviewer's authority. Counsel acceptance records a qualified professional's
review of substantive behaviour. Deployment authorisation and risk acceptance
name the accountable decision-maker, environment and permitted release scope.
These are separate decisions: an agent cannot supply a counsel identity or
deployment approval, and approval cannot change FAIL or NOT RUN into PASS.

### 2.1 For a fix: accept the demonstrated family and its limits

**Accept the demonstrated scope, never universal future-proofing.** A technical
reviewer other than the implementer examines the measured cause, shared owner,
whole-product inventory, original and transfer witnesses, distinguishing
boundaries, unrelated-behaviour checks and cumulative results. A second agent's
review may assist but cannot invent human, counsel or deployment authority.
Substantive legal changes still need qualified counsel acceptance.

Name the supported defect family and tested population, exclusions, unrun
evidence, remaining risks and before/after identities. Confirm permissions and
required proof were not weakened, and legitimate legal differences survive.
Do not sign off a general fix from a one-incident pass, a populated review form
or keyword lint. No finite suite proves all future inputs safe; the earned
claim is bounded by the demonstrated mechanism, scope and evidence.

Link recurrence signals to the same defect family and owner so the next
occurrence reopens the mechanism, not another point patch. A safe, approved
capability-wide disable/rollback may contain harm while investigation proceeds;
record its scope and review date. Containment does not close the underlying
defect or earn a permanent-fix claim.

## 3. Reconcile the control plane

Update the authoritative records:

- `status.yaml`: implementation, verification, evidence references and next
  action;
- `BACKLOG.md`: forensic explanation, observations, decisions and how the work
  was proved;
- `plan.json`: only if authorised delivery order or dependencies changed;
- `steps.yaml`: only if the authoritative journey mapping or contract changed;
- `professional.json`: only if PA/EW/AM/ROLE/GC mappings changed;
- feature, gate, schema or release source: only when its owned rule changed.

Regenerate the board and workbook views. Check unique IDs, valid states,
non-zero populations, bidirectional references, wave coverage, dependency
order, stage order and proof links.

Do not edit a generated view to make it agree. Correct its source and
regenerate it.

## 4. Apply the cumulative release ladder

For a release decision, confirm each applicable gate in order:

1. plan and registry integrity;
2. fast correctness and negative controls;
3. integration, persistence, encryption and recovery;
4. served journey success, refusal, recovery and return loops;
5. legal quality and real-model evaluation;
6. named counsel acceptance;
7. security, privacy, role isolation, accessibility, performance and recovery
   fitness;
8. signed release decision with current evidence and controlled exceptions;
9. production watch capable of invalidating evidence and reopening work.

The exact gate definitions live in the current project plan and release
sources. Gates are cumulative. A later PASS cannot override an earlier FAIL,
NOT RUN, STALE or BLOCKED result.

An earlier failure can be resolved by a relevant corrected rerun on the release
candidate; retain the original evidence and explanation. Separate suites can
support one candidate when their source and applicable input identities agree.
An unrelated green suite cannot resolve a failed gate.

## 5. Review professional conformance

For every applicable PA standard, confirm that the evidence supports the
observable behaviour, not merely the existence of a field or component.

Pay particular attention to:

- integrity and visible correction;
- independent judgment, adverse points and refusal;
- role, commission, decision rights and authority;
- confidentiality, privilege and purpose;
- listening, question economy and faithful multimodal use;
- memory, continuity and ownership;
- issue priority, proof, authority hierarchy and adverse case;
- advice maturity, candour and calibrated confidence;
- remedy, enforceability, proportionality and strategy;
- clear communication, agency, controlled action and follow-through.

Material counsel reservations remain blocking unless the governing plan
expressly records a different approved treatment, owner and expiry.

## 6. Review open risk and exceptions

Do not release with an unnamed exception. Every accepted exception must state:

- the exact failed or missing rule;
- user and professional consequence;
- reason it is accepted;
- accountable owner;
- compensating control;
- scope and affected population;
- expiry or review date;
- trigger that stops rollout;
- linked work item for permanent resolution.

No exception may downgrade a mandatory gate or P0 confidentiality, authority,
grounding, persistence or legal-correctness risk. Risk acceptance records a
permitted residual risk; it is not test evidence and does not complete the work
item that still owns the gap.

## 7. Confirm rollback, recovery and monitoring

Before release, identify:

- how to disable or roll back the behaviour;
- how state written by the new version remains readable or migrates safely;
- how partial actions and unknown outcomes are reconciled;
- which telemetry detects material failure without leaking matter content;
- thresholds and owners for corrections, refusals, withheld turns, retries,
  latency, incomplete processing and incidents;
- which evidence and work items each signal invalidates;
- how users receive truthful status and recovery.

A feature whose harmful failure cannot be controlled is not releasable.

These are release checks. A document, control or prerequisite item can earn its
own non-release sign-off without pretending that production deployment occurred.
Record why any release-only fields do not apply and retain the downstream
release obligation.

## 8. Make the decision

Choose one result:

- `SIGNED OFF`: the item or feature earns its exact non-release claim.
- `RELEASED`: all mandatory release inputs pass and authorised deployment is
  recorded.
- `RETURN TO TEST`: evidence is missing, stale, failed or ambiguous.
- `RETURN TO BUILD`: implementation or recovery must change.
- `RETURN TO START`: contract, scope, role, authority or acceptance must change.
- `BLOCKED`: a named external decision or prerequisite prevents progress.

Record why. “Mostly complete,” “looks good” and “tests passed” are not decisions.

## 9. Production watch

After deployment:

- review material user corrections and professional reservations;
- monitor refusals, withheld answers, retries, unknown action outcomes,
  processing failures and latency;
- assign each material signal an owner and review date;
- mark affected evidence stale and reopen the right stage;
- control or stop rollout until the signal is explained and recovered;
- preserve the event and decision trail.

Production evidence can invalidate pre-release evidence. It does not wait for a
planned wave or the next release.

## Stop sign-off when

- the Evidence Pack does not match the current source;
- a required result is FAIL, NOT RUN, STALE or BLOCKED;
- a professional standard requiring qualified review lacks that review;
- the served and persisted outcomes disagree;
- a P0 or mandatory gate remains open;
- a status or workbook value conflicts with its authoritative registry;
- an exception lacks owner, compensation or expiry;
- rollback, recovery or monitoring is not credible;
- the requested claim is stronger than the evidence.
- a fix has no independent scoped review, unresolved collateral regression or
  a generality claim that exceeds the measured population.

Return to the earliest stage that owns the problem.

## Close Sign-off

Sign-off is closed only when all applicable statements are true:

- [ ] The Evidence Pack matches the source and environment being signed off.
- [ ] The exact claim is named and no stronger claim is implied.
- [ ] Every required gate is current and PASS.
- [ ] Applicable professional standards and counsel reservations are resolved.
- [ ] Status, evidence, next action and forensic prose are reconciled.
- [ ] Generated board and workbook views are current.
- [ ] No P0 or mandatory release blocker affects the claim.
- [ ] Every exception is owned, compensated, scoped and expiring.
- [ ] Rollback, recovery and monitoring are ready.
- [ ] Approval and decision-maker authority are recorded.
- [ ] Production signals will invalidate evidence and reopen work.

### Conformance Record

```text
Item / build / environment identity:
Start Record / Build Record / Evidence Pack:
Claim requested:
Claim earned:
Fix only — accepted causal family / population / exclusions / limits:
Fix only — independent technical review / unchanged safeguards / recurrence owner:
Applicable PA standards and counsel decision:
Gates G0–G8 (or applicable subset) and evidence:
Open FAIL / NOT RUN / STALE / BLOCKED results:
Exceptions — owner / compensation / scope / expiry:
Rollback and recovery:
Monitoring signals / thresholds / owners:
Control-plane and generated-view reconciliation:
Decision-maker / authority / date:
Decision: SIGNED OFF / RELEASED / RETURN / BLOCKED:
Reason:
```

The change is closed only at the level named in this record. A production
signal may reopen it by invalidating the evidence on which that level depended.

---

<!-- THE RULES THIS PLAYBOOK CARRIES. `docs/backlog/build_rules.json`
     is the registry; this manifest is how the card CLAIMS its rules.
     Dropping one now means deleting an id here, which lint refuses --
     because two rules were lost when the guide was split and nothing
     noticed. Do not edit by hand except to add a genuinely new rule
     to the registry first. -->
<!-- BUILD_RULES: BG-017 BG-018 BG-031 BG-032 BG-033 BG-034 BG-035 BG-036 BG-037 BG-038 BG-039 BG-040 BG-041 BG-042 BG-043 BG-044 BG-045 BG-057 BG-058 BG-059 BG-075 BG-076 BG-077 BG-081 -->
