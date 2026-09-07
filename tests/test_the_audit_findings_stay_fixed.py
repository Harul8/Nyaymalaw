"""BK-14 to BK-19 — the forensic audit's findings, each with the check.

A fix without an invariant is a fix that lasts until the next person has a
reason. These are the rules, stated as rules rather than as the scenarios that
exposed them.
"""
from __future__ import annotations

import ast
import contextlib
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _sources():
    return [p for p in (ROOT / "nm").rglob("*.py")
            if "__pycache__" not in p.parts]


def _code(path: pathlib.Path) -> str:
    """A file with its comments and docstrings blanked.

    FOURTH INSTANCE OF THIS SHAPE TODAY. A comment quoting a z-index literal
    broke that check; a comment quoting `("18", "19")` broke the section-list
    check; a docstring naming a gate broke T9 (B-140); and both sweeps in this
    file failed on their OWN docstrings, which quote the very strings they
    refuse.

    ONE OWNER. `tools/trace.py` grew `_without_prose` for B-140 and this
    imports it rather than carrying a third copy -- §4, applied to the fix for
    the thing §4 keeps catching.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.trace import _without_prose

    return _without_prose(path.read_text(encoding="utf-8"))


# ==================== BK-14 — which day is it, and whose ==================

def test_the_forum_date_crosses_at_the_forums_midnight():
    """THE DEFECT, AS ARITHMETIC.

    A server keeping UTC is on the previous day from 18:30 UTC, which is
    midnight in India. Every limitation period computed in that window was a
    day short, and `expired(turn.today)` decides whether the salvage pass runs
    at all.
    """
    from nm.domain.clock import today

    # 18:29 UTC is still the 30th at the forum; 18:30 is the 1st.
    assert today(datetime(2026, 9, 30, 18, 29, tzinfo=timezone.utc)) == date(2026, 9, 30)
    assert today(datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)) == date(2026, 10, 1)
    assert today(datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)) == date(2026, 10, 1)


def test_nothing_in_the_product_asks_the_machine_what_day_it_is():
    """THE SWEEP. `date.today()` means "the date where this process happens to
    be running", which is not a fact about the matter.

    `nm/domain/clock.py` is the one place allowed to read a wall clock, and it
    reads it in UTC and converts."""
    offenders = []
    for path in _sources():
        if path.name == "clock.py":
            continue
        src = path.read_text(encoding="utf-8")
        for n, line in enumerate(src.splitlines(), 1):
            code = line.split("#", 1)[0]
            if "date.today()" in code or "datetime.today()" in code:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{n}")
    assert not offenders, (
        "these ask the machine what day it is instead of the forum:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse `nm.domain.clock.today()`. A server keeping UTC is a day "
          "behind India from 18:30 UTC, and a limitation date is the most "
          "consequential number this product produces.")


def test_the_clock_needs_no_timezone_database():
    """A FIXED OFFSET, DELIBERATELY. India is one zone at UTC+5:30 with no
    DST, so the offset is exact -- and `ZoneInfo` would depend on a system tz
    database that Windows does not ship, raising on some machines and working
    on others. A clock correct on the developer's laptop and raising in
    production is worse than no clock."""
    assert "ZoneInfo" not in _code(ROOT / "nm" / "domain" / "clock.py"), (
        "the clock depends on a system timezone database")
    from nm.domain.clock import IST
    assert IST.utcoffset(None) == timedelta(hours=5, minutes=30)


# ==================== BK-15 — one owner for the forum =====================

def test_the_jurisdiction_has_one_owner():
    """It was a literal default in six modules. CLAUDE.md supplies the failure
    mode: an answer about another state's law is confidently wrong and nothing
    downstream catches it, so a jurisdiction that can drift between the
    retrieval and the binding computation is S9 with a silent wrong answer."""
    offenders = []
    for path in _sources():
        if path.name == "clock.py":
            continue
        src = path.read_text(encoding="utf-8")
        for n, line in enumerate(src.splitlines(), 1):
            code = line.split("#", 1)[0]
            if '"Telangana"' in code or "'Telangana'" in code:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{n}")
    assert not offenders, (
        "the forum is written out instead of imported:\n  "
        + "\n  ".join(offenders) + "\n\nUse `nm.domain.clock.FORUM`.")


# ==================== BK-16 — the cipher does not downgrade ===============

def test_the_cipher_refuses_to_downgrade_without_being_told():
    """It fell back to `xor-keystream(NOT-SECURE)` on ImportError, silently.

    Honest -- the scheme was named and `/api/health` disclosed it -- and
    nothing REFUSED it, while both neighbouring degradations are hard
    failures: a missing key raises, and the authority index will not fall back
    to a scan with different recall.

    Keystream XOR under a key every matter shares is trivially broken: two
    ciphertexts XORed together cancel the keystream.
    """
    src = (ROOT / "nm" / "adapters" / "store" / "file_store.py").read_text(
        encoding="utf-8")
    body = src[src.index("except ImportError:"):src.index("def encrypt")]
    assert "raise EncryptionNotConfigured" in body, (
        "the cipher downgrades to a keystream XOR without refusing")
    assert "NM_ALLOW_INSECURE_CIPHER" in body, (
        "there is no named opt-in, so a developer without the wheel cannot "
        "run the suite -- and a guard that blocks ordinary work is one people "
        "delete")


def test_a_missing_key_is_still_a_hard_failure():
    """The rule that was already right, kept. An unset key must never become a
    silent no-op writing privileged client material in plaintext."""
    from nm.adapters.store.file_store import EncryptionNotConfigured, _Cipher

    with pytest.raises(EncryptionNotConfigured):
        _Cipher("")
    with pytest.raises(EncryptionNotConfigured):
        _Cipher("   ")


# ==================== BK-17 — guards survive `python -O` ==================

def test_no_guard_in_the_product_is_an_assert():
    """`python -O` DELETES EVERY ASSERT.

    All three in `nm/` were load-bearing: that `may_admit_substance` still
    refuses an unscreened matter, and both halves of `spoken.complete()`. The
    last two were written under a docstring promising a missing phrase is an
    ImportError rather than a surprise in a served turn -- false under `-O`,
    where it becomes a KeyError mid-turn.

    Asserts stay right in TESTS: nothing runs the suite under `-O`, and an
    assert there is the vocabulary of the thing.
    """
    offenders = []
    for path in _sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                offenders.append(
                    f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert not offenders, (
        "these are guards that `python -O` removes:\n  " + "\n  ".join(offenders)
        + "\n\nRaise instead. A check the interpreter can be asked to skip is "
          "S11 with a flag on it.")


def test_a_missing_phrase_raises_rather_than_asserts():
    """The promise, exercised. Not the absence of `assert` -- the presence of
    the failure it was standing in for."""
    from enum import Enum, nonmember

    from nm.domain.spoken import Spoken

    class _Gappy(Spoken, str, Enum):
        FINE = "fine"
        FORGOTTEN = "forgotten"
        SAID = nonmember({"fine": "fine"})

    with pytest.raises(ValueError, match="forgotten"):
        _Gappy.complete()


# ==================== BK-18 — the session cookie ==========================

def test_the_session_cookie_is_secure_when_the_connection_is():
    """It set `httponly` and `samesite` and not `secure`, and the comment
    beside it reasoned about the first two only -- overlooked, not decided.

    DERIVED FROM THE CONNECTION, not a flag. The first fix defaulted to
    `secure=True` with an env-var opt-out, and a secure cookie on a plain
    connection is DROPPED: six served-path tests went 401 and local
    development would have too. A default that needs a flag to work is one
    somebody sets permanently.
    """
    src = (ROOT / "nm" / "edge" / "api.py").read_text(encoding="utf-8")
    assert "secure=secure" in src, "the cookie no longer sets `secure` at all"
    assert 'request.url.scheme == "https"' in src, (
        "`secure` is no longer derived from the connection")
    assert "x-forwarded-proto" in src, (
        "a proxy terminating TLS would leave every cookie insecure")
    assert "NM_INSECURE_COOKIES" not in src, (
        "the env-var opt-out is back; it defaults to broken on http and is "
        "the setting somebody makes permanent")


# ==================== BK-19 — a missing count is not zero =================

def test_a_missing_index_count_is_none_and_not_zero():
    """`int(rows.get(key, 0))` made an identity missing `indexed_paragraphs`
    report ZERO INDEXED -- indistinguishable from an index built and holding
    nothing.

    CLAUDE.md's worked example is this shape: `table.get(kind, 0.0)` made
    every unlisted atom type score worse than every listed one.
    """
    src = _code(ROOT / "nm" / "adapters" / "search" / "authority.py")
    assert "rows.get(key, 0)" not in src, (
        "a missing count reads as zero again")
    assert "def num(key: str) -> int | None:" in src, (
        "`num` no longer distinguishes absent from zero")


# ==================== the positive controls ==============================
#
# `test_every_sweep_has_a_positive_control` caught all three sweeps above
# the moment they landed. A checker that always returns [] passes a sweep
# identically -- and one did, on every commit for weeks (B-049).
#
# ONE PLANTER, THREE PROBES. Three copies of write-then-unlink would be
# three chances to leave a probe module behind in `nm/`, where every other
# sweep in this suite would then trip over it.


@contextlib.contextmanager
def _planted(name: str, body: str):
    """A real module under `nm/`, removed however the block exits.

    UNDER `nm/` BECAUSE THAT IS WHERE THE SWEEPS LOOK. A fixture anywhere
    else would prove the matcher works, not that the walk reaches it.
    """
    path = ROOT / "nm" / "core" / ("_" + name + "_probe.py")
    path.write_text(body + chr(10), encoding="utf8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def test_the_assert_sweep_can_see_a_guard_it_would_delete():
    with _planted("assert", chr(10).join(('def f(x):', "    assert x, 'a guard'",))):
        with pytest.raises(AssertionError, match="_assert_probe"):
            test_no_guard_in_the_product_is_an_assert()


def test_the_clock_sweep_can_see_a_call_to_the_machine():
    body = chr(10).join((
        'from datetime import date', '', 'def when():',
        '    return date.today()',))
    with _planted("clock", body):
        with pytest.raises(AssertionError, match="_clock_probe"):
            test_nothing_in_the_product_asks_the_machine_what_day_it_is()


def test_the_forum_sweep_can_see_a_second_owner():
    with _planted("forum", chr(10).join(('WHERE = "Telangana"',))):
        with pytest.raises(AssertionError, match="_forum_probe"):
            test_the_jurisdiction_has_one_owner()
