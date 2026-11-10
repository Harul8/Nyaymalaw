"""The frozen install list for a hosting machine (the hosting review of 10 Nov 2026, after plan AN.48's 48f6).

    python development_environment/developer_tooling/hosting_requirements.py          # write requirements-hosting.txt
    python development_environment/developer_tooling/hosting_requirements.py --check  # say whether it still matches

pyproject.toml names only the lowest versions NM needs, so a fresh install can pull releases nobody has run NM with. This writes,
from the environment NM is run and tested in, every package the server needs at run time - nyaymalaw's own dependencies and its
openai, semantic and documents extras, with everything they need in turn - each pinned to the version installed here. A package
that only one platform needs keeps the marker that says so. Torch is pinned by its version alone: which build (for a graphics card or
the processor) is the hosting machine's choice, and docs/HOSTING.md says how to make it.
"""
from __future__ import annotations

import importlib.metadata as metadata
import sys
import tomllib
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "requirements-hosting.txt"
EXTRAS = ("openai", "semantic", "documents")
LEFT_OUT = {"pip", "setuptools", "wheel", "nyaymalaw"}
HEADER = """\
# The packages a hosting machine installs for NM, pinned to the versions NM is run and tested with (docs/HOSTING.md).
# Written by development_environment/developer_tooling/hosting_requirements.py from the working environment; run it again after an
# upgrade there (tests/test_the_hosting_install_list_matches.py says when the two have parted). Install with:
#     pip install -r requirements-hosting.txt
# On Windows with a graphics card, install torch from the PyTorch index first (its CUDA build), then this list.
"""


def runtime_requirements():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return [*project["dependencies"], *(text for extra in EXTRAS for text in project["optional-dependencies"][extra])]


def closure():
    """{package: extras asked of it} for everything the runtime requirements need here, and the platform markers met on the way."""
    environment = default_environment()
    found, platform = {}, {}
    queue = [(Requirement(text), "") for text in runtime_requirements()]
    while queue:
        requirement, asked_with = queue.pop()
        if requirement.marker is not None and not requirement.marker.evaluate({**environment, "extra": asked_with}):
            continue
        name = canonicalize_name(requirement.name)
        if requirement.marker is not None and any(word in str(requirement.marker) for word in ("platform", "os_name")):
            platform.setdefault(name, str(requirement.marker))
        extras, first = set(requirement.extras), name not in found
        added = extras - found.get(name, set())
        if not first and not added:
            continue
        found.setdefault(name, set()).update(extras)
        try:
            needs = metadata.distribution(requirement.name).requires or ()
        except metadata.PackageNotFoundError:
            continue
        for text in needs:
            child = Requirement(text)
            for extra in ({""} if first else set()) | added:
                if child.marker is None or child.marker.evaluate({**environment, "extra": extra}):
                    queue.append((child, extra))
                    break
    return found, platform


def lines():
    found, platform = closure()
    out = []
    for name in sorted(found):
        if name in LEFT_OUT:
            continue
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        extras = "[" + ",".join(sorted(found[name])) + "]" if found[name] else ""
        line = f"{name}{extras}=={version.split('+')[0]}"
        out.append(line + (f"; {platform[name]}" if name in platform else ""))
    return out


def main(argv):
    written = HEADER + "\n".join(lines()) + "\n"
    if "--check" in argv:
        same = TARGET.exists() and TARGET.read_text(encoding="utf-8").replace("\r\n", "\n") == written
        print("requirements-hosting.txt matches this environment." if same else
              "requirements-hosting.txt no longer matches this environment: write it again.")
        return 0 if same else 1
    TARGET.write_text(written, encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET.name}: {len(lines())} packages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
