"""Isolated journey-shaped files with explicitly authored probe roles."""
from pathlib import Path


def role_tree(root: Path, statement: str, *, role: str = "core",
              target_role: str = "adapters") -> dict[str, str]:
    rows = {"nm": "domain", "nm.work_the_file": "domain", "nm.shared": "domain",
            "nm.work_the_file.probe": role, "nm.shared.target": target_role}
    for module in rows:
        path = (root / module.replace(".", "/") / "__init__.py"
                if module in {"nm", "nm.work_the_file", "nm.shared"}
                else root / (module.replace(".", "/") + ".py"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(statement if module == "nm.work_the_file.probe" else "",
                        encoding="utf8")
    return rows
