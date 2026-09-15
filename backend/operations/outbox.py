"""Read the password-reset messages queued in this installation's local outbox.

    python backend/operations/outbox.py --email advocate@example.com

Implementation Plan F-A-03. Until a mail provider is approved and wired, a
"Forgot password" request writes its message -- with the reset link -- to a
sealed outbox on this machine instead of a mailbox. This is how the operator
running a controlled-local installation reads it and passes the link on.

Run by a person, never by the product. It prints a working reset link, so it
reads only the address it is asked for and prints nothing else.

THE OUTBOX IS OPENED THROUGH THE COMPOSITION ROOT, exactly as `enrol.py` opens
the directory: which store, which key and which root are decided there once,
and a tool that worked them out for itself would be a second owner that
disagreed the day one of them moved.
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", required=True, help="the account email the link was sent to")
    ap.add_argument("--all", action="store_true",
                    help="print every queued message for the address, not only the newest")
    args = ap.parse_args()

    from nm.bootstrap.composition import Application

    outbox = Application().mail
    messages = outbox.messages_for(args.email)
    unreadable = outbox.unreadable()
    if not messages:
        # NOT "no messages". A request for an unknown address queues nothing,
        # and so does a message sealed under a key this installation no longer has.
        print(f"no readable message is queued for {args.email}"
              + (f"; {unreadable} message(s) could not be opened with this key"
                 if unreadable else ""))
        return 1
    for message in (messages if args.all else messages[-1:]):
        print(f"queued {message.get('queued_at')}  to {message.get('to')}")
        print(f"subject: {message.get('subject')}")
        print()
        print(message.get("text", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
