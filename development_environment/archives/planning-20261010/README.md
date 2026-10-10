# Planning custody and retained dependencies — 10 October 2026

This directory implements the historical-document part of owner decision P12.
It is a custody record, not a work queue. Current decisions, slice contracts,
build order and status belong to **Advocate build plan** in
`docs/Nyaymalaw_Implementation_Plan.xlsx`; legal brain retains capability intent.

[`manifest.json`](manifest.json) records original paths, archive paths, SHA-256
digests, retained consumers and a static Python import inventory. Documents are
exact pre-cleanup working-tree copies, including any changes already present when
the cleanup began. They are not asserted to be pristine copies of a Git commit.

## Moved out of active tooling

Six scripts solely evaluating retired brain behaviour are preserved byte for
byte at their former repository-relative paths under this directory:

| Original path | Reason for retirement |
|---|---|
| `development_environment/one_off_tools/independence_classifier_20260922.py` | Dated experiment against the earlier dependency classifier |
| `development_environment/one_off_tools/consistency_check_20260923.py` | Dated experiment against the earlier consistency verifier |
| `development_environment/one_off_tools/dispute_separation_measure_20260929.py` | Dated experiment against the earlier dispute reader |
| `development_environment/developer_tooling/launch_fictional_brain.py` | Constructs the archived controlled brain and its old evaluation protocol |
| `pipeline/read_stability.py` | Replays retired cause/factor/posture prompts |
| `pipeline/recall.py` | Measures the archived CorpusEvidenceAdapter, not the new retrieval engine; its claimed RG-19 consumer is absent from current release configuration |

Their CLI examples and relative-root assumptions are preserved as history.
They are **reference only**, not supported launch commands from this location.
Do not add compatibility shims that silently run an old brain. Dated evidence,
the historical defect register and journey-layout records may still name the
original paths; this manifest resolves that custody rather than rewriting the
earlier evidence. Existing private results and sample files were not moved.

## Preserved documentation

Thirteen original documents are preserved before navigation was reconciled:
BUILD_GUIDE, four playbooks, PROJECT_STRUCTURE, the application README, blueprint
README/EXECUTION/COMMUNICATION, PLAN, BACKLOG and the old plan-generator README.
Their live paths now identify the current workbook owner and distinguish old
plans from current method. Their former relative links are interpreted from the
original repository path recorded in the manifest.

## Kept in place because something still reads them

The old PRD, backlog registries and generated plan workbooks are historical
planning inputs. They retain their paths because current checks and tools still
read them. In particular:

- `assurance/gate/speccheck.py` and `export_spec.py` read the PRD and original
  plan; the control-plane evidence module includes their semantic identity.
- `assurance/control_plane/plan_view.py` and `backlog.py` read the registry and
  historical projections. Their verdicts describe those contracts, not the new
  engine's feature acceptance.
- `pipeline/measure.py`, `assurance/journeys/journey.py`, gate helpers and
  `tests/conftest.py` still consume control-plane evidence machinery.
- Historical blueprint packet and scope tools still resolve their source
  documents and JSON records.

This is why the whole `assurance/control_plane/` tree, PRD generators and old
workbooks were not moved wholesale. Keeping them readable does not give them
authority to choose current work. New status is not written into those registries.

Twelve other tooling files still import archived helpers. Nine maintain or
measure corpus acquisition, inventory, index and lineage contracts. Three
(`label_eval_documents.py`, `verify_set.py`, `find_goldens2.py`) curate or check
corpus evaluation sources. Every file and reason is listed in the manifest.
No ingest, acquisition, index build, model run or corpus amendment was performed.

## Meaning of the import count

The manifest counts AST `Import` and `ImportFrom` references in six repository
roots, excluding archive directories and caches. It separates retained
application dependencies, corpus tooling and tests. It does not count dynamic
imports or textual mentions and is therefore not interchangeable with an earlier
grep count of 102 references. A static dependency is not proof that a module is
on the currently served request path.

The application and test owners decide whether their remaining imports are
needed. Removing an archived helper while a retained consumer still needs it is
a code migration with its own checks, not documentation cleanup. The manifest
captures this cleanup checkpoint; subsequent changes must be assessed against
their own source tree rather than treated as a discrepancy with historical bytes.
