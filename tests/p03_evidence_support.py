"""Real cryptographic fixtures for P03's fail-closed evidence tests."""
from __future__ import annotations

import base64
import pathlib
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from assurance.control_plane.evidence_verification import (
    SignedArtifactVerifier,
    canonical_json,
    sha256_bytes,
)


class TrustHarness:
    def __init__(self, root: pathlib.Path, *, base: pathlib.Path | None = None) -> None:
        self.root = root
        self.base = (base or root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.keys = {
            person: Ed25519PrivateKey.generate()
            for person in ("authority-root", "alice", "bob", "mallory")
        }
        public = {
            (person, "key-1"): key.public_key()
            for person, key in self.keys.items()
        }
        self.verifier = SignedArtifactVerifier(
            base=self.base, allowed_roots=(self.root,), trusted_keys=public,
            authority_issuers=frozenset({"authority-root"}),
        )

    def _ref(self, path: pathlib.Path) -> str:
        try:
            return path.resolve().relative_to(self.base).as_posix()
        except ValueError:
            return str(path.resolve())

    def raw(self, name: str, value: bytes) -> dict:
        path = self.root / name
        path.write_bytes(value)
        return {"ref": self._ref(path), "sha256": sha256_bytes(value)}

    def signed(self, name: str, payload: object, signers: tuple[str, ...]) -> dict:
        material = canonical_json(payload)
        signatures = [{
            "person_id": person, "key_id": "key-1",
            "signature": base64.b64encode(self.keys[person].sign(material)).decode("ascii"),
        } for person in signers]
        body = canonical_json({"schema": 1, "payload": payload,
                               "signatures": signatures})
        return self.raw(name, body)

    def authority(self, name: str, *, person: str, role: str, basis: str,
                  scopes: list[str], now: datetime) -> dict:
        payload = {
            "kind": "authority_grant", "person_id": person,
            "role": role, "basis": basis, "scopes": scopes,
            "valid_from": (now - timedelta(days=30)).isoformat(),
            "valid_until": (now + timedelta(days=30)).isoformat(),
        }
        return self.signed(name, payload, ("authority-root",))

    def condition(self, name: str, *, approval_id: str, condition_id: str,
                  requirement: str, now: datetime) -> dict:
        payload = {
            "kind": "condition_evidence", "approval_id": approval_id,
            "condition_id": condition_id, "requirement": requirement,
            "valid_until": (now + timedelta(days=7)).isoformat(),
        }
        return self.signed(name, payload, ("bob",))


UTC = timezone.utc
