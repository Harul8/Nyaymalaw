"""Write a bounded, read-only inventory of selected legal-source storage."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "backend"))
from nm.knowledge.source_registry import Assessment, inventory_sources  # noqa: E402

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def write_report(report: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    temporary.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--consumer-root", default=str(ROOT))
    parser.add_argument("--max-entries", type=int, default=10_000)
    parser.add_argument("--max-hash-bytes", type=int, default=16 * 1024 * 1024)
    args = parser.parse_args()

    source = Path(args.source_root)
    destination = Path(args.output)
    try:
        resolved_source = source.resolve(strict=True)
    except OSError:
        resolved_source = None
    if resolved_source is not None and _within(destination, resolved_source):
        parser.error("output must be outside the inspected source tree")

    report = inventory_sources(
        source,
        observed_at=datetime.now(timezone.utc),
        max_entries=args.max_entries,
        max_hash_bytes=args.max_hash_bytes,
        consumer_root=args.consumer_root,
        consumer_terms=("legal_database", "chunks.db", "authority.db", "identity.db"),
    )
    write_report(report.as_dict(), destination)
    print(f"{report.status.value}: {len(report.assets)} asset row(s), "
          f"{len(report.consumers)} consumer reference(s) -> {destination}")
    return 0 if report.status is Assessment.COMPLETE else 2


if __name__ == "__main__":
    raise SystemExit(main())
