"""Set an account's user type from the trusted operator host: the FIRST admin, before any admin exists to do it from the Users page
(plan AN.46; owner, 7 Nov 2026), or the way back if the last admin is lost.

Possession of the deployment's storage is the operator boundary, as for the other tools here. This changes one thing about one account - its
user type, advocate or admin - and writes the audit entry the Users page would have written, naming the operator.

    python operations/admin.py list
    python operations/admin.py make-admin --account advocate@chambers.in --operator rahul --reason "first admin"
    python operations/admin.py make-advocate --account advocate@chambers.in --operator rahul --reason "no longer needs it"

`list` shows each account's user type and who is named as an admin in the server's own settings. Nothing is changed by `list`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from assurance.common._console import utf8_console  # noqa: E402

utf8_console()


def main(argv: list[str] | None = None, *, application=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="every account's user type")
    for name, help_text in (("make-admin", "make an account an Admin"), ("make-advocate", "make an account an Advocate")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--account", required=True)
        sub.add_argument("--operator", required=True)
        sub.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    from nm.arrive.admin_port import AdminChangeRefused, AdminUnavailable, AuditEntry
    from nm.arrive.advocate_contracts import canonical_id, utcnow

    if application is None:
        from nm.app.composition import Application
        application = Application()
    now = utcnow()
    try:
        if args.command == "list":
            named = dict(application.admin_roster.named())
            for account in application.admin_directory.listing(now).accounts:
                level = named.get(account.id)
                print(f"{account.id}\t{'admin' if account.user_type == 'admin' else 'advocate'}"
                      + (f"\tnamed in the server's settings as {level.value}" if level is not None else ""))
            return 0
        wanted = "admin" if args.command == "make-admin" else "advocate"
        account = canonical_id(args.account)
        reason = args.reason.strip()
        if not reason or len(reason) > 200 or any(ord(c) < 32 for c in reason):
            raise ValueError("give a reason in one line of at most 200 characters")
        label, actor = f"user type {wanted}", f"operator {args.operator.strip()}"[:254]
        application.admin_record.append(AuditEntry(now, actor, label, account, reason, "started"))
        try:
            changed = application.admin_accounts.set_user_type(account, wanted)
        except (AdminChangeRefused, AdminUnavailable, ValueError) as exc:
            application.admin_record.append(AuditEntry(now, actor, label, account, reason, "not made"))
            raise
        application.admin_record.append(AuditEntry(now, actor, label, account, reason, "done"))
        print(f"{account} is {'now' if changed else 'already'} {'an Admin' if wanted == 'admin' else 'an Advocate'}.")
    except AdminChangeRefused as exc:
        parser.exit(2, f"Nothing was changed: {exc.detail}\n")
    except (AdminUnavailable, ValueError) as exc:
        parser.exit(2, f"Nothing was changed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
