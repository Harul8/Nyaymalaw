"""Serve a finite, operator-attested fictional legal-brain evaluation only.

The operator supplies a private JSON record under ``.nm/evaluations``. It must
name the exact actor, matter IDs, owner approval, expiry, pinned models and a
separate fictional-only attestation for every matter. This launcher never
creates an approval, infers fictionality from a title, or changes normal-client
processing. ``--check`` validates locally without starting a server or model.

Example (no credential on the command line)::

    python development_environment/developer_tooling/launch_fictional_brain.py \
      --authorization .nm/evaluations/current-fictional-approval.json \
      --actor ACTUAL_ACCOUNT_ID --matter-id ACTUAL_MATTER_ID \
      --approval-reference OWNER-RECORDED-REFERENCE --check

Replace ``--check`` with ``--serve`` only after the local check succeeds. The
approval record's schema is exercised in the adjacent tests. Secrets remain in
the installation's ordinary local configuration and are never printed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import ssl
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".nm/evaluations/legal-brain-20260927-usd5.sqlite"
AUTHOR = "gpt-4o-mini-2024-07-18"
VERIFIER = "gpt-5.1-2025-11-13"
PURPOSE = "fictional_legal_brain_evaluation_no_client_release"
MAX_MATTERS = 60
MAX_USD = "5"
_FIELDS = frozenset({
    "schema", "approval_reference", "approved_at", "expires_at", "actor_id",
    "matter_ids", "matter_attestations", "maximum_matter_count",
    "maximum_total_usd", "author_model", "verifier_model",
    "interaction_protocol_version", "purpose",
})
_ATTESTATION_FIELDS = frozenset({"matter_id", "classification", "attested_by", "attested_at"})
_MATTER_ID = re.compile(r"(?:mat_[0-9a-f]{12}|m_[0-9a-f]{32})\Z", re.ASCII)


class ApprovalRefused(ValueError):
    """The trusted local record cannot admit this fictional evaluation."""


def _instant(value):
    if not isinstance(value, str):
        raise ApprovalRefused("The approval needs explicit UTC instants.")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ApprovalRefused("The approval has an invalid instant.") from exc
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        raise ApprovalRefused("The approval needs explicit UTC instants.")
    return instant


def _private_authorization(path: Path, *, root: Path) -> tuple[dict, str]:
    private = (root / ".nm" / "evaluations").resolve()
    target = path.resolve()
    if target.parent != private or target.suffix.lower() != ".json" or not target.is_file():
        raise ApprovalRefused("A private installation-owned approval file is required.")
    try:
        raw = target.read_bytes()
        record = json.loads(raw)
    except (OSError, ValueError, UnicodeError) as exc:
        raise ApprovalRefused("The private approval cannot be read and verified.") from exc
    if type(record) is not dict:
        raise ApprovalRefused("The private approval must be a closed record.")
    return record, hashlib.sha256(raw).hexdigest()


def _existing_ledger(path: Path, *, minimum_attempts: int = 1) -> int:
    """Never let CallBudget silently create/reset the owner's shared ledger."""
    if not path.is_file():
        raise ApprovalRefused("The original USD5 ledger is absent; no new ledger is authorised.")
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            row = db.execute("SELECT maximum FROM budget WHERE singleton=1").fetchone()
            rows = db.execute("SELECT charge,state,model FROM attempts").fetchall()
    except (OSError, sqlite3.Error) as exc:
        raise ApprovalRefused("The existing evaluation ledger cannot be verified.") from exc
    reservations = {AUTHOR: 30_000, VERIFIER: 550_000}
    if (row != (5_000_000,) or len(rows) < minimum_attempts
            or any(type(charge) is not int or charge < 0
                   or type(state) is not str or state not in {"measured", "reserved_or_unknown"}
                   or model not in reservations
                   or charge > reservations.get(model, -1)
                   or state == "reserved_or_unknown" and charge != reservations[model]
                   for charge, state, model in rows)
            or sum(charge for charge, _, _ in rows) > 5_000_000):
        raise ApprovalRefused("The original USD5 ledger is not within its approved bounds.")
    return len(rows)


