"""Read Act files the way the append job reads them, and say what it would find. FREE: no encoder, nothing written, nothing changed.

    .venv-arrive\\Scripts\\python.exe pipeline\\check_bare_acts.py "<Act file>.txt" ... --jurisdiction "Union of India"

For each file it prints, as one line of JSON, the Act's identity, how many sections it found and where (the ranges the owner checks against
the arrangement of sections), how many passages the append would make, how many lines it would not keep, and every place the numbering
was read as something other than sections. This is the first half of what `append_bare_acts.py --dry-run` prints, without loading the
encoder; the Admin area's Library page runs it on files an admin has chosen (plan AN.46), so the reading of an Act can be seen before the
owner appends it. A file it cannot read is reported with the reason, and the others are still read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.append_bare_acts import _ranges, parse_act, passages_for  # noqa: E402


def check(path: Path, jurisdiction: str) -> dict:
    try:
        act = parse_act(path, jurisdiction)
        cut = passages_for(act)
    except (ValueError, OSError) as exc:
        return {"name": path.name, "error": str(exc)[:300]}
    return {"name": path.name, "act_id": act.act_id, "act_name": act.act_name, "year": act.year, "sections": len(act.sections),
            "passages": len(cut), "skipped": act.skipped, "ranges": _ranges([s.number for s in act.sections]), "notes": list(act.notes)[:60],
            "notes_in_all": len(act.notes)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--jurisdiction", required=True, help="as the library's folders name it, e.g. 'Union of India' or 'Telangana'")
    args = ap.parse_args(argv)
    print(json.dumps({"acts": [check(path, args.jurisdiction) for path in args.files]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
