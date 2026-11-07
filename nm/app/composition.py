"""Compose the served application with the existing authenticated, sealed adapters."""
from __future__ import annotations
import logging
import os
import re
import threading
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from nm.arrive.admin_access import roster_from
from nm.arrive.admin_directory import AdminFileDirectory
from nm.arrive.admin_checks import AdminChecks
from nm.arrive.admin_library import AdminLibrary
from nm.arrive.admin_port import (AdminAccountsPort, AdminChecksPort, AdminDirectoryPort, AdminLibraryPort, AdminRecordPort,
                                  AdminTurnsPort, AdminUsagePort)
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
                 audit_root: Path | None = None):
        if environment is None:
            load_dotenv(ROOT / '.env')
        settings = MappingProxyType(dict(os.environ if environment is None else environment))
        self.environment = settings
        self.root = root or ROOT
        self.audit_root = Path(audit_root) if audit_root is not None else self.root / '.nm'
        self.config = load(dict(settings))
        key = settings.get('NM_MATTER_KEY') or _ensure_local_key(self.root)
        _refuse_a_shared_seal(key, settings)
        self._gate = Gatekeeper(policy=egress_policy(self.root), audit=self._egress_audit)
        storage = storage_root(settings, self.root)
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
        self.admin_library = PolicedPort(inner=AdminLibrary(checks=checks, root=self.root, corpus_dir=checks.corpus),
            gate=self._gate, port=AdminLibraryPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        self.admin_record = PolicedPort(inner=_DeferredAdapter(lambda: FileAdminRecord(storage / ADMIN_FILE)),
            gate=self._gate, port=AdminRecordPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        mail_adapter, processor = ((mail, OUTBOX_PROCESSOR) if mail is not None else
                                    build_mail(settings, storage, key, self._gate))
        self.mail = PolicedPort(inner=mail_adapter, gate=self._gate, port=MailPort,
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
        # What each running turn is doing, for its own advocate (memory only).
        self.turn_progress = TurnProgress()
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
        self.questions = QuestionDesk()
        self.propose_questions = questions.propose
        # Plan AN.41-AN.42: the turns this process is working on, each with the advocate's Stop and the steers waiting for it.
        self._running, self._running_lock = {}, threading.Lock()

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

    def run_turn(self, *, advocate_id, session_current, document_refs=(), model_choice=None, effort=None, **request):
        """One turn for an advocate. model_choice and effort: what they chose for it (plan AN.33, D23) - the model every text call
        of the turn runs on, and how hard each reasons; None: as configured, at the table's own levels."""
        from nm.core_engine import routing, titles
        from nm.core_engine.turn import process

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
                             entitle=lambda given: titles.entitle(model, given), **request)
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
        matter = self.store.load(chat_matter_id(advocate_id, chat_id))
        if matter is None or matter.advocate_id != advocate_id:
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
        return self.run_turn(advocate_id=advocate_id, session_current=session_current,
                             document_refs=tuple(asked.get('document_refs', ())), model_choice=asked.get('model'),
                             effort=asked.get('effort'), message=held['message'], turn_id=turn_id,
                             chat_id=asked['chat_id'])

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
        """Stop (plan AN.42, D78): the answer stops after the step in progress. False where this process is not working on it."""
        with self._running_lock:
            running = self._running.get((advocate_id, turn_id))
        if running is None or not self.turn_running(advocate_id, turn_id):
            return False
        running.stop.set()
        return True

    def steer_turn(self, *, advocate_id, turn_id, text, document_refs=()):
        """Steer (plan AN.42, D79): the message goes into the answer being worked on, with the documents sent with it as they were
        read; the answer stops after the step in progress and goes on with it. False where this process is not working on it -
        the answer has finished, and the page sends the message as the next one."""
        from datetime import datetime, timezone
        with self._running_lock:
            running = self._running.get((advocate_id, turn_id))
        if running is None or not self.turn_running(advocate_id, turn_id):
            return False
        documents = []
        if document_refs:
            from nm.core_engine import documents as turn_documents
            if self.documents is None:
                raise turn_documents.DocumentRefused("Documents cannot be read on this installation.")
            documents = turn_documents.turn_material([self.documents.load(advocate_id, ref) for ref in document_refs])
        running.add({'text': text, 'documents': list(documents), 'at': datetime.now(timezone.utc).isoformat()})
        return True

    def save_queued(self, *, advocate_id, chat_id, queued):
        """What waits to be sent as the next message of a conversation (plan AN.42, D77), saved with it: on the versions of the
        turn this process is working on in it, where there is one, so that neither write undoes the other."""
        from nm.core_engine.conversation import chat_matter_id, hold_queued, save_queued
        from nm.shared.store_port import StaleWrite
        with self._running_lock:
            writers = [running.writer for running in self._running.values()
                       if running.advocate_id == advocate_id and running.chat_id == chat_id and running.writer is not None]
        for writer in writers:
            try:
                writer(lambda context: hold_queued(self.store, context, queued))
                return
            except (OSError, StaleWrite, ValueError):
                pass  # that turn has just been saved: what waits is saved on the conversation as it now is
        matter = self.store.load(chat_matter_id(advocate_id, chat_id))
        if matter is None or matter.advocate_id != advocate_id:
            raise LookupError('Conversation not available.')
        save_queued(self.store, matter, queued)

    def turn_running(self, advocate_id, turn_id):
        """Whether one of this advocate's turns is being worked on in this process now."""
        return self.turn_progress.read(advocate_id, turn_id).get('state') == 'working'

    def browser_asset_paths(self):
        return browser_assets(root=ROOT)

    def _egress_audit(self, line):
        try:
            path = self.audit_root / 'egress.log'
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf8') as handle:
                handle.write(utcnow().isoformat(timespec='seconds') + '\t' + line + '\n')
        except OSError:
            pass

    def health(self):
        routine = self.config.for_tier(Tier.ROUTINE)
        return {'runtime': 'ready', 'provider': routine.provider, 'model': routine.model,
                'corpus': 'configured_unverified' if self.legal_search is not None else 'not_connected',
                'brain': {'engine': 'core_engine', 'state': 'development', 'stages': [
                    'understanding', 'research_planning', 'held_retrieval',
                    'response_writing', 'authority_checks', 'independent_review', 'atomic_release']}}


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
        if exc.code == 'stopped':
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


def _require_session(check):
    from nm.app.model_permission import ModelPermissionRefused
    if not callable(check) or not check():
        raise ModelPermissionRefused('Sign in again before continuing.')


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
