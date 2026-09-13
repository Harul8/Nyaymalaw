"""The adaptive lead runtime: choose and revise the investigation. P46.

    from nm.core.lead import classify, assess_support, observe_source_change,
                             propose, readiness, dispatch, integrate_result

BK-91-AC1 (choose and revise evidence-driven next actions within the mandate; no
fixed cognitive sequence, no self-expanded authority) and BK-91-AC2 (claims stay
attributed and version-linked; unsupported material conclusions are refused;
affected work is invalidated when a source, instruction or permission changes).

WHY THERE IS NO CHECKLIST HERE
--------------------------------
`propose` reads the STATE -- open needs, the epistemic status of each claim, the
side we act for -- and returns the next action that state calls for. It does not
walk a fixed list of legal steps, because AUTO-01 forbids a fixed scenario
router: a matter with an open unknown needs retrieval, a matter with an
unassessed extract needs assessment, a matter with everything supported needs a
draft or a stop, and which one is next is a function of the file, not of a
hardcoded order. Change the side we act for and the adverse claims flip, so the
proposal changes -- a reasoned difference, not narrative drift.

THE LEAD PROPOSES; THE APPLICATION ADMITS AND ACCEPTS
-------------------------------------------------------
`dispatch` and `integrate_result` are the ONLY doors to a specialist, and both
go through P47 (`nm.core.delegation`): admission narrows the child mandate and
reserves the shared budget, and acceptance is the one version-checked path that
refuses stale, revoked, cancelled or forged results. The lead never writes
canonical state and never grants itself authority; it hands candidates to that
path. This is also where P47's admission and acceptance get their production
caller.

INVALIDATION IS THE HEART OF AC2
----------------------------------
`observe_source_change` bumps the snapshot and reverts every claim resting on the
changed source from SUPPORTED back to its evidential base -- support was assessed
against a version, and a new version has not been assessed. A plan that read
`completed` cannot stay so once a premise it rested on has moved; `readiness`
derives completion and returns it to open. Nothing invents a fact to fill the
gap: `classify` never yields SUPPORTED, and only an assessment against a current
version promotes a claim.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from nm.core import delegation
from nm.domain.lead import Action, Claim, EpistemicStatus, Plan, StepProposal
from nm.domain.text import refuses_blank_text, snippet


def classify(claim_id: str, statement: str, source_id: str, source_version: int,
             *, asserted_by_party: bool = True, locator: str = "",
             subject: str = "", asserted_by: str = "") -> Claim:
    """A source becomes a claim -- an ALLEGATION where a party asserts it, an
    EXTRACTED where text is merely present. NEVER a SUPPORTED claim: a source
    existing, quoted or located does not establish that it means what it is cited
    for (autonomy.json `semantic_support`)."""
    status = (EpistemicStatus.ALLEGATION if asserted_by_party
              else EpistemicStatus.EXTRACTED)
    return Claim(id=claim_id, statement=statement, status=status,
                 source_id=source_id, source_version=source_version,
                 locator=locator, subject=subject, asserted_by=asserted_by)


def mark_disputes(claims: tuple[Claim, ...]) -> tuple[Claim, ...]:
    """Two claims on the same SUBJECT that assert different statements are both
    DISPUTED -- set arithmetic on the subject, not prose comparison. A supported
    claim is not demoted by a bare allegation against it; only unassessed claims
    move to DISPUTED, so a dispute is a question still open, not a finding."""
    by_subject: dict[str, list[Claim]] = {}
    for c in claims:
        if c.subject:
            by_subject.setdefault(c.subject, []).append(c)
    disputed_ids: set[str] = set()
    for group in by_subject.values():
        statements = {c.statement for c in group}
        if len(statements) > 1:
            for c in group:
                if c.status in (EpistemicStatus.ALLEGATION,
                                EpistemicStatus.EXTRACTED):
                    disputed_ids.add(c.id)
    return tuple(replace(c, status=EpistemicStatus.DISPUTED)
                 if c.id in disputed_ids else c for c in claims)


def assess_support(claim: Claim, *, supported: bool, snapshot: dict) -> Claim:
    """Promote a claim to SUPPORTED, but ONLY from an assessment AND against the
    current source version. A stale version is not promoted -- support against
    an old version is not support of what the file now holds. Provenance is kept
    whichever way it goes."""
    if (supported and claim.source_version > 0 and claim.is_current(snapshot)):
        return replace(claim, status=EpistemicStatus.SUPPORTED)
    return claim


def infer(claim_id: str, statement: str, *, from_source: str = "reasoning",
          subject: str = "") -> Claim:
    """A hypothesis the product formed. Labelled INFERENCE, never SUPPORTED --
    `model_knowledge: investigation_hypothesis_not_evidence`. It carries no
    source version because it rests on none."""
    return Claim(id=claim_id, statement=statement,
                 status=EpistemicStatus.INFERENCE, source_id=from_source,
                 source_version=0, subject=subject)


def observe_source_change(plan: Plan, source_id: str, new_version: int) -> Plan:
    """A source moved. Bump the snapshot, revert every claim resting on it from
    SUPPORTED back to EXTRACTED (its assessed status no longer holds against the
    new version), raise a recheck need, and un-complete the plan. This is the
    invalidation AC2 requires and the reconsideration AC1's negative control
    plants -- affected work is reopened, unaffected work is left alone."""
    touched = False
    new_claims = []
    for c in plan.claims:
        if c.source_id == source_id and c.status is EpistemicStatus.SUPPORTED:
            new_claims.append(replace(c, status=EpistemicStatus.EXTRACTED))
            touched = True
        else:
            new_claims.append(c)
    needs = list(plan.open_needs)
    if touched:
        need = f"re-assess claims resting on {source_id} at version {new_version}"
        if need not in needs:
            needs.append(need)
    return replace(plan, snapshot_version=plan.snapshot_version + 1,
                   claims=tuple(new_claims), open_needs=tuple(needs),
                   completed=plan.completed and not touched)


def recheck(claim: Claim, snapshot: dict) -> Claim:
    """A SUPPORTED claim that is no longer current reverts to EXTRACTED before it
    can be relied on -- the recheck-on-change AC2 requires at the point of
    acceptance or publication. Provenance is retained; only the status falls."""
    if claim.status is EpistemicStatus.SUPPORTED and not claim.is_current(snapshot):
        return replace(claim, status=EpistemicStatus.EXTRACTED)
    return claim


@refuses_blank_text()
@dataclass(frozen=True)
class Readiness:
    """Whether the objective can be reported met. Four states, and the escape is
    a value: `open` (work remains), `blocked` (a controlling need cannot be
    met), `escalate` (authority is insufficient), `useful` (met).

    Both fields carry content always: a readiness with no state says nothing,
    and one with no `why` is the silent verdict this product refuses."""

    state: str
    why: str
    open_predicates: tuple[str, ...] = ()


def readiness(plan: Plan, *, controlling_needs: tuple[str, ...] = (),
              unavailable: tuple[str, ...] = (), authority_permits: bool = True
              ) -> Readiness:
    """Derive completion. NEVER read from a flag the agent set: a plan is useful
    only when nothing is open, no controlling need is unmet, every conclusion is
    SUPPORTED, and authority permits the outcome. A controlling need that is
    unavailable is `blocked`, not quietly complete."""
    blocked = [n for n in controlling_needs if n in set(unavailable)]
    if blocked:
        return Readiness("blocked", "a controlling need is unavailable: "
                         + "; ".join(blocked), tuple(plan.open_needs))
    if plan.open_needs:
        return Readiness("open", "work remains", tuple(plan.open_needs))
    unmet = [n for n in controlling_needs
             if n not in {c.subject for c in plan.conclusions()}]
    if unmet:
        return Readiness("open", "a controlling need has no supported "
                         "conclusion: " + "; ".join(unmet), tuple(unmet))
    if not authority_permits:
        return Readiness("escalate",
                         "the outcome exceeds the recorded authority", ())
    return Readiness("useful", "the objective is met on supported conclusions", ())


def wants_specialist(need: str, *, parallelisable: bool, budget_units: float,
                     direct_reach: bool) -> bool:
    """Delegate ONLY when a bounded specialist adds value: the need is a
    separable investigation, the budget affords it, and the lead cannot as
    easily reach it directly. Ordinary work uses no specialist -- direct reach
    is the default, and delegation is the exception it must earn."""
    return parallelisable and budget_units > 0 and not direct_reach


def propose(plan: Plan, *, side: str = "", opposing_party: str = "",
            objective: str = "", wants_draft: bool = False) -> StepProposal:
    """The next action the STATE calls for -- not a step in a fixed sequence.

    Priority is over the file, not over a checklist: an open need is retrieved or
    asked; an unassessed material extract is assessed; a dispute is challenged on
    the claim ADVERSE to the side we act for (so the proposal differs by side); a
    fully supported file with nothing open is drafted or stopped. The lead
    proposes within the mandate; admission is the application's.
    """
    v = plan.snapshot_version
    if plan.open_needs:
        need = plan.open_needs[0]
        return StepProposal(
            action=Action.ASK if need.lower().startswith("ask") else Action.RETRIEVE,
            objective=objective or f"resolve: {need}", snapshot_version=v,
            rationale=f"an open need remains: {need}",
            open_predicates=tuple(plan.open_needs))

    unassessed = [c for c in plan.claims
                  if c.status in (EpistemicStatus.EXTRACTED,
                                  EpistemicStatus.ALLEGATION)]
    disputed = [c for c in plan.claims if c.status is EpistemicStatus.DISPUTED]

    if disputed:
        # ADVERSE TO US = asserted by the opposing party. Change side and the
        # target flips -- a reasoned different assessment, not drift.
        target = next((c for c in disputed if c.asserted_by
                       and c.asserted_by == opposing_party), disputed[0])
        return StepProposal(
            action=Action.CHALLENGE,
            objective=objective or f"test the disputed claim {target.subject!r}",
            snapshot_version=v,
            rationale=(f"the claim on {target.subject!r} is disputed and, "
                       f"asserted by {target.asserted_by or 'a party'}, is "
                       f"adverse to the {side or 'unresolved'} side"),
            evidence_refs=(target.id,),
            open_predicates=(target.subject,))

    if unassessed:
        c = unassessed[0]
        about = c.subject or snippet(c.statement, 40)
        return StepProposal(
            action=Action.ASSESS,
            objective=objective or f"assess whether the source supports {about!r}",
            snapshot_version=v,
            rationale="a material claim rests on an extract that has not been "
                      "assessed for semantic support",
            evidence_refs=(c.id,),
            open_predicates=(c.subject or c.id,))

    if wants_draft:
        return StepProposal(
            action=Action.DRAFT, objective=objective or "prepare a draft from "
            "the accepted, supported conclusions", snapshot_version=v,
            rationale="every conclusion is supported and current; a draft can be "
                      "prepared from the accepted version")
    return StepProposal(
        action=Action.STOP,
        objective=objective or "report the supported conclusions and stop",
        snapshot_version=v,
        rationale="the objective is met on supported conclusions and nothing is "
                  "open")


def dispatch(parent_mandate, request_task, server_mandate, ledger,
             *, specialists_may_delegate: bool = False):
    """Propose a specialist to the P47 admission boundary. The lead does not
    admit -- it asks, and the application narrows and reserves or refuses. This
    is P47's production caller for admission."""
    return delegation.admit(parent_mandate, request_task, server_mandate, ledger,
                            specialists_may_delegate=specialists_may_delegate)


