"""The composition root. The only place that knows which adapters are real.

Everything else takes ports. This module is where the wiring happens, and it is
also where the byte boundary is enforced -- deliberately, because a guard that
is right in the core and wrong at the edge is not a guard, and EVERY defect the
first external review found lived between a correct module and the served path.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from nm.arrive.advocate_contracts import utcnow
from nm.arrive.directory_port import DirectoryPort
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.mail_port import MailPort
from nm.arrive.store_directory import FileDirectory
from nm.legal_brain.orchestrate.turn import TurnEngine
from nm.legal_brain.procedure.filing_requirement_adapter import (
    CuratedFilingRequirements,
)
from nm.legal_brain.procedure.governing_law_adapter import CuratedGoverningLaw
from nm.legal_brain.procedure.institution_adapter import CuratedPreInstitution
from nm.legal_brain.procedure.interim_relief_adapter import CuratedInterimRelief
from nm.legal_brain.procedure.procedural_period_adapter import CuratedProceduralPeriods
from nm.legal_brain.reason.elements_adapter import CuratedElements
from nm.legal_brain.retrieve.authority_weight_adapter import CuratedAuthorityWeight
from nm.legal_brain.retrieve.corpus_evidence import CorpusEvidenceAdapter, default_authority_index
from nm.legal_brain.retrieve.coverage_sources import CoverageProfile
from nm.legal_brain.retrieve.manifest_sources import (
    CorpusPublicationRefused,
    Manifest,
    PublishedCorpus,
)
from nm.legal_brain.retrieve.search_authority import AuthorityIndexSearch
from nm.legal_brain.retrieve.search_policed import PolicedSearch
from nm.open_matter.speech_local_whisper import LocalWhisper
from nm.open_matter.speech_vosk_live import VoskLive
from nm.open_matter.transcription_port import LiveTranscriptionPort, TranscriptionPort
from nm.open_matter.upload_port import UploadPort
from nm.open_matter.uploads_api import UploadService
from nm.shared.clock_contracts import FORUM
from nm.shared.deployment_contracts import shares_value_with
from nm.shared.egress_contracts import DataClass, Gatekeeper, Sink
from nm.shared.egress_policy import (
    INDEX_PROCESSOR,
    OUTBOX_PROCESSOR,
    STORAGE_PROCESSOR,
    TRANSCRIPTION_PROCESSOR,
    egress_policy,
)
from nm.shared.gates_contracts import GATES, withholding
from nm.shared.model_config import ModelConfig, load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_policed import PolicedModel
from nm.shared.model_port import ModelPort, Tier
from nm.shared.model_scripted import ScriptedModelAdapter
from nm.shared.model_traced import TracedModel
from nm.shared.policed_port_adapter import PolicedPort
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_port import StorePort

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
    if provider == "anthropic":
        from nm.shared.model_anthropic_adapter import AnthropicModelAdapter

        return AnthropicModelAdapter(config)
    if provider == "scripted":
        return ScriptedModelAdapter(config, responses={
            "__default__": "Confirm the date of service and file within the window."})
    raise RuntimeError(f"no adapter registered for provider {provider!r}")


def build_mail(settings, root, key, gate):
    """Disabled unless both delivery and NM's processor policy admit Gmail.

    This runtime currently admits local processors only. Enabling a flag alone
    must not approve Google or transfer any account data to it.
    """
    from nm.arrive.mail_gmail import GMAIL_PROCESSOR, MAIL_CLASSES, DisabledMail, GmailMail

    provider = settings.get('NM_MAIL_PROVIDER', 'local-outbox')
    delivery = settings.get('NM_MAIL_DELIVERY', 'disabled')
    if delivery not in {'disabled', 'enabled'}:
        raise ValueError('Unknown account-mail delivery setting.')
    if provider == 'local-outbox':
        if delivery == 'enabled':
            raise ValueError('A local outbox cannot enable real email delivery.')
        return FileOutbox(root, key=key), OUTBOX_PROCESSOR
    if provider != 'gmail':
        raise ValueError('Unknown account-mail provider.')
    if delivery == 'disabled':
        return DisabledMail(), OUTBOX_PROCESSOR
    gate.permit(Sink.MAIL, GMAIL_PROCESSOR, MAIL_CLASSES)
    adapter = GmailMail(settings.get('NM_MAIL_SENDER', ''),
                        Path(settings.get('NM_GMAIL_TOKEN_FILE', '')), gate, enabled=True)
    return adapter, GMAIL_PROCESSOR


class Application:
    def __init__(self, *, root: Path | None = None, model: ModelPort | None = None,
                 store=None, evidence=None, search=None,
                 directory=None, uploads=None, mail=None, transcriber=None,
                 live_dictation=None,
                 document_text=None, document_derivatives=None, document_quarantine=None,
                 document_quarantine_processor: str = "",
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
        # Only trusted composition may install finite expiring evaluation
        # grants. Registration, a model call and an HTTP body cannot do so.
        self.controlled_evaluations = ()
        self.manifest = Manifest.load(self.root / "pipeline" / "manifest.yaml")

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
        # ACCOUNT MAIL, POLICED LIKE EVERY OTHER DESTINATION. Implementation
        # Plan F-A-03. The only message today is the password-reset link, which
        # carries an address and a bearer secret and never matter material.
        # This build admits the sealed local outbox and nothing else: a real
        # mail provider is an external recipient, and the inventory refuses it
        # until an approval exists. The outbox shares the matter key and root.
        mail_adapter, mail_processor = ((mail, OUTBOX_PROCESSOR) if mail is not None else
                                       build_mail(settings, settings.get('NM_MATTER_STORE')
                                                  or self.root / '.nm', key, self._gate))
        self.mail: MailPort = PolicedPort(
            inner=mail_adapter,
            gate=self._gate, port=MailPort, sink=Sink.MAIL,
            processor_id=mail_processor,
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        # DICTATION, POLICED LIKE EVERY OTHER DESTINATION. Implementation Plan
        # F-C-02. A dictated brief is the client's instructions in the
        # advocate's voice -- client matter material -- so this build
        # transcribes it in this process, and the inventory refuses any outside
        # speech service until one is approved. The model loads on first use.
        self.transcriber: TranscriptionPort = PolicedPort(
            inner=transcriber or LocalWhisper(
                model=settings.get("NM_DICTATION_MODEL") or "large-v3",
                device=settings.get("NM_DICTATION_DEVICE") or "auto",
                compute_type=settings.get("NM_DICTATION_COMPUTE") or "",
                download_root=self.root / ".nm" / "models",
                # ENGLISH UNLESS TOLD OTHERWISE: `auto` detects the language,
                # and detection on a short Indian-accented clip is a guess.
                language=settings.get("NM_DICTATION_LANGUAGE") or "en",
                translate=(settings.get("NM_DICTATION_TRANSLATE") or "") == "1"),
            gate=self._gate, port=TranscriptionPort, sink=Sink.TRANSCRIPTION,
            processor_id=TRANSCRIPTION_PROCESSOR,
            weigh=lambda args, kwargs: len(kwargs.get("audio", args[0] if args else b"")))
        # THE LIVE WORDS ARE A SECOND SPEECH DESTINATION, and admitted as one
        # (F-C-03). Same processor -- both models run in this process, on this
        # machine -- and a separate wrapper, because a port that is admitted
        # through another port's wrapper is a route nobody asked the inventory
        # about.
        self.live_dictation: LiveTranscriptionPort = PolicedPort(
            inner=live_dictation or VoskLive(
                model_dir=self.root / ".nm" / "models" / (
                    settings.get("NM_DICTATION_LIVE_MODEL") or "vosk-model-small-en-in-0.4")),
            gate=self._gate, port=LiveTranscriptionPort, sink=Sink.TRANSCRIPTION,
            processor_id=TRANSCRIPTION_PROCESSOR)
        corpus_path = Path(
            settings.get("NM_CORPUS_DIR")
            or (self.root / "legal_database" / "vector_store")
        )
        published_corpus = (corpus_path / "current.json").is_file()
        published_snapshot = None
        from nm.legal_brain.retrieve.provision_registry_composition import load_provision_registry

        self.provision_registry = load_provision_registry(
            None, source_generation="not_established", generation_current=lambda *_: False)
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
            def registry_generation_current(generation, _metadata_identity):
                try:
                    return PublishedCorpus.open(corpus_path).snapshot_id == generation
                except (CorpusPublicationRefused, OSError):
                    return False

            self.provision_registry = load_provision_registry(
                published_snapshot, source_generation=published_snapshot.snapshot_id,
                generation_current=registry_generation_current)
            from nm.legal_brain.retrieve.provision_review import build_revision_review_owner

            revision_reviews = build_revision_review_owner(
                base=self.root, artifact_refs=self.provision_registry.review_artifact_refs,
                now=utcnow, environment=self.environment)
            self.evidence = CorpusEvidenceAdapter.from_published_snapshot(
                published_snapshot, source_registry=self.provision_registry.registry,
                revision_review_owner=revision_reviews,
                revision_checked_at=lambda: utcnow().date())
        else:
            # NO PROVISION-VERSION REGISTER EXISTS ON THIS BRANCH, so a held
            # provision is read as the library's current text and says so on the
            # passage (LB-156; owner, 29 September 2026: every dispute's law is
            # retrieved and shown). A published corpus installs its register above
            # and keeps the strict rule.
            self.evidence = CorpusEvidenceAdapter(
                corpus_path,
                self.manifest,
                authority_index=(settings.get("NM_AUTHORITY_INDEX")
                                 or default_authority_index(self.root)),
                identity_index=(settings.get("NM_IDENTITY_INDEX")
                                or (self.root / ".nm" / "identity.db")),
                current_text_when_unversioned=True)
        # LB-106. THE BARE-ACT SEARCH (owner, 29 September 2026): the earlier system's
        # vector index, BM25 index and passage store and the same two models, reused as
        # they are, with the search rebuilt here. Only where the library is read in place
        # and the index is there; it checks its lineage before it will run and says why
        # when it will not. The advocate's words go only to this machine's models and
        # index, and that destination is admitted like every other.
        self.sections = None
        if (evidence is None and not published_corpus
                and (corpus_path / "bareacts_v3.index").is_file()):
            from nm.legal_brain.retrieve.hybrid_sections import HybridSections
            from nm.legal_brain.retrieve.section_search_port import SectionSearchPort

            self.sections = PolicedPort(
                inner=HybridSections(
                    corpus_path, self.manifest, read_provision=self.evidence.read_provision,
                    models=self.root / ".nm" / "models",
                    lineage=self.root / ".nm" / "retrieval" / "bare_acts.lineage.json"),
                gate=self._gate, port=SectionSearchPort, sink=Sink.INDEX,
                processor_id=INDEX_PROCESSOR)
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
        self._model_adapter = model or build_model(self.config)
        budget_path = settings.get("NM_EVAL_BUDGET_FILE")
        if budget_path:
            if not isinstance(self._model_adapter, OpenAIModelAdapter):
                raise ValueError("A live evaluation budget requires the real OpenAI adapter.")
            from nm.shared.model_call_budget import CallBudget
            from nm.shared.model_config import PRICES, reservation_micro_usd
            from nm.shared.model_port import Tier

            # THE LEDGER NAMES THE MODEL THIS SERVER IS CONFIGURED FOR, with its
            # recorded price and worst-case reservation -- never a default pin that
            # a configuration change would contradict on the first call.
            routine = self.config.tiers[Tier.ROUTINE].model
            worst = reservation_micro_usd(routine)   # refuses an unpriced model first
            self._model_adapter = self._model_adapter.with_call_budget(
                CallBudget(Path(budget_path), settings.get("NM_EVAL_MAX_USD", "25"),
                           model=routine,
                           price_per_million=tuple(str(p) for p in PRICES[routine]),
                           reservation_micro_usd=worst))
        self.model = PolicedModel(
            inner=TracedModel(inner=self._model_adapter),
            policy=self._gate.policy, audit=self._egress_audit,
            gate=self._gate)
        self.coverage = CoverageProfile.load(
            self.root / "assurance" / "specification" / "coverage.yaml")
        # D5'S ELEMENT TABLE, WIRED. `nm.core` may not import `nm.knowledge`,
        # so the curated lists reach the turn through a port -- the same route
        # the evidence plane already uses for the cause-to-Article edge. An
        # unwired installation fires G-PROOF `not_assessed` rather than
        # producing a conclusion with no proof section, which reads as though
        # everything were established.
        self.elements = CuratedElements()
        # LB-121. THE SAME SPLIT AGAIN: the curated pre-institution conditions
        # live in the knowledge plane and reach the turn through a port, so
        # `nm.core` holds no legal table of its own. Wired here rather than
        # defaulted inside the engine, so a deployment that has not curated
        # these conditions is a deployment whose map says so.
        self.pre_institution = CuratedPreInstitution()
        # LB-122. IT READS THE SAME IDENTITY INDEX THE EVIDENCE ADAPTER
        # READS, beside the authority index, so the bench a ranking rests on
        # is the bench the authority was rendered with. A second index would
        # be a second answer to "how many judges decided this".
        self.authority_weight = CuratedAuthorityWeight(
            settings.get("NM_IDENTITY_INDEX")
            or (self.root / ".nm" / "identity.db"))
        # LB-123. THE INTERIM TESTS, same split. Wired here rather than
        # defaulted in the engine so that an installation that has not curated
        # them sets out no test at all, instead of reporting that none is held
        # for the relief the advocate asked about.
        self.interim_relief = CuratedInterimRelief()
        # LB-124. The clocks that run INSIDE a proceeding, on the same
        # register as limitation. Wired here for the same reason as the rest:
        # an installation that has not curated them enters no period, rather
        # than entering one it cannot source.
        self.procedural = CuratedProceduralPeriods()
        # LB-125. IT READS THE MANIFEST, the curated assertion of intended
        # coverage, at the moment it is asked -- so the day the Telangana
        # schedule is ingested the forum, valuation and court-fee rows answer
        # differently with nothing here edited. A manifest that cannot be read
        # measures nothing and says so, rather than reading as an empty one.
        self.filing = CuratedFilingRequirements(self.root / "pipeline" / "manifest.yaml")
        self.governing = CuratedGoverningLaw()
        self.engine = TurnEngine(store=self.store, evidence=self.evidence,
                                 model=self.model, coverage=self.coverage,
                                 elements=self.elements,
                                 pre_institution=self.pre_institution,
                                 authority_weight=self.authority_weight,
                                 interim_relief=self.interim_relief,
                                 procedural=self.procedural,
                                 filing=self.filing,
                                 professional_approval=self.directory.professional_approval,
                                 sections=self.sections)

        self.documents = None
        from nm.open_matter.document_permission import build_quarantine

        document_checker = build_quarantine(document_quarantine, document_quarantine_processor,
                                            self._gate)
        derivative_adapter = document_derivatives
        if (derivative_adapter is None and self.uploads is not None
                and isinstance(self.store.inner, FileMatterStore)):
            derivative_adapter = self.store.inner.document_storage()
        if self.uploads is not None and derivative_adapter is not None:
            from nm.open_matter.document_local import LocalDocumentText
            from nm.open_matter.document_text_port import DOCUMENT_PROCESSOR, DocumentTextPort
            from nm.open_matter.documents_api import DocumentService
            from nm.open_matter.matter_documents_port import DocumentDerivativePort

            parser = PolicedPort(inner=document_text or LocalDocumentText(),
                gate=self._gate, port=DocumentTextPort, sink=Sink.MEDIA,
                processor_id=DOCUMENT_PROCESSOR,
                data_classes=(DataClass.CLIENT_MATTER, DataClass.RESTRICTED),
                weigh=lambda args, kwargs: len(
                    kwargs.get("document", args[0] if args else None).data))
            derivatives = PolicedPort(inner=derivative_adapter, gate=self._gate,
                port=DocumentDerivativePort, sink=Sink.STORAGE,
                processor_id=STORAGE_PROCESSOR,
                data_classes=(DataClass.CLIENT_MATTER, DataClass.RESTRICTED))
            self.documents = DocumentService(self.uploads, derivatives, parser,
                                              quarantine=document_checker)

    def browser_asset_paths(self) -> Mapping[str, Path]:
        """The immutable shipped browser population, never a matter-data root.

        HTTP only renders these paths. Source-layout loading/reconciliation
        belongs to trusted composition and is not an edge dependency.
        """
        if not hasattr(self, "_browser_asset_paths"):
            from nm.shared.source_layout import browser_assets

            self._browser_asset_paths = MappingProxyType(browser_assets(root=ROOT))
        return self._browser_asset_paths

    def documents_for(self, *, session_current):
        """A request-bound local reader; no missing scanner is treated as clean."""
        if self.documents is None:
            return None
        from nm.open_matter.documents_api import DocumentService

        return DocumentService(self.documents.uploads, self.documents.derivatives,
            self.documents.parser, quarantine=self.documents.quarantine,
            bounds=self.documents.bounds, session_current=session_current)

    def source_generation_guard(self):
        """The actual small source/table binding, never a caller-authored label."""
        from nm.legal_brain.orchestrate.controlled_generations import GenerationGuard

        manifest_path = (self._published_snapshot.member_path("corpus/manifest.yaml")
                         if self._published_snapshot else self.root / "pipeline" / "manifest.yaml")
        from nm.shared.source_layout import ROOT as CODE_ROOT
        from nm.shared.source_layout import source_paths

        return GenerationGuard(knowledge_root=CODE_ROOT / "nm",
            knowledge_paths=lambda: source_paths("knowledge"),
            manifest_path=manifest_path, snapshot=self._published_snapshot)

    def checklist_source_current_for(self, matter_id: str, advocate_id: str, *,
                                     expected_version: int,
                                     session_current: Callable[[], bool],
                                     generation_guard=None):
        """Request-bound cached law; missing source evidence never becomes a tick."""
        from nm.legal_brain.orchestrate.controlled_generations import (
            GenerationGuard,
            GenerationUnavailable,
        )
        from nm.legal_brain.retrieve.checklist_sources import bind_source_current

        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("A checklist projection names its exact captured file version")

        def owned_current():
            matter = self.store.load(matter_id)
            return bool(matter and matter.advocate_id == advocate_id
                        and matter.version == expected_version)

        if generation_guard is None:
            try:
                guard = self.source_generation_guard()
            except GenerationUnavailable:
                # The file remains readable. Only source-current certification is
                # unavailable, and every dependent candidate remains unresolved.
                return lambda _source, _generation: False
        elif isinstance(generation_guard, GenerationGuard):
            guard = generation_guard
        else:
            raise ValueError("A checklist source owner needs its actual generation guard")
        return bind_source_current(self.evidence, guard,
            owned_current=owned_current, session_current=session_current)

    def engine_for(self, advocate_id: str, *,
                   session_current: Callable[[], bool] | None = None) -> TurnEngine:
        """Authenticated turn route; generic tooling remains deny-by-default."""
        if not isinstance(self._model_adapter, OpenAIModelAdapter):
            return self.engine
        bound = self._model_for(advocate_id, session_current=session_current)
        return TurnEngine(store=self.store, evidence=self.evidence, model=bound,
                          coverage=self.coverage, elements=self.elements,
                          pre_institution=self.pre_institution,
                          authority_weight=self.authority_weight,
                          interim_relief=self.interim_relief,
                          procedural=self.procedural,
                          filing=self.filing,
                          professional_approval=self.directory.professional_approval,
                          sections=self.sections)

    def _model_for(self, advocate_id: str, *, session_current: Callable[[], bool] | None):
        """One authenticated external-text dispatch owner for both reasoning paths."""
        if not isinstance(self._model_adapter, OpenAIModelAdapter):
            return self.model
        from nm.app.model_permission import bind_text_model

        return bind_text_model(self._model_adapter, directory=self.directory,
            account_id=advocate_id, config=self.config,
            session_current=session_current, audit=self._egress_audit)

    def controlled_brain_for(self, scope, *, session_current: Callable[[], bool],
                             cost_ceiling: Callable[[int, int, Tier], float],
                             source_version: str, table_version: str,
                             reviewer=None, review_interactions: bool = False,
                             controlled_model=None, interaction_protocol_version=1):
        """Trusted bounded evaluation composition; never a client cutover switch.

        A caller must supply its attributed finite scope and exact corpus/table
        generations. API/model parameters cannot approve their own matter IDs.
        The same account permission wraps every model dispatch, not just startup.
        No external filing, settlement, media release or legal approval is a tool.
        """
        from nm.legal_brain.common.principles_file_adapter import FilePrinciples
        from nm.legal_brain.orchestrate.controlled_brain import ControlledBrain, EvaluationScope
        from nm.legal_brain.orchestrate.controlled_generations import GenerationUnavailable
        from nm.legal_brain.orchestrate.controlled_registry_composition import (
            ControlledRegistryPorts,
            assemble_controlled_registry,
        )
        from nm.legal_brain.orchestrate.tool_catalogue import PracticeTables
        from nm.legal_brain.orchestrate.tools import Boundary
        from nm.legal_brain.procedure.reviewed_limitation_selection import (
            LimitationSelectionReviewService,
        )
        from nm.legal_brain.understand import parties
        from nm.legal_brain.understand.advocate_memory import preference_context
        from nm.legal_brain.verify import output_checks
        from nm.legal_brain.verify.brain_assessment import AssessmentService
        from nm.legal_brain.verify.brain_finalization import FinalizationService, SavedCheckReader
        from nm.legal_brain.verify.brain_publication import PrivatePublicationService
        from nm.legal_brain.verify.checklist_review import ChecklistReviewService
        from nm.legal_brain.verify.interaction_review import (
            COMMUNICATION_PROTOCOL_VERSIONS,
            InteractionReviewService,
        )
        from nm.legal_brain.verify.interaction_subject import InteractionSubjectOwner
        from nm.open_matter import screens
        from nm.open_matter.commission_contracts import Commission
        from nm.shared.authority_contracts import Act, capacity_for, permits
        from nm.shared.store_loop_log import MatterLoopLog

        if not isinstance(scope, EvaluationScope) or not session_current():
            raise PermissionError("No current session and trusted controlled scope")
        if type(review_interactions) is not bool or review_interactions and reviewer is None:
            raise ValueError("Interaction review needs its trusted independent reviewer")
        if (type(interaction_protocol_version) is not int
                or interaction_protocol_version not in COMMUNICATION_PROTOCOL_VERSIONS):
            raise ValueError("Interaction review uses an explicit owned protocol version")
        generations = self.source_generation_guard()
        from nm.legal_brain.retrieve.checklist_sources import (
            bind_source_current,
            bind_window_current,
        )

        def sources_owned():
            # This callback receives public law, not case material. Exact active
            # file/version checks remain with the caller; no foreign file may
            # enter even the installation's finite controlled population.
            return all((matter := self.store.load(matter_id)) is not None
                       and matter.advocate_id == scope.advocate_id
                       for matter_id in scope.matter_ids)

        source_current = bind_source_current(self.evidence, generations,
            owned_current=sources_owned, session_current=session_current)
        window_current = bind_window_current(self.evidence, generations,
            owned_current=sources_owned, session_current=session_current)

        def boundary(context, act):
            try:
                generations.require_current()
            except GenerationUnavailable:
                return Boundary(False, "The admitted legal sources or practice tables changed.")
            if not session_current() or context.identity.matter_id not in scope.matter_ids:
                return Boundary(False,
                                "The session or controlled matter scope no longer permits work.")
            matter = self.store.load(context.identity.matter_id)
            if (matter is None or matter.advocate_id != scope.advocate_id
                    or context.identity.advocate_id != scope.advocate_id
                    or matter.version != context.current_version):
                return Boundary(False,
                                "The complete checked file is not available at this version.")
            commission = Commission.from_stored(matter.commission)
            acting_as = capacity_for(scope.advocate_id, matter.authority_bindings,
                                     commission.version if commission else 0, utcnow())
            ruling = permits(scope.advocate_id, acting_as, act)
            return Boundary(ruling.authorises(), ruling.why)

        tables = PracticeTables(version=table_version, elements=self.elements,
                                institution=self.pre_institution, interim=self.interim_relief,
                                procedural=self.procedural, filing=self.filing,
                                governing=self.governing)
        model = self._model_for(scope.advocate_id, session_current=session_current)
        if controlled_model is not None:
            # Only the trusted finite evaluation grant supplies this already
            # permission-bound author. Ordinary TurnEngine composition is not
            # changed to consume the evaluation ledger or verifier allowance.
            model = controlled_model
        from nm.legal_brain.retrieve.practice_playbooks_adapter import FilePracticePlaybooks

        playbooks = FilePracticePlaybooks()
        playbook_snapshot = playbooks.load()
        principles = FilePrinciples(playbooks=playbooks)
        document_reader = self.documents_for(session_current=session_current)

        tool_assembly = assemble_controlled_registry(
            store=self.store,
            ports=ControlledRegistryPorts(
                evidence=self.evidence, manifest=self.manifest, search=self.search,
                tables=tables, authority_weight=self.authority_weight,
                matter_documents=document_reader, model=model, principles=principles,
                playbooks=playbooks, playbook_snapshot=playbook_snapshot),
            boundary=boundary, generations=generations, source_version=source_version,
            source_current=source_current, window_current=window_current,
            cost_ceiling=cost_ceiling, reviewer=reviewer)
        registry = tool_assembly.registry
        working_owner = tool_assembly.working_owner
        interest_owner = tool_assembly.interest_owner
        interest_reviews = tool_assembly.interest_reviews
        fee_owner = tool_assembly.fee_owner
        fee_reviews = tool_assembly.fee_reviews

        def document_current(matter, span):
            # Re-open through the owned local service, not metadata equality or
            # a model's assertion that the uploaded document remains readable.
            from nm.legal_brain.reason.matter_support import REFERENCE_KEYS
            from nm.open_matter.matter_documents_port import DocumentRefused
            from nm.open_matter.upload_port import UploadRefused
            from nm.shared.storage_errors_port import (
                StoredObjectScopeRefused,
                StoredObjectUnreadable,
            )

            if document_reader is None:
                return False
            try:
                span.validate()
                quote = document_reader.quote(matter.id, matter.advocate_id, matter.version,
                                              **{key: span.source[key] for key in REFERENCE_KEYS})
            except (DocumentRefused, UploadRefused, StoredObjectScopeRefused,
                    StoredObjectUnreadable, OSError):
                return False
            return quote == span.captured_quote

        if reviewer is not None:
            # Trusted installation composition supplies the ReviewService; its
            # document-current owner cannot be selected by model/HTTP data.
            reviewer.document_current = document_current
        if reviewer is not None and reviewer.store is not self.store:
            raise ValueError("Independent review must share this exact transactional matter store")
        log = (reviewer.log if reviewer is not None else
               MatterLoopLog(self.store, advocate_id=scope.advocate_id))

        def current_tools_version():
            try:
                generations.require_current()
            except GenerationUnavailable:
                return "generation_not_current"
            return registry.version

        def current_boundaries(matter, _outcome):
            commission = Commission.from_stored(matter.commission)
            acting_as = capacity_for(scope.advocate_id, matter.authority_bindings,
                                     commission.version if commission else 0, utcnow())
            # Only actual recorded/current owners contribute. A missing duty
            # assessment is not reconstructed from an intake permission.
            return output_checks.BoundarySubjects(
                screens=screens.from_stored(matter.screens),
                parties=parties.on_file(matter).names,
                authority=permits(scope.advocate_id, acting_as, Act.ADVISE))

        def current_observers(_matter, _outcome, _review):
            return output_checks.OutputSubjects(
                empty_reads=output_checks.observe_reads(model, "empty_decisive"),
                refused_reads=output_checks.observe_reads(model, "refused_reads"),
                coverage=output_checks.measured_coverage(self.coverage, FORUM),
                competence=output_checks.competence_screen(self.coverage, FORUM))

        assessment = AssessmentService(
            store=self.store, log=log, session_current=session_current,
            supplement=current_observers, boundaries=current_boundaries,
            current_tools_version=current_tools_version,
            current_principles_version=lambda: principles.load().version,
            document_current=document_current)
        finalizer = None
        interaction_review = None
        working_review = None
        working_scope = None
        working_explanations = None
        early_review = None
        input_continuations = None
        if reviewer is not None:
            from nm.legal_brain.orchestrate.checked_input_continuation import (
                CheckedInputContinuationService,
            )
            from nm.legal_brain.procedure.reviewed_limitation_selection import (
                prepare_limitation_selections,
            )
            from nm.legal_brain.reason.matter_support import captured_documents
            from nm.legal_brain.reason.working_record import WorkingRecordReviewService
            from nm.legal_brain.retrieve.tool_sources import findings_from_record
            from nm.legal_brain.verify.brain_release import ReviewRefused
            from nm.legal_brain.verify.early_independent_review import (
                EarlyIndependentReviewService,
                EarlyReviewSubject,
            )
            from nm.legal_brain.verify.working_scope import WorkingScopeService
            from nm.shared.clock_contracts import today as forum_today

            working_review = WorkingRecordReviewService(reviewer=reviewer, owner=working_owner)
            early_matter_ids = {}

            def early_subject(parent, matter, candidate_id):
                _inventory, annotations, packages = working_owner.candidates_for_record(
                    parent, matter)
                matching = [row for row in annotations if row.id == candidate_id]
                if len(matching) != 1:
                    raise ReviewRefused("There is no unique current recorded working candidate")
                package = next(row for row in packages if row.id == matching[0].package_id)
                # One sequential check, no growing private shadow register.
                early_matter_ids.clear()
                early_matter_ids[package.identity] = str(matter.id)
                return EarlyReviewSubject(package, findings_from_record(parent),
                                          captured_documents(parent))

            def early_sources_current(subject):
                matter_id = early_matter_ids.get(subject.package.identity)
                matter = self.store.load(matter_id) if matter_id is not None else None
                return (matter is not None and all(source_current(span.finding, source_version)
                            for span in (*subject.package.spans, *subject.package.contrary))
                    and all(matter is not None and document_current(matter, span)
                            for span in (*subject.package.documents,
                                         *subject.package.document_contrary)))

            early_review = EarlyIndependentReviewService(
                store=self.store, log=log, verifier=reviewer.verifier, subject_owner=early_subject,
                source_current=early_sources_current, session_current=session_current,
                current_tools_version=current_tools_version,
                current_principles_version=lambda: principles.load().version,
                cost_ceiling=cost_ceiling)
            tool_assembly.install_early(early_review)
            registry = tool_assembly.registry
            input_continuations = CheckedInputContinuationService(reviewer=reviewer,
                binding_owners={
                    "limitation": lambda outcome, matter: prepare_limitation_selections(
                        outcome, matter, source_generation=source_version,
                        source_current=source_current),
                    "interest": interest_owner.candidates,
                    "fee": fee_owner.candidates,
                }, current_tools_version=current_tools_version,
                current_principles_version=lambda: principles.load().version)
            working_scope = WorkingScopeService(owner=working_owner, working=working_review,
                reader=SavedCheckReader(store=self.store, log=log, model=reviewer.verifier.model,
                    session_current=session_current, cost_ceiling=cost_ceiling,
                    current_tools_version=current_tools_version,
                    current_principles_version=lambda: principles.load().version,
                    document_current=document_current, subject_packages=working_owner.packages,
                    max_tokens=4096))

            def current_authority(matter, _outcome):
                commission = Commission.from_stored(matter.commission)
                acting_as = capacity_for(scope.advocate_id, matter.authority_bindings,
                    commission.version if commission else 0, utcnow())
                return permits(scope.advocate_id, acting_as, Act.ADVISE)

            finalizer = FinalizationService(reader=SavedCheckReader(
                store=self.store, log=log, model=model, session_current=session_current,
                cost_ceiling=cost_ceiling, current_tools_version=current_tools_version,
                current_principles_version=lambda: principles.load().version,
                document_current=document_current),
                today=forum_today, jurisdiction=FORUM, coverage=self.coverage,
                authority=current_authority)
            from nm.legal_brain.communicate.working_explanation import WorkingExplanationService

            working_explanations = WorkingExplanationService(
                working=working_review, scope=working_scope, finalizer=finalizer,
                reader=SavedCheckReader(
                    store=self.store, log=log, model=reviewer.verifier.model,
                    session_current=session_current, cost_ceiling=cost_ceiling,
                    current_tools_version=current_tools_version,
                    current_principles_version=lambda: principles.load().version,
                    document_current=document_current, subject_packages=working_owner.packages,
                    max_tokens=4096))
            assessment.supplement = finalizer.subjects
            assessment.boundaries = finalizer.boundaries
            if review_interactions:
                interaction_owner = InteractionSubjectOwner(
                    principles=principles, source_current=source_current)
                interaction_review = InteractionReviewService(
                    owner=interaction_owner, protocol_version=interaction_protocol_version,
                    reader=SavedCheckReader(
                        store=self.store, log=log, model=reviewer.verifier.model,
                        session_current=session_current, cost_ceiling=cost_ceiling,
                        current_tools_version=current_tools_version,
                        current_principles_version=lambda: principles.load().version,
                        document_current=document_current,
                        subject_packages=interaction_owner.packages, max_tokens=2048))
        publication = (PrivatePublicationService(assessment=assessment, finalizer=finalizer)
                       if finalizer is not None else None)
        return ControlledBrain(
            store=self.store, model=model, principles=principles, log=log,
            registry=registry, scope=scope, cost_ceiling=cost_ceiling,
            session_current=session_current, reviewer=reviewer, assessment=assessment,
            finalizer=finalizer, publication=publication,
            interaction_review=interaction_review,
            interest_selection_review=interest_reviews,
            fee_selection_review=fee_reviews,
            working_review=working_review, working_scope=working_scope,
            working_explanations=working_explanations,
            early_review=early_review, input_continuations=input_continuations,
            working_preferences=lambda: preference_context(self.directory, scope.advocate_id),
            limitation_selection_review=LimitationSelectionReviewService(reviewer,
                source_generation=source_version, source_current=source_current)
                if reviewer is not None else None,
            checklist_review=ChecklistReviewService(reviewer, source_current=source_current)
                if reviewer is not None else None)

    def evaluate_private_work(self, **arguments):
        from nm.legal_brain.evaluate.controlled_evaluations_composition import evaluate

        return evaluate(self, now=utcnow, **arguments)

    def read_reviewed_private_source(self, **arguments):
        from nm.legal_brain.evaluate.controlled_evaluations_composition import (
            reviewed_preview_source,
        )

        return reviewed_preview_source(self, now=utcnow, **arguments)

    def read_reviewed_private_preview(self, **arguments):
        from nm.legal_brain.evaluate.controlled_evaluations_composition import reviewed_preview

        return reviewed_preview(self, now=utcnow, **arguments)

    def record_private_preview_seen(self, **arguments):
        from nm.legal_brain.evaluate.controlled_evaluations_composition import record_preview_seen

        return record_preview_seen(self, now=utcnow, **arguments)

    # ------------------------------------------------------------ P21 ------

    def binding_for(self, court: str | None, year: object):
        """Whether an authority's court binds THIS forum. THE EDGE ASKS HERE.

        `nm.edge` may not import `nm.knowledge` (layercheck), and the rule is
        a knowledge-plane fact -- binding is a relationship between the
        deciding court and the forum, measured in `jurisdiction.py`. Exposing
        it through the composition root keeps one owner of the rule and no
        provider knowledge on the serving path.
        """
        from nm.legal_brain.retrieve.jurisdiction_sources import binding_status

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

        from nm.legal_brain.retrieve.manifest_sources import (
            CorpusDependency,
            record_corpus_dependency,
        )

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
            # WHERE A PASSWORD-RESET LINK ACTUALLY GOES. A queued message is not
            # a delivered one, and an installation that writes reset links to a
            # local outbox must say so here rather than let a locked-out
            # advocate wait for an email that no mailbox will receive.
            "account_mail": ("mailbox transport enabled -- receipt not verified"
                             if getattr(self.mail, "delivers_to_mailbox", False)
                             else ('LOCAL OUTBOX ONLY -- account messages are not '
                                   'delivered to a mailbox'
                                   if getattr(self.mail, 'delivery_mode', '') == 'local_outbox_only'
                                   else 'DISABLED -- no account messages are sent')),
            # WHETHER THE MIC CAN WORK, before an advocate presses it and finds
            # out (F-C-02). Read from the adapter; the model is never loaded to
            # answer.
            "dictation": (self.transcriber.inner.readiness()
                          if hasattr(self.transcriber.inner, "readiness")
                          else "not assessed -- this speech adapter reports no readiness"),
            # AND WHETHER THE WORDS CAN APPEAR WHILE THEY SPEAK (F-C-03),
            # separately: live words can be off while dictation itself works.
            "dictation_live": (self.live_dictation.inner.readiness()
                               if hasattr(self.live_dictation.inner, "readiness")
                               else "not assessed -- this live adapter reports no readiness"),
            "corpus": "readable" if self.evidence.available else "NOT READABLE",
            # LB-106. WHETHER THE BARE-ACT SEARCH CAN RUN, said before a turn relies on it.
            "section_search": (self.sections.readiness() if self.sections is not None
                               else "not configured -- no bare-act search index here"),
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

    AND THE COMPARISON ITSELF IS NOT MADE HERE. `deployment.shares_value_with`
    is the one owner of "do these hold the same string", and it answers by
    digest: a check that compared plaintext would hold both values beside each
    other, and P39 has to ask the same question over a candidate's secret
    sources without a second copy of the rule. WHICH NAMES COUNT AS
    CREDENTIALS stays here, because that is composition's policy about this
    environment rather than a fact about secrets.
    """
    env = os.environ if env is None else env
    if not key.strip():
        return                     # an unset key is a different defect
    population = {name: value for name, value in env.items()
                  if name != _SEAL and _CREDENTIAL_NAME.search(name)}
    population[_SEAL] = key
    shared = sorted(shares_value_with(_SEAL, population))
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
