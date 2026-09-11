"""Inspect a staged acquisition run without publishing it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nm.knowledge.acquisition import (  # noqa: E402
    ReconciliationState,
    reconcile_acquisition,
)
from tools._console import utf8_console  # noqa: E402

utf8_console()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_path", help="staged acquisition run directory")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    report = reconcile_acquisition(args.run_path)
    if args.as_json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"{report.state.value}: {report.staged} staged, "
              f"{report.failed} failed, {report.unresolved} unresolved")
        for reason in report.reasons:
            print(f"  - {reason}")
        print(f"  {report.run_path}")
    return 0 if report.state is ReconciliationState.COMPLETE else 2


if __name__ == "__main__":
    raise SystemExit(main())
