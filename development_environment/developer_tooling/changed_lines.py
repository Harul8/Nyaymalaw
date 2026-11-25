"""The lint and the type check, held on the lines a push changes (plan AN.57, pieces 57c and 57d; D265, D354).

The project's lint rules (pyproject.toml) were never enforced, and the code holds thousands of findings written before anyone
checked; reflowing them in one sweep was ruled out (D265). So a push is held only to the lines it adds: this tool reads those
lines from Git, runs the checker on the Python files they are in, and keeps the findings that fall on an added line. A finding
that spans lines - an import block - is kept where any of its lines was added. One mechanism decides for both checks.

THE LENGTH OF A LINE IS NOT HELD (D354): over a quarter of the lines written in the forty commits before this tool passed the
project's limit, and the prompts' text cannot be wrapped without changing what the model reads. Long added lines are counted
and said, and do not fail. Every other selected rule does.

The base is the commit the push started from, or the pull request's base. Where the runner gives none (a new branch), or one
this history does not hold (a rewritten one), the commit before HEAD is used, and the tool says so. Compared against the
working tree, so the same command run on a laptop also checks what is not yet committed (new files count as wholly added).

  python development_environment/developer_tooling/changed_lines.py lint  [--base REF]
  python development_environment/developer_tooling/changed_lines.py types [--base REF]

Exit 0 when nothing held is found; 1 when something is; 2 when the check could not be made, which is never a pass.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

#: Rules reported on changed lines but not failed on, each with its reason (D354).
NOT_HELD = {"E501": "the length of a line (D354)"}
#: Git's tree with nothing in it: the base of a history's first commit.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
#: A type checker's line: path:line[:column]: error: message  [code]
TYPE_LINE = re.compile(r"^(?P<path>(?:[A-Za-z]:)?[^:\n]+):(?P<row>\d+):(?:(?P<col>\d+):)?\s*(?P<level>error|warning|note):"
                       r" (?P<message>.*?)(?:\s+\[(?P<code>[a-z0-9-]+)\])?\s*$")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf8", errors="replace")


def base_commit(root: Path, given: str | None) -> tuple[str, str]:
    """The commit to compare against, and what the tool says about how it was chosen."""
    given = (given or "").strip()
    if given and set(given) != {"0"} and git(root, "cat-file", "-e", f"{given}^{{commit}}").returncode == 0:
        return given, f"compared with {given[:12]}"
    if git(root, "rev-parse", "--verify", "-q", "HEAD~1").returncode == 0:
        said = "no base was given" if not given or set(given) == {"0"} else f"{given[:12]} is not in this history"
        return "HEAD~1", f"{said}: compared with the commit before HEAD"
    return EMPTY_TREE, "the history's first commit: every line counts as added"


def added_lines(root: Path, base: str) -> dict[str, set[int]]:
    """Each Python file's added lines, by its path from the root: the lines base -> working tree adds, and every line of a new
    file Git does not yet track."""
    diff = git(root, "diff", "-U0", "--no-color", "--no-ext-diff", "--diff-filter=AMR", base, "--", "*.py")
    if diff.returncode != 0:
        raise RuntimeError(f"git diff failed: {diff.stderr.strip()}")
    added: dict[str, set[int]] = {}
    path = None
    for line in diff.stdout.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
            if path is not None:
                added.setdefault(path, set())
        elif path is not None and (hunk := HUNK.match(line)):
            start, count = int(hunk.group(1)), int(hunk.group(2) or 1)
            added[path].update(range(start, start + count))
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "--", "*.py")
    for path in untracked.stdout.splitlines():
        text = (root / path).read_text(encoding="utf8", errors="replace")
        added[path] = set(range(1, len(text.splitlines()) + 1))
    return {path: rows for path, rows in added.items() if rows and (root / path).is_file()}


def relative(root: Path, filename: str) -> str:
    path = Path(filename)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(root.resolve())
        except ValueError:
            pass
    return path.as_posix()


def on_added(findings: list[dict], added: dict[str, set[int]]) -> list[dict]:
    """The findings any of whose lines was added."""
    return [finding for finding in findings
            if set(range(finding["row"], finding.get("end_row", finding["row"]) + 1)) & added.get(finding["path"], set())]


def lint_findings(root: Path, files: list[str]) -> list[dict]:
    run = subprocess.run([sys.executable, "-m", "ruff", "check", "--no-cache", "--exit-zero", "--output-format", "json",
                          *files], cwd=root, capture_output=True, text=True, encoding="utf8", errors="replace")
    if run.returncode != 0:
        raise RuntimeError(f"the lint could not run: {run.stderr.strip()}")
    return [{"path": relative(root, item["filename"]), "row": item["location"]["row"],
             "end_row": item["end_location"]["row"], "column": item["location"]["column"],
             "code": item["code"] or "syntax", "message": item["message"]} for item in json.loads(run.stdout or "[]")]


def type_findings(root: Path, output: str) -> list[dict]:
    """A type checker's errors from its plain output; its notes belong to an error and are not findings of their own."""
    found = []
    for line in output.splitlines():
        match = TYPE_LINE.match(line.strip())
        if match and match["level"] == "error":
            found.append({"path": relative(root, match["path"]), "row": int(match["row"]),
                          "column": int(match["col"] or 0), "code": match["code"] or "error", "message": match["message"]})
    return found


def run_types(root: Path, files: list[str]) -> list[dict]:
    run = subprocess.run([sys.executable, "-m", "mypy", "--no-error-summary", "--show-column-numbers", "--no-pretty",
                          "--no-color-output", *files], cwd=root, capture_output=True, text=True, encoding="utf8",
                         errors="replace")
    found = type_findings(root, run.stdout)
    # It answers 1 when it finds something; a 1 with nothing found is a checker that did not run (not installed, say).
    if run.returncode not in (0, 1) or (run.returncode == 1 and not found):
        raise RuntimeError(f"the type check could not run: {(run.stderr or run.stdout).strip()[-2000:]}")
    return found


def report(findings: list[dict], added: dict[str, set[int]], what: str) -> int:
    kept = on_added(findings, added)
    held = [finding for finding in kept if finding["code"] not in NOT_HELD]
    for finding in held:
        print(f"{finding['path']}:{finding['row']}:{finding['column']}: {finding['code']} {finding['message']}")
    for code, reason in NOT_HELD.items():
        count = sum(finding["code"] == code for finding in kept)
        if count:
            print(f"not held: {count} changed line(s) with {code}, {reason}")
    lines = sum(len(rows) for rows in added.values())
    print(f"{what}: {len(held)} finding(s) held on {lines} changed line(s) in {len(added)} file(s)")
    return 1 if held else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The lint or the type check, held on the lines a push changes.")
    parser.add_argument("check", choices=("lint", "types"))
    parser.add_argument("--base", default="")
    parser.add_argument("--root", default=".")
    arguments = parser.parse_args(argv)
    root = Path(arguments.root).resolve()
    try:
        base, said = base_commit(root, arguments.base)
        print(said)
        added = added_lines(root, base)
        if not added:
            print("no Python line changed")
            return 0
        files = sorted(added)
        if arguments.check == "lint":
            return report(lint_findings(root, files), added, "lint")
        return report(run_types(root, files), added, "type check")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"the check could not be made: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
