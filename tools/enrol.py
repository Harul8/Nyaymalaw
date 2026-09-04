"""A1 — enrol an advocate. Run by a person, never by the product.

    python tools/enrol.py --id adv_rahul --name "R Kumar" \\
        --enrolment "AP/1234/2010" --practice "Hyderabad" --firm firm_rk

The password is GENERATED and printed once. It is not read from a prompt, not
taken on the command line, and not stored anywhere but the derived hash:

  * a prompt cannot be driven by an agent, and this tool has to be runnable
    from a script as well as a keyboard;
  * a password on the command line is in the shell history and in the process
    table, which is a worse place for it than this terminal;
  * an agent that CHOOSES a password has chosen the thing that stands between
    two advocates' client files.

Set `NM_NEW_PASSWORD` to supply your own. It is checked against the same
minimum as everything else, because a rule that lives at one door has a back
one.

WHAT IT REFUSES
----------------
An id that is already enrolled. Re-enrolling would replace a credential
without anyone deciding to, and the advocate would discover it at a login
that no longer works.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools._console import utf8_console  # noqa: E402

utf8_console()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", required=True, help="the advocate id, e.g. adv_rahul")
    ap.add_argument("--name", required=True)
    ap.add_argument("--enrolment", required=True,
                    help="Bar Council enrolment number")
    ap.add_argument("--practice", required=True, help="where they practise")
    ap.add_argument("--firm", required=True,
                    help="the firm whose conflicts registry governs this "
                         "session. B3 screens against it and a blank firm is a "
                         "conflict check run against nothing.")
    args = ap.parse_args()

    from nm.adapters.store.directory import AlreadyEnrolled, FileDirectory
    from nm.bootstrap.composition import Application
    from nm.domain.advocate import AdvocateIdentity, Enrolment, enrol

    app = Application()
    directory: FileDirectory = app.directory

    supplied = os.environ.get("NM_NEW_PASSWORD")
    password = supplied or _generated()

    try:
        identity = AdvocateIdentity(
            id=args.id, name=args.name, enrolment=args.enrolment,
            practice=args.practice, firm_id=args.firm)
        directory.enrol(Enrolment(identity=identity, credential=enrol(password)))
    except AlreadyEnrolled as exc:
        print(f"REFUSED: {exc}")
        return 1
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 1

    print(f"enrolled {identity.id} — {identity.name}, {identity.enrolment}, "
          f"{identity.practice}, firm {identity.firm_id}")
    if supplied:
        print("password: taken from NM_NEW_PASSWORD")
    else:
        print()
        print("  password (shown ONCE, it is not recoverable):")
        print(f"      {password}")
        print()
        print("  Only a derived scrypt hash is on disk. Nothing can print this")
        print("  again, including this tool.")
    return 0


def _generated() -> str:
    """Five words and a number. Long, and typable from a phone.

    A generated string of symbols gets written on paper beside the machine,
    which is a worse outcome than a passphrase somebody can remember for the
    length of a working day.
    """
    words = ("harbour", "lantern", "meadow", "cinder", "gallery", "thistle",
             "quarry", "ember", "current", "marble", "ridge", "willow",
             "beacon", "hollow", "pigment", "trellis", "anchor", "vellum")
    return "-".join(secrets.choice(words) for _ in range(5)) + \
        f"-{secrets.randbelow(90) + 10}"


if __name__ == "__main__":
    raise SystemExit(main())
