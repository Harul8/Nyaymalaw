"""Where each part of the repository lives. ONE OWNER for the layout.

    from assurance.common.homes import ROOT, BACKEND_PACKAGE, FRONTEND, TOOLING

WHY THIS EXISTS
---------------
On 14 September 2026 the repository was reorganised into production homes --
`backend/`, `frontend/`, `pipeline/`, `assurance/` -- and `development_environment/`
for everything kept but not shipped. Before that, every piece of tooling lived under
one `tools/` directory, and a dozen sweeps scanned "all the tooling" by writing
`ROOT / "tools"`.

After the move that population is four directories. Writing those four into each
sweep would give the layout a dozen owners, and the day a fifth home is added the
sweeps that were not updated would scan less than they did -- quietly, with every one
of them still green. A sweep whose population shrinks without failing is defect
shape S11. So the homes are declared here, once, and every sweep reads them.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The advocate service's Python package. The package NAME stays `nm`; only its
#: directory moved, so no import changed.
BACKEND_PACKAGE = "backend/nm"

#: The advocate UI the backend mounts at `/`.
FRONTEND = "frontend"

#: Every top-level home a repository path can start with. A check that reads paths
#: out of prose (the defect register names its checks that way) matches on this
#: tuple, so a path under a new home is recognised rather than silently skipped.
HOMES = ("backend", "frontend", "pipeline", "assurance", "docs", "tests",
         "development_environment")

#: Every home of repository tooling -- what `tools/` held before the move. A sweep
#: over "all tooling" reads this tuple, never a hand-written list.
TOOLING = (
    # NOT the whole of assurance/. The specification generators under
    # assurance/specification/ came from spec/, never from tools/, and were never in
    # these populations. Counting them would GROW every "all tooling" sweep -- and for
    # a sweep asking whether an owner is referenced anywhere, a bigger population can
    # hide a dead one.
    "assurance/gate",
    "assurance/journeys",
    "assurance/control_plane",
    "assurance/common",
    "assurance/hooks",
    "pipeline",
    "backend/operations",
    "development_environment/one_off_tools",
    "development_environment/developer_tooling",
)


def tooling_sources(pattern: str = "*.py") -> list[Path]:
    """Every file under every tooling home matching `pattern`, sorted, no caches."""
    return sorted(
        path for home in TOOLING for path in (ROOT / home).rglob(pattern)
        if path.is_file() and "__pycache__" not in path.parts
    )
