"""The lint and the type check are held on the lines a push changes (plan AN.57, pieces 57c and 57d; D265, D354; the second
review of 17 Nov 2026).

The project's lint rules were never enforced and there was no type check. A push is now held to the lines it adds: the tool
reads them from Git, runs the checker on the files they are in, and keeps only the findings on an added line - every selected
rule but the length of a line, which is counted and said (D354). Planted repositories made in a temporary folder show a finding
held on an added line and not on an untouched one, an import block unsorted by one added line held, new and uncommitted files
counted, the base chosen when the runner gives none, and planted type-checker output filtered by the same mechanism. Offline;
the lint is the project's own; the type checker is not installed here, so its own runs are the hosted runner's.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from development_environment.developer_tooling import changed_lines

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = '[tool.ruff]\nline-length = 100\n\n[tool.ruff.lint]\nselect = ["E", "F", "I"]\n'


def git(root, *args):
    done = subprocess.run(["git", "-c", "user.name=Planted", "-c", "user.email=planted@example.test",
                           "-c", "commit.gpgsign=false", *args], cwd=root, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def planted(tmp_path, files):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q")
    for name, text in {"pyproject.toml": SETTINGS, **files}.items():
        (root / name).write_text(text, encoding="utf8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root, git(root, "rev-parse", "HEAD")


def held(capsys, root, base, check="lint"):
    code = changed_lines.main([check, "--base", base, "--root", str(root)])
    return code, capsys.readouterr().out


def test_a_finding_on_an_added_line_is_held_the_same_on_an_untouched_line_is_not_and_a_long_line_is_only_counted(
        tmp_path, capsys):
    root, base = planted(tmp_path, {"old.py": "import os\n\n\ndef f():\n    return 1\n"})
    with open(root / "old.py", "a", encoding="utf8") as file:
        file.write("\n\ndef g():\n    unused = 1\n    return 2\n\n\n# " + "a long comment " * 8 + "\n")
    git(root, "commit", "-qam", "change")
    code, out = held(capsys, root, base)
    assert code == 1, out
    assert "old.py:9:5: F841" in out, out
    assert "F401" not in out, "the unused import was there before the push and stays unheld"
    assert "not held: 1 changed line(s) with E501" in out
    # A push that touches only lines with nothing to find passes, though the file still holds the old finding.
    root2, base2 = planted(tmp_path / "second", {"old.py": "import os\n\n\ndef f():\n    return 1\n"})
    (root2 / "old.py").write_text("import os\n\n\ndef f():\n    return 2\n", encoding="utf8")
    code, out = held(capsys, root2, base2)
    assert code == 0 and "lint: 0 finding(s) held on 1 changed line(s) in 1 file(s)" in out, out


def test_one_added_line_that_unsorts_an_import_block_is_held_and_an_untouched_unsorted_block_is_not(tmp_path, capsys):
    root, base = planted(tmp_path, {"a.py": "import os\nimport sys\n\nprint(os, sys)\n",
                                    "b.py": "import sys\nimport os\n\nprint(os, sys)\n"})
    (root / "a.py").write_text("import os\nimport sys\nimport abc\n\nprint(abc, os, sys)\n", encoding="utf8")
    (root / "b.py").write_text("import sys\nimport os\n\nprint(os, sys, 1)\n", encoding="utf8")
    code, out = held(capsys, root, base)
    assert code == 1 and "a.py:1:1: I001" in out and "b.py" not in out, out


def test_new_and_uncommitted_files_count_as_added(tmp_path, capsys):
    root, base = planted(tmp_path, {"old.py": "X = 1\n"})
    (root / "new.py").write_text("import json\n", encoding="utf8")
    code, out = held(capsys, root, base)
    assert code == 1 and "new.py:1:8: F401" in out, out
    assert changed_lines.added_lines(root, base) == {"new.py": {1}}


def test_the_base_falls_back_to_the_commit_before_head_and_says_why(tmp_path):
    root, first = planted(tmp_path, {"old.py": "X = 1\n"})
    assert changed_lines.base_commit(root, "") == (changed_lines.EMPTY_TREE,
                                                   "the history's first commit: every line counts as added")
    (root / "old.py").write_text("X = 2\n", encoding="utf8")
    git(root, "commit", "-qam", "second")
    assert changed_lines.base_commit(root, first) == (first, f"compared with {first[:12]}")
    assert changed_lines.base_commit(root, "0" * 40) == ("HEAD~1", "no base was given: compared with the commit before HEAD")
    unknown = "1234567890abcdef1234567890abcdef12345678"
    assert changed_lines.base_commit(root, unknown) == (
        "HEAD~1", "1234567890ab is not in this history: compared with the commit before HEAD")


def test_the_type_checker_s_errors_are_held_on_changed_lines_by_the_same_filter_and_its_notes_are_not_findings(
        tmp_path, capsys):
    absolute = tmp_path / "pkg" / "b.py"
    output = "\n".join([
        'pkg/a.py:3:12: error: Incompatible return value type (got "int", expected "str")  [return-value]',
        "pkg/a.py:3:12: note: an explanation that belongs to the error above",
        'pkg/a.py:10:1: error: Name "later" is not defined  [name-defined]',
        f"{absolute}:2: error: Missing return statement  [return]",
    ])
    found = changed_lines.type_findings(tmp_path, output)
    assert [(item["path"], item["row"], item["code"]) for item in found] == [
        ("pkg/a.py", 3, "return-value"), ("pkg/a.py", 10, "name-defined"), ("pkg/b.py", 2, "return")]
    added = {"pkg/a.py": {3, 4}, "pkg/b.py": {7}}
    assert [item["row"] for item in changed_lines.on_added(found, added)] == [3]
    assert changed_lines.report(found, added, "type check") == 1
    assert "pkg/a.py:3:12: return-value Incompatible return value type" in capsys.readouterr().out


def test_a_check_that_cannot_run_is_never_a_pass(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "not-a-repository"
    plain.mkdir()
    assert changed_lines.main(["lint", "--root", str(plain)]) == 2
    assert "the check could not be made" in capsys.readouterr().err
    # A type checker that is not installed answers 1 with nothing found: that is not taken for a pass.
    monkeypatch.setattr(changed_lines.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a, 1, stdout="", stderr="No module named mypy"))
    try:
        changed_lines.run_types(tmp_path, ["a.py"])
    except RuntimeError as exc:
        assert "No module named mypy" in str(exc)
    else:
        raise AssertionError("a type checker that did not run was taken for a pass")


def test_the_runner_holds_both_checks_on_changed_lines_with_the_whole_history():
    workflow = (ROOT / ".github" / "workflows" / "offline-tests.yml").read_text(encoding="utf8")
    job = workflow[workflow.index("\n  lint:"):]
    assert "fetch-depth: 0" in job
    assert "changed_lines.py lint --base" in job and "changed_lines.py types --base" in job
    settings = (ROOT / "pyproject.toml").read_text(encoding="utf8")
    assert "[tool.mypy]" in settings
