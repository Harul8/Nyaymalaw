"""Record or revoke a bounded professional approval from the trusted operator host.

No HTTP endpoint exposes this writer. Possession of the deployment's storage
and sealing key is the operator boundary, not a self-registered account. The
operator must actually review the supporting artifact before using this tool.
This records that review; it cannot determine professional qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._console import utf8_console  # noqa: E402

utf8_console()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    approve = commands.add_parser("approve", help="record a review already performed")
    revoke = commands.add_parser("revoke", help="withdraw the current approval")
    status = commands.add_parser("status", help="read the version before an operator update")
    status.add_argument("--account", required=True)
    for command in (approve, revoke):
        command.add_argument("--account", required=True)
        command.add_argument("--operator", required=True)
        command.add_argument("--basis", required=True)
        command.add_argument("--expected-version", type=int, required=True,
                             help="0 only for an account with no previous approval")
    approve.add_argument("--evidence", type=Path, required=True,
                         help="reviewed local artifact; only its reference/digest is stored")
    approve.add_argument("--valid-until", required=True,
                         help="aware ISO date/time, for example 2026-10-01T12:00:00+05:30")
    args = parser.parse_args(argv)

    from nm.bootstrap.composition import Application
    from nm.domain.advocate import canonical_id, utcnow
    from nm.domain.professional_access import ProfessionalApproval, professional_status

    now = utcnow()
    account = canonical_id(args.account)
    directory = Application().directory
    if args.command == "status":
        print(json.dumps(professional_status(directory.professional_approval(account),
                                             account, now), indent=2))
        return 0
    try:
        if args.command == "approve":
            artifact = args.evidence.resolve(strict=True)
            if not artifact.is_file():
                raise ValueError("supporting evidence must be an existing file")
            supporting_bytes = artifact.read_bytes()
            if not supporting_bytes:
                raise ValueError("supporting evidence must not be empty")
            digest = hashlib.sha256(supporting_bytes).hexdigest()
            approval = ProfessionalApproval(
                account_id=account, reviewer_id=args.operator, basis=args.basis,
                evidence_ref=str(artifact), evidence_sha256=digest,
                approved_at=now, valid_until=datetime.fromisoformat(args.valid_until),
                version=args.expected_version + 1)
        else:
            previous = ProfessionalApproval.from_record(directory.professional_approval(account))
            if previous is None or previous.version != args.expected_version:
                raise ValueError("read the current approval version before revoking it")
            approval = previous.revoke(args.operator, args.basis, now)
        saved = directory.record_professional_approval(
            approval, expected_version=args.expected_version, now=now)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Approval was not recorded: {exc}\n")
    print(json.dumps(professional_status(saved, account, now), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
