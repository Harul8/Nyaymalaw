"""Owner-approved OpenAI text route, narrowed by each authenticated advocate.

The inventory alone still cannot approve external processing. This explicitly
records the owner's 2026-09-21 exception to the India-local product policy;
BK-85-AC3 remains open. User acceptance is neither client authority nor counsel
review. No raw-media, embeddings, telemetry or alternative endpoint is admitted.
"""
from __future__ import annotations

from datetime import datetime, timezone

from nm.domain.egress import DataClass, Policy, ProcessingException, Processor, Sink
from nm.domain.external_ai import NOTICE_VERSION, PROVIDER, ModelPermissionRefused

OWNER_BASIS = "OWNER-2026-09-21-GLOBAL-OPENAI-TEXT-NOT-COUNSEL-CLEARANCE"


def text_policy() -> Policy:
    return Policy(
        processors=(Processor(PROVIDER, "global", (Sink.MODEL,),
                              (DataClass.CLIENT_MATTER,), OWNER_BASIS),),
        processing_exceptions=(ProcessingException(
            PROVIDER, "global", Sink.MODEL, (DataClass.CLIENT_MATTER,), OWNER_BASIS),))


def require_permission(directory, account_id: str, config) -> None:
    # Closed endpoint contract. No URL guessed from a provider's display name.
    if any(row.provider != PROVIDER or (row.base_url or "https://api.openai.com/v1")
           not in {"https://api.openai.com/v1", "https://api.openai.com/v1/"}
           for row in config.tiers.values()):
        raise ModelPermissionRefused("AI sharing permits only the direct OpenAI API endpoint.")
    try:
        permission = directory.model_permission(account_id)
    except Exception as exc:  # noqa: BLE001 -- unreadable authority is not permission
        raise ModelPermissionRefused(
            "AI data-sharing permission could not be verified. "
            "No further request was sent.") from exc
    if permission is None or not permission.permits(account_id, datetime.now(timezone.utc)):
        raise ModelPermissionRefused(
            "Open AI data sharing in your profile to review and accept OpenAI text processing. "
            "Your workspace and matters remain available.")
    if permission.notice_version != NOTICE_VERSION:
        raise ModelPermissionRefused("Read the current AI data-sharing notice before continuing.")
