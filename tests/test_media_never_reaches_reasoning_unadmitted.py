"""MEDIA REACHES LEGAL REASONING ONLY AS AN ADMISSION. BK-69, GC-14.

Media intake is not built, and that is precisely when this has to land.
`plan.json` puts BK-69 at W0 as the FOUNDATION and BK-54's intake at W2, so the
boundary exists before the pipeline that must pass through it. A control
written after its subject is a control written around whatever the subject
already does.

THE RULE. Nothing in `nm/core` -- the layer that reasons -- may accept audio,
video, images, recordings or uploaded bytes. It may accept a
`MediaAdmission`: a typed record of what was taken in, for what purpose, on
whose authority, in what quarantine state, processed by whom, derived from
what. The bytes stay behind the boundary.

THE POPULATION IS EMPTY TODAY AND THIS TEST IS NOT VACUOUS
------------------------------------------------------------
Zero media-shaped entry points exist in `nm/core`, so a sweep asserting "none
of them is unguarded" would pass by having nothing to check -- the exact
failure this repository has now recorded against sweeps, journey phases, CSS
rules and its own linter. So the scanner is proved on PLANTED source in both
directions before the real population is read, and the emptiness is asserted
as a fact rather than enjoyed as a pass.

The day BK-54 adds intake, this fails until the parameter is an admission.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.class_a

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: What a media-shaped parameter looks like. Deliberately broad, and broad in
#: the direction that costs a false positive rather than a miss: a reviewer
#: told "this looks like media, wrap it" loses a minute, and a miss puts
#: unscanned bytes in front of legal reasoning.
MEDIA_WORDS = ("audio", "video", "image", "photo", "recording", "voice",
               "media", "upload", "attachment", "scan", "waveform",
               "frame", "clip")

#: The word that makes a name safe: it is the admission, not the material.
ADMITTED = ("admission", "admitted")

#: The layer that reasons. `nm/adapters` is where bytes legitimately live --
#: an adapter that decodes an upload is doing its job. The boundary is the
#: line between that and the code which draws legal conclusions.
REASONING = ("nm/core", "nm/domain", "nm/knowledge")

#: The boundary module itself. See the assertion in the sweep.
EXEMPT = frozenset({"nm/domain/media.py"})


def media_shaped_parameters(source: str) -> list[str]:
    """Every parameter in this source that carries media rather than a record.

    Reads the ANNOTATION as well as the name: `def read(x: bytes)` in a module
    about recordings is the same defect wearing a shorter name, and a
    parameter annotated `MediaAdmission` is safe whatever it is called.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:                     # pragma: no cover -- defensive
        return []

    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
            name = arg.arg.lower()
            annotation = ast.unparse(arg.annotation).lower() if arg.annotation \
                else ""
            if any(w in annotation for w in ADMITTED) or \
                    any(w in name for w in ADMITTED):
                continue                    # it is the record, not the bytes
            if any(w in name for w in MEDIA_WORDS) or \
                    any(w in annotation for w in MEDIA_WORDS):
                found.append(f"{node.name}({arg.arg}"
                             + (f": {ast.unparse(arg.annotation)}"
                                if arg.annotation else "") + ")")
    return found


def test_the_scanner_sees_media_reaching_a_reasoning_function():
    """THE POSITIVE CONTROL, and it runs FIRST.

    The real population is empty today. Without this, the sweep below would
    report a clean product for the same reason an empty registry reported a
    clean journey and an emptied sweep list reported a clean codebase.
    """
    for planted in (
        "def derive(audio_bytes): ...",
        "def derive(x: AudioClip): ...",
        "async def read_it(recording): ...",
        "def summarise(uploaded_image, thread): ...",
        "def frames(v: list[VideoFrame]): ...",
    ):
        assert media_shaped_parameters(planted), (
            f"the scanner did not see media in {planted!r}, so it reports a "
            f"clean product whether or not one exists")