def validate_authorization(record: dict, *, actor: str, matter_ids: tuple[str, ...],
                           approval_reference: str, application, ledger: Path,
                           now: datetime) -> datetime:
    """Fail closed on scope, matter ownership, attestations, consent and money."""
    from nm.app.model_permission import require_permission
    from nm.Archives.legal_brain.evaluate.evaluation_models import AUTHOR as CODE_AUTHOR
    from nm.Archives.legal_brain.evaluate.evaluation_models import VERIFIER as CODE_VERIFIER
    from nm.Archives.legal_brain.verify.interaction_review import COMMUNICATION_PROTOCOL_VERSIONS
    from nm.shared.model_config import ModelConfig, TierConfig
    from nm.shared.model_port import Tier

    if (type(record) is not dict or frozenset(record) != _FIELDS
            or record["schema"] != 2 or record["purpose"] != PURPOSE
            or record["maximum_matter_count"] != MAX_MATTERS
            or record["maximum_total_usd"] != MAX_USD
            or record["author_model"] != AUTHOR or AUTHOR != CODE_AUTHOR
            or record["verifier_model"] != VERIFIER or VERIFIER != CODE_VERIFIER):
        raise ApprovalRefused("The private approval has an unrecognised scope or model.")
    if (not isinstance(actor, str) or not actor.strip()
            or not isinstance(approval_reference, str) or not approval_reference.strip()
            or not matter_ids or len(matter_ids) > MAX_MATTERS
            or any(type(item) is not str or _MATTER_ID.fullmatch(item) is None
                   for item in matter_ids)
            or len(set(matter_ids)) != len(matter_ids)):
        raise ApprovalRefused("Exact actor, approval and finite matter IDs are required.")
    if (record["actor_id"] != actor
            or record["approval_reference"] != approval_reference
            or type(record["matter_ids"]) is not list
            or any(type(item) is not str or _MATTER_ID.fullmatch(item) is None
                   for item in record["matter_ids"])
            or set(record["matter_ids"]) != set(matter_ids)
            or len(record["matter_ids"]) != len(matter_ids)):
        raise ApprovalRefused("The supplied actor and matters do not match the owner approval.")
    approved = _instant(record["approved_at"])
    expires = _instant(record["expires_at"])
    if (now.tzinfo is None or now.utcoffset() is None
            or not approved <= now < expires
            or expires > approved + timedelta(hours=2)
            or expires > now + timedelta(hours=2)):
        raise ApprovalRefused("The finite owner approval is not current or exceeds two hours.")
    protocol = record["interaction_protocol_version"]
    if type(protocol) is not int or protocol not in COMMUNICATION_PROTOCOL_VERSIONS:
        raise ApprovalRefused("The interaction protocol is not an owned current version.")
    attestations = record["matter_attestations"]
    if (type(attestations) is not list or len(attestations) != len(matter_ids)
            or any(type(row) is not dict or frozenset(row) != _ATTESTATION_FIELDS
                   for row in attestations)):
        raise ApprovalRefused("Every approved matter needs its own closed attestation.")
    seen = set()
    for row in attestations:
        ident = row["matter_id"]
        if (ident not in matter_ids or ident in seen
                or row["classification"] != "fictional_only"
                or row["attested_by"] != actor
                or not approved <= _instant(row["attested_at"]) <= now):
            raise ApprovalRefused("A matter lacks a current, actor-owned fictional attestation.")
        seen.add(ident)
    for ident in matter_ids:
        matter = application.store.load(ident)
        if matter is None or matter.id != ident or matter.advocate_id != actor:
            raise ApprovalRefused("A matter is absent or does not belong to the approved actor.")
    _existing_ledger(ledger)
    # This checks the actual account record; neither the CLI nor the approval
    # document can supply consent. The served edge separately checks session
    # currency, and model binding repeats this check on each dispatch.
    config = ModelConfig({
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "openai", AUTHOR, None,
                                 "https://api.openai.com/v1"),
        Tier.JUDGE: TierConfig(Tier.JUDGE, "openai", VERIFIER, None,
                               "https://api.openai.com/v1"),
    })
    require_permission(application.directory, actor, config)
    return expires


def _models_and_config(settings):
    from nm.Archives.legal_brain.evaluate.evaluation_models import bounded_pair
    from nm.shared.model_config import load
    from nm.shared.model_port import Tier

    evaluation_settings = dict(settings)
    for name in ("NM_EVAL_BUDGET_FILE", "NM_EVAL_MAX_USD", "NM_MODEL_HARD",
                 "NM_EMBED_MODEL"):
        evaluation_settings.pop(name, None)
    evaluation_settings.update(NM_MODEL_PROVIDER="openai", NM_MODEL_ROUTINE=AUTHOR,
        NM_MODEL_JUDGE=VERIFIER, NM_MODEL_BASE_URL="https://api.openai.com/v1")
    for suffix in ("ROUTINE", "JUDGE"):
        evaluation_settings.pop(f"NM_MODEL_PROVIDER_{suffix}", None)
        evaluation_settings.pop(f"NM_MODEL_BASE_URL_{suffix}", None)
    config = load(evaluation_settings)

    def client(tier):
        import httpx
        from openai import OpenAI

        context = ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise ApprovalRefused("The provider needs verified TLS and hostname checks.")
        selected = config.for_tier(tier)
        if not selected.api_key:
            raise ApprovalRefused("No local provider credential is configured.")
        return OpenAI(api_key=selected.api_key, base_url="https://api.openai.com/v1",
            max_retries=0, http_client=httpx.Client(verify=context, trust_env=False,
                                                    follow_redirects=False, timeout=90))

    return bounded_pair(config, ledger=LEDGER, maximum_usd=MAX_USD,
        author_client=client(Tier.ROUTINE), verifier_client=client(Tier.JUDGE))


