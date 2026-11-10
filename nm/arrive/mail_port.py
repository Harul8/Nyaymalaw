"""Account mail delivery. Implementation Plan F-A-03.

ONE METHOD, AND IT RAISES
---------------------------
`send` either hands the message to its channel or raises. It never returns a
value that could be read as "probably sent": a delivery channel that could not
run returning the shape of a clean result is the most repeated defect in this
codebase, and here it would tell an advocate who is locked out that a link is
on its way when nothing was queued.

Which channel is live is the composition root's business: the sealed local
outbox (`nm.arrive.mail_outbox`) by default, or Gmail (`nm.arrive.mail_gmail`)
under the owner's exception for account mail (plan AN.48, D168), admitted by a
gate of its own. A channel that could not confirm it took the message raises
MailNotConfirmed (a local outbox that could not write raises OSError), and
every caller says so as a delivery failure - never as a programming error.
"""
from __future__ import annotations

from typing import Protocol

from nm.arrive.mail_contracts import MailMessage


class MailNotConfirmed(RuntimeError):
    """The channel did not confirm it took the message: refused, unreachable, its sign-in refused, or delivery disabled. Its
    words are content-free - never an address, a link, a code or a secret - and nothing is retried by itself."""


class MailPort(Protocol):
    def send(self, message: MailMessage) -> None:
        """Queue one message on the channel, or raise. Never a silent drop."""
        ...
