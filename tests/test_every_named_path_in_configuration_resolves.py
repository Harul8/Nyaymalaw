"""A path named in configuration must name something that is there.

WHY
---
On 14 September 2026 the repository was reorganised into production homes, and
every reference was rewritten by one map. One reference was missed: the
verification fingerprint excluded `docs/Archives`, spelled without the trailing
slash the map matched on. After the move nothing lived at `docs/Archives`, so
the exclusion excluded nothing -- and the archives, which had never been part of
the checked identity, silently became part of it. Every test stayed green,
because an exclusion that names nothing does not fail; it just stops applying.

The same is true of every configuration entry that names a repository path: a
per-file lint ignore on a moved file, a package directory, a test path, a
pytest `pythonpath` entry. Renamed or moved, each one keeps parsing and quietly
stops doing its job. Defect shape S11: an absent input that reads as success.

So the population is every such entry, drawn from the configuration itself, and
each must resolve AGAINST THE TRACKED TREE, not the disk. A move leaves the old
directory behind, empty, in the checkout that made it -- measured in this very
worktree -- so a disk check passes the dead exclusion there and fails it only in
a fresh clone.
"""
from __future__ import annotations

import subprocess
import tomllib
from functools import cache
from pathlib import Path

import pytest

from assurance.control_plane.evidence import IDENTITY_MANIFEST

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]
GLOB = set("*?[")


def _pyproject_paths() -> list[tuple[str, str]]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    tool = config.get("tool", {})
    ruff = tool.get("ruff", {})
    named = [
        *(("pytest pythonpath", p) for p in tool.get("pytest", {})
          .get("ini_options", {}).get("pythonpath", [])),
        *(("pytest testpaths", p) for p in tool.get("pytest", {})
          .get("ini_options", {}).get("testpaths", [])),
        *(("wheel packages", p) for p in tool.get("hatch", {}).get("build", {})
          .get("targets", {}).get("wheel", {}).get("packages", [])),
        *(("ruff extend-exclude", p) for p in ruff.get("extend-exclude", [])),
        *(("ruff per-file-ignores", p) for p in ruff.get("lint", {})
          .get("per-file-ignores", {})),
    ]
    return [(where, path) for where, path in named if not GLOB & set(path)]


def _identity_paths(manifest=IDENTITY_MANIFEST) -> list[tuple[str, str]]:
    named = []
    for source in manifest:
        named.append((f"identity input ({source.mode})", source.path))
        base = Path(source.path)
        named.extend((f"identity exclusion under {source.path!r}", (base / exclusion).as_posix())
                     for exclusion in source.exclude)
    return named


def test_the_population_is_not_empty():
    """A guard on the guard: an empty population passes the test below."""
    assert len(_pyproject_paths()) >= 5, _pyproject_paths()
    assert any("exclusion" in where for where, _ in _identity_paths()), _identity_paths()


@cache
def _tracked() -> frozenset[str]:
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True,
                            capture_output=True).stdout.decode("utf-8")
    return frozenset(name for name in listed.split(chr(0)) if name)


def _resolves(path: str) -> bool:
    path = Path(path).as_posix()
    if path == ".":
        return bool(_tracked())
    return path in _tracked() or any(name.startswith(path + "/") for name in _tracked())


def _missing(named: list[tuple[str, str]]) -> list[str]:
    return [f"{where}: {path}" for where, path in named if not _resolves(path)]


def test_every_path_named_in_configuration_exists():
    missing = _missing([*_pyproject_paths(), *_identity_paths()])
    assert not missing, (
        "configuration names paths that are not in the repository -- each entry "
        "still parses and has silently stopped applying:\n  " + "\n  ".join(missing))


def test_the_check_bites_on_a_moved_exclusion():
    """The counterexample is the real one: the exclusion the move left behind."""
    from assurance.control_plane.evidence import IdentityInput

    left_behind = (IdentityInput(".", exclude=("docs/Archives",)),)
    assert _missing(_identity_paths(left_behind)) == [
        "identity exclusion under '.': docs/Archives"]
