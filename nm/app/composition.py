"""Compose the served application with the existing authenticated, sealed adapters."""
from __future__ import annotations
import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from nm.arrive.advocate_contracts import utcnow
from nm.arrive.directory_port import DirectoryPort
from nm.arrive.mail_outbox import FileOutbox
from nm.arrive.mail_port import MailPort
from nm.arrive.store_directory import FileDirectory
from nm.shared.deployment_contracts import shares_value_with
from nm.shared.egress_contracts import DataClass, Gatekeeper, Sink
from nm.shared.egress_policy import OUTBOX_PROCESSOR, STORAGE_PROCESSOR, egress_policy
from nm.shared.model_config import load, load_dotenv
from nm.shared.model_openai_adapter import OpenAIModelAdapter
from nm.shared.model_policed import PolicedModel
from nm.shared.model_port import ModelPort, Tier
from nm.shared.model_traced import TracedModel
from nm.shared.policed_port_adapter import PolicedPort
from nm.shared.source_layout import browser_assets
from nm.shared.store_file_store import FileMatterStore
from nm.shared.store_port import StorePort
from nm.shared.turn_attempt_port import TurnAttemptPort
from nm.shared.turn_attempt_store import FileTurnAttempts
from nm.core_engine.retrieval import HybridSearcher

ROOT = Path(__file__).resolve().parents[2]
_CREDENTIAL_NAME = re.compile(r'KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL', re.I)
_SEAL = 'NM_MATTER_KEY'
_DEFAULT_SEARCH = object()

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
        storage_root = settings.get('NM_MATTER_STORE') or self.root / '.nm'
        self.store = PolicedPort(inner=store or FileMatterStore(storage_root, key=key),
            gate=self._gate, port=StorePort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR)
        self.turn_attempts = PolicedPort(inner=_DeferredAdapter(
            lambda: FileTurnAttempts(Path(storage_root) / 'turn-attempts.sqlite')),
            gate=self._gate, port=TurnAttemptPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL,))
        self.directory = PolicedPort(inner=directory or FileDirectory(storage_root, key=key),
            gate=self._gate, port=DirectoryPort, sink=Sink.STORAGE, processor_id=STORAGE_PROCESSOR,
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        mail_adapter, processor = ((mail, OUTBOX_PROCESSOR) if mail is not None else
                                    build_mail(settings, storage_root, key, self._gate))
        self.mail = PolicedPort(inner=mail_adapter, gate=self._gate, port=MailPort,
            sink=Sink.MAIL, processor_id=processor,
            data_classes=(DataClass.OPERATIONAL, DataClass.RESTRICTED))
        self._model_adapter = model if model is not None else build_model(self.config)
        budget_path = settings.get('NM_EVAL_BUDGET_FILE')
        if budget_path:
            if not isinstance(self._model_adapter, OpenAIModelAdapter):
                raise ValueError('A live evaluation budget requires the OpenAI adapter.')
            from nm.shared.model_call_budget import SessionCallBudget
            models = tuple(dict.fromkeys(c.model for tier, c in self.config.tiers.items() if tier is not Tier.EMBED))
            self._model_adapter = self._model_adapter.with_call_budget(SessionCallBudget(
                Path(budget_path), settings.get('NM_EVAL_MAX_USD', '25'), models=models))
        # Configuration is not corpus readiness; models and indices load on demand.
        # Explicit None supports isolated flows without making provider-specific choices.
        self.legal_search = (HybridSearcher.local(root=self.root,
            corpus_dir=settings.get('NM_CORPUS_DIR')) if legal_search is _DEFAULT_SEARCH else legal_search)

    def _model_for(self, advocate_id, *, session_current):
        if isinstance(self._model_adapter, OpenAIModelAdapter):
            from nm.app.model_permission import bind_text_model
            return bind_text_model(self._model_adapter, directory=self.directory,
                account_id=advocate_id, config=self.config,
                session_current=session_current, audit=self._egress_audit)
        # Fresh tracing per request prevents parallel conversations sharing traces.
        return PolicedModel(inner=TracedModel(inner=self._model_adapter),
            policy=self._gate.policy, audit=self._egress_audit,
            authorize=lambda: _require_session(session_current))

    def run_turn(self, *, advocate_id, session_current, **request):
        from nm.core_engine.turn import process

        # Saved replay performs no provider work. Permission/model construction
        # belongs to the first fresh model operation, not to receipt readback.
        model = _DeferredAdapter(lambda: self._model_for(advocate_id, session_current=session_current))
        return process(model, self.store, self.legal_search, advocate_id=advocate_id,
                       session_current=session_current, attempts=self.turn_attempts, **request)

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
                    'response_writing', 'independent_review', 'atomic_release']}}


class _DeferredAdapter:
    def __init__(self, factory):
        self.factory, self.inner = factory, None

    def _resolve(self):
        if self.inner is None:
            self.inner = self.factory()
        return self.inner

    def __getattr__(self, name):
        return getattr(self._resolve(), name)

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
