"""Assembling and verifying a drafting package. BK-56-AC1/AC2/AC3, BK-92-AC3. P29.

`nm.domain.drafting` holds the record and the readiness rule; this holds the
decisions -- what goes in, what is checked against what, and what the served
export may say.

WHAT IS REUSED, AND WHY EACH ONE MATTERS
------------------------------------------
Nothing here re-answers a question the product already answers:

    quotations   `nm.core.research.quote_fidelity` (P21). *Are these the
                 source's words* has one owner, and it already distinguishes
                 VERBATIM from DIFFERS on a whitespace-only fold -- the
                 distinction that stops a paraphrase being reported as a
                 quotation.
    staleness    `nm.core.dependency` through `nm.core.reassessment` (P18/P28).
                 A second freshness answer would be the §4 defect on the
                 subject where two answers are most expensive.
    decisions    `nm.domain.advice_decision` (P27).
    advice       `nm.domain.advice.Recommendation` (P26).

VERIFICATION IS A PASS OVER CLAIMS, NOT A FLAG ON THE PACKAGE
---------------------------------------------------------------
`verify` returns a NEW brief whose claims carry `verified` where the source
actually bore them out, and it never sets `verified` on a claim it could not
check. An unchecked claim reads as unverified, which is its true state: the
alternative -- defaulting to verified and clearing the flag on failure -- makes
a source the product could not read look like one that agreed.
"""
from __future__ import annotations

from dataclasses import replace

from nm.core.research import QuoteState, quote_fidelity
from nm.domain.advice_decision import AdviceDecision
from nm.domain.drafting import (
    Claim,
    DrafterBrief,
    Provenance,
    refuse_filing_claim,
)
from nm.domain.text import blank, clean, snippet


def verify(brief: DrafterBrief, sources: dict[str, str]) -> DrafterBrief:
    """Check every quotation against the source it names. BK-56-AC3.

    `sources` maps a locator to the text actually held at it. A locator absent
    from the map is NOT a failure of the claim -- it is a source the product
    could not read, and the claim stays unverified with the reason. Treating an
    unreadable source as a mismatch would tell the advocate their citation is
    wrong when what is wrong is the retrieval.
    """
    def checked(claim: Claim) -> Claim:
        if blank(claim.quoted):
            return claim
        held = sources.get(claim.locator)
        if held is None:
            return replace(claim, verified=False)
        state = quote_fidelity(claim.quoted, held)
        return replace(claim, verified=state is QuoteState.VERBATIM)

    return replace(
        brief,
        material_facts=tuple(checked(c) for c in brief.material_facts),
        provisions=tuple(checked(c) for c in brief.provisions),
        authorities=tuple(checked(c) for c in brief.authorities),
        version=brief.version + 1)


def unverified_quotations(brief: DrafterBrief) -> tuple[str, ...]:
    """Every claim that quotes something and has not been borne out.

    Named individually because "3 unverified quotations" sends an advocate
    looking through the whole package for them.
    """
    return tuple(
        f"{snippet(c.text, 70)!r} quotes {snippet(c.quoted, 50)!r} at {c.locator or 'no locator'}"
        for c in brief.claims if not blank(c.quoted) and not c.verified)


def misused_provenance(brief: DrafterBrief) -> tuple[str, ...]:
    """Claims pleaded as fact that are not entitled to be. BK-56-AC3.

    THE DEFECT THIS NAMES is an inference rendered the way an established fact
    is rendered. It is invisible in the finished document -- both are just
    sentences -- and it is the first thing an opponent takes apart.
    """
    return tuple(
        f"{snippet(c.text, 70)!r} is {c.provenance.value} and sits among the material "
        f"facts, where it would be read as established"
        for c in brief.material_facts
        if not c.provenance.may_be_pleaded_as_fact)


def stale_against(brief: DrafterBrief, decisions: tuple[AdviceDecision, ...],
                  ) -> tuple[str, ...]:
    """Decisions the package rests on that are no longer current. BK-56-AC1.

    A package built on advice version 3 and read after a decision was
    superseded is a package about something the advocate can no longer see.
    """
    out: list[str] = []
    for decision in decisions:
        if not decision.is_current:
            out.append(
                f"decision {decision.decision_id} ({decision.disposition.value}) "
                f"was superseded by {decision.superseded_by}")
        elif (brief.advice_version and decision.advice_version
                and decision.advice_version != brief.advice_version):
            out.append(
                f"decision {decision.decision_id} was taken on advice "
                f"{decision.advice_version} and this package is built on "
                f"{brief.advice_version}")
    return tuple(out)


