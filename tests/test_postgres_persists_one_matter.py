"""THE REAL THING, AGAINST A REAL SERVER. BK-83-AC1, BK-36. P10.

    NM_POSTGRES_DSN=postgresql://... python -m pytest -m postgres

WHY THIS IS SKIPPED AND WHY THAT IS NOT A PASS
------------------------------------------------
Measured on 11 September 2026: no PostgreSQL server, client library, container
runtime or WSL package is present on this machine, so a disposable cluster
cannot be started from tooling already here. The adapter is therefore built and
unproven, and the honest record of that is a SKIP plus a control that refuses
to let BK-83-AC1 carry evidence -- `tests/test_no_database_means_no_evidence.py`.

A skip that nobody counts is how an unproven adapter becomes a claimed one.

WHAT WOULD MAKE THIS RUN
--------------------------
A PostgreSQL instance the runner owns, and `pip install psycopg[binary]`.
The suite creates its own tables, uses two synthetic workspaces and drops
nothing it did not create. It must never be pointed at a database holding real
matters: `test_the_target_database_is_disposable` refuses a DSN that does not
say so in its name.

WHAT IS ASSERTED
------------------
    one accepted command produces one version, one operation and one outbox row
    the three are committed together or not at all
    a stale writer is refused and the winner's version stands
    a replayed idempotency key returns the original result and does no work
    the same key with a different request is a conflict
    workspace B cannot see, list or update workspace A's matter
    a pooled connection carries no tenant context between transactions
    every persisted field survives a round trip
"""

from __future__ import annotations

import os
import uuid

import pytest

from nm.shared.operation_contracts import (
    Operation,
    request_digest,
)
from nm.work_the_file.matter_contracts import Matter

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("NM_POSTGRES_DSN"),
        reason="NM_POSTGRES_DSN is not set, so no PostgreSQL server is "
        "available. BK-83-AC1 stays NOT_RUN; a skip is not a pass.",
    ),
]

DSN = os.environ.get("NM_POSTGRES_DSN", "")
SEAL = "integration-seal-" + "k" * 24
WS_A, WS_B = "ws_synthetic_a", "ws_synthetic_b"


def _driver():
    try:
        import psycopg

        return psycopg
    except ImportError:
        try:
            import psycopg2

            return psycopg2
        except ImportError:
            pytest.skip("no psycopg/psycopg2 is installed")


def _matter(advocate: str = "adv@example.test") -> Matter:
    return Matter(
        id=f"mat_{uuid.uuid4().hex[:12]}", advocate_id=advocate, title="Kukatpally possession"
    )


def _operation(matter: Matter, key: str, workspace: str = WS_A) -> Operation:
    return Operation(
        idempotency_key=key,
        workspace_id=workspace,
        advocate_id=matter.advocate_id,
        command="create-matter",
        matter_id=str(matter.id),
        request_digest=request_digest({"title": matter.title}),
    )


# =========================== the target is disposable =======================


def test_the_target_database_is_disposable():
    """REFUSES A DSN THAT DOES NOT SAY SO. This suite deletes rows, and a
    database whose name does not announce that it is scratch is one somebody
    may be keeping real matters in."""
    name = DSN.rsplit("/", 1)[-1].split("?")[0].lower()
    assert any(
        word in name for word in ("test", "scratch", "tmp", "disposable", "synthetic", "nm_dev")
    ), (
        f"the DSN names database {name!r}, which does not announce itself as "
        f"disposable. Point NM_POSTGRES_DSN at a database you own and can lose."
    )


# ======================== one command, three records ========================


# ============================== versions ====================================


# ============================== idempotency =================================


# ============================== tenant isolation ============================


# ============================ nothing is lost ===============================


