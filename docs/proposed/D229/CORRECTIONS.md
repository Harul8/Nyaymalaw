# D229 drafts: what would change, for the owner to accept, change or refuse

*Plan AN.54, D229 (17 Nov 2026): "these are the owner's documents: each change is shown to the owner before it is made." Nothing
in this folder has been applied. Each item says what the document says now, what it would say, and how the fact was checked.*

Three drafts:

1. [CURRENT_STATE.md](CURRENT_STATE.md) - a new file, to live at `docs/CURRENT_STATE.md`: the branch, the checkouts, the servers,
   the models, the spending limits and the state of the build, as of 17 Nov 2026.
2. [CLAUDE.proposed.md](CLAUDE.proposed.md) - CLAUDE.md with its dated facts moved to that file (items 1-5 below). Compare it with
   the current CLAUDE.md side by side; nothing else in it changes.
3. The corrections to the other documents below (items 6-19), each to be made by hand once accepted.

## CLAUDE.md (in the proposed file)

| # | Says now | Would say | Why |
|---|---|---|---|
| 1 | "On 10 October 2026 the owner resumed SEQ.1–SEQ.9 implementation and approved a fresh, shared $5 API development cap ... The integrated turn is in development verification; live semantic and browser acceptance remain open." | The paragraph keeps the standing rules and points to docs/CURRENT_STATE.md for the branch, models, spending limits, servers and build state, to be corrected in the same commit as the change. | The $5 cap is spent and superseded (D283 is the limit today); the state of the build has moved on (AN.48-AN.60). |
| 2 | The table of sources | Gains one line: docs/CURRENT_STATE.md. | So the new file has a stated role beside the plan. |
| 3 | "The app serves the new engine in development verification." | "The app serves the new engine (how far it is accepted: docs/CURRENT_STATE.md)." | A dated state in a standing rule. |
| 4 | "The owner approved GPT-6 Luna for understanding/research planning and GPT-6.1 Sol for grounded writing/independent review on 10 October 2026 ... Luna-versus-Sol comparisons have a $1 allocation inside the shared $5 development cap." | Which model does which step is the owner's decision, named in code and listed in CURRENT_STATE.md; ask before every paid run the owner has not named. The rest of the paragraph (record each call's model, tokens, cost; push every 10-15 minutes; P16; a comparison does not promote its model) is kept word for word. | Sol writes nothing today: Luna is the default writer and Terra the reviewer (15 Oct, 1 Nov, D288, D289). The $1 allocation belonged to the spent $5 cap. |
| 5 | "Commit and push each authorised verified milestone to s0-foundations" | "... to the working branch named in docs/CURRENT_STATE.md" | Work is pushed to `redesigned-architecture` since 9 Nov 2026; `s0-foundations` has not moved since. |

## README.md

| # | Line | Says now | Would say | Checked |
|---|---|---|---|---|
| 6 | 19-21 | "The application currently starts with conversations paused." | "The application serves the new core engine; what is applied and how far it is accepted is in docs/CURRENT_STATE.md." The sentence on the M1 candidate stays. | The pilot serves turns (the owner's own turns; D198's run of 17 Nov). |
| 7 | 71 | `nm/` holds app, core_engine, the journey folders and shared | Adds "`site/` the public pages (home, how it works, what it holds, plans, about, trust, legal)". | `nm/site/` exists and its files are declared in `nm/source_layout.json` (AN.16). |
| 8 | 72 | operations: "enrolment, invitation, professional approval, outbox, store migration and re-keying" | Adds the first admin, usage, titling old conversations, the comparison of old and new search vectors and the pilot's launcher. | The folder holds `admin.py`, `usage.py`, `title_conversations.py`, `compare_retrieval.py`, `pilot.ps1` beside the ones named. |
| 9 | 75 | docs: "... review links, limitation scenarios, and the two blueprint files" | Adds the hosting guide (`docs/HOSTING.md`). | The file exists (AN.48 48f, D167). |
| 10 | 77 | development_environment: "The code-graph launcher and vector refresh used by the hooks — not shipped" | Adds: the recorded baseline turn and its free replay, the step drills, the journey file list, the hosting requirements check and the plan's export - not shipped. | The folder holds `an48_baseline.py`, `step_drills.py`, `journey_files.py`, `hosting_requirements.py`, `plan_export.py` beside the two named. |

## docs/PROJECT_STRUCTURE.md

