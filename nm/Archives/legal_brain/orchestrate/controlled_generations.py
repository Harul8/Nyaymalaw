"""Actual small generation bindings, not caller-authored currentness claims.

Practice code bytes and the immutable corpus publication owner are checked.
Legacy unsealed corpus availability is explicitly not a freshness certificate;
source readers and dated/binding/treatment checks still own individual findings.
No full-index rebuild or repeated multi-gigabyte hashing is hidden here.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from nm.Archives.legal_brain.orchestrate.generations_port import GenerationUnavailable
from nm.Archives.legal_brain.orchestrate.loop_contracts import digest
from nm.Archives.legal_brain.retrieve.manifest_sources import CorpusPublicationRefused, PublishedCorpus


class GenerationGuard:
    def __init__(self, *, knowledge_root: Path, manifest_path: Path | None = None,
                 snapshot=None, knowledge_paths=None):
        self.knowledge_root = Path(knowledge_root).resolve()
        self.manifest_path = Path(manifest_path) if manifest_path is not None else None
        self.snapshot = snapshot
        self.knowledge_paths = knowledge_paths
        self.binding = self.observe()
        self.version = digest(self.binding)

    def observe(self):
        try:
            # Enumerate this actual plane, including future tables. A copied
            # short list would leave the next practice area unguarded.
            paths = sorted(self.knowledge_paths() if self.knowledge_paths is not None
                           else self.knowledge_root.rglob("*.py"))
            if not paths or any(path.is_symlink() or self.knowledge_root not in
                                path.resolve().parents for path in paths):
                raise GenerationUnavailable("The knowledge-plane byte population is unavailable")
            table_bytes = {str(path.relative_to(self.knowledge_root)):
                           sha256(path.read_bytes()).hexdigest() for path in paths}
            corpus = {"state": "legacy_unsealed_freshness_not_established"}
            if self.snapshot is not None:
                self.snapshot.require_usable()
                active = PublishedCorpus.open(self.snapshot.root)
                # The older pinned immutable source remains a source, but a
                # newly published active generation requires a new context.
                corpus = {"state": "bound_immutable_publication",
                          "bound_snapshot": self.snapshot.snapshot_id,
                          "active_snapshot": active.snapshot_id,
                          "published_manifest_sha256": active.pointer["manifest_sha256"]}
            manifest = (sha256(self.manifest_path.read_bytes()).hexdigest()
                        if self.manifest_path is not None else "not_bound")
            return {"knowledge_bytes": table_bytes, "corpus": corpus,
                    "coverage_manifest_sha256": manifest}
        except (OSError, CorpusPublicationRefused) as exc:
            raise GenerationUnavailable("The actual bound generation cannot be rechecked") from exc

    def require_current(self):
        if self.observe() != self.binding:
            raise GenerationUnavailable("The bound corpus or practice-table generation changed")
