"""Immutable retrieved text, not a claim of full-document or legal currency."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


def content_identity(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceExcerpt:
    label: str
    locator: str
    namespace: str
    text: str
    kind: str
    valid_from: str
    valid_to: str
    digest: str

    def __post_init__(self):
        values = asdict(self)
        digest = values.pop("digest")
        if any(type(value) is not str for value in values.values()):
            raise ValueError("source excerpt fields must be text")
        if any(not values[name].strip() for name in ("label", "locator", "namespace", "text")):
            raise ValueError("source excerpt identity and text must be recorded")
        if self.kind not in ("provision", "authority"):
            raise ValueError("source excerpt kind is not recognised")
        if digest != content_identity(values):
            raise ValueError("source excerpt does not match its recorded content identity")

    def header(self) -> dict:
        """Chat carries identity only; the authorised reader pages the text."""
        return {name: value for name, value in asdict(self).items()
                if name not in ("text", "namespace")}

    @classmethod
    def capture(cls, **values):
        return cls(**values, digest=content_identity(values))
