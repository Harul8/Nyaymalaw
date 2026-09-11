"""The composition root. The only place that knows which adapters are real.

Everything else takes ports. This module is where the wiring happens, and it is
also where the byte boundary is enforced -- deliberately, because a guard that
is right in the core and wrong at the edge is not a guard, and EVERY defect the
first external review found lived between a correct module and the served path.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter, default_authority_index
from nm.adapters.knowledge.elements import CuratedElements
from nm.adapters.model.config import ModelConfig, load, load_dotenv
from nm.adapters.model.openai_adapter import OpenAIModelAdapter
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.search.authority import AuthorityIndexSearch
from nm.adapters.store.directory import FileDirectory
from nm.adapters.store.file_store import FileMatterStore
from nm.core.turn import TurnEngine
from nm.domain.clock import FORUM
from nm.domain.gates import GATES, withholding
from nm.knowledge.coverage import CoverageProfile
from nm.knowledge.manifest import Manifest, PublishedCorpus
from nm.ports.directory import DirectoryPort
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
                 store=None, evidence=None, search=None,
                 directory=None) -> None:
        load_dotenv(ROOT / ".env")
        self.root = root or ROOT
        self.config = load()
        self.manifest = Manifest.load(self.root / "spec" / "manifest.yaml")

        key = os.environ.get("NM_MATTER_KEY") or ""
        if not key.strip():
            # Generated per-installation rather than defaulted to empty: an
            # unconfigured key must never become "no encryption".
            key = _ensure_local_key(self.root)
        _refuse_a_shared_seal(key)

        self.store = store or FileMatterStore(
            os.environ.get("NM_MATTER_STORE") or (self.root / ".nm"), key=key)
        # A1. THE SAME KEY AS THE MATTERS, and the same root. Two stores with
        # two keys is two things to configure and one of them to forget.
        self.directory: DirectoryPort = directory or FileDirectory(
            os.environ.get("NM_MATTER_STORE") or (self.root / ".nm"), key=key)
        corpus_path = Path(
            os.environ.get("NM_CORPUS_DIR")
            or (self.root / "legal_database" / "vector_store")
        )
        published_corpus = (corpus_path / "current.json").is_file()
        published_snapshot = None
        if published_corpus and evidence is None and any(
            os.environ.get(name) for name in (
                "NM_AUTHORITY_INDEX", "NM_IDENTITY_INDEX",
            )
        ):
            raise RuntimeError(
                "NM_CORPUS_DIR names an immutable published corpus; standalone "
                "authority or identity index overrides would mix generations"
            )
        if evidence is not None:
            self.evidence = evidence
        elif published_corpus:
            published_snapshot = PublishedCorpus.open(corpus_path, verify_all=True)
            self.manifest = Manifest.load(
                published_snapshot.member_path("corpus/manifest.yaml")
            )
            self.evidence = CorpusEvidenceAdapter.from_published_snapshot(
                published_snapshot,
            )
        else:
            self.evidence = CorpusEvidenceAdapter(
                corpus_path,
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
        if search is not None:
            self.search = search
        elif published_corpus and evidence is None:
            if published_snapshot is None:
                raise AssertionError("published corpus snapshot was not bound")
            self.search = AuthorityIndexSearch.from_published_snapshot(
                published_snapshot,
            )
        else:
            self.search = AuthorityIndexSearch(
                os.environ.get("NM_AUTHORITY_INDEX")
                or default_authority_index(self.root))
        # EVERY MODEL CALL IS KEPT, and the wrapping happens HERE.
        #
        # `TurnMetrics` already counts the calls; it does not say which read
        # each was, what it was given, or which returned nothing. B-088 was
        # diagnosed by diffing two scenario runs by hand for exactly that
        # reason. Tracing inside each adapter would have been two owners of
        # one decision -- the shape CLAUDE.md §4 records -- so it is a
        # decorator over the port, applied once, and nothing in the core knows.
        #
        # The trace rides in the TRANSCRIPT, which is sealed with the matter
        # cipher, because a prompt carries everything the advocate has said.
        self.model = TracedModel(inner=model or build_model(self.config))
        self.coverage = CoverageProfile.load(self.root / "spec" / "coverage.yaml")
        # D5'S ELEMENT TABLE, WIRED. `nm.core` may not import `nm.knowledge`,
        # so the curated lists reach the turn through a port -- the same route
        # the evidence plane already uses for the cause-to-Article edge. An
        # unwired installation fires G-PROOF `not_assessed` rather than
        # producing a conclusion with no proof section, which reads as though
        # everything were established.
        self.elements = CuratedElements()
        self.engine = TurnEngine(store=self.store, evidence=self.evidence,
                                 model=self.model, coverage=self.coverage,
                                 elements=self.elements)

    def health(self) -> dict:
        return {
            "provider": self.model.provider,
            "routine_model": self.model.resolved_model(Tier.ROUTINE),
            "hard_tier": ("configured" if self.config.configured(Tier.HARD)
                          else "not configured"),
            "judge_tier": ("configured" if self.config.configured(Tier.JUDGE)
                           else "not configured"),
            "encryption": self.store.scheme,
            # A LIMITER THAT IS NOT RUNNING IS VISIBLE HERE, before an
            # incident rather than during one. It fails OPEN by design,
            # and a control that could not run returning the shape of a
            # clean result is exactly what this line refuses.
            "rate_limiting": ("running"
                              if self.directory.limiter_available()
                              else "NOT RUNNING -- the attempt log cannot be written"),
            "corpus": "readable" if self.evidence.available else "NOT READABLE",
            # Each retrieval capability reports its OWN readiness. One rolled-up
            # "corpus: readable" would let an unbuilt authority index hide
            # behind a readable provision store, and the advocate would learn
            # about it as an empty answer.
            # DECLARED ON THE PORT, so this is a call and not a guess. It read
            # `self.evidence.readiness() if hasattr(...) else {}` -- and an
            # adapter without the method then produced an empty retrieval
            # section, which reads exactly like an adapter that answered and
            # had nothing to report. Same line, `available` was reached with
            # no guard at all and 500'd this route for every such adapter.
            "retrieval": self.evidence.readiness(),
            "gates": {
                "total": len(GATES),
                "built": sum(1 for g in GATES if g.built),
                "withholding": [g.id for g in withholding()],
            },
            "coverage": {
                "measured_at": self.coverage.measured_at or "NEVER MEASURED",
                "corpus_version": self.coverage.corpus_version,
                FORUM: self.coverage.position(FORUM).state.value,
            },
            "manifest_acts": len(self.manifest.entries),
            "manifest_corpus_version": self.manifest.corpus_version,
        }


#: What a credential looks like, by name. Deliberately broad: the rule is about
#: the VALUE being shared, and a narrow list would only refuse the collision
#: that was found rather than the shape.
_CREDENTIAL_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL", re.I)

#: The seal is the matter key itself. Nothing else may hold the same value.
_SEAL = "NM_MATTER_KEY"


class SharedSealRefused(RuntimeError):
    """The seal on client files is also being used for something else."""


def _refuse_a_shared_seal(key: str, env: dict[str, str] | None = None) -> None:
    """BK-21. THE SEAL ON CLIENT FILES MAY NOT BE ANY OTHER CREDENTIAL.

    `NM_MATTER_KEY` and `NM_MODEL_API_KEY` held the same `sk-proj-...` value,
    so one secret was doing two unrelated jobs. That is not untidiness. The
    OpenAI credential is rotated as a matter of routine -- it leaks, a laptop
    goes, a provider forces it -- and rotating it would have made **every
    stored matter permanently unreadable**, because the same string was sealing
    them. It has already been demonstrated at zero cost: `start.ps1` supplied a
    different key, the real one was shadowed, and the account could not be
    opened. That is the shape of a rotation, and the only difference was that
    the old value still existed.

    THE GUARD IS AT THE COMPOSITION ROOT, not in the store. A store that
    refuses this is right in the core and wrong where the application is
    assembled -- CLAIM section 8's exact failure, where forty offline tests
    passed while every served turn crashed. This runs once, where the key is
    chosen.

    THE POPULATION IS EVERY CREDENTIAL IN THE ENVIRONMENT, not
    `NM_MODEL_API_KEY`. Naming the one variable that collided would refuse
    today's mistake and none of the others -- the one-site patch this
    repository has recorded forty-seven times. The rule is that the seal is
    unique, so the comparison is against everything credential-shaped.
    """
    env = os.environ if env is None else env
    if not key.strip():
        return                     # an unset key is a different defect
    shared = sorted(
        name for name, value in env.items()
        if name != _SEAL and value and value.strip() == key.strip()
        and _CREDENTIAL_NAME.search(name))
    if not shared:
        return
    raise SharedSealRefused(
        f"{_SEAL} holds the same value as {', '.join(shared)}. The matter key "
        f"seals client files; every other credential here is rotated as a "
        f"matter of routine, and rotating one that is also the seal makes "
        f"every stored matter permanently unreadable. Generate a new "
        f"{_SEAL}, re-key the store with it, and only then rotate the other "
        f"credential -- in that order, because rotating first destroys the "
        f"matters.")


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
