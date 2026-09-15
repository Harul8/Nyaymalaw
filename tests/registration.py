"""What a registration from the register card carries besides the account details.

Implementation Plan F-A-09. The public registration route refuses an account
without the privacy consent the card collects, so every test that registers
through that route sends the same consent a person ticking both boxes sends.
Read from the domain's notice version, never retyped, so a new notice does not
leave the tests agreeing to the old one.
"""
from __future__ import annotations

from nm.domain.advocate import PRIVACY_NOTICE_VERSION

CONSENT = {"notice_version": PRIVACY_NOTICE_VERSION, "agreed": True, "adult": True}
