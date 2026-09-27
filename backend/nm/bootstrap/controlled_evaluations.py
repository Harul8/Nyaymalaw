"""Installation-owned, expiring evaluation grants; HTTP cannot author approvals.

This is a private engineering transport, not the normal-client cutover. The
grant, identities, limits and reviewer come from trusted composition. Account
permission and session currency remain necessary at every model dispatch.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from nm.core.controlled_brain import EvaluationScope
from nm.core.interaction_review import COMMUNICATION_PROTOCOL_VERSIONS
from nm.domain.loop import LoopLimits
from nm.ports.model import Tier
from nm.ports.store import StaleWrite


class EvaluationUnavailable(PermissionError):
    """No current, finite installation grant admits this private work."""


@dataclass(frozen=True)
class ControlledEvaluation:
    scope: EvaluationScope
    limits: LoopLimits
    expires_at: datetime
    source_version: str
    table_version: str
    cost_ceiling: Callable[[int, int, Tier], float]
    reviewer_factory: Callable
    max_repairs: int = 2
    review_interactions: bool = False
    author_factory: Callable | None = None
    permission_current: Callable | None = None
    interaction_protocol_version: int = 1

    def __post_init__(self):
        if not isinstance(self.scope, EvaluationScope) or not isinstance(self.limits, LoopLimits):
            raise ValueError("A private evaluation needs a typed finite grant and limits")
        if (not isinstance(self.expires_at, datetime)
                or self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None):
            raise ValueError("An evaluation approval must expire at an aware instant")
        if any(not isinstance(value, str) or not value.strip()
               for value in (self.source_version, self.table_version)):
            raise ValueError("An evaluation needs exact source and practice-table identities")
        if (type(self.max_repairs) is not int or not 0 <= self.max_repairs <= 10
                or type(self.interaction_protocol_version) is not int
                or self.interaction_protocol_version not in COMMUNICATION_PROTOCOL_VERSIONS
                or type(self.review_interactions) is not bool
                or self.author_factory is not None and not callable(self.author_factory)
                or self.permission_current is not None and not callable(self.permission_current)
                or self.author_factory is not None and self.permission_current is None
                or not callable(self.cost_ceiling) or not callable(self.reviewer_factory)):
            raise ValueError("An evaluation needs bounded repairs and trusted reviewer composition")


def grant_for(grants, *, actor: str, matter_id: str, now: datetime) -> ControlledEvaluation:
    if not isinstance(grants, tuple) or any(not isinstance(row, ControlledEvaluation)
                                          for row in grants):
        raise EvaluationUnavailable("Private evaluation is not configured")
    matches = [row for row in grants
               if row.scope.advocate_id == actor and matter_id in row.scope.matter_ids]
    if len(matches) != 1 or now >= matches[0].expires_at:
        raise EvaluationUnavailable("No unique current approval admits this private work")
    return matches[0]


def _current_admission(application, *, actor, matter_id, session_current, now):
    grant = grant_for(application.controlled_evaluations, actor=actor,
                      matter_id=matter_id, now=now())

    def current():
        try:
            admitted = grant_for(application.controlled_evaluations, actor=actor,
                                 matter_id=matter_id, now=now())
        except EvaluationUnavailable:
            return False
        if admitted is not grant or session_current() is not True:
            return False
        if grant.permission_current is not None:
            return grant.permission_current(application, grant.scope) is True
        # Reuse the actual installation's permission owner on late reads too.
        # A scripted local adapter remains a legitimate offline control.
        from nm.domain.external_ai import ModelPermissionRefused

        try:
            application._model_for(actor, session_current=session_current)
        except ModelPermissionRefused:
            return False
        return True

    if not current():
        raise EvaluationUnavailable("The session or approval no longer permits this work")
    return grant, current


def evaluate(application, *, actor: str, matter_id: str, expected_version: int,
             turn_id: str, message: str, selected_issue_ids: tuple[str, ...],
             session_current: Callable[[], bool], now: Callable[[], datetime]):
    grant, current = _current_admission(application, actor=actor, matter_id=matter_id,
                                        session_current=session_current, now=now)
    matter = application.store.load(matter_id)
    if matter is None or matter.advocate_id != actor:
        raise EvaluationUnavailable("The controlled file is unavailable")
    if type(expected_version) is not int or matter.version != expected_version:
        raise StaleWrite("The checked file changed before the private evaluation")
    brain = application.controlled_brain_for(
        grant.scope, session_current=current, cost_ceiling=grant.cost_ceiling,
        source_version=grant.source_version, table_version=grant.table_version,
        reviewer=grant.reviewer_factory(application, grant.scope, current),
        review_interactions=grant.review_interactions,
        interaction_protocol_version=grant.interaction_protocol_version,
        controlled_model=grant.author_factory(application, grant.scope, current)
            if grant.author_factory is not None else None)
    current_matter = application.store.load(matter_id)
    if current_matter is None or current_matter.version != expected_version:
        raise StaleWrite("The checked file changed during private evaluation admission")
    return brain.evaluate(matter_id=matter_id, turn_id=turn_id, message=message,
        selected_issue_ids=selected_issue_ids, limits=grant.limits,
        max_repairs=grant.max_repairs, cancelled=lambda: not current())


def _preview_service(application, *, actor: str, matter_id: str,
                     session_current: Callable[[], bool], now: Callable[[], datetime]):
    """One admission owner for reading and acknowledging the exact private view."""
    from nm.core.reviewed_preview import ReviewedPreviewService
    from nm.domain.loop import LoopMode

    grant, current = _current_admission(application, actor=actor, matter_id=matter_id,
                                        session_current=session_current, now=now)
    if grant.scope.mode is not LoopMode.SYNTHETIC:
        raise EvaluationUnavailable("Only the approved fictional population has a preview")
    matter = application.store.load(matter_id)
    if matter is None or matter.advocate_id != actor:
        raise EvaluationUnavailable("The controlled file is unavailable")
    brain = application.controlled_brain_for(
        grant.scope, session_current=current, cost_ceiling=grant.cost_ceiling,
        source_version=grant.source_version, table_version=grant.table_version,
        reviewer=grant.reviewer_factory(application, grant.scope, current),
        review_interactions=grant.review_interactions,
        interaction_protocol_version=grant.interaction_protocol_version,
        controlled_model=grant.author_factory(application, grant.scope, current)
            if grant.author_factory is not None else None)
    return ReviewedPreviewService(brain=brain, current=current)


def reviewed_preview(application, *, actor: str, matter_id: str, turn_id: str,
                     session_current: Callable[[], bool], now: Callable[[], datetime]):
    """The same expiring grant admits a read; it starts no model or paid check."""
    return _preview_service(application, actor=actor, matter_id=matter_id,
        session_current=session_current, now=now).read(
            actor=actor, matter_id=matter_id, turn_id=turn_id)


def record_preview_seen(application, *, actor: str, matter_id: str, turn_id: str,
                        session_current: Callable[[], bool], now: Callable[[], datetime]):
    """Record checked rendering, not delivery of advice or human attention."""
    from nm.core.preview_seen import PreviewSeenService

    preview = _preview_service(application, actor=actor, matter_id=matter_id,
                               session_current=session_current, now=now)
    return PreviewSeenService(preview=preview, log=preview.brain.log).record(
        actor=actor, matter_id=matter_id, turn_id=turn_id)