def export(brief: DrafterBrief) -> dict:
    """The reviewable, advocate-controlled export. BK-92-AC3.

    ONE ACCEPTED CONTENT VERSION, rendered once. The criterion asks for Word
    and PDF *from the same accepted content version with rendered-byte
    parity*; what is built here is that single accepted version and the digest
    that any renderer must reproduce. The renderers themselves are NOT built,
    and `renditions` says so rather than shipping a stub whose parity check
    would pass over nothing.

    IT CARRIES NO DISPATCH AUTHORITY, and says so in the payload. BK-92-AC3
    ends with those words and CHOICE-09 is why: the connectors are disabled and
    the decision's `approval` field reads `None`.
    """
    from nm.core.research import digest_of

    body = "\n".join(
        f"[{c.provenance.value}] {c.text}"
        + (f" ({c.locator})" if c.locator else "")
        + ("" if c.verified or blank(c.quoted) else "  [QUOTATION UNVERIFIED]")
        for c in brief.claims)
    content_digest = digest_of(body)
    return {
        "package_id": brief.package_id,
        "version": brief.version,
        "readiness": brief.readiness().value,
        "content_digest": content_digest,
        "body": body,
        "problems": list(brief.problems()),
        "unverified_quotations": list(unverified_quotations(brief)),
        "misused_provenance": list(misused_provenance(brief)),
        "adverse": list(brief.adverse),
        "reservations": list(brief.reservations),
        "missing_instructions": list(brief.missing_instructions),
        "stale_dependencies": list(brief.stale_dependencies),
        "open_gaps": [dict(g) for g in brief.open_gaps],
        "blanks_permitted": brief.blanks_permitted,
        "lossless": brief.lossless,
        # NOT BUILT, AND NAMED AS NOT BUILT. A stub returning empty bytes would
        # satisfy a parity check between two things that do not exist.
        "renditions": {"docx": "not_built", "pdf": "not_built",
                       "parity": "not_assessed",
                       "why": "both renditions must render this exact "
                              "content_digest; no renderer is built, so parity "
                              "is not assessed rather than assumed"},
        "dispatch_authority": False,
        "filing_note": refuse_filing_claim(brief),
    }


def as_dict(brief: DrafterBrief) -> dict:
    def claim(c: Claim) -> dict:
        return {"text": c.text, "provenance": c.provenance.value,
                "source_id": c.source_id, "locator": c.locator,
                "source_version": c.source_version, "quoted": c.quoted,
                "verified": c.verified, "why_unresolved": c.why_unresolved}

    return {
        "schema": 1, "package_id": brief.package_id,
        "matter_id": brief.matter_id, "document": brief.document,
        "audience": brief.audience, "purpose": brief.purpose,
        "posture": brief.posture, "cause_title": dict(brief.cause_title),
        "theory_sentence": brief.theory_sentence,
        "material_facts": [claim(c) for c in brief.material_facts],
        "provisions": [claim(c) for c in brief.provisions],
        "limitation": dict(brief.limitation),
        "reliefs": list(brief.reliefs),
        "authorities": [claim(c) for c in brief.authorities],
        "proof_positions": list(brief.proof_positions),
        "facts_not_to_plead": [dict(x) for x in brief.facts_not_to_plead],
        "arguments_parked": [dict(x) for x in brief.arguments_parked],
        "open_gaps": [dict(x) for x in brief.open_gaps],
        "blanks_permitted": brief.blanks_permitted,
        "lossless": brief.lossless, "adverse": list(brief.adverse),
        "reservations": list(brief.reservations),
        "missing_instructions": list(brief.missing_instructions),
        "stale_dependencies": list(brief.stale_dependencies),
        "advice_version": brief.advice_version, "version": brief.version,
    }


