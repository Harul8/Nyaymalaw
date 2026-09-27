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

#: The advocate service's package at the owning repository root. Architectural
#: roles come from the manifest, not the new journey directory names.
BACKEND_PACKAGE = "nm"

#: Compatibility root for co-located browser sources. A specific served asset
#: is resolved through browser_assets(), never by appending its URL basename.
FRONTEND = "nm"

#: Every top-level home a repository path can start with. A check that reads paths
#: out of prose (the defect register names its checks that way) matches on this
#: tuple, so a path under a new home is recognised rather than silently skipped.
# Historic backend/frontend prefixes remain recognizable in dated references;
# they are not current production or browser scan populations.
HOMES = ("nm", "operations", "backend", "frontend", "pipeline", "assurance", "docs", "tests",
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
    "operations",
    "development_environment/one_off_tools",
    "development_environment/developer_tooling",
)


def tooling_sources(pattern: str = "*.py") -> list[Path]:
    """Every file under every tooling home matching `pattern`, sorted, no caches."""
    return sorted(
        path for home in TOOLING for path in (ROOT / home).rglob(pattern)
        if path.is_file() and "__pycache__" not in path.parts
    )


def production_sources(*, root: Path = ROOT) -> list[Path]:
    """The full physical source population, never a former layer directory."""
    from assurance.common.module_roles import source_files

    return list(source_files(root=root))


def browser_assets(*, root: Path = ROOT) -> dict[str, Path]:
    """Every actual served URL basename and its co-located source owner."""
    from assurance.common.module_roles import LayoutError, load_module_roles

    assets = dict(load_module_roles(root=root).assets)
    if not assets or any(not path.is_file() or path.is_symlink()
                         or root.resolve() not in path.resolve().parents
                         for path in assets.values()):
        raise LayoutError("served browser source population is missing or escapes its root")
    return assets


def browser_sources(*, root: Path = ROOT) -> list[Path]:
    return sorted(set(browser_assets(root=root).values()))