| # | Line | Says now | Would say | Checked |
|---|---|---|---|---|
| 11 | 17-32 | The tree of `nm/` | Gains `site/  the public pages` under `nm/`. | As item 7. |
| 12 | 33-35 | operations: "(enrol, invite, outbox, professional approval, store migration, re-keying, titling old conversations, usage)" | Adds the first admin (`admin.py`) and the pilot's launcher (`pilot.ps1`). | As item 8. |
| 13 | 98 | development_environment/developer_tooling: "The code-graph launcher ... and the vector refresh the hooks call" | As item 10. | As item 10. |
| 14 | 99 | docs row | Adds HOSTING.md. | As item 9. |
| 15 | 100 | "`legal_database/` - The corpus, a gitignored directory junction" | "The corpus, a gitignored folder inside the checkout (since 6 Nov 2026; no longer a junction)" | The owner's decision of 6 Nov 2026, as CLAUDE.md and README.md already say. |

## docs/DEFECT_SHAPES.md

| # | Line | Says now | Would say | Checked |
|---|---|---|---|---|
| 16 | 6 and 407 | "The full entries are in `development_environment/archives/DEFECT_REGISTER.md` and stay there." | "The full entries were in `development_environment/archives/DEFECT_REGISTER.md`, deleted with the other archives on 19 Oct 2026 (P24, commit 369e8dc8); they are kept in Git history." | git: the file was deleted in 369e8dc8 on 19 Oct 2026. |
| 17 | 285 | "the journey portfolio in `JOURNEY.md` §5" | Adds "(development_environment/archives/JOURNEY.md, deleted on 19 Oct 2026, P24; in Git history)". | git: deleted in the same commit. |
| 18 | 287 | "`nm/legal_brain/common/citation_contracts.py` is now the only module permitted to define such a pattern" | "`nm/shared/citation_contracts.py` (then `nm/legal_brain/common/citation_contracts.py`) is now the only module ..." | The old path was deleted on 1 Oct 2026 (f7afc62c); `tests/test_citation_patterns.py` enforces `nm/shared/citation_contracts.py`. |

## The folders' READMEs

| # | README | Modules it does not list | Would add (each module's own first line) |
|---|---|---|---|
| 19a | nm/app | 11 | `activity.py` what a stop must not cut off (AN.52 52c); `admin_api.py` the Admin area's HTTP edge; `admin_changes.py` how an admin's change is made; `admin_views.py` what the Admin pages are told; `documents.py` receiving an advocate's documents; `turn_progress.py` what a turn in progress is doing; `admin.html`, `admin.css`, `admin.js` the Admin page; `brain-sources.js` the reading pane's sources (frozen, D60); `person.js` the advocate's initials, one rule for the app and the website |
| 19b | nm/arrive | 13 | the Admin area's ports and readers (`admin_access.py`, `admin_checks.py`, `admin_directory.py`, `admin_library.py`, `admin_port.py`, `admin_staging.py`, `admin_turns.py`, `admin_usage.py`, `store_admin.py`); the content-free turn record (`turn_event_port.py`, `store_turn_events.py`); the account preferences (`advocate_memory_contracts.py`, `advocate_memory_codec.py`) |
| 19c | nm/open_matter | 1 | `clamav_check.py` ClamAV as the malware checker for uploads |
| 19d | nm/shared | 6 | `citation_contracts.py` the one owner of citation patterns; `held_acts.py` the Acts a calculation relies on, read exactly as held; `source_excerpt_contracts.py`; `sqlite_creation.py` a store file published whole or not at all; `turn_attempt_port.py` and `turn_attempt_store.py` content-free turn ownership |
| 19e | nm/work_the_file | 1 | `loop_record_contracts.py` the work-log values kept for reading older matter records |

`nm/core_engine/` has no README; PROJECT_STRUCTURE.md describes it. Writing one is not proposed here.

## How the list was made, and what it cannot show

Every path each document cites was checked against the checkout (a script read each path-like word and looked for the file); the
words that are not paths were set aside by eye. Each folder's modules were compared with its README's index. The dated facts were
found by reading CLAUDE.md, README.md and PROJECT_STRUCTURE.md whole and searching the others for the words that date (paused,
s0-foundations, Sol, junction, development verification, the $5 cap). What this cannot show: a sentence that is out of date
without naming a file or one of those words. AGENTS.md and BUILD_GUIDE.md are D231's stage 2, not D229.
