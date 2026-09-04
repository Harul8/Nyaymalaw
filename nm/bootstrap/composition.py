"""The composition root. The only place that knows which adapters are real.

Everything else takes ports. This module is where the wiring happens, and it is
also where the byte boundary is enforced -- deliberately, because a guard that
is right in the core and wrong at the edge is not a guard, and EVERY defect the
first external review found lived between a correct module and the served path.
"""
from __future__ import annotations

import os
from pathlib import Path

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter, default_authority_index
from nm.adapters.model.config import ModelConfig, load, load_dotenv
from nm.adapters.model.openai_adapter import OpenAIModelAdapter
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.search.authority import AuthorityIndexSearch
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine
from nm.domain.gates import GATES, withholding
from nm.knowledge.coverage import CoverageProfile
from nm.knowledge.manifest import Manifest
from nm.ports.model import ModelPort, Tier

ROOT = Path(__file__).resolve().parents[2]


def build_model(config: ModelConfig) -> ModelPort:
    """Pick the adapter by PROVIDER NAME ALONE.

    This function is the whole of "switching provider is an environment
    variable". If it ever grows a branch on anything but the provider string,
    the switch has stopped being a configuration change.
    """
    provider = config.for_tier(Tier.ROUTINE).provider
    if provider == "openai":
        return OpenAIModelAdapter(config)
    if provider == "scripted":
        return ScriptedModelAdapter(config, responses={
            "__default__": "Confirm the date of service and file within the window."})
    raise RuntimeError(f"no adapter registered for provider {provider!r}")


class Application:
    def __init__(self, *, root: Path | None = None, model: ModelPort | None = None,
                 store=None, evidence=None, search=None) -> None:
        load_dotenv(ROOT / ".env")
        self.root = root or ROOT
        self.config = load()
        self.manifest = Manifest.load(self.root / "spec" / "manifest.yaml")

        key = os.environ.get("NM_MATTER_KEY") or ""
        if not key.strip():
            # Generated per-installation rather than defaulted to empty: an
            # unconfigured key must never become "no encryption".
            key = _ensure_local_key(self.root)

        self.store = store or FileMatterStore(
            os.environ.get("NM_MATTER_STORE") or (self.root / ".nm"), key=key)
        self.evidence = evidence or CorpusEvidenceAdapter(
            os.environ.get("NM_CORPUS_DIR")
            or (self.root / "legal_database" / "vector_store"),
            self.manifest,
            authority_index=(os.environ.get("NM_AUTHORITY_INDEX")
                             or default_authority_index(self.root)),
            identity_index=(os.environ.get("NM_IDENTITY_INDEX")
                            or (self.root / ".nm" / "identity.db")))
        # A4. The SAME index the evidence adapter reads, named once. Two
        # paths to one file, configured separately, is how the grounding gate
        # and the evidence adapter came to hold different provision patterns
        # (CLAUDE.md §4) -- so the search surface takes the resolved path
        # rather than re-reading the environment.
        self.search = search or AuthorityIndexSearch(
            os.environ.get("NM_AUTHORITY_INDEX")
            or default_authority_index(self.root))
        self.model = model or build_model(self.config)
        self.coverage = CoverageProfile.load(self.root / "spec" / "coverage.yaml")
        self.engine = TurnEngine(store=self.store, evidence=self.evidence,
                                 model=self.model, coverage=self.coverage)

    def health(self) -> dict:
        return {
            "provider": self.model.provider,
            "routine_model": self.model.resolved_model(Tier.ROUTINE),
            "hard_tier": ("configured" if self.config.configured(Tier.HARD)
                          else "not configured"),
            "judge_tier": ("configured" if self.config.configured(Tier.JUDGE)
                           else "not configured"),
            "encryption": self.store.scheme,
            "corpus": "readable" if self.evidence.available else "NOT READABLE",
            # Each retrieval capability reports its OWN readiness. One rolled-up
            # "corpus: readable" would let an unbuilt authority index hide
            # behind a readable provision store, and the advocate would learn
            # about it as an empty answer.
            "retrieval": (self.evidence.readiness()
                          if hasattr(self.evidence, "readiness") else {}),
            "gates": {
                "total": len(GATES),
                "built": sum(1 for g in GATES if g.built),
                "withholding": [g.id for g in withholding()],
            },
            "coverage": {
                "measured_at": self.coverage.measured_at or "NEVER MEASURED",
                "corpus_version": self.coverage.corpus_version,
                "Telangana": self.coverage.position("Telangana").state.value,
            },
            "manifest_acts": len(self.manifest.entries),
            "manifest_corpus_version": self.manifest.corpus_version,
        }


def _ensure_local_key(root: Path) -> str:
    """A per-installation key, outside the repository, created once.

    Not a default and not a constant: a hardcoded fallback key is encryption
    theatre. This is written to a file the repo ignores, and if it cannot be
    written the store raises rather than degrading to plaintext.
    """
    import secrets

    path = Path(root) / ".nm" / "matter.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48), encoding="utf8")
    return path.read_text(encoding="utf8").strip()
