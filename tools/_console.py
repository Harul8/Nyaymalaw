"""The console these tools write to. ONE OWNER.

WHY
---
`tools/run_goldens.py --suite full` died halfway through its own report:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2194'

Windows gives a Python process a **cp1252** stdout. Ten of the twenty-five
golden scenarios never printed, because scenario sixteen's text contains an
arrow -- `IPC s.447 <-> BNS s.329` -- and the encoder raised on it.

A REPORT THAT DIES HALFWAY IS WORSE THAN ONE THAT DOES NOT RUN. It had already
printed fifteen rows, so it looked like a report; it exited non-zero, so it
looked like a verdict; and it was neither. Nothing in the output said the list
was cut short.

The docstrings in this repo are written in prose with en-dashes and arrows, and
every tool prints them. So this is not one scenario's problem: it is every
tool's, and it was latent in all fourteen. `tools/check.py` runs most of them
as subprocesses, which captures output through a different encoding path, which
is exactly why it stayed hidden until a tool was run directly.

WHY A SHARED FUNCTION AND NOT A LINE IN EACH TOOL
--------------------------------------------------
Because that is the defect this project keeps paying for -- 47 of 52 register
entries had a guard covering only the site the bug was found at. A line copied
into fourteen files is fourteen chances to differ and one guarantee that the
fifteenth tool will not have it.

`tools/__init__.py` cannot carry it: these are run as scripts
(`python tools/x.py`), so the package `__init__` is never imported. Each tool
calls this instead, and `tests/test_tooling_bites.py` fails the build when one
does not.
"""
from __future__ import annotations

import sys


def utf8_console() -> None:
    """Make stdout and stderr survive the prose this repo actually prints.

    `errors="replace"` and not `strict`: a tool whose job is to report a
    verdict must not lose the verdict over a dash. A replacement character is
    a legible defect; a truncated report is an invisible one.

    Safe to call more than once, and safe where the streams have been swapped
    for something that cannot be reconfigured -- pytest's capture, a pipe, a
    subprocess wrapper. Those cases are not failures and must not raise.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # NOT ASSESSED, and it does not matter here: the stream is already
            # something other than a raw console, which is the case that was
            # never broken.
            pass
