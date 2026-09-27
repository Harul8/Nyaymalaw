# Legal Brain sub-stage reorganisation — 27 September 2026

## Scope and result

Implemented the owner's requested shallow organisation of the large Legal Brain
folder, on top of the journey-first migration at `bf3e63e`. This is a structural
delivery, not acceptance of the legal brain or a fresh release gate.

Existing code now has eight capability homes: `understand`, `retrieve`, `reason`,
`procedure`, `verify`, `communicate`, `orchestrate` and `evaluate`. Eleven genuinely
shared guidance/contract files live once in `common`. Each group is flat. These
are responsibilities in a reasoning loop, not a compulsory execution sequence.
Capability-specific tools, ports, adapters and contracts stay beside their
capability. Cross-product infrastructure remains in `nm/shared`.

The root and nine group READMEs provide the review entry points. Their indexes
reconcile all 230 physical files: 214 moved Python implementations, seven moved
browser assets and nine new docstring-only package initializers. All navigation
links resolve; no duplicate implementation or tool auto-discovery was introduced.

## How the move was controlled

- Captured 998 original files and the pre-change Git status under
  `.nm/reorganisation/legal-brain-substages/`, before moving anything.
- Declared every one of the 214 module moves and seven asset moves explicitly in
  `assurance/common/legal_brain_layout.json`. Historical byte digests describe
  custody, not a current passing verdict.
- Composed original architecture identities through the earlier journey map to
  the new capability owners. The historical journey manifest is byte-identical;
  the original dependency-direction rules and all 293 original role aliases remain.
- Updated imports, active source references, browser allowlist and specification
  exports. The checkout root remains the sole import root and `nm/app/main.py`
  remains the entry point. No runtime compatibility copies were added.
- Split package-import lists into their actual new parents without changing
  aliases or local scope. Corrected the two file-depth-derived blueprint roots
  in `practice_playbooks_adapter.py` and `principles_file_adapter.py`.
- Kept model registry admission, child-only finish scopes, permissions, generation
  checks, grounding and source-owner boundaries. Tests now enumerate the complete
  declared source population instead of assuming one folder depth.
- Verified all seven moved assets byte-for-byte. No client cutover, permission,
  evaluation grant, budget, provider request or runtime record was changed.

An independent read-only comparison checked all 378 original production modules
(214 moved and 164 unchanged-location). All original digests and scoped import
bindings match. After exact relocation references, the two root-depth fixes and
identified documentation formatting, there are no unexpected executable AST
changes. Runtime prompts were not broadly whitespace-normalised to obtain this
result. The nine added initializers have no imports or runtime exports.

## Recorded verification

Artifacts below live in `.nm/reorganisation/legal-brain-substages/` and are local
execution records, not promoted Class-A evidence.

| Check | Actual result | Artifact |
|---|---|---|
| Identity, role and fail-closed relocation controls | 153 passed; no failures/errors/skips | `boundary-controls.xml` |
| Browser assets, composed tools, child scope and layout | Final 130 passed; no failures/errors/skips | `asset-tools-layout-final.xml` |
| Exact mutation anchor and source/reachability population | 3 passed; no failures/errors/skips | `anchors-source-population.xml` |
| Prompt/generation checks and controlled browser journey | 174 examined; 172 passed, two failed | `generations-prompts-browser.xml` |
| Isolated repeat of the two browser findings | One passed, one failed | `browser-two-final.xml` |
| Original-code isolated comparison | Same History failure; reload passed | `baseline-browser.xml` |
| Full ordered original-code comparison | Same two failing nodes as the moved code; all other nodes pass | `baseline-generations-prompts-browser.xml` |

These cohorts overlap and must not be summed into a full-gate count. The first
asset/tools run had four layout-sensitive test failures; that original result is
retained as `asset-tools-layout.xml`. Their repaired enumerators retain ownership,
scope and dispatch assertions rather than accepting the actual handler as its
own oracle. No old test function was removed: all 4,742 original function
identities remain, with seven additional relocation controls. Final collection
contains 8,632 parametrised nodes across 435 files.

Additional checks passed: 387 current module identities under the unchanged
dependency matrix; runtime/assurance and the new owned tooling's Ruff population;
principles generation; migration custody verification; and the canonical six
specification exports. Those exports are current, with no status promotion
(`built: 27`, `decided: 17`). Broad test/pipeline lint was not declared clean.

## Browser findings retained, not routed around

1. `test_phase_8b_history_is_a_record_and_not_a_json_dump`: advice and History
   paragraphs agree, but opening the audit door does not show the raw `turn_id`
   record expected by the test. This reproduces with original pre-move source.
2. `test_phase_9_reload_restores_the_matter`: the ordered cohort timed out waiting
   for a matter row after reload. The same ordered failure reproduces with
   original pre-move source. Its isolated repeat passes on both current and
   original source. This order-dependent finding remains visible; a passing
   retry is not substituted for the failed cohort.

No assertion, timeout or UI behaviour was weakened to turn these green. The
complete ordered baseline reproduces exactly the same two failing nodes; these
are not new relocation failures. The broader browser journey is not claimed to
pass and the prior migration's six broader source-sweep findings remain open.

## Preserved and intentionally outside scope

The owner's dirty implementation workbook, existing dated status review and 14
untracked offline progress/review records are not included in this delivery.
The workbook retains SHA-256
`a80ead260b81f96855597da44955ae3929c8e64bf98fc534cccb0654a96d4214`.
The private corpus junction, credentials, matter history and existing evaluation
ledgers remain untouched. No full Class-A run, evidence promotion, paid model
evaluation, professional sign-off or whole-brain completion is asserted.

Already-running processes retain old imported identities until restarted. Moving
files does not refresh a running NM server; no unrelated server was terminated.
