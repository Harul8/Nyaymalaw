"""The frozen install list for a hosting machine (the hosting review of 10 Nov 2026): requirements-hosting.txt pins every package the
server needs at run time to the version NM is run and tested with here, so that a hosting machine installs what was tested rather than
whatever is newest. It says when the two have parted - an upgrade here, the list not written again - and it holds every runtime
dependency pyproject.toml names, each pinned exactly. Offline: reads the installed packages' own metadata."""
import importlib.util
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def tool():
    spec = importlib.util.spec_from_file_location(
        "hosting_requirements", ROOT / "development_environment" / "developer_tooling" / "hosting_requirements.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pinned():
    rows = [line.strip() for line in (ROOT / "requirements-hosting.txt").read_text(encoding="utf-8").splitlines()]
    return [Requirement(line) for line in rows if line and not line.startswith("#")]


def test_the_list_is_what_this_environment_runs_nm_with():
    # The list is written in the environment NM is run and tested in. A pinned line whose platform this environment does not meet
    # shows it was written on another platform - a clone on Linux, the runner - where the comparison is not this environment's to
    # make (14 Nov 2026, plan AN.54, D227); where it was written, it is made.
    foreign = [str(requirement) for requirement in pinned() if requirement.marker is not None and not requirement.marker.evaluate()]
    if foreign:
        pytest.skip(f"the list was written on another platform ({foreign[0]}); it is checked where it is written")
    assert tool().main(["--check"]) == 0, ("requirements-hosting.txt no longer matches the environment NM is tested in: run "
                                          "development_environment/developer_tooling/hosting_requirements.py")


def test_every_runtime_dependency_is_on_the_list_and_every_line_is_pinned_exactly():
    listed = {canonicalize_name(requirement.name): requirement for requirement in pinned()}
    for text in tool().runtime_requirements():
        wanted = Requirement(text)
        if wanted.marker is not None and not wanted.marker.evaluate():
            continue  # another platform's (truststore is Windows only)
        assert canonicalize_name(wanted.name) in listed, wanted.name
    for requirement in listed.values():
        (specifier,) = requirement.specifier
        assert specifier.operator == "==" and "+" not in specifier.version, str(requirement)
    assert "standard" in listed["uvicorn"].extras, "the server's own extras travel with it"
