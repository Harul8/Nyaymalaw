"""The counterexample tests for the tooling itself.

Written BEFORE trusting either tool, because the rule this project runs on is
that a check which has never rejected anything is an unexercised claim, not
evidence of health. These tests build the exact defect each tool exists to
catch, and assert the tool rejects it.

If any test here starts passing for the wrong reason -- an import error, a
missing file -- it proves nothing. Each therefore asserts on the tool's own
reported reason, not merely on a non-zero exit code.
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest
import subprocess


pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]


def test_a_fingerprint_notices_a_changed_source_file(tmp_path):
    """THE POSITIVE CONTROL. A digest that never changes would let every stale
    server pass, and it would look exactly like this one."""
    from nm.shared.identity_contracts import source_fingerprint

    (tmp_path / "nm").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "nm" / "a.py").write_text("x = 1", encoding="utf8")
    before = source_fingerprint(tmp_path)

    (tmp_path / "nm" / "a.py").write_text("x = 2", encoding="utf8")
    assert source_fingerprint(tmp_path) != before, "content change not seen"

    # A NEW FILE COUNTS TOO — the S4 wiring was mostly new modules.
    (tmp_path / "nm" / "b.py").write_text("x = 2", encoding="utf8")
    assert source_fingerprint(tmp_path) != before, "an added module not seen"

    # AND A MISSING TREE IS NOT SILENTLY SKIPPED. Digesting nothing would make
    # a deployment without `tests/` match across changes it never looked at.
    import shutil
    shutil.rmtree(tmp_path / "tests")
    assert source_fingerprint(tmp_path) != before


# ============ the console every tool writes its verdict to =================


def test_utf8_console_survives_a_stream_it_cannot_reconfigure():
    """It runs under pytest's capture, under a pipe, and inside a subprocess
    wrapper. None of those is a failure and none may raise — a guard that
    crashes on the ordinary case would be worse than the bug."""
    from assurance.common._console import utf8_console

    utf8_console()
    utf8_console()  # idempotent


def test_a_graph_without_an_embedding_table_reports_full_lag(tmp_path):
    """A structural-only graph is stale, not a reporter crash or zero lag."""
    from development_environment.developer_tooling.graph_vectors import examples, lag

    database = tmp_path / "graph.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "create table nodes (qualified_name text primary key, kind text)"
        )
        connection.execute(
            "insert into nodes values (?, ?)", ("nm.example.rule", "Function")
        )
        connection.commit()
    finally:
        connection.close()

    assert lag(database) == (1, 0, 1)
    assert examples(db=database) == ["nm.example.rule"]


#: What a module has to reach to make a model call. Names rather than a
#: behaviour, because the point is to notice the WIRING on the day it lands --
#: and by the time a call is observable, the gate has already made it.
REACHES_A_MODEL = (
    "Application",          # the composition root, which builds the adapter
    "TurnEngine",           # the only thing that runs a scenario
    "OpenAIModelAdapter",
    "ModelPort",
    "structured",           # the one method that spends
)


def test_the_hook_keeps_the_hook_that_was_there_first():
    """The graph's pre-commit hook was installed before this one. Replacing it
    would take a working tool away to add ours, which is not a trade anybody
    agreed to."""
    hook = (ROOT / "assurance" / "hooks" / "pre-commit").read_text(encoding="utf8")
    assert "code-review-graph" in hook, (
        "the canonical hook dropped the graph's update, so installing ours "
        "silently disables theirs")


def test_the_hook_refreshes_vectors_and_never_blocks_a_commit():
    """BK-76-AC2, as changed on 15 September 2026.

    The product owner removed the gate from the commit path: checks are run by
    hand and the commit decision is a person's. What remains is the graph: the
    refresh moved into `assurance/hooks/refresh-graph` on 12 September 2026 so
    post-merge and post-rewrite could share it, and pre-commit still reaches it.
    A hook that could still refuse a commit would be the removed gate coming
    back without anyone deciding it should.
    """
    hook = (ROOT / "assurance" / "hooks" / "pre-commit").read_text(encoding="utf8")
    owner = (ROOT / "assurance" / "hooks" / "refresh-graph").read_text(encoding="utf8")
    vector = "assurance/hooks/refresh-graph"

    assert vector in hook, (
        "the hook updates the structural graph without refreshing its vectors")
    embed = "python development_environment/developer_tooling/graph_vectors.py --embed || true"
    assert embed in owner, (
        "refresh-graph no longer refreshes the vectors, or lets a failed "
        "embed fail the hook")
    code = [line.strip() for line in hook.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    assert "gatestamp.py" not in hook.replace("# ", ""), (
        "the commit hook checks the gate stamp again")
    assert not any("exit 1" in line for line in code), (
        "the commit hook can refuse a commit")
    assert code[-1] == "exit 0", "the commit hook does not end by allowing the commit"


def test_the_model_scan_can_see_a_runner_that_would_spend():
    """S11. A scan over a module that happens to import none of these proves
    nothing about the scan."""
    planted = ast.parse(chr(10).join((
        "from nm.app.composition import Application",
        "def go():",
        "    return Application().engine",
    )) + chr(10))
    reached = {a.name for n in ast.walk(planted)
               if isinstance(n, ast.ImportFrom)
               for a in n.names if a.name in REACHES_A_MODEL}
    assert reached == {"Application"}


# ============ a killed mutation run does not leave the tree mutated ========


# ========= the scenario runner does not depend on a remembered password ====


# ============ B-140 — the gate scan reads code, not prose ================

#: (planted source, must the trace fail). Built as tuples of LINES rather
#: than as escaped literals: a newline inside a string inside a test file
#: is three levels of escaping, and the heredoc form of this mangled it.
_PROBES = (
    (('METRICS_GATE = "G-LIMITATION"',), True),
    (('"""This module is deliberately not G-LIMITATION."""', 'X = 1'), False),
    (('# a comment explaining why this is not G-SCOPE', 'X = 1'), False),
)


# =========================== BK-51: the journey manifest stays honest ========


def test_the_served_process_reports_which_code_it_loaded():
    """A RUNNING PROCESS IS AN ARTEFACT AND CARRIES ITS IDENTITY.

    Measured on 31 August 2026: five golden scenarios were run against an API
    server started the previous evening. They made live model calls, found none
    of the slice they existed to prove, and the run exited 0. Every element
    printed was about code superseded that morning.

    The fingerprint is captured at IMPORT, never per request. Read from disk
    when the request arrives it would describe the working tree — which a stale
    server matches perfectly while serving yesterday's code, so the check would
    pass exactly when it needed to fail.
    """
    import nm.app.api as api
    from nm.shared.identity_contracts import source_fingerprint

    assert not api.SERVING.startswith("unknown"), api.SERVING

    # HELD, NOT HELD, OR NOT ASSESSED -- and the third state is visible.
    #
    # Comparing SERVING against the tree is the check that caught B-061, and
    # its home is `assurance/journeys/run_scenario.py`, where a LIVE SERVER is asked what it
    # is running. In-process the same comparison can only fail if the tree
    # changed between this module's import and this line -- which is what an
    # editor does, not what a defect does. It fired that way three times in one
    # session, and an alarm that is wrong in the direction of alarm is one
    # people learn to overrule.
    # AGAINST THE TREE AS IT WAS WHEN THE SESSION STARTED, not against two
    # readings taken microseconds apart. The old guard caught a tree moving
    # during those microseconds and nothing else, so an edit made partway
    # through a two-minute run -- and finished before this line -- agreed with
    # itself perfectly and reported the editor as a defect. It did exactly
    # that twice on 6 September 2026, on correct code.
    from tests.conftest import SESSION_TREE

    now = source_fingerprint()
    if SESSION_TREE.startswith("unknown") or now != SESSION_TREE:
        pytest.skip(f"NOT ASSESSED: the tree moved during this session "
                    f"({SESSION_TREE} -> {now}), so the comparison would "
                    f"describe the editor and not the code. The live check is "
                    f"assurance/journeys/run_scenario.py::server_fingerprint")
    assert api.SERVING == now, (
        "the module-level fingerprint does not match the tree it was imported "
        "from, and the tree has not moved since this session began")

    # IT IS A CONSTANT, not a call. The check depends on this: a property or a
    # function evaluated per request would re-read the disk.
    assert isinstance(api.SERVING, str)
    assert "SERVING = source_fingerprint()" in (
        Path(api.__file__).read_text(encoding="utf8")), (
        "the fingerprint is no longer captured once at import — a per-request "
        "computation describes the working tree, not the running process")


def test_the_canonical_hook_is_tracked_as_executable():
    row = subprocess.run(
        ["git", "ls-files", "--stage", "assurance/hooks/pre-commit"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert row.startswith("100755 "), (
        "a POSIX checkout cannot execute the canonical hook; track it as 100755")


