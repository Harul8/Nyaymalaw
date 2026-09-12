"""Every git path that changes the tree refreshes the graph AND its vectors,
through one script.

WHAT WAS MEASURED, 12 September 2026
--------------------------------------
`tools/hooks/pre-commit` had refreshed the vectors on every `git commit`
since 10 September, and the semantic index was 600 non-File nodes behind:
`manifest.py` 43, `source_registry.py` 43, `test_immutable_corpus_publication.py`
42, `commission.py` 25 and fifteen more files. A query about sealed corpus
generations returned five confident results about matter-store seals and
not one of the classes that answered it.

Every one of the 600 arrived by a path pre-commit never sees. `1399a53`
reached HEAD as a fast-forward, which runs no commit hook; `68927c3` and
`a3d9c47` as merge commits, for which git runs pre-merge-commit and not
pre-commit. The work itself had been committed on codex/ branches on another
machine, where the hook was not installed.

THE RULE
----------
A tree can change four ways -- commit, merge, rewrite, and a commit made
elsewhere and merged here -- and a refresh that covers one of them is
bypassed by the other three, silently. So:

1. A hook exists for each local path (pre-commit, post-merge, post-rewrite).
2. Each reaches the refresh through ONE script, `refresh-graph`, and none
   carries its own copy of the update or the embed. Three hooks with three
   copies is three places for the fourth to drift (CLAUDE.md §4).
3. The hooks are the tracked directory itself (`core.hooksPath tools/hooks`),
   because the copy in `.git/hooks/` was measured two revisions behind the
   file it was copied from, and nothing compared them.

The fourth path -- work merged from a machine without the hook -- is what
post-merge closes: the merge is local even when the commits were not.

What this test CANNOT prove is that the vectors are current on this
machine: `.code-review-graph/` is gitignored, and a test that skipped when it
was absent would pass on every clean checkout. That number is printed by
`tools/graph_vectors.py --check` at commit, merge and session start, where
the artefact actually lives.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOKS = ROOT / "tools" / "hooks"
OWNER = "refresh-graph"

#: The local ways a tree changes, and the hook git runs for each.
TREE_CHANGING_HOOKS = ("pre-commit", "post-merge", "post-rewrite")

#: The two refresh commands. Their presence anywhere but the owner is a copy.
REFRESH_COMMANDS = (
    re.compile(r"code-review-graph\s+update\b"),
    re.compile(r"graph_vectors\.py\s+--embed\b"),
)


def _hook(name: str) -> str:
    return (HOOKS / name).read_text(encoding="utf8")


def _code_lines(text: str) -> list[str]:
    """The lines that execute -- comments describe, they do not refresh."""
    return [ln for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


# ================================================================ coverage ===

@pytest.mark.parametrize("name", TREE_CHANGING_HOOKS)
def test_each_way_the_tree_changes_has_a_hook_that_refreshes(name):
    """A hook per path, and each one reaches the refresh."""
    assert (HOOKS / name).exists(), (
        f"tools/hooks/{name} is missing, so a tree changed by that path "
        f"leaves the graph describing the previous one")
    code = "\n".join(_code_lines(_hook(name)))
    assert f"tools/hooks/{OWNER}" in code, (
        f"{name} does not call {OWNER}, so its refresh -- if any -- is a "
        f"second copy or absent")


def test_the_owner_performs_both_halves_of_the_refresh():
    """Structure and vectors, together. `update` alone is the 10 September
    defect; `embed` alone would embed nodes the graph has not yet seen."""
    code = "\n".join(_code_lines(_hook(OWNER)))
    for pattern in REFRESH_COMMANDS:
        assert pattern.search(code), (
            f"{OWNER} lacks `{pattern.pattern}`, so half the refresh is gone")
    assert code.index("code-review-graph update") < code.index("graph_vectors.py"), (
        "the vectors are embedded before the graph is updated, so new nodes "
        "are not there to be embedded")


def test_the_owner_never_blocks():
    """A post-* hook cannot block and pre-commit must not block on this:
    offline is a normal state and a search index is not a release criterion.
    The gate that DOES block lives in pre-commit, after the refresh."""
    code = _code_lines(_hook(OWNER))
    for ln in code:
        for pattern in REFRESH_COMMANDS:
            if pattern.search(ln):
                assert "|| true" in ln, (
                    f"`{ln.strip()}` can fail the hook, so an offline "
                    f"developer cannot commit")
    assert code[-1].strip() == "exit 0"


# ========================================================== the second copy ==

def test_no_hook_carries_its_own_copy_of_the_refresh():
    """§4: what refuses the second copy? This does. A refresh command in any
    hook but the owner is a copy that will drift from it."""
    for path in HOOKS.iterdir():
        if path.name == OWNER or path.suffix:  # .sample, .md etc. are not hooks
            continue
        code = "\n".join(_code_lines(path.read_text(encoding="utf8")))
        for pattern in REFRESH_COMMANDS:
            assert not pattern.search(code), (
                f"tools/hooks/{path.name} carries `{pattern.pattern}` "
                f"itself; only {OWNER} may")


def test_the_refresh_is_not_duplicated_outside_the_hooks_either():
    """The embed command is INVOKED from exactly one place. `graph_vectors.py`
    names itself in its own docstring and its own report -- that is the
    tool saying what to run, not a second thing running it -- so it is the
    one file excused, by name and for that reason."""
    homes = set()
    for path in (ROOT / "tools").rglob("*"):
        if not path.is_file() or path.suffix in (".pyc", ".md"):
            continue
        if path.name == "graph_vectors.py":
            continue
        text = path.read_text(encoding="utf8", errors="replace")
        for ln in _code_lines(text):
            if REFRESH_COMMANDS[1].search(ln):
                homes.add(path.relative_to(ROOT).as_posix())
    assert homes == {f"tools/hooks/{OWNER}"}, (
        f"`graph_vectors.py --embed` is invoked from {sorted(homes)}; "
        f"one owner, and it is tools/hooks/{OWNER}")


# ============================================================ installation ===

@pytest.mark.parametrize("name", (OWNER, *TREE_CHANGING_HOOKS))
def test_every_hook_is_tracked_as_executable(name):
    row = subprocess.run(
        ["git", "ls-files", "--stage", f"tools/hooks/{name}"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert row.startswith("100755 "), (
        f"tools/hooks/{name} is not tracked as 100755 -- a POSIX checkout "
        f"cannot execute it, and git runs a hook it cannot execute as nothing")


@pytest.mark.parametrize("name", (OWNER, *TREE_CHANGING_HOOKS))
def test_every_hook_stays_lf_through_a_windows_checkout(name):
    """sh does not strip \\r. With core.autocrlf=true a checkout rewrites a
    hook CRLF and `|| true` becomes `|| true\\r`: command not found -- silent
    in post-*, blocking in pre-commit. `.gitattributes` pins the directory,
    and this asks git which attribute actually applies rather than reading
    the file for a pattern that might not match."""
    attrs = subprocess.run(
        ["git", "check-attr", "eol", "--", f"tools/hooks/{name}"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert attrs.endswith(": eol: lf"), (
        f"tools/hooks/{name} has no `eol=lf` attribute ({attrs!r}); a Windows "
        f"checkout can rewrite it CRLF and sh will not run it")
    raw = (HOOKS / name).read_bytes()
    assert b"\r" not in raw, f"tools/hooks/{name} already carries CRLF"


def test_the_hooks_are_installed_by_path_not_by_copy():
    """The documented install must be `core.hooksPath`, because the copy was
    measured two revisions behind and nothing compared them."""
    text = _hook("pre-commit")
    assert "core.hooksPath tools/hooks" in text, (
        "pre-commit no longer documents `git config core.hooksPath "
        "tools/hooks`, so the next install is a copy that can drift")
    assert not re.search(r"^# INSTALL:.*\bcp\b", text, flags=re.M), (
        "pre-commit still documents installing by `cp`")
