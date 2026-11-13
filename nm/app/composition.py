"""Compose the served application with the existing authenticated, sealed adapters."""
from __future__ import annotations
import logging
import os
import re
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from nm.arrive.admin_access import Level, roster_from
from nm.arrive.admin_directory import AdminFileDirectory
from nm.arrive.admin_checks import AdminChecks
from nm.arrive.admin_library import AdminLibrary
from nm.arrive.admin_port import (UNWRITTEN_LOG_LINES, AdminAccountsPort, AdminChecksPort, AdminDirectoryPort, AdminLibraryPort,
                                  AdminRecordPort, AdminStagingPort, AdminTurnsPort, AdminUsagePort)
from nm.arrive.admin_staging import AdminStaging
from nm.arrive.admin_turns import AdminTurns
from nm.arrive.admin_usage import AdminUsage
from nm.arrive.advocate_contracts import utcnow
from nm.arrive.directory_port import DirectoryPort
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.mail_port import MailPort
from nm.arrive.store_admin import FileAdminRecord
from nm.arrive.store_directory import FileDirectory
from nm.arrive.store_turn_events import FileTurnEvents
from nm.arrive.store_usage import FileUsage
from nm.arrive.turn_event_port import TurnEventPort, TurnEventRefused
from nm.arrive.usage_port import AllowanceUsedUp, UsagePort, UsageRefused
from nm.shared.deployment_contracts import shares_value_with
from nm.shared.egress_contracts import DataClass, EgressRefused, Gatekeeper, Sink
from nm.shared.egress_log_store import EgressLog, keep_days_from
from nm.shared.egress_policy import INDEX_PROCESSOR, OUTBOX_PROCESSOR, STORAGE_PROCESSOR, egress_policy
from nm.shared.model_config import AUTO_TURN, DEFAULT_TURN_MODEL, TURN_MODELS, load, load_dotenv
from nm.shared.model_metered import MeteredModel
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_policed import PolicedModel
from nm.shared.model_port import USAGE_LIMIT_MESSAGE, ModelPort, ProviderUnavailable, Tier
from nm.shared.model_traced import TracedModel
from nm.shared.policed_port_adapter import PolicedPort
from nm.shared.source_layout import browser_assets
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_port import StorePort
from nm.shared.turn_attempt_port import TurnAttemptPort
from nm.shared.turn_attempt_store import FileTurnAttempts
from nm.core_engine.retrieval import HybridSearcher, SearchPort
from nm.core_engine.citations import CaseIdentityIndex
from nm.app.step_jobs import AT_ONCE, PER_ADVOCATE, StepJobs, count_from, wait_from
from nm.app.turn_progress import TurnProgress

ROOT = Path(__file__).resolve().parents[2]
_CREDENTIAL_NAME = re.compile(r'KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL', re.I)
_SEAL = 'NM_MATTER_KEY'
_DEFAULT_SEARCH = object()
#: Each account's usage of the paid AI service, beside the turn attempts (plan AN.17).
USAGE_FILE = 'usage.sqlite'
#: What the Admin area did and who just confirmed their password (plan AN.46, piece 46g).
ADMIN_FILE = 'admin.sqlite'
#: One content-free line per finished turn (plan AN.46, piece 46h; owner decision D120).
TURN_EVENTS_FILE = 'turn-events.sqlite'


def storage_root(settings: Mapping[str, str], root: Path) -> Path:
    """Where this installation keeps its records: NM_MATTER_STORE, or .nm under its root. One rule,
    read by the application and by an operator command that needs one store and not the rest."""
    return Path(settings.get('NM_MATTER_STORE') or Path(root) / '.nm')

def build_model(config):
    provider = config.for_tier(Tier.ROUTINE).provider
    if provider == 'openai':
        return OpenAIModelAdapter(config)
    if provider == 'anthropic':
        from nm.shared.model_anthropic_adapter import AnthropicModelAdapter
        return AnthropicModelAdapter(config)
    raise ValueError('Scripted evaluation requires an explicitly injected model adapter.')

