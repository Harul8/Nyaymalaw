# Corrections to NM Brain offline evidence

This checkpoint responds to the independent review of `611b1e8`. Before Build
and the existing defect register remain the status owners. Scripted tests prove
exercised contracts and recovery, not semantic accuracy or live error rates.

## Independently authored mutation authority

`tests/test_brain_material.py` no longer supplies reader proposals to its
permission transport. Explicit interpreter scopes remain unchanged; an
independently authored typed change request may supply its own targets and
relation. A reader proposal, its quotation, relation or target cannot create
permission. An absent declaration stays empty even when a candidate proposes
an owned target.

Affected public scenarios now author their scopes separately in their test
plans: advance and handover corrections, answer-route corrections, supported
mixed account contributions, dispute corrections, shipment correction and
withdrawal, source aliases, assignment and ownership neighbours. Pure
examination and unrelated positions do not acquire correction authority merely
because the fabricated reader proposes one. Existing record, audit, call-count,
release and replay assertions are retained.

The fixture migration guards vary the reader target through the selected,
neighbouring and foreign IDs, and vary empty extraction independently of the
request. They also preserve explicitly empty authority. These checks protect
fixture independence; they are not evidence that a real interpreter chooses the
right source, target or operation.

## The eight pressure observations

The executable register now identifies all eight observations individually:

| Register | Case | Interpretation |
| --- | --- | --- |
| B-175 | `mutation-release-mislabeled-operational-account` | Public prevention regression for fresh free-prose rejection |
| B-176 | `release_08_prose_accept_gap` | Public prevention regression under a deliberately wrong response ACCEPT |
| B-177 | `material-20-wrong-date-false-judge-acceptance` | Open desired-rule strict expected failure: false proposition must not be admitted |
| B-178 | `source-pressure-16-semantic-mislabel-false-rejection` | Open desired-rule strict expected failure: valid account must survive wrong purpose classification |
| B-179 | `source-pressure-17-semantic-mislabel-false-admission` | Open desired-rule strict expected failure: an unadopted draft must not supply admitted account |
| B-180 | `source-pressure-18-instruction-only-mixed-false-admission` | Open desired-rule strict expected failure: work authority must not supply a new fact |
| B-181 | `extractor-14-wrong-fact-exact-source` | Proposal-only positive guard; independent admission and public trace remain a qualification requirement |
| B-182 | `extractor-17-empty-is-proposal-only` | Proposal-only positive guard; coverage, recovery and public completion need an explicit trace |

The four semantic desired-rule cases use `xfail(strict=True, raises=AssertionError)`
and name their register IDs. The tests assert the wanted result. A genuine fix
must turn them into strict XPASS and require removing the marker; a contract or
provider exception cannot masquerade as the expected semantic failure.

The two extractor cases remain positive tests. An extractor is allowed to
return an untrusted proposal, including an empty envelope. Marking that
behaviour as a defect would move semantic judgment into the wrong boundary and
create false rejection. Their register rows explicitly retain the missing
end-to-end qualification rather than claiming they prove a released failure.

`tests/test_brain_semantic_defect_register.py` binds the eight identities and
reproductions to the existing register. It requires desired-rule markers for
open semantic failures, ordinary prevention regressions for fixed failures,
and explicit qualification wording for proposal-only boundaries.

Four historical check locators were stale after archiving. Only their check
paths were relocated: B-016 `retrieve/manifest_sources.py`, B-018
`verify/grounding.py`, B-031 `understand/posture.py`, and B-109
`common/tiers_contracts.py` now resolve under `nm/Archives/legal_brain/`.
Historical findings, causes and status were preserved.

## The 2,382 result is a selected subset

The historical manifest
`docs/backlog/evidence/brain-gap-qualified-summary-20261006.json` lists **128
selected test modules**, not the whole repository. It excludes the defect
register and fixture migration tests. It records 2,382 passing cases at
`dd0107d`, with production reported identical to the pressure head `1be2d6f`.
The original shell command was not recorded and cannot be claimed recovered.

The exact recorded module population is reconstructed without expansion in
`docs/backlog/evidence/brain-offline-subset-611b1e8.txt`. This command reruns that
selection against the current checkout; it is a reconstructed command, not a
copy of the historical invocation:

```sh
xargs .venv/bin/python -m pytest -o addopts= -q < docs/backlog/evidence/brain-offline-subset-611b1e8.txt
```

The focused evidence repair checks use this explicit selection:

```sh
.venv/bin/python -m pytest tests/test_defect_register.py tests/test_fixture_scope_migration.py tests/test_brain_semantic_defect_register.py tests/test_brain_pressure_verification.py tests/test_brain_pressure_sources.py tests/test_a_documented_defect_uses_a_strict_marker.py --tb=short
```

The authored-scope public checks use eleven modules:

```sh
.venv/bin/python -m pytest tests/test_brain_material.py tests/test_fixture_scope_migration.py tests/test_brain_material_answer_routing.py tests/test_brain_material_operations.py tests/test_brain_dispute_transitions.py tests/test_brain_source_selection.py tests/test_brain_material_assignment.py tests/test_brain_material_scope.py tests/test_brain_material_record.py tests/test_brain_material_purpose.py tests/test_brain_semantic_recovery.py --tb=short
```

## Cost claims and deferred measurements

“No routine model stage was added” is meaningful only against a named baseline.
The independent review reports greeting calls increasing from one to three and
ordinary correction calls from seven to eight relative to `ea1253e`. Its input
estimates rise approximately 3.4k to 14k tokens for a greeting and 18.8k to 32.4k
for a correction. It reports stable prompt words rising 12,354 to 15,365 (24%),
with writer words 1,638 to 2,371 and reviewer words 1,244 to 2,125. These are the
reviewer's historical measurements, not measurements newly reproduced here.

A later mechanical slice adding no dispatch does not erase those earlier
increases. Future call reports must distinguish their baseline, initial logical
stages, conditional corrections and provider attempts. Live model token cost,
latency, interpreter scope quality and semantic false acceptance/rejection
remain unverified. No real-model or browser acceptance was performed for this
checkpoint.

## Observed checkpoint results

The explicit evidence-repair selection passed **79 tests with four strict
expected failures**. The four failures are the open semantic desired rules,
not missing metadata or schema exceptions. The eleven-module public scope
selection passed **122 tests**, including the source-rereview replacement
neighbour. The execution-consumer module passed another **26 tests**, with its original
response replay occurring only after an explicitly authorised correction is
observed in the current record. Ruff passed the changed test modules, and
`git diff --check` passed. These are focused offline subsets.

A preliminary broad diagnostic also selected a browser-only importing module
by mistake. Its fourteen setup attempts failed before browser creation because
the executable was absent. It was removed from the offline selection; no
browser ran and no real-model call occurred. That diagnostic is not acceptance
evidence. The initial register run also found four stale archived paths, which
were repaired and then verified by the final register selection above.

Recorded artifacts for this checkpoint are
`docs/backlog/evidence/brain-evidence-register-20261006.{log,xml}`,
`brain-authored-scopes-20261006.{log,xml}` and
`brain-consumer-supersession-20261006.{log,xml}` in the same directory.
The consumer command is
`.venv/bin/python -m pytest tests/test_brain_turn_execution_consumer.py --tb=short`.
The source-version fixture preparation additionally passed 48 tests with three
strict expected semantic failures using
`tests/test_brain_pressure_sources.py tests/test_brain_semantic_recovery.py tests/test_brain_semantic_defect_register.py`.
This preparation emits owned whole-passage or empty portions only for an
explicitly authored role, preserves adversarial ranges unchanged, and changes
no production admission decision.