def _claims(rows) -> tuple[Claim, ...]:
    out = []
    for r in rows or ():
        if not isinstance(r, dict):
            continue
        try:
            prov = Provenance(r.get("provenance"))
        except ValueError:
            # AN UNREADABLE PROVENANCE FALLS TO THE KIND THAT CLAIMS LEAST.
            # Falling to ESTABLISHED_FACT would let a corrupt row plead as
            # fact something nobody established.
            prov = Provenance.UNRESOLVED_GAP
        out.append(Claim(
            text=str(r.get("text") or "?"), provenance=prov,
            source_id=str(r.get("source_id") or ""),
            locator=str(r.get("locator") or ""),
            source_version=str(r.get("source_version") or ""),
            quoted=str(r.get("quoted") or ""),
            verified=bool(r.get("verified")),
            why_unresolved=str(r.get("why_unresolved") or "")))
    return tuple(out)


def from_dict(value: dict) -> DrafterBrief:
    return DrafterBrief(
        package_id=clean(str(value.get("package_id") or "?")),
        matter_id=clean(str(value.get("matter_id") or "?")),
        document=str(value.get("document") or ""),
        audience=str(value.get("audience") or ""),
        purpose=str(value.get("purpose") or ""),
        posture=str(value.get("posture") or ""),
        cause_title=dict(value.get("cause_title") or {}),
        theory_sentence=str(value.get("theory_sentence") or ""),
        material_facts=_claims(value.get("material_facts")),
        provisions=_claims(value.get("provisions")),
        limitation=dict(value.get("limitation") or {}),
        reliefs=tuple(str(r) for r in (value.get("reliefs") or ())),
        authorities=_claims(value.get("authorities")),
        proof_positions=tuple(str(r) for r in (value.get("proof_positions") or ())),
        facts_not_to_plead=tuple(
            dict(x) for x in (value.get("facts_not_to_plead") or ())
            if isinstance(x, dict)),
        arguments_parked=tuple(
            dict(x) for x in (value.get("arguments_parked") or ())
            if isinstance(x, dict)),
        open_gaps=tuple(dict(x) for x in (value.get("open_gaps") or ()) if isinstance(x, dict)),
        blanks_permitted=bool(value.get("blanks_permitted", True)),
        lossless=bool(value.get("lossless")),
        adverse=tuple(str(x) for x in (value.get("adverse") or ())),
        reservations=tuple(str(x) for x in (value.get("reservations") or ())),
        missing_instructions=tuple(str(x) for x in (value.get("missing_instructions") or ())),
        stale_dependencies=tuple(str(x) for x in (value.get("stale_dependencies") or ())),
        advice_version=str(value.get("advice_version") or ""),
        version=int(value.get("version") or 1))


def rows(matter) -> tuple[DrafterBrief, ...]:
    return tuple(from_dict(r) for r in (getattr(matter, "drafting_packages", ()) or ())
                 if isinstance(r, dict))


def put(existing: tuple[DrafterBrief, ...],
        brief: DrafterBrief) -> tuple[DrafterBrief, ...]:
    return tuple(b for b in existing if b.package_id != brief.package_id) + (brief,)


def find(existing: tuple[DrafterBrief, ...], package_id: str) -> DrafterBrief | None:
    for b in existing:
        if b.package_id == package_id:
            return b
    return None


def projection(brief: DrafterBrief) -> dict:
    """What the advocate is served. The problems travel WITH the package."""
    return {
        "package_id": brief.package_id, "document": brief.document,
        "audience": brief.audience, "purpose": brief.purpose,
        "posture": brief.posture, "version": brief.version,
        "readiness": brief.readiness().value,
        "problems": list(brief.problems()),
        "claims": [{"text": c.text, "provenance": c.provenance.value,
                    "locator": c.locator or "not established",
                    "verified": c.verified,
                    "may_be_pleaded_as_fact": c.provenance.may_be_pleaded_as_fact}
                   for c in brief.claims],
        "adverse": list(brief.adverse),
        "reservations": list(brief.reservations),
        "missing_instructions": list(brief.missing_instructions),
        "stale_dependencies": list(brief.stale_dependencies),
        "open_gaps": [dict(g) for g in brief.open_gaps],
        "dispatch_authority": False,
        "filing_note": refuse_filing_claim(brief),
    }