class Application:
    def __init__(self, *, root: Path | None = None, model: ModelPort | None = None,
                 store=None, directory=None, mail=None, legal_search=_DEFAULT_SEARCH,
                 environment: Mapping[str, str] | None = None,
                 audit_root: Path | None = None, steps: str | None = None):
        """steps (plan AN.48, 48f4): where this process stands to the steps - "inside" (it works them, as always), "web" (a web
        server whose steps the step worker works) or "worker" (that worker); None: as NM_STEP_WORKER says ("separate": web)."""
        if environment is None:
            load_dotenv(ROOT / '.env')
        settings = MappingProxyType(dict(os.environ if environment is None else environment))
        self.environment = settings
        self.root = root or ROOT
        self.audit_root = Path(audit_root) if audit_root is not None else self.root / '.nm'
        # The outgoing-data log (plan AN.48, D169): one file a day in the audit root, kept a year; swept by the processes that
        # serve (nm/app/main.py, nm/app/step_worker.py), never by building an application.
        self.egress_log = EgressLog(self.audit_root, keep_days=keep_days_from(settings.get('NM_EGRESS_LOG_KEEP_DAYS')))
        self.config = load(dict(settings))
        key = settings.get('NM_MATTER_KEY') or _ensure_local_key(self.root)
        _refuse_a_shared_seal(key, settings)
        self._gate = Gatekeeper(policy=egress_policy(self.root), audit=self._egress_audit)
        storage = storage_root(settings, self.root)
        # Plan AN.53 (53e, D220): where a line the outgoing-data log could not take is counted - in the store, since the log's
        # own folder is the one that failed - one time and nothing else a line, for the Admin diagnostics.
        self._log_unwritten, self._log_failure_said = Path(storage) / UNWRITTEN_LOG_LINES, False
        raw_store = store or FileMatterStore(storage, key=key)
        self.store = PolicedPort(inner=raw_store,
            gate=self._gate, port=StorePort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR)
        # An advocate's documents (owner decisions, 15 Oct 2026): checked by ClamAV,
        # read on this installation, sealed under the advocate's own key.
        self.documents = _document_desk(raw_store, storage, self._gate, settings)
        self.turn_attempts = PolicedPort(inner=_DeferredAdapter(
            lambda: FileTurnAttempts(storage / 'turn-attempts.sqlite')),
            gate=self._gate, port=TurnAttemptPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        # Each account's usage of the paid AI service and the allowance it draws on (owner decision
        # O24, plan AN.17): content-free, beside the turn attempts.
        self.usage = PolicedPort(inner=_DeferredAdapter(
            lambda: FileUsage(storage / USAGE_FILE)),
            gate=self._gate, port=UsagePort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        # One content-free line when each turn ends (plan AN.46, piece 46h; owner decision D120), in a sidecar of its own.
        self.turn_events = PolicedPort(inner=_DeferredAdapter(lambda: FileTurnEvents(storage / TURN_EVENTS_FILE)),
            gate=self._gate, port=TurnEventPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        self.directory = PolicedPort(inner=directory or FileDirectory(storage, key=key),
            gate=self._gate, port=DirectoryPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        # The Admin area (plan AN.46, D117-D119, D126): who the settings name as admins, and three narrow ports of its own that only
        # the Admin routes are given - the sign-in edge's directory port still cannot list accounts (A1).
        self.admin_roster = roster_from(settings)
        self.admin_directory = PolicedPort(inner=_DeferredAdapter(lambda: AdminFileDirectory(storage, key=key)),
            gate=self._gate, port=AdminDirectoryPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        # What an admin may change about an account itself (D116, D121): the same directory files, through a port that can only suspend
        # an account and end its sessions.
        self.admin_accounts = PolicedPort(inner=_DeferredAdapter(lambda: AdminFileDirectory(storage, key=key)),
            gate=self._gate, port=AdminAccountsPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        self.admin_usage = PolicedPort(inner=AdminUsage(storage / USAGE_FILE),
            gate=self._gate, port=AdminUsagePort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        self.admin_turns = PolicedPort(inner=AdminTurns(storage / TURN_EVENTS_FILE),
            gate=self._gate, port=AdminTurnsPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        checks = AdminChecks(storage=storage, root=self.root, settings=settings)
        self.admin_checks = PolicedPort(inner=checks,
            gate=self._gate, port=AdminChecksPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        # What the held law holds, described (plan AN.46, piece 46l): read from the store's own records and catalogue, never opened.
        library = AdminLibrary(checks=checks, root=self.root, corpus_dir=checks.corpus)
        self.admin_library = PolicedPort(inner=library,
            gate=self._gate, port=AdminLibraryPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        # Acts an admin has staged for the library (plan AN.46, pieces 46m and 46o): in a folder of their own, read free, never appended here.
        self.admin_staging = PolicedPort(inner=AdminStaging(storage / 'admin-staging', root=self.root, held=library.held_act_ids),
            gate=self._gate, port=AdminStagingPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        self.admin_record = PolicedPort(inner=_DeferredAdapter(lambda: FileAdminRecord(storage / ADMIN_FILE)),
            gate=self._gate, port=AdminRecordPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        # Account mail through the gate that admits its sender: NM's own for the outbox, the owner's Gmail exception's (D168).
        mail_adapter, processor, mail_gate = ((mail, OUTBOX_PROCESSOR, self._gate) if mail is not None else
                                              build_mail(settings, storage, key, self._gate))
        self.mail = PolicedPort(inner=mail_adapter, gate=mail_gate, port=MailPort,
            sink=Sink.MAIL, processor_id=processor,
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        self._model_adapter = model if model is not None else build_model(self.config)
        budget_path = settings.get('NM_EVAL_BUDGET_FILE')
        if budget_path:
            if not isinstance(self._model_adapter, OpenAIModelAdapter):
                raise ValueError('A live evaluation budget requires the OpenAI adapter.')
            from nm.shared.model_call_budget import SessionCallBudget
            # Every model an advocate may choose for a turn may run in a bounded session too (plan AN.33, D23).
            models = tuple(dict.fromkeys([*(c.model for tier, c in self.config.tiers.items() if tier is not Tier.EMBED),
                                          *(model for model, _, _ in TURN_MODELS)]))
            self._model_adapter = self._model_adapter.with_call_budget(SessionCallBudget(
                Path(budget_path), settings.get('NM_EVAL_MAX_USD', '25'), models=models))
        # Configuration is not corpus readiness; models and indices load on demand.
        # Explicit None supports isolated flows without making provider-specific choices.
        search = (HybridSearcher.local(root=self.root,
            corpus_dir=settings.get('NM_CORPUS_DIR')) if legal_search is _DEFAULT_SEARCH else legal_search)
        # The held-law index is a destination too: each query carries the advocate's words.
        # In this process, but policed like every other destination (open items round, 16 Oct 2026).
        self.legal_search = None if search is None else PolicedPort(inner=search, gate=self._gate,
            port=SearchPort, sink=Sink.INDEX, processor_id=INDEX_PROCESSOR,
            data_classes=(DataClass.CLIENT_MATTER,))
        self.case_index = _DeferredAdapter(lambda: CaseIdentityIndex.local(self.root))
        # Plan AN.48 (48f4, D167): where this process stands to the steps, and, where they run in a worker process of their own,
        # what it shares with the other (sealed under the installation's key, as conversations are).
        from nm.app import step_worker
        self.steps_mode = steps if steps in step_worker.MODES else step_worker.mode_from(settings.get('NM_STEP_WORKER'))
        self.step_share = None
        if self.steps_mode != 'inside':
            from nm.shared.step_share_port import StepSharePort
            from nm.shared.step_share_store import FileStepShare
            from nm.shared.store_file_store import _Cipher
            self.step_share = PolicedPort(inner=_DeferredAdapter(lambda: FileStepShare(storage / 'step-share.sqlite', _Cipher(key))),
                gate=self._gate, port=StepSharePort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
                data_classes=(DataClass.CLIENT_MATTER, DataClass.OPERATIONAL))
        # What each running turn is doing, for its own advocate (memory only; 48f4: the worker's, told to the web server).
        self.turn_progress = (TurnProgress() if self.steps_mode == 'inside' else
                              step_worker.SharedProgress(self.step_share) if self.steps_mode == 'web' else
                              step_worker.MirroredProgress(self.step_share))
        # Plan AN.48 (48f1, D167): the steps this server works on its own step threads, and how long a request waits for one;
        # 48f2: how many work at once, and for one advocate - each step that waits for a place told its place in its progress.
        # 48f4: a web server hands them to the worker and waits for them the same while.
        wait = wait_from(settings.get('NM_STEP_WAIT_SECONDS'))
        self.step_jobs = (step_worker.RemoteSteps(self.step_share, wait_seconds=wait) if self.steps_mode == 'web' else
                          StepJobs(wait_seconds=wait, at_once=count_from(settings.get('NM_STEPS_AT_ONCE'), AT_ONCE),
                                   per_advocate=count_from(settings.get('NM_STEPS_PER_ADVOCATE'), PER_ADVOCATE)))
        self.step_jobs.placed = lambda advocate_id, turn_id, ahead: self.turn_progress.report(
            advocate_id, turn_id, 'queued', {'ahead': ahead})
        # A step that waited and was then refused as it began, before its run said anything, says working no longer.
        self.step_jobs.settled = lambda advocate_id, turn_id: self.turn_progress.end(advocate_id, turn_id, 'stopped')
        # 48f3: what each step is, kept content-free beside the turn attempts, so that the next start takes up what this run left.
        from nm.shared.step_record_port import StepRecordPort
        from nm.shared.step_record_store import FileStepRecords
        self.step_records = PolicedPort(inner=_DeferredAdapter(lambda: FileStepRecords(storage / 'step-records.sqlite')),
            gate=self._gate, port=StepRecordPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        self.step_jobs.records = self.step_records
        # The Acts time limits may be worked out under (owner decisions, 15 Oct 2026).
        from nm.shared.held_acts import HeldActs
        self.held_acts = HeldActs(settings.get('NM_BARE_ACTS_DIR')
                                  or self.root / 'legal_database' / 'raw_data' / 'BareActs')
        # Voice notes and dictation (owner decisions, 15 Oct 2026).
        self.transcription_model = (settings.get('NM_TRANSCRIBE_MODEL') or 'gpt-transcribe').strip()
        # Live words while dictating, only for an advocate who turns them on (owner, 15 Oct 2026).
        self.live_transcription_model = (settings.get('NM_LIVE_TRANSCRIBE_MODEL') or 'gpt-live-transcribe').strip()
        # Plan AN.37 (D37-D40): the windows of questions turns have open, and what proposes the questions (piece 37d).
        from nm.core_engine import questions
        # 48f4: a web server reads the worker's windows and hands it the answers; the worker shows the windows it opens.
        self.questions = (QuestionDesk() if self.steps_mode == 'inside' else step_worker.SharedDesk(self.step_share)
                          if self.steps_mode == 'web' else MirroredDesk(self.step_share))
        self.propose_questions = questions.propose
        # Plan AN.41-AN.42: the turns this process is working on, each with the advocate's Stop and the steers waiting for it.
        self._running, self._running_lock = {}, threading.Lock()

    def admin_level_of(self, advocate_id):
        """The Admin level of a signed-in account, or None for an advocate (AN.46; owner, 7 Nov 2026). The server's settings name the
        first admins, at either level, and cannot be changed from the page; any other account is an admin when an admin has set that
        as its user type. One answer for the page's gate, every Admin route and the user lists."""
        named = self.admin_roster.level_of(advocate_id)
        if named is not None:
            return named
        return Level.ADMIN if self.directory.user_type(advocate_id) == 'admin' else None

    def turns_of_an_earlier_run_released(self):
        """At the server's start (plan AN.41, D73): every turn the earlier run of it was working on has stopped with it, and is
        made able to continue - by itself as soon as its advocate's page is back, or by Continue. Returns how many."""
        return self.turn_attempts.release_ended("interrupted")

    def _model_for(self, advocate_id, *, session_current, page_images=False, audio_model=None, text_model=None):
        # Every call made for an advocate is metered against their account (plan AN.17), on either route.
        record = lambda call: self.usage.record(advocate_id, call)  # noqa: E731
        # What is left is asked again before every call is sent (plan AN.37, D42), not only before the work starts.
        before = lambda: self._require_allowance(advocate_id)  # noqa: E731
        if isinstance(self._model_adapter, OpenAIModelAdapter):
            from nm.app.model_permission import bind_text_model
            model = bind_text_model(self._model_adapter, directory=self.directory,
                account_id=advocate_id, config=self.config,
                session_current=session_current, audit=self._egress_audit,
                page_images=page_images, audio_model=audio_model, record=record, text_model=text_model,
                before=before)
        else:
            # Fresh tracing per request prevents parallel conversations sharing traces.
            model = PolicedModel(inner=TracedModel(inner=MeteredModel(inner=self._model_adapter, record=record,
                                                                      before=before)),
                policy=self._gate.policy, audit=self._egress_audit,
                authorize=lambda: _require_session(session_current))
        # After the permission, so an advocate who has not allowed AI sharing is told that first.
        self._require_allowance(advocate_id)
        return model

    def _require_allowance(self, advocate_id):
        """Once nothing is left, new paid work is refused (owner, O24: "Once nothing is left"): before it
        starts - a turn's first call, a reading of pages, a voice note, dictation, live dictation - and, from
        plan AN.37 (D42, D46), before each further call it would send, so a turn stops in the middle once the
        allowance runs out. Raised as the usage limit, in the owner's words of P51, so each says it as it says
        the provider's. A call already sent finishes and is charged; a saved answer reopens without coming here."""
        try:
            left = self.usage.standing(advocate_id)['left']
        except UsageRefused as exc:
            # Unknown usage is never free usage.
            raise ProviderUnavailable("This account's usage could not be checked.") from exc
        if left <= 0:
            raise AllowanceUsedUp(USAGE_LIMIT_MESSAGE)

    def document_reader(self, advocate_id, *, session_current):
        """The model that reads one advocate's scanned pages and transcribes their voice
        notes (owner decisions, 15 Oct 2026), under that advocate's current permission
        and session."""
        return self._model_for(advocate_id, session_current=session_current, page_images=True,
                               audio_model=self.transcription_model)

    def dictation_reader(self, advocate_id, *, session_current):
        """The model that transcribes one advocate's dictation; nothing else leaves."""
        return self._model_for(advocate_id, session_current=session_current,
                               audio_model=self.transcription_model)

    def live_dictation_reader(self, advocate_id, *, session_current):
        """The live speech model, for an advocate who turned live words on."""
        return self._model_for(advocate_id, session_current=session_current,
                               audio_model=self.live_transcription_model)

    def run_turn(self, *, advocate_id, session_current, document_refs=(), model_choice=None, effort=None, steps=None, go=None,
                 **request):
        """One turn for an advocate. model_choice and effort: what they chose for it (plan AN.33, D23) - the model every text call
        of the turn runs on, and how hard each reasons; None: as configured, at the table's own levels. steps (plan AN.48, 48a):
        "interactive" - the message is worked step by step, stopping for the advocate's go-ahead after each step; anything else -
        end to end, as before. go: the go-ahead of a matter already worked step by step (go_turn, continue_turn)."""
        from nm.core_engine import routing, steps as stepwise, titles
        from nm.core_engine.turn import process

        if go is None and steps == 'interactive':
            go = stepwise.first()

        if document_refs:
            # The documents sent with the message, read from this advocate's own space;
            # refused plainly, never cut, when one cannot be used.
            from nm.core_engine import documents
            if self.documents is None:
                raise documents.DocumentRefused("Documents cannot be read on this installation.")
            request["documents"] = documents.turn_material(
                [self.documents.load(advocate_id, ref) for ref in document_refs])

        # Saved replay performs no provider work. Permission/model construction
        # belongs to the first fresh model operation, not to receipt readback.
        # Plan AN.38 (D47-D49): Auto runs every call on 6 Luna and moves one to the stronger model where the turn's own evidence
        # says so; that model is bound, under the same permission and allowance, only if a call moves to it.
        auto = model_choice == AUTO_TURN
        model = _DeferredAdapter(lambda: self._model_for(advocate_id, session_current=session_current,
                                                         text_model=DEFAULT_TURN_MODEL if auto else model_choice))
        stronger = (_DeferredAdapter(lambda: self._model_for(advocate_id, session_current=session_current,
                                                             text_model=routing.STRONGER)) if auto else None)
        turn_id, reported = request.get('turn_id'), []

        def progress(stage, **detail):
            reported.append(stage)
            if stage == 'shown':  # the answer showed more (owner decisions P26-P27)
                self.turn_progress.shown(advocate_id, turn_id, detail.get('shown'), detail.get('chat_id'))
                return
            if stage == 'tentative':  # plan AN.48 (48e): how long the step should take, said while it runs
                self.turn_progress.tentative(advocate_id, turn_id, detail.get('seconds'))
                return
            if stage in ('sent', 'saved'):  # the message, then the work finished, saved with the conversation (plan AN.41)
                self.turn_progress.saved(advocate_id, turn_id, detail.get('saved', 0), detail.get('chat_id'))
                return
            self.turn_progress.report(advocate_id, turn_id, stage, detail)

        # Plan AN.42 (D78-D79): this run's Stop and the steers waiting for it, reached while it works; a same-turn retry refused
        # while the first run works leaves the first run's alone.
        key, running = (advocate_id, turn_id), _Running()
        with self._running_lock:
            mine = key not in self._running
            if mine:
                self._running[key] = running
                # Plan AN.48 (48f2): a Stop pressed as this step began, before Stop could reach it here.
                if self.step_jobs.stop_asked(advocate_id, turn_id):
                    running.stop.set()
            else:
                running = self._running[key]
        ended, began, outcome, metrics, replayed = 'stopped', utcnow(), 'failed', None, False
        try:
            result = process(model, self.store, self.legal_search, advocate_id=advocate_id,
                             session_current=session_current, attempts=self.turn_attempts,
                             held_acts=self.held_acts,
                             case_index=self.case_index,
                             provision_reader=getattr(self.legal_search, 'collections', {}).get('provision'),
                             progress=progress, running=lambda held: self.turn_running(advocate_id, held),
                             chosen_model=model_choice, effort=effort, stronger=stronger,
                             propose=self.propose_questions, desk=self.questions.bound(advocate_id),
                             stopping=running.stop.is_set, steers=running.take, attach=running.attach,
                             # Plan AN.43 (D82): the conversation's title, on the turn's own model port - metered as any call.
                             entitle=lambda given: titles.entitle(model, given), go=go, **request)
            ended = 'finished'
            outcome = 'answered'
            if isinstance(result, Mapping):
                metrics, replayed = result.get('metrics'), bool(result.get('replayed'))
            return result
        except Exception as exc:
            outcome, metrics = _how_a_turn_ended(exc), getattr(exc, 'metrics', None)
            raise
        finally:
            if mine:
                with self._running_lock:
                    self._running.pop(key, None)
                if not replayed:  # reopening a saved answer is not a turn (plan AN.46, D120)
                    self._note_turn(advocate_id, began, outcome, metrics, model_choice, effort, len(document_refs or ()))
            # The window closes with the turn; an answer after it goes as the next message (plan AN.37, D44).
            self.questions.close(advocate_id, turn_id)
            # Only the run that did the work closes its progress: a same-turn retry
            # refused while the first run works must not mark that run stopped.
            if reported:
                self.turn_progress.end(advocate_id, turn_id, ended)

    def _note_turn(self, advocate_id, began, outcome, metrics, model_choice, effort, documents):
        """One content-free line when a turn ends (plan AN.46, piece 46h; owner decision D120): when, how long, how it ended, the model
        and effort chosen, the calls it made, what they cost, the documents sent. Its failure loses the line and nothing else: it never
        fails, delays or changes an answer, and only the kind of fault is logged."""
        try:
            calls = metrics.get('llm_calls') if isinstance(metrics, Mapping) else None
            cost = metrics.get('cost_usd') if isinstance(metrics, Mapping) else None
            self.turn_events.record(advocate_id, {
                'started_at': began, 'ended_at': max(utcnow(), began), 'outcome': outcome,
                'model': model_choice or 'default', 'effort': effort or 'default',
                'calls': calls if type(calls) is int and calls >= 0 else None,
                'micro_usd': round(cost * 1_000_000) if isinstance(cost, (int, float)) and cost >= 0 else None,
                'documents': documents})
        except (TurnEventRefused, EgressRefused, ValueError, TypeError) as exc:
            logging.getLogger('nm.turns').warning('A turn line could not be kept (%s).', type(exc).__name__)

    def _held(self, advocate_id, chat_id):
        """The conversation and the turn being worked on in it, as saved: (matter, held), held None where there is none."""
        from nm.core_engine.conversation import chat_matter_id, shown_of
        matter = self.store.load_for(chat_matter_id(advocate_id, chat_id), advocate_id)  # the store compares the owner (AN.53, 53b)
        if matter is None:
            return None, None
        try:
            return matter, shown_of(matter)
        except ValueError:
            return matter, None

    def continue_turn(self, *, advocate_id, chat_id, turn_id, session_current):
        """Continue (plan AN.41, D70; D73 by itself after a restart): the answer that stopped picks up where it stopped - the
        same message, files and choice of model and effort, sent again, which keeps each step it finished that still passes its
        check. ConversationRefused where that turn is not stopped in this conversation."""
        from nm.core_engine.conversation import ConversationRefused
        matter, held = self._held(advocate_id, chat_id)
        if held is None or held['turn_id'] != turn_id:
            raise ConversationRefused('There is no answer that stopped part-way to continue here.', status=404,
                                      code='nothing_to_continue')
        if self.turn_running(advocate_id, turn_id):
            raise ConversationRefused('NM is already working on this answer.', code='turn_in_progress')
        asked = held['request']
        # Plan AN.48 (48a5): a step of a matter worked step by step continues as the same step, under its own go-ahead.
        go = {**held['go'], 'waiting': None} if held.get('go') else None
        return self.run_turn(advocate_id=advocate_id, session_current=session_current,
                             document_refs=tuple(asked.get('document_refs', ())), model_choice=asked.get('model'),
                             effort=asked.get('effort'), message=held['message'], turn_id=turn_id,
                             chat_id=asked['chat_id'], go=go)

    def go_turn(self, *, advocate_id, chat_id, turn_id, choice, session_current, disputes=None):
        """The advocate's go-ahead at a stop (plan AN.48, 48a3, 48b): "research" or "write" - that step for the disputes named
        (None: every dispute it can now take, D163); "next" - the next step for every dispute; "end_to_end" - every remaining step
        without stopping (D135); "done" - finish with what is written and save it as one answer (D147), or, before any analysis is
        written, save the matter as it stands with no step run. ConversationRefused where the matter does not wait for the
        advocate here, or the go-ahead is not one its stop offers."""
        from nm.core_engine import steps as stepwise, turn
        from nm.core_engine.conversation import ConversationRefused
        matter, held = self._held(advocate_id, chat_id)
        if held is None or held['turn_id'] != turn_id or stepwise.waiting_of(held) is None:
            raise ConversationRefused('This matter is not waiting for your go-ahead.', status=409, code='not_waiting')
        if self.turn_running(advocate_id, turn_id):
            raise ConversationRefused('NM is already working on this answer.', code='turn_in_progress')
        try:
            go = stepwise.given(held['go'], choice, held=held, disputes=list(disputes) if disputes is not None else None)
        except ValueError as exc:
            raise ConversationRefused('NM cannot take that go-ahead for this matter now.', status=409,
                                      code='not_offered') from exc
        if go is None:
            saved = turn.done(self.store, matter, advocate_id, turn_id,
                              running=lambda held_turn: self.turn_running(advocate_id, held_turn),
                              session_current=session_current)
            if saved is None:
                raise ConversationRefused('This matter is not waiting for your go-ahead.', status=409, code='not_waiting')
            return saved
        asked = held['request']
        return self.run_turn(advocate_id=advocate_id, session_current=session_current,
                             document_refs=tuple(asked.get('document_refs', ())), model_choice=asked.get('model'),
                             effort=asked.get('effort'), message=held['message'], turn_id=turn_id,
                             chat_id=asked['chat_id'], go=go)

    def message_turn(self, *, advocate_id, chat_id, turn_id, message, session_current, document_refs=()):
        """A message sent while a matter waits for the advocate (plan AN.48, 48c; D146, D158): the message reader judges what it is.
        A go-ahead runs its step, as its button would; information, a correction or a rethink joins the matter as the advocate's
        words and the matter is understood again with them (D149); a new question waits above the message box until the matter is
        done; an unclear message is answered with the question that would settle it. Papers sent with it are information. How NM
        took the message is kept with the matter ('heard') and said at its stop. Returns the step's outcome as go_turn does, or
        raises ConversationRefused 'heard' (kept) where no step runs. Where the reader cannot be reached the message is kept and
        the stop says so."""
        from datetime import datetime, timezone
        from nm.core_engine import message_reader, steps as stepwise, turn
        from nm.core_engine.conversation import ConversationRefused, queued_of, save_waiting
        from nm.shared.model_port import ModelError
        matter, held = self._held(advocate_id, chat_id)
        if held is None or held['turn_id'] != turn_id or stepwise.waiting_of(held) is None:
            raise ConversationRefused('This matter is not waiting for your go-ahead.', status=409, code='not_waiting')
        if self.turn_running(advocate_id, turn_id):
            raise ConversationRefused('NM is already working on this answer.', code='turn_in_progress')
        documents = []
        if document_refs:
            from nm.core_engine import documents as turn_documents
            if self.documents is None:
                raise turn_documents.DocumentRefused("Documents cannot be read on this installation.")
            documents = turn_documents.turn_material([self.documents.load(advocate_id, ref) for ref in document_refs])
        asked = held['request']

        def heard_only(taken, said, *, queued=None):
            """No step runs: what NM heard is kept with the matter and said at its stop."""
            held['go'] = stepwise.heard(held['go'], message, taken, said)
            save_waiting(self.store, matter, held, queued=queued)
            refusal = ConversationRefused(said, status=409, code='heard', retryable=False)
            refusal.kept, refusal.heard = True, {'taken': taken, 'said': said}
            raise refusal

        def ran(go, **words):
            return self.run_turn(advocate_id=advocate_id, session_current=session_current,
                                 document_refs=tuple(asked.get('document_refs', ())), model_choice=asked.get('model'),
                                 effort=asked.get('effort'), message=held['message'], turn_id=turn_id,
                                 chat_id=asked['chat_id'], go=go, **words)
        if documents:
            judgement = {'kind': 'information', 'said': 'Taken as new papers for the matter: NM reads the matter again with them.'}
        else:
            choice = asked.get('model')
            model = self._model_for(advocate_id, session_current=session_current,
                                    text_model=DEFAULT_TURN_MODEL if choice == AUTO_TURN else choice)
            try:
                judgement = message_reader.read(model, held, message)
            except ModelError:
                logging.getLogger('nm.turns').warning('A message sent while a matter waited could not be read.')
                heard_only('unread', 'NM could not read this message just now. It is kept here: use the buttons, or send it '
                                     'again.')
        kind = judgement['kind']
        if kind == 'go':
            listened = stepwise.heard(held['go'], message, kind, judgement['said'])['heard']
            go = {**judgement['go'], 'heard': listened} if judgement['go'] is not None else None
            if go is None:  # Done before any analysis: saved as it stands
                held['go'] = stepwise.heard(held['go'], message, kind, judgement['said'])
                matter = save_waiting(self.store, matter, held)
                return turn.done(self.store, matter, advocate_id, turn_id,
                                 running=lambda held_turn: self.turn_running(advocate_id, held_turn),
                                 session_current=session_current)
            return ran(go)
        entry = {'text': message, 'documents': list(documents), 'at': datetime.now(timezone.utc).isoformat()}
        if kind == 'rethink':
            go = stepwise.rethink(stepwise.heard(held['go'], message, kind, judgement['said']))
            return ran(go, steered_with=[entry])
        if kind in ('information', 'correction'):
            # 48h (D159): kept as the advocate's message, after the latest one, citable; the research stays as it is.
            state = stepwise.state_of(held['steps'])
            written = [name for name in state['order'] if name in state['written']]
            critical = judgement['critical']
            said = judgement['said']
            proposed = [{'dispute_id': entry['dispute'], 'question': entry['question'], 'why_needed': entry['why_needed'],
                         'law_to_check': entry['law_to_check'], 'source': f"{turn_id}:added{len(held.get('added', ())) + 1}"}
                        for entry in (judgement.get('new_questions') or ())]
            if proposed:
                # 48i (D156): what is new offered for research, run only on the advocate's go-ahead (D136, D144); code says it.
                def offered(entry):
                    name = 'this matter' if state['whole'] else state['names'].get(entry['dispute_id'], entry['dispute_id'])
                    question = entry['question'] if entry['question'][-1:] in '.?!' else entry['question'] + '.'
                    return f'NM can research what is new for {name}: {question}'
                said = ' '.join([said, *(offered(entry) for entry in proposed),
                                 'Choose Research what is new to have it researched.']).strip()
            if kind == 'correction' and judgement.get('item'):
                # 48g (D148): kept with the item it corrects, for the board's mark.
                entry = {**entry, 'corrects': {'item': judgement['item'], 'value': judgement['value']}}
                if stepwise.limit_rests_on(held['steps'], judgement['item']):
                    # D161 (Claude's detail): a date a worked-out time limit runs from is critical by code - the limits are
                    # worked out again.
                    critical = True
                    held['steps'] = {**held['steps'], 'limits': None}
                    matter = save_waiting(self.store, matter, held)
            listened = stepwise.heard(held['go'], message, kind, said)
            if proposed:
                listened = stepwise.proposing(listened, proposed)
            if critical and written:
                # D161: critical - the analyses written are checked against it at once, each written again where wanting.
                go = {'mode': stepwise.MODE, 'allowed': ['write'], 'n': held['go']['n'] + 1, 'waiting': None,
                      'disputes': None if state['whole'] else written, **stepwise._carried(listened), 'recheck': True}
                return ran(go, appended=[entry])
            # D161-D162: not critical - nothing is redone now; the analyses written are checked against it once, at Done.
            held['added'] = [*held.get('added', ()), entry]
            held['go'] = {**listened, **({'recheck': True} if written else {})}
            save_waiting(self.store, matter, held)
            refusal = ConversationRefused(said, status=409, code='heard', retryable=False)
            refusal.kept, refusal.heard = True, {'taken': kind, 'said': said}
            raise refusal
        if kind == 'question':
            try:
                queued = queued_of(matter)
            except ValueError:
                queued = []
            heard_only(kind, judgement['said'], queued=[*queued, {'text': message, 'documents': []}])
        heard_only('unclear', f"{judgement['said']} {judgement['ask']}".strip())

    def answer_turn(self, *, advocate_id, chat_id, turn_id, answers, session_current):
        """Answers to NM's questions given while a matter waits (plan AN.48, 48d; D142, D154): taken as the window takes them,
        and kept with its questions. A step that stopped for them resumes by itself from its saved work once every question is
        answered; otherwise the answers wait for the step that needs them, and the stop says they are taken. ConversationRefused
        where the matter does not wait here, asks nothing, or an answer cannot be taken."""
        from nm.core_engine import questions, steps as stepwise
        from nm.core_engine.conversation import ConversationRefused, asking_of, save_asking, save_waiting
        matter, held = self._held(advocate_id, chat_id)
        if held is None or held['turn_id'] != turn_id or stepwise.waiting_of(held) is None:
            raise ConversationRefused('This matter is not waiting for your go-ahead.', status=409, code='not_waiting')
        if self.turn_running(advocate_id, turn_id):
            raise ConversationRefused('NM is already working on this answer.', code='turn_in_progress')
        try:
            asked = asking_of(matter, turn_id)
        except ValueError:
            asked = None
        if asked is None:
            raise ConversationRefused('NM is not asking anything about this matter.', status=409, code='no_question')
        window = questions.Asking(asked['state']['questions'])
        window.start(given={entry['id']: {'chosen': entry['chosen'], 'other': entry['other']}
                            for entry in asked['state']['answers'] if entry['how'] in ('answered', 'late')})
        try:
            window.receive(answers)
        except questions.Refused as exc:
            raise ConversationRefused(str(exc), status=422, code='answer_refused') from exc
        state = window.state()
        matter = save_asking(self.store, matter, turn_id, state)
        # 48h (D159): the answers given here are the advocate's messages too, after the latest one, citable as theirs.
        from datetime import datetime, timezone
        said = {question['id']: question['question'] for question in state['questions']}
        words = '\n'.join(f'Answer to NM\'s question "{said[identity]}": '
                          + '; '.join([*value.get('chosen', ()), *([value['other']] if value.get('other') else [])])
                          for identity, value in answers.items() if identity in said)
        entry = {'text': words, 'documents': [], 'at': datetime.now(timezone.utc).isoformat()}
        written = stepwise.state_of(held['steps'])['written']
        if stepwise.waiting_of(held) == stepwise.ASKED and not stepwise.unanswered(state):
            asked_for = held['request']
            # D154: the step that stopped for the answers goes on from its saved work, under its own go-ahead.
            return self.run_turn(advocate_id=advocate_id, session_current=session_current,
                                 document_refs=tuple(asked_for.get('document_refs', ())), model_choice=asked_for.get('model'),
                                 effort=asked_for.get('effort'), message=held['message'], turn_id=turn_id,
                                 chat_id=asked_for['chat_id'], go={**held['go'], 'waiting': None,
                                                                   **({'recheck': True} if written else {})},
                                 appended=[entry])
        held['added'] = [*held.get('added', ()), entry]
        if written:
            held['go'] = {**held['go'], 'recheck': True}
        save_waiting(self.store, matter, held)
        left = len(stepwise.unanswered(state))
        said = ('Your answer is taken.' + (f' NM still needs {left} more.' if left and stepwise.waiting_of(held) == stepwise.ASKED
                                           else ''))
        refusal = ConversationRefused(said, status=409, code='heard', retryable=False)
        refusal.kept, refusal.heard = True, {'taken': 'answer', 'said': said}
        raise refusal

    def discard_turn(self, *, advocate_id, chat_id, turn_id, session_current):
        """Discard (plan AN.41, D71): the red message and its buttons go; the answer that stopped is saved as it stopped. Returns
        the saved response, or None where that turn is not stopped in this conversation."""
        from nm.core_engine import turn
        matter, held = self._held(advocate_id, chat_id)
        if held is None:
            return None
        return turn.discard(self.store, matter, advocate_id, turn_id,
                            running=lambda held_turn: self.turn_running(advocate_id, held_turn),
                            session_current=session_current)

    def stop_turn(self, advocate_id, turn_id):
        """Stop (plan AN.42, D78): the answer stops after the step in progress. Plan AN.48 (48f2): a step still waiting for a free
        place is taken out instead - nothing of it ran and nothing was charged - and one just begun is stopped as it reaches the
        point Stop is heard at. False where this process is not working on it. 48f4: a web server asks the step worker, which says
        whether it heard."""
        if self.steps_mode == 'web':
            from nm.app import step_worker
            verdict = step_worker.ask_worker(self.step_share, advocate_id, turn_id, 'stop', {})
            return bool(verdict and verdict.get('stopping'))
        with self._running_lock:
            running = self._running.get((advocate_id, turn_id))
            if running is None:
                if self.step_jobs.cancel(advocate_id, turn_id):
                    self.turn_progress.end(advocate_id, turn_id, 'stopped')
                    return True
                return self.step_jobs.ask_stop(advocate_id, turn_id)
        if not self.turn_running(advocate_id, turn_id):
            return False
        running.stop.set()
        return True

    def steer_turn(self, *, advocate_id, turn_id, text, document_refs=()):
        """Steer (plan AN.42, D79): the message goes into the answer being worked on, with the documents sent with it as they were
        read; the answer stops after the step in progress and goes on with it. False where this process is not working on it -
        the answer has finished, and the page sends the message as the next one. 48f4: a web server reads the documents and hands
        the steer to the step worker, which says whether the turn took it."""
        from datetime import datetime, timezone
        running = None
        if self.steps_mode != 'web':
            with self._running_lock:
                running = self._running.get((advocate_id, turn_id))
        if self.steps_mode != 'web' and running is None or not self.turn_running(advocate_id, turn_id):
            return False
        documents = []
        if document_refs:
            from nm.core_engine import documents as turn_documents
            if self.documents is None:
                raise turn_documents.DocumentRefused("Documents cannot be read on this installation.")
            documents = turn_documents.turn_material([self.documents.load(advocate_id, ref) for ref in document_refs])
        steer = {'text': text, 'documents': list(documents), 'at': datetime.now(timezone.utc).isoformat()}
        if self.steps_mode == 'web':
            from nm.app import step_worker
            verdict = step_worker.ask_worker(self.step_share, advocate_id, turn_id, 'steer', steer)
            return bool(verdict and verdict.get('taken'))
        return self._steer_saved_then_taken(running, steer)

    def _steer_saved_then_taken(self, running, steer):
        """Plan AN.52 (52h, D214): a steer is saved beside its conversation before it is said to be taken, so a restart before
        the turn's next step does not lose the advocate's correction. Where it cannot be saved - the turn has just been saved,
        or the store refused - it is NOT taken, and the page sends the message as the next one, as it does for a turn that has
        finished. A turn that has not yet reached its conversation (its first moments) takes it in memory, as before."""
        from nm.core_engine.conversation import hold_steer
        from nm.shared.store_port import StaleWrite
        if running.writer is not None:
            try:
                running.writer(lambda context: hold_steer(self.store, context, steer))
            except (OSError, StaleWrite, ValueError):
                return False
        running.add(steer)
        return True

    def steered(self, advocate_id, turn_id, steer):
        """Plan AN.48 (48f4): the step worker's part of Steer - a steer the web server read, into the turn this process works on."""
        with self._running_lock:
            running = self._running.get((advocate_id, turn_id))
        if running is None or not self.turn_running(advocate_id, turn_id):
            return False
        return self._steer_saved_then_taken(running, steer)

    def save_queued(self, *, advocate_id, chat_id, queued):
        """What waits to be sent as the next message of a conversation (plan AN.42, D77), saved with it: on the versions of the
        turn this process is working on in it, where there is one, so that neither write undoes the other. 48f4: a web server hands
        it to the step worker, which works the turns; where no worker is there, no turn is at work, and it is saved here."""
        from nm.core_engine.conversation import chat_matter_id, hold_queued, save_queued
        from nm.shared.store_port import StaleWrite
        if self.steps_mode == 'web':
            from nm.app import step_worker
            if step_worker.alive(self.step_share):
                verdict = step_worker.ask_worker(self.step_share, advocate_id, '', 'queued',
                                                 {'chat_id': chat_id, 'queued': queued})
                if verdict is not None and verdict.get('missing'):
                    raise LookupError('Conversation not available.')
                if verdict is None or not verdict.get('saved'):
                    raise OSError('What waits could not be saved with the conversation.')
                return
        with self._running_lock:
            writers = [running.writer for running in self._running.values()
                       if running.advocate_id == advocate_id and running.chat_id == chat_id and running.writer is not None]
        for writer in writers:
            try:
                writer(lambda context: hold_queued(self.store, context, queued))
                return
            except (OSError, StaleWrite, ValueError):
                pass  # that turn has just been saved: what waits is saved on the conversation as it now is
        matter = self.store.load_for(chat_matter_id(advocate_id, chat_id), advocate_id)  # the store compares the owner (AN.53, 53b)
        if matter is None:
            raise LookupError('Conversation not available.')
        save_queued(self.store, matter, queued)

    def turn_running(self, advocate_id, turn_id):
        """Whether one of this advocate's turns is being worked on in this process now. Plan AN.48 (48f2): not counting the step this
        very thread works for that turn - one that waited for a place has progress saying it is working from then on, and its own
        checks against a second run of its turn (Continue, a go-ahead, Done) are about any other."""
        if self.step_jobs.running_here(advocate_id, turn_id):
            return False
        return self.turn_progress.read(advocate_id, turn_id).get('state') == 'working'

    def browser_asset_paths(self):
        return browser_assets(root=ROOT)

    def _egress_audit(self, line):
        """One line of the outgoing-data log (D169). A line that cannot be written is NEVER SILENT (plan AN.53, 53e, D220; the
        review's F-30): it is counted where the Admin diagnostics read it, by whichever process failed, and said once on this
        process's console. The call itself still goes: whether an unwritable log should refuse the call is the owner's decision."""
        try:
            self.egress_log.write(line)
        except OSError as exc:
            if not self._log_failure_said:
                self._log_failure_said = True
                print(f"THE OUTGOING-DATA LOG COULD NOT BE WRITTEN ({type(exc).__name__}). Calls go on; each line lost is counted "
                      "in the Admin diagnostics.", file=sys.stderr, flush=True)
            try:
                from nm.shared.egress_log_store import _append
                self._log_unwritten.parent.mkdir(parents=True, exist_ok=True)
                _append(self._log_unwritten, (utcnow().isoformat() + chr(10)).encode("ascii"))
            except OSError:
                pass  # the store refuses too: said above, and every other check of the diagnostics will show it

    def health(self):
        routine = self.config.for_tier(Tier.ROUTINE)
        return {'runtime': 'ready', 'provider': routine.provider, 'model': routine.model,
                'corpus': 'configured_unverified' if self.legal_search is not None else 'not_connected',
                'brain': {'engine': 'core_engine', 'state': 'development', 'stages': [
                    'understanding', 'research_planning', 'held_retrieval',
                    'response_writing', 'authority_checks', 'independent_review', 'atomic_release']},
                'steps': self.steps_state()}

    def steps_state(self):
        """Plan AN.48 (48f6, D167): where the steps are worked, and how many wait and are at work - counts only, never whose or
        what. A web server whose steps the step worker works says whether the worker has been heard from within BEAT_LASTS."""
        if self.steps_mode == 'web':
            from nm.app import step_worker
            try:
                beats = self.step_share.workers()
            except Exception:  # noqa: BLE001 - a store that cannot be read says no worker is known to be there
                beats = []
            heard = [beat for beat in beats if beat[1] <= step_worker.BEAT_LASTS]
            return {'mode': 'separate', 'worker': 'alive' if heard else 'not heard from',
                    'waiting': sum(beat[2] for beat in heard), 'working': sum(beat[3] for beat in heard)}
        return {'mode': self.steps_mode, 'waiting': self.step_jobs.count_waiting(),
                'working': self.step_jobs.count_working()}


def _document_desk(raw_store, storage, gate, settings):
    """None where the store cannot seal originals (insecure test ciphers, fakes)."""
    if not all(hasattr(raw_store, name) for name in ('upload_storage', 'document_storage', 'prepare_custody')):
        return None
    from nm.app.documents import DocumentDesk
    from nm.open_matter.clamav_check import ClamAVCheck
    from nm.open_matter.document_local import LocalDocumentText
    from nm.open_matter.matter_documents_port import DocumentDerivativePort
    from nm.open_matter.upload_port import UploadPort
    from nm.shared.store_file_store import EncryptionNotConfigured
    try:
        originals, texts = raw_store.upload_storage(), raw_store.document_storage()
    except EncryptionNotConfigured:
        return None
    checker = ClamAVCheck(settings.get('NM_CLAMSCAN'), settings.get('NM_CLAMAV_DATABASE'), storage / 'scan')
    # The resident engine loads at start; definitions over a day old are refreshed at start
    # and daily (owner decision, 15 Oct 2026).
    checker.warm()
    checker.keep_refreshed()
    return DocumentDesk(prepare_space=raw_store.prepare_custody,
        originals=PolicedPort(inner=originals, gate=gate, port=UploadPort, sink=Sink.STORAGE,
                              processor_id=STORAGE_PROCESSOR),
        texts=PolicedPort(inner=texts, gate=gate, port=DocumentDerivativePort, sink=Sink.STORAGE,
                          processor_id=STORAGE_PROCESSOR),
        checker=checker, reader=LocalDocumentText())


class _DeferredAdapter:
    def __init__(self, factory):
        self.factory, self.inner = factory, None
        self._building = threading.Lock()

    def _resolve(self):
        # Callers arriving together at the first use build it once and all use the same one (plan AN.24): a
        # store built twice at once is two callers racing to make one file. A build that fails is not kept.
        if self.inner is None:
            with self._building:
                if self.inner is None:
                    self.inner = self.factory()
        return self.inner

    def __getattr__(self, name):
        return getattr(self._resolve(), name)

class _Running:
    """A turn this process is working on (plan AN.42, D78-D79): the advocate's Stop, the steers waiting to go into it, and the
    way to write beside its conversation on its own versions (D77)."""

    def __init__(self):
        self.stop, self._steers, self._lock = threading.Event(), [], threading.Lock()
        self.writer, self.advocate_id, self.chat_id = None, None, None

    def add(self, steer):
        with self._lock:
            self._steers.append(steer)
            self.stop.set()

    def take(self):
        """The steers waiting, taken; the stop they came with cleared. [] where none waited (a Stop of the advocate's own)."""
        with self._lock:
            taken, self._steers = self._steers, []
            if taken:
                self.stop.clear()
        return taken

    def attach(self, advocate_id, chat_id, writer):
        self.advocate_id, self.chat_id, self.writer = advocate_id, chat_id, writer


def _how_a_turn_ended(exc) -> str:
    """How a turn that raised ended, for its line (plan AN.46, D120): stopped by the advocate; refused before it could be answered
    (a sign-in that ended, AI sharing off, an allowance used up, an earlier answer still being worked on, a document it could not
    use); or failed - on NM's side or the AI service's, or a refusal that says the conversation could not be read or the answer
    could not be given reliably."""
    from nm.core_engine.conversation import ConversationRefused
    from nm.core_engine.documents import DocumentRefused
    from nm.shared.external_ai_contracts import ModelPermissionRefused
    if isinstance(exc, ConversationRefused):
        # Plan AN.48: a step of a matter worked step by step ends waiting for the advocate, as an answer the advocate stopped does.
        if exc.code in ('stopped', 'waiting'):
            return 'stopped'
        if exc.status in (401, 402, 403, 422, 429):  # signed out, allowance, not permitted, not accepted, too many
            return 'refused'
        failed = exc.status >= 500 or exc.committed == 'unconfirmed' or exc.code in (
            'history_unavailable', 'answer_withheld', 'attempt_unconfirmed')
        return 'failed' if failed else 'refused'
    if isinstance(exc, (DocumentRefused, ModelPermissionRefused, AllowanceUsedUp)):
        return 'refused'
    return 'failed'


class QuestionDesk:
    """The windows of questions the turns this process is working on have open (plan AN.37, D37-D40): opened by a turn when it
    asks, read and answered from its advocate's page, closed when the turn stops - an answer after that goes as the next message
    (D44). Each advocate reaches only their own; nothing here outlives the process (a retry reuses what was sealed instead)."""

    def __init__(self):
        self._open, self._lock = {}, threading.Lock()

    def bound(self, advocate_id):
        """What a turn of this advocate opens its window on."""
        desk = self

        class _Bound:
            def open(self, turn_id, asking):
                with desk._lock:
                    desk._open[(advocate_id, turn_id)] = asking
        return _Bound()

    def close(self, advocate_id, turn_id):
        with self._lock:
            self._open.pop((advocate_id, turn_id), None)

    def window(self, advocate_id, turn_id):
        """The advocate's window for that turn while it is open, or None."""
        with self._lock:
            asking = self._open.get((advocate_id, turn_id))
        return asking if asking is not None and asking.open() else None

    def answer(self, advocate_id, turn_id, given):
        """The advocate's answers for that turn's window: "taken", or "closed" where there is no open window."""
        asking = self.window(advocate_id, turn_id)
        return "closed" if asking is None else asking.receive(given)


class MirroredDesk(QuestionDesk):
    """The step worker's windows of questions (plan AN.48, 48f4): each one a turn opens shown in the shared store for the web
    server's page, kept shown as it changes, and taken out when it closes; answers reach it from the web server through the worker."""

    def __init__(self, share):
        super().__init__()
        self._share = share

    def _show(self, advocate_id, turn_id, asking):
        try:
            self._share.show_window(advocate_id, turn_id, asking.view())
        except Exception as exc:  # noqa: BLE001 - shown again at the worker's next look
            logging.getLogger('nm.steps').warning('A window of questions could not be shown (%s).', type(exc).__name__)

    def bound(self, advocate_id):
        inner, desk = super().bound(advocate_id), self

        class _Bound:
            def open(self, turn_id, asking):
                inner.open(turn_id, asking)
                desk._show(advocate_id, turn_id, asking)
        return _Bound()

    def close(self, advocate_id, turn_id):
        super().close(advocate_id, turn_id)
        try:
            self._share.close_window(advocate_id, turn_id)
        except Exception as exc:  # noqa: BLE001 - the worker's next start closes every window it left
            logging.getLogger('nm.steps').warning('A window of questions could not be closed (%s).', type(exc).__name__)

    def answer(self, advocate_id, turn_id, given):
        state = super().answer(advocate_id, turn_id, given)
        asking = self.window(advocate_id, turn_id)
        if asking is not None:
            self._show(advocate_id, turn_id, asking)
        return state

    def show_open(self):
        """Each open window shown as it now is; one that has closed by itself taken out."""
        with self._lock:
            held = list(self._open.items())
        for (advocate_id, turn_id), asking in held:
            if asking.open():
                self._show(advocate_id, turn_id, asking)
            else:
                self.close(advocate_id, turn_id)


def _require_session(check):
    from nm.app.model_permission import ModelPermissionRefused
    if not callable(check) or not check():
        raise ModelPermissionRefused('Sign in again before continuing.')


#: The owner's exception for account mail (plan AN.48, D168, 10 Nov 2026): Gmail may carry NM's account mail - the confirmation
#: and password-reset messages, operational and restricted data - and nothing else. Recorded here, at the composition root, as the
#: OpenAI exception is (nm/app/model_permission.py): the reviewed inventory still admits no mail provider, so the gate of every
#: other route still refuses Gmail, and only the mail port's own gate (gmail_policy) admits it.
GMAIL_BASIS = 'OWNER-2026-11-10-GLOBAL-GMAIL-ACCOUNT-MAIL'


def gmail_policy():
    from nm.arrive.mail_gmail import GMAIL_PROCESSOR, MAIL_CLASSES
    from nm.shared.egress_contracts import Policy, ProcessingException, Processor
    return Policy(
        processors=(Processor(GMAIL_PROCESSOR, 'global', (Sink.MAIL,), MAIL_CLASSES, GMAIL_BASIS),),
        processing_exceptions=(ProcessingException(GMAIL_PROCESSOR, 'global', Sink.MAIL, MAIL_CLASSES, GMAIL_BASIS),))


def build_mail(settings, root, key, gate):
    """The account-mail adapter, the processor it is, and the gate that admits it.

    The sealed local outbox by default, through NM's own gate. Gmail (D168) only when NM_MAIL_PROVIDER=gmail and
    NM_MAIL_DELIVERY=enabled, through a gate of its own that admits Gmail for account mail alone (gmail_policy), writing to the
    same outgoing-data log. It signs in with a Google app password (NM_GMAIL_APP_PASSWORD_FILE) or an OAuth access token
    (NM_GMAIL_TOKEN_FILE): one of the two, each a local file read at each send. A provider named without delivery enabled
    sends nothing.
    """
    from nm.arrive.mail_gmail import GMAIL_PROCESSOR, MAIL_CLASSES, DisabledMail, GmailMail

    provider = settings.get('NM_MAIL_PROVIDER', 'local-outbox')
    delivery = settings.get('NM_MAIL_DELIVERY', 'disabled')
    if delivery not in {'disabled', 'enabled'}:
        raise ValueError('Unknown account-mail delivery setting.')
    if provider == 'local-outbox':
        if delivery == 'enabled':
            raise ValueError('A local outbox cannot enable real email delivery.')
        return FileOutbox(root, key=key), OUTBOX_PROCESSOR, gate
    if provider != 'gmail':
        raise ValueError('Unknown account-mail provider.')
    if delivery == 'disabled':
        return DisabledMail(), OUTBOX_PROCESSOR, gate
    mail_gate = Gatekeeper(policy=gmail_policy(), audit=gate.audit)
    mail_gate.permit(Sink.MAIL, GMAIL_PROCESSOR, MAIL_CLASSES)
    password, token = settings.get('NM_GMAIL_APP_PASSWORD_FILE', ''), settings.get('NM_GMAIL_TOKEN_FILE', '')
    if bool(password) == bool(token):
        raise ValueError('Gmail needs NM_GMAIL_APP_PASSWORD_FILE or NM_GMAIL_TOKEN_FILE: one of the two.')
    adapter = GmailMail(settings.get('NM_MAIL_SENDER', ''), Path(token) if token else None, mail_gate, enabled=True,
                        password_file=Path(password) if password else None)
    return adapter, GMAIL_PROCESSOR, mail_gate


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
