# Current plan workbook

`docs/Nyaymalaw_End_to_End_Project_Plan.xlsx` is a generated reader view.
`docs/Nyaymalaw_Project_Plan.xlsx` is the preserved original slice plan. The
original end-to-end workbook under `outputs/` is also preserved unchanged.

The current workbook reads `status.yaml`, `steps.yaml`, `plan.json`,
`professional.json` and `build_rules.json`. Its read-only Python exporter calls
the existing backlog functions to bind evidence and derive completion. It does
not run tests, promote evidence, edit status or approve a release. A stale result
must remain stale in the workbook.

The execution-readiness view also reads every Markdown/JSON blueprint contract,
validates the combined execution graph, and exports Modules, Execution Packets,
Packet Guide, Acceptance, Decisions, Command Contracts and Evaluation Specs.
These are projections, not seven new sources of truth. The latter scenarios
remain NOT RUN; packet proofs also require every registered criterion's exact
requirement, negative control and required evidence methods.

Final pre-build corrections retain the same 28-sheet layout. The Decisions
view reads the scoped adoption register, not proposal `approval` flags. The
planning view reports presence only because it has no attempted operation or
protected trust input; P03's resolver performs those checks at actual use.
Acceptance includes the media policy's foundation, served integration and
confidential-path criteria. BK-87/BK-89/BK-90 are current planning deliveries,
not future application packets; their evidence remains subject to the normal
backlog lifecycle.

The bounded-autonomy amendment preserves the 28-sheet layout. Its measured
source population on 10 September 2026 is **101 work items, 198 acceptance
criteria, 47 packets, 13 modules, 44 features, 47 journey steps, 34 synthetic
scenario specifications and 81 build rules**. Of the criteria, 187 have future
final packet owners; 11 belong to the three current planning deliveries above.
These are source populations, not passed-test counts or a new permanent quota.
Recount after later changes and preserve earlier counts as historical evidence.

`blueprint/autonomy.json` adds the adaptive task/result/claim contract and eight
obligation mappings. Its details project into the existing evaluation detail
view; P46/P47 and BK-91/BK-92 project through the normal packet, acceptance and
item views. They remain proposed runtime work. Dynamic reasoning does not
change the deterministic admission, permission, validation or publication
boundary, and a complete workbook does not certify autonomous operation.

Source text hashes normalise CRLF/LF so Windows and Linux compare the same
contracts. Binary inputs hash exact bytes. The published Class-A result is
labelled **Captured execution artifact**, not an authored source that must stay
current: otherwise evidence promotion would invalidate the test that certified
it. Its captured hash is retained, while every authored source must still match.
Refresh the workbook to display newly published effective proof.

`view_content.json` preserves supplementary narrative from the original
end-to-end workbook: scenario and risk examples, review decisions, and
interaction context. These are design catalogues, not additional delivery
states or executable evidence. Every scenario, risk and review decision links
to registered BK work; professional context is keyed to the registered IDs.
Edit the registry whenever a requirement or delivery claim changes. Edit this
file only for explanatory context. Never make a workbook cell the only owner of
a requirement, acceptance criterion, status or release decision.

## Regenerate

Use the bundled Node and `@oai/artifact-tool` packages. Create a writable,
conversation-specific runtime directory whose `node_modules` is a junction (on
Windows) or symlink to the bundled package directory. No dependency directory
needs modification. Pass that directory as `--runtime-path`.

The read-only status exporter needs the project's Python environment, including
PyYAML. This is separate from spreadsheet authoring, which uses bundled Node.

```text
<bundled-node> spec/plan/build_current_plan.mjs
  --python <project-python>
  --runtime-path <conversation-runtime-directory>
  --output docs/Nyaymalaw_End_to_End_Project_Plan.xlsx
  --preview-dir <conversation-output-directory>/plan-previews
```

Use `--snapshot-time <ISO-8601-UTC>` to reuse the same stated snapshot time when
regenerating for a layout-only correction. Omit it for a fresh source snapshot.
This does not promise byte-identical XLSX packaging.

The generator requires non-empty, unique registered populations; exact source
IDs; valid narrative work links; current structural lint; matching authored
status, feature, basis and wave projections; and a formula-error-free rendered
view. It records source hashes and rejects sources changed during rendering.
It also checks the source-defined wave and release-profile populations are
present. It does **not** enforce profile membership, legal adequacy or release
approval: those mechanisms remain owned by BK-80 and the release approvers.

Review the preview for every sheet after a layout change. The workbook's
Reconciliation sheet reports the population examined; Sources records hashes
and execution fingerprint. The local preview report is supporting evidence,
not a substitute for current product, browser, professional or deployment proof.

## Avoid accidental claims

- A complete written journey contract is an intended requirement.
- `implementation: complete` is the authored implementation claim.
- Effective evidence is the existing evidence binder's current result.
- A legacy closure is a declared prose exception, not current executable proof.
- Derived item readiness is not permission to activate a pilot or production.
- Release-profile criterion membership and evidence state are mechanically
  checked; accountable adoption and release authority remain separate.
- Professional and privacy reference links inherited from the earlier plan
  require current qualified verification for the actual release jurisdiction.

The workbook is a snapshot. Refresh it after source or evidence changes, and
use the live registry and authorised conformance record for a release decision.