def integrate_result(plan: Plan, result, task, *, current_mandate_version: int,
                     revoked_epochs=frozenset(), cancelled: bool = False,
                     ledger=None):
    """Take a specialist result through the P47 acceptance path and fold accepted
    candidates into the plan as EXTRACTED claims -- candidates, never SUPPORTED,
    because a specialist's finding is evidence to assess, not a conclusion to
    trust. A refused (stale/forged/revoked/cancelled) result changes nothing.
    Returns (plan, acceptance). This is P47's production caller for acceptance.
    """
    prior = tuple(c for c in plan.claims if c.subject)
    prior_findings = tuple(
        delegation.Finding(claim=c.statement, source_locator=c.locator or c.id,
                           source_version=str(c.source_version), subject=c.subject)
        for c in prior)
    acceptance = delegation.accept(
        result, task, current_mandate_version=current_mandate_version,
        revoked_epochs=revoked_epochs, cancelled=cancelled, ledger=ledger,
        prior_findings=prior_findings)
    if not acceptance.accepted or acceptance.duplicate:
        return plan, acceptance
    new_claims = list(plan.claims)
    existing_subjects = {c.subject for c in plan.claims if c.subject}
    for finding in acceptance.candidates:
        if finding.subject and finding.subject in existing_subjects:
            continue
        new_claims.append(Claim(
            id=f"{task.task_id}:{finding.source_locator}",
            statement=finding.claim, status=EpistemicStatus.EXTRACTED,
            source_id=finding.source_locator,
            source_version=int(finding.source_version or 0) or 1,
            subject=finding.subject))
    needs = list(plan.open_needs)
    if acceptance.incomplete:
        need = f"a delegated specialist result was incomplete ({task.role.value})"
        if need not in needs:
            needs.append(need)
    revised = replace(plan, claims=tuple(new_claims), open_needs=tuple(needs),
                      completed=plan.completed and not acceptance.incomplete)
    return revised, acceptance
