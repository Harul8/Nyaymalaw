"""The local outbox: account mail sealed onto this installation's disk.
Implementation Plan F-A-03.

WHAT THIS IS, AND WHAT IT IS NOT
----------------------------------
It is where a password-reset message goes in a controlled-local installation.
It is NOT a mailbox, and nothing here pretends otherwise: `delivers_to_mailbox`
is `False`, `/api/health` reports it, and an operator reads a queued message
with `backend/operations/outbox.py`. A real mail provider is an external
recipient; this build's egress policy admits none until it is approved.

WHY SEALED
------------
A queued reset message holds a working reset link. An outbox in plaintext would
be a directory of ways into accounts, readable by anything that can read the
disk. Each message is sealed with the same cipher as the matters and the roster
(`_Cipher`, one owner of "how is data at rest sealed here"), and the filename
carries a timestamp and random suffix -- never the address.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from nm.adapters.store.file_store import _Cipher
from nm.domain.advocate import canonical_id
from nm.domain.mail import MailMessage
from nm.domain.traceability import implements


@implements("A1")
class FileOutbox:
    #: Read by `/api/health`. A queued message is not a delivered one.
    delivers_to_mailbox = False

    def __init__(self, root: str | Path, key: str | None = None) -> None:
        # Created at the first send, not here: composing an application that
        # never sends mail must not leave directories behind.
        self._outbox = Path(root) / "outbox"
        self._cipher = _Cipher(
            key if key is not None else os.environ.get("NM_MATTER_KEY", ""))

    def send(self, message: MailMessage) -> None:
        """Seal and write one message. Exclusive creation; raises on any failure."""
        if not isinstance(message, MailMessage):
            raise TypeError("the outbox accepts only MailMessage")
        queued_at = datetime.now(timezone.utc)
        payload = json.dumps({
            "to": message.to,
            "subject": message.subject,
            "text": message.text,
            "purpose": message.purpose,
            "queued_at": queued_at.isoformat(),
        }).encode("utf8")
        name = f"{queued_at.strftime('%Y%m%dT%H%M%S%f')}-{secrets.token_hex(8)}.nm"
        self._outbox.mkdir(parents=True, exist_ok=True)
        with (self._outbox / name).open("xb") as handle:
            handle.write(self._cipher.encrypt(payload))

    def messages_for(self, address: str) -> tuple[dict, ...]:
        """Every readable queued message for one address, oldest first.

        For the operator tool and tests. A message that will not open is
        skipped here and COUNTED by `unreadable()`, never silently lost.
        """
        wanted = canonical_id(address)
        found = []
        for path in sorted(self._outbox.glob("*.nm")):
            message = self._open(path)
            if message is not None and canonical_id(message.get("to")) == wanted:
                found.append(message)
        return tuple(found)

    def unreadable(self) -> int:
        return sum(1 for path in self._outbox.glob("*.nm") if self._open(path) is None)

    def _open(self, path: Path) -> dict | None:
        try:
            message = json.loads(self._cipher.decrypt(path.read_bytes()).decode("utf8"))
        except Exception:  # noqa: BLE001 -- counted by unreadable(), not dropped
            return None
        return message if isinstance(message, dict) else None
