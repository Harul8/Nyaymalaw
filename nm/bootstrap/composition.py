"""The composition root. The only place that knows which adapters are real.

Everything else takes ports. This module is where the wiring happens, and it is
also where the byte boundary is enforced -- deliberately, because a guard that
is right in the core and wrong at the edge is not a guard, and EVERY defect the
first external review found lived between a correct module and the served path.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from nm.adapters.evidence.corpus import CorpusEvidenceAdapter, default_authority_index
from nm.adapters.knowledge.elements import CuratedElements
from nm.adapters.model.config import ModelConfig, load, load_dotenv
from nm.adapters.model.openai_adapter import OpenAIModelAdapter
from nm.adapters.model.policed import PolicedModel
from nm.adapters.model.scripted import ScriptedModelAdapter
from nm.adapters.model.traced import TracedModel
from nm.adapters.policed_port import PolicedPort
from nm.adapters.search.authority import AuthorityIndexSearch
from nm.adapters.search.policed import PolicedSearch
from nm.adapters.store.directory import FileDirectory
from nm.adapters.store.file_store import FileMatterStore
from nm.bootstrap.egress_policy import (
    INDEX_PROCESSOR,
    STORAGE_PROCESSOR,
    egress_policy,
)
from nm.core.turn import TurnEngine
from nm.domain.advocate import utcnow
from nm.domain.clock import FORUM
from nm.domain.egress import DataClass, Gatekeeper, Sink
from nm.domain.gates import GATES, withholding
from nm.edge.uploads import UploadService
from nm.knowledge.coverage import CoverageProfile
from nm.knowledge.manifest import Manifest, PublishedCorpus
from nm.ports.directory import DirectoryPort
from nm.ports.model import ModelPort, Tier
from nm.ports.store import StorePort
from nm.ports.upload import UploadPort

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
                 directory=None, uploads=None,
                 environment: Mapping[str, str] | None = None,
                 audit_root: Path | None = None) -> None:
        # Explicit composition must never read or temporarily replace process
        # configuration: another served app may be running in the same process.
        # The omitted case retains the production startup contract.
        if environment is None:
            load_dotenv(ROOT / ".env")
        settings = MappingProxyType(dict(os.environ if environment is None else environment))
        self.environment = settings
        self.root = root or ROOT
        self.audit_root = Path(audit_root) if audit_root is not None else self.root / ".nm"
        self.config = load(dict(settings))
        self.manifest = Manifest.load(self.root / "spec" / "manifest.yaml")

        key = settings.get("NM_MATTER_KEY") or ""
        if not key.strip():
            # Generated per-installation rather than defaulted to empty: an
            # unconfigured key must never become "no encryption".
            key = _ensure_local_key(self.root)
        _refuse_a_shared_seal(key, settings)

        # ONE GATEKEEPER FOR EVERY SINK. The decision -- build the route,
        # refuse, audit -- exists once; each wrapper contributes only what it
        # alone knows, which is the processor it is about to talk to. Two
        # implementations of one decision is the shape CLAUDE.md section 4
        # records, and it is how a change described as global lands in half
        # the product.
        self._gate = Gatekeeper(policy=egress_policy(self.root),
                                audit=self._egress_audit)
        # EVERY LIVE DESTINATION IS ADMITTED BEFORE IT EXISTS. BK-85-AC1.
        #
        # `Sink.STORAGE` is a real sink even when the destination is this
        # machine's own disk: recording it is what lets the inventory refuse
        # the day it becomes a bucket in another region, and an inventory can
        # only refuse a route it was asked about. An installation whose
        # storage processor is unapproved therefore cannot be constructed at
        # all, rather than failing at its first write with a store object
        # somebody is already holding.
        self.store = PolicedPort(
            inner=store or FileMatterStore(
                settings.get("NM_MATTER_STORE") or (self.root / ".nm"),
                key=key),
            gate=self._gate, port=StorePort, sink=Sink.STORAGE,
            processor_id=STORAGE_PROCESSOR)
        # Originals use the same root and per-matter keys as the injected or
        # live file store. An unsupported store requires an explicit adapter;
        # never silently write uploads to a second default location.
        upload_adapter = uploads
        if upload_adapter is None and isinstance(self.store.inner, FileMatterStore):
            upload_adapter = self.store.inner.upload_storage()
        self.uploads = None
        if upload_adapter is not None:
            upload_objects = PolicedPort(
                inner=upload_adapter, gate=self._gate, port=UploadPort,
                sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
                weigh=lambda args, kwargs: len(
                    kwargs.get("data", args[2] if len(args) > 2 else b"")))
            self.uploads = UploadService(self.store, upload_objects)
        # A1. THE SAME KEY AS THE MATTERS, and the same root. Two stores with
        # two keys is two things to configure and one of them to forget.
        self.directory: DirectoryPort = PolicedPort(
            inner=directory or FileDirectory(
                settings.get("NM_MATTER_STORE") or (self.root / ".nm"),
                key=key),
            gate=self._gate, port=DirectoryPort, sink=Sink.STORAGE,
            processor_id=STORAGE_PROCESSOR,
            # THE ROSTER IS NOT A MATTER. It holds advocate identities and
            # credential material, which is restricted rather than client
            # matter, and saying so keeps the two separable in the audit.
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        corpus_path = Path(
            settings.get("NM_CORPUS_DIR")
            or (self.root / "legal_database" / "vector_store")
        )
        published_corpus = (corpus_path / "current.json").is_file()
        published_snapshot = None
        #: KEPT, for P21: the research routes record a reliance's source
        #: dependency against the bound generation and read its withdrawals.
        self._corpus_path = corpus_path
        if published_corpus and evidence is None and any(
            settings.get(name) for name in (
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
                authority_index=(settings.get("NM_AUTHORITY_INDEX")
                                 or default_authority_index(self.root)),
                identity_index=(settings.get("NM_IDENTITY_INDEX")
                                or (self.root / ".nm" / "identity.db")))
        # A4. The SAME index the evidence adapter reads, named once. Two
        # paths to one file, configured separately, is how the grounding gate
        # and the evidence adapter came to hold different provision patterns
        # (CLAUDE.md §4) -- so the search surface takes the resolved path
        # rather than re-reading the environment.
        if search is not None:
            search_adapter = search
        elif published_corpus and evidence is None:
            if published_snapshot is None:
                raise AssertionError("published corpus snapshot was not bound")
            search_adapter = AuthorityIndexSearch.from_published_snapshot(
                published_snapshot,
            )
        else:
            search_adapter = AuthorityIndexSearch(
                settings.get("NM_AUTHORITY_INDEX")
                or default_authority_index(self.root))
        # THE QUERY IS WHAT LEAVES. An advocate searching for authority types
        # the substance of the matter into the box, so the text going TO the
        # index is client material even though the law coming back is public.
        # Every adapter selection reaches this one wrapper, including a
        # published generation and an explicitly supplied search port.
        self.search = PolicedSearch(
            inner=search_adapter,
            gate=self._gate, processor_id=INDEX_PROCESSOR)
        self._published_snapshot = published_snapshot
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
        # THE POLICY IS IN FRONT OF THE PROVIDER, NOT BESIDE IT. BK-85-AC1.
        #
        # `TracedModel` records what was sent; `PolicedModel` decides whether
        # it may be sent at all, and the order matters: a refused dispatch must
        # never reach the provider, so the policy wraps the tracer rather than
        # the other way round. The trace still records the attempt, because a
        # refusal is exactly the call an operator wants to find later.
        self.model = PolicedModel(
            inner=TracedModel(inner=model or build_model(self.config)),
            policy=self._gate.policy, audit=self._egress_audit,
            gate=self._gate)
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
                                 elements=self.elements,
                                 professional_approval=self.directory.professional_approval)

    # ------------------------------------------------------------ P21 ------

    def binding_for(self, court: str | None, year: object):
        """Whether an authority's court binds THIS forum. THE EDGE ASKS HERE.

        `nm.edge` may not import `nm.knowledge` (layercheck), and the rule is
        a knowledge-plane fact -- binding is a relationship between the
        deciding court and the forum, measured in `jurisdiction.py`. Exposing
        it through the composition root keeps one owner of the rule and no
        provider knowledge on the serving path.
        """
        from nm.knowledge.jurisdiction import binding_status

        return binding_status(court, year, FORUM)

    def record_source_dependency(self, *, work_id: str, case_id: str,
                                 fallback_version: str) -> tuple[str, str | None, str]:
        """Link a matter to the exact law version it attached. P20 → P21.

        Returns `(source_version, dependency_id, why)`. THREE OUTCOMES:

          * a published generation is bound AND names a source version for
            this case -> the dependency is written through
            `record_corpus_dependency` and its id returned;
          * a published generation is bound and names no version for this
            case -> the reliance records the SNAPSHOT id, no dependency is
            written, and `why` says the manifest could not name the source;
          * no published generation (the legacy index) -> the reliance
            records the index's corpus version and `why` says no generation
            is bound. Nothing is invented in either gap.
        """
        snapshot = self._published_snapshot
        if snapshot is None:
            return (fallback_version, None,
                    "no immutable published generation is bound; the index's "
                    "corpus version is recorded instead")
        version_id = snapshot.version_for_source(case_id)
        if not version_id:
            return (snapshot.snapshot_id, None,
                    f"generation {snapshot.snapshot_id} names no source version "
                    f"for {case_id!r}, so the generation itself is recorded")
        from datetime import datetime, timezone

        from nm.knowledge.manifest import CorpusDependency, record_corpus_dependency

        dependency_id = record_corpus_dependency(
            self._corpus_path,
            CorpusDependency(work_id=work_id, snapshot_id=snapshot.snapshot_id,
                             source_versions=(version_id,),
                             observed_at=datetime.now(timezone.utc)))
        return version_id, dependency_id, ""

    def _egress_audit(self, line: str) -> None:
        """One line per dispatch decision, beside the auth log.

        CONTENT-FREE BY CONSTRUCTION, not by discipline: `audit_line` composes
        the route, the reason and a byte count and has no access to the prompt
        at all. A writer that could quote the payload would eventually be asked
        to, for debugging, by somebody reasonable.

        NEVER RAISES. An audit that can break a turn is worse than one that
        misses a line -- the same rule `note_failure` already follows.
        """
        try:
            path = self.audit_root / "egress.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf8") as handle:
                stamp = utcnow().isoformat(timespec="seconds")
                handle.write(stamp + "\t" + line + "\n")
        except OSError:
            pass

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


def _refuse_a_shared_seal(key: str, env: Mapping[str, str] | None = None) -> None:
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
