"""Issue one expiring, identity-bound Nyaymalaw roster invitation.

    python backend/operations/invite.py --email r.kumar@example.com --name "R Kumar" \
        --firm firm_rk --issued-by chambers-admin

The token is printed once and only its SHA-256 fingerprint is retained.  Name,
email, enrolment, practice and firm are fixed by this command; the registration
request cannot choose a different identity or workspace.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "backend"))
from assurance.common._console import utf8_console  # noqa: E402

utf8_console()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--enrolment", default="")
    parser.add_argument("--practice", default="")
    parser.add_argument("--firm", required=True,
                        help="workspace whose conflicts boundary applies")
    parser.add_argument("--issued-by", required=True,
                        help="accountable operator recorded in the audit")
    args = parser.parse_args(argv)

    from nm.bootstrap.composition import Application
    from nm.domain.advocate import AdvocateIdentity, canonical_id, utcnow

    email = canonical_id(args.email)
    identity = AdvocateIdentity(
        id=email, email=email, name=args.name.strip(),
        enrolment=args.enrolment.strip(), practice=args.practice.strip(),
        firm_id=args.firm.strip())
    application = Application()
    token = application.directory.issue_invitation(
        identity, args.issued_by, utcnow())
    print(f"invited {identity.name} <{identity.email}> to firm {identity.firm_id}")
    print("invitation (shown ONCE; expires in 48 hours):")
    print(f"    {token}")
    print("Only its fingerprint is stored. Reissue rather than copying it into a file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
