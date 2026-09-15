"""Account mail delivery. Implementation Plan F-A-03.

ONE METHOD, AND IT RAISES
---------------------------
`send` either hands the message to its channel or raises. It never returns a
value that could be read as "probably sent": a delivery channel that could not
run returning the shape of a clean result is the most repeated defect in this
codebase, and here it would tell an advocate who is locked out that a link is
on its way when nothing was queued.

Which channel is live is the composition root's business. This build admits
only an in-process outbox (`nm.adapters.mail.outbox`); a real mail provider is
an external recipient and the egress policy refuses it until it is approved.
"""
from __future__ import annotations

from typing import Protocol

from nm.domain.mail import MailMessage


class MailPort(Protocol):
    def send(self, message: MailMessage) -> None:
        """Queue one message on the channel, or raise. Never a silent drop."""
        ...
