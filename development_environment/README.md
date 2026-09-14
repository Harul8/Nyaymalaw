# Development environment

Everything kept for future use that is **not needed to run, prove, release or
operate** Nyaymalaw. Organised 14 September 2026, when the repository root was
reorganised into production homes.

Nothing here is authority, and nothing here is deleted. Material is moved here
intact so it can be consulted, mined or revived deliberately — never reinstated
wholesale (CLAUDE.md, "Archived — reference, not authority").

| Folder | What it holds | Tracked |
|---|---|---|
| `archives/` | The previous build's specifications — PRD, journey, architecture, golden scenarios, the full defect register, the original build plan and prompt audits. Moved from `docs/Archives/` | yes |
| `reviews/` | Dated one-off reviews: the line-by-line review order and the 10 September execution-readiness review. Moved from `docs/` | yes |
| `one_off_tools/` | Tools written for a single task — the expanded golden-set candidate search | yes |
| `developer_tooling/` | Tooling for developing in this repository rather than for the product — the code-review-graph semantic index and its MCP launcher. The commit and merge hooks call `graph_vectors.py` | yes |
| `worktrees/` | Earlier `codex/` branch worktrees, moved from `outputs/`. Every one of their branches is merged into `s0-foundations`; they are kept, not pruned. Move them with `git worktree move`, never a plain file move | no — ignored |
| `runs/` | Earlier plan-preview and review run output, moved from `outputs/` | no — ignored |

## The rule that decided what came here

A file is **production** if it is needed to run, prove, release or operate the
product, and everything else comes here. Two consequences are easy to get wrong:

- *Unreferenced does not mean development.* `pipeline/quality/probe_gaps.py` is
  called by nothing, and CLAUDE.md requires it before any Act is reported absent.
- *Old does not mean development.* `docs/Nyaymalaw_Project_Plan.xlsx` is the
  original slice plan, and CLAUDE.md still lists it as a live reference; its
  generator is wired into the gate. It stays in `docs/`.