def _install_grant(application, *, record, fingerprint, authorization_path, actor,
                   matter_ids, approval_reference, expires, pair):
    from nm.app.model_permission import require_permission
    from nm.Archives.legal_brain.evaluate.controlled_evaluations_composition import ControlledEvaluation
    from nm.Archives.legal_brain.orchestrate.controlled_brain import EvaluationScope
    from nm.Archives.legal_brain.orchestrate.loop_contracts import LoopLimits, LoopMode, digest
    from nm.Archives.legal_brain.verify.brain_release import ReviewService
    from nm.Archives.legal_brain.verify.verifier import IndependentVerifier
    from nm.shared.budget_contracts import Budget
    from nm.shared.store_loop_log import MatterLoopLog

    initial_attempts = _existing_ledger(LEDGER)
    scope = EvaluationScope(approval_reference, actor, frozenset(matter_ids),
                            LoopMode.SYNTHETIC)

    def current_permission(app, admitted):
        try:
            latest, identity = _private_authorization(authorization_path, root=ROOT)
            if identity != fingerprint or latest != record:
                return False
            validate_authorization(latest, actor=actor, matter_ids=matter_ids,
                approval_reference=approval_reference, application=app, ledger=LEDGER,
                now=datetime.now(timezone.utc))
            _existing_ledger(LEDGER, minimum_attempts=initial_attempts)
            require_permission(app.directory, admitted.advocate_id, pair.config)
        except Exception:  # noqa: BLE001 -- unreadable authority never renews permission
            return False
        return True

    def author_for(app, admitted, current):
        return pair.bind(directory=app.directory, account_id=admitted.advocate_id,
                         session_current=current, audit=app._egress_audit)[0]

    def cost_ceiling(incoming, outgoing, tier):
        priced = pair.config.for_tier(tier)
        return (incoming * priced.price_in + outgoing * priced.price_out) / 1_000_000

    def reviewer_for(app, admitted, current):
        judge = pair.bind(directory=app.directory, account_id=admitted.advocate_id,
                          session_current=current, audit=app._egress_audit)[1]
        return ReviewService(store=app.store,
            log=MatterLoopLog(app.store, advocate_id=admitted.advocate_id),
            verifier=IndependentVerifier(judge, max_tokens=2048),
            session_current=current, cost_ceiling=cost_ceiling)

    generation = application.source_generation_guard()
    limits = LoopLimits(Budget(max_ms=240000, max_tokens=120000,
                               max_cost_usd=0.75, max_retries=2, max_children=12),
                        max_steps=36, per_call_tokens=1800, max_stagnant_steps=3)
    grant = ControlledEvaluation(scope=scope, limits=limits, expires_at=expires,
        source_version=generation.version,
        table_version=digest(generation.binding["knowledge_bytes"]),
        cost_ceiling=cost_ceiling, reviewer_factory=reviewer_for, max_repairs=1,
        review_interactions=True,
        interaction_protocol_version=record["interaction_protocol_version"],
        author_factory=author_for, permission_current=current_permission)
    application.controlled_evaluations = (grant,)
    return grant


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--matter-id", action="append", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument("--port", type=int, default=8071)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--serve", action="store_true")
    args = parser.parse_args(argv)
    try:
        from nm.app.composition import Application
        from nm.shared.model_config import load_dotenv

        load_dotenv(ROOT / ".env")
        settings = dict(os.environ)
        record, fingerprint = _private_authorization(args.authorization, root=ROOT)
        application = Application(root=ROOT, environment=settings)
        expires = validate_authorization(record, actor=args.actor,
            matter_ids=tuple(args.matter_id), approval_reference=args.approval_reference,
            application=application, ledger=LEDGER, now=datetime.now(timezone.utc))
        if args.check:
            print("Current fictional approval, matter ownership, account permission and "
                  "original USD5 ledger verified. No model request or server was started.")
            return 0
        if not 1024 <= args.port <= 65535:
            raise ApprovalRefused("Choose a local, nonprivileged TCP port.")
        pair = _models_and_config(settings)
        _install_grant(application, record=record, fingerprint=fingerprint,
            authorization_path=args.authorization, actor=args.actor,
            matter_ids=tuple(args.matter_id), approval_reference=args.approval_reference,
            expires=expires, pair=pair)
        import uvicorn

        from nm.app.main import create_app

        print("Finite fictional-only preview ready. Normal client processing is unchanged.",
              flush=True)
        print("The original shared USD5 ledger remains in force; no authority comes "
              "from the browser request.", flush=True)
        uvicorn.run(create_app(application), host="127.0.0.1", port=args.port,
                    log_level="warning")
        return 0
    except Exception as exc:  # noqa: BLE001 -- startup fails closed, never print case data
        reason = str(exc) if isinstance(exc, ApprovalRefused) else "local configuration refused"
        print(f"REFUSED TO START: {type(exc).__name__}: {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