def test_the_scanner_leaves_an_admission_alone():
    """THE NEGATIVE CONTROL. A rule that refuses the correct shape too is a
    rule that gets deleted the first time somebody builds intake properly."""
    for allowed in (
        "def derive(admission: MediaAdmission): ...",
        "def derive(audio_admission): ...",
        "def summarise(text: str, thread: ThreadId): ...",
        "def compute(days: int): ...",
    ):
        assert not media_shaped_parameters(allowed), (
            f"the scanner flagged {allowed!r}, which is the shape this rule "
            f"is asking for")


def test_no_reasoning_function_accepts_media():
    """THE SWEEP. Every module in the layers that draw legal conclusions."""
    files = [p for layer in REASONING
             for p in (ROOT / layer).rglob("*.py")
             if "__pycache__" not in p.parts
             and p.relative_to(ROOT).as_posix() not in EXEMPT]

    # ONE EXEMPTION, NAMED. The module that DEFINES the boundary necessarily
    # names the thing it bounds -- `admitted(media_id, kind)` is the
    # constructor, not a leak. It was caught by this sweep on its first run
    # against the real population, which is also the answer to whether an
    # empty population makes this vacuous: it does not, because the boundary
    # itself is in it.
    #
    # The list is asserted at length so a second file cannot join it quietly.
    assert len(EXEMPT) == 1, (
        f"the media sweep now exempts {sorted(EXEMPT)}. One exemption is the "
        f"boundary defining itself; a second is a hole with a comment.")
    assert len(files) > 30, (
        f"only {len(files)} modules found across {REASONING}, so this sweep "
        f"is reading a population too small to be the product")

    offenders: list[str] = []
    for path in files:
        for hit in media_shaped_parameters(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(ROOT)}: {hit}")

    assert not offenders, (
        "these draw legal conclusions and accept media rather than an "
        "admission:\n  " + "\n  ".join(offenders)
        + "\n\nMedia reaches reasoning as `nm.domain.media.MediaAdmission` -- "
          "what was taken in, for what purpose, on whose authority, in what "
          "quarantine state, processed by whom. The bytes stay behind the "
          "boundary. See BK-69.")


def test_the_boundary_refuses_what_it_says_it_refuses():
    """The type's own rule, in the three states that matter.

    Asserted here rather than only in the sweep because the sweep proves
    nothing CALLS it wrongly, and this proves it would refuse if something
    did -- two different claims, and only the pair is worth anything.
    """
    from nm.domain.media import MediaKind, Quarantine, admitted

    unchecked = admitted("m1", MediaKind.AUDIO, purpose="the account",
                         authority="the client",
                         quarantine=Quarantine.NOT_ASSESSED)
    ok, why = unchecked.may_reach_reasoning()
    assert not ok and "not been checked" in why, (
        "unchecked material read as admissible, which is the absent-input-"
        "reads-as-success shape aimed at privileged bytes")

    held = admitted("m2", MediaKind.VIDEO, purpose="the account",
                    authority="the client", quarantine=Quarantine.HELD)
    ok, why = held.may_reach_reasoning()
    assert not ok and "held" in why

    fine = admitted("m3", MediaKind.AUDIO, purpose="the account",
                    authority="the client", quarantine=Quarantine.RELEASED)
    assert fine.may_reach_reasoning()[0], (
        "a fully admitted recording was refused; a boundary nothing can cross "
        "is not a boundary, it is an outage waiting for BK-54")


def test_an_admission_cannot_be_built_without_purpose_or_authority():
    """REFUSED, NOT REPAIRED. A default here is a decision this function has
    no standing to make: 'the advocate' as an authority makes an unauthorised
    recording indistinguishable from an authorised one."""
    from nm.domain.media import MediaKind, Quarantine, admitted

    for kwargs, missing in (
        ({"media_id": "", "purpose": "p", "authority": "a"}, "identified"),
        ({"media_id": "m", "purpose": "  ", "authority": "a"}, "purpose"),
        ({"media_id": "m", "purpose": "p", "authority": ""}, "authority"),
    ):
        with pytest.raises(ValueError) as caught:
            admitted(kind=MediaKind.AUDIO, quarantine=Quarantine.RELEASED,
                     **kwargs)
        assert missing in str(caught.value).lower(), (
            f"the refusal for {kwargs} did not name what was missing")
