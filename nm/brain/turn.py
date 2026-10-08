"""Current brain orchestration: context, proposals, checked display, atomic save."""
from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from nm.brain.message_labels import label_message
from nm.brain.dispute_queries import prepare_queries, research_input, validate_queries
from nm.brain.retrieval import SearchUnavailable, validate_search
from nm.brain.disputes_objectives import (
    CONTRACT as EXTRACTION_RECORD, LEGACY_CONTRACT as LEGACY_EXTRACTION_RECORD,
    PASSAGE_LEGACY_CONTRACT as PASSAGE_LEGACY_EXTRACTION_RECORD,
    check_targets, extract_disputes_objectives, extraction_units, open_items,
    repair_disputes_objectives,
)
from nm.brain.release import (
    LEGACY_EXTRACTION_RENDERER, PASSAGE_LEGACY_EXTRACTION_RENDERER,
    PASSAGE_LEGACY_REVIEW_RENDERER, PASSAGE_REVIEW_RENDERER, UNCONFIRMED_REVIEW_RENDERER,
    extraction_review_gaps, prepare_release, render_saved_release,
)
from nm.shared.model_port import ContextOverflow, ModelError, Prompt, SchemaViolation, estimate_tokens
from nm.shared.store_port import StaleWrite
from nm.work_the_file.matter_contracts import Matter

CONTRACT = 'current_brain_turn_v7'
UNCONFIRMED_LEGACY_CONTRACT = 'current_brain_turn_v6'
RESEARCH_LEGACY_CONTRACT = 'current_brain_turn_v5'
RESEARCH_CONTRACT = 'private_dispute_research_v1'
SEGMENT_LEGACY_CONTRACT = 'current_brain_turn_v4'
PASSAGE_LEGACY_CONTRACT = 'current_brain_turn_v3'
EXTRACTION_LEGACY_CONTRACT = 'current_brain_turn_v2'
LEGACY_CONTRACT = 'current_brain_turn_v1'
# Each saved turn version is re-checked with exactly the review rendering and
# extraction record it was produced with, and so with the passage-cutting rule
# behind them. v5-v7 passages end at sentences; v3/v4 passages end at every mark.
# v7 replies ask the user to confirm each objective NM worded; v5/v6 never asked.
_EXTRACTION_BINDINGS = {
    CONTRACT: (PASSAGE_REVIEW_RENDERER, EXTRACTION_RECORD),
    UNCONFIRMED_LEGACY_CONTRACT: (UNCONFIRMED_REVIEW_RENDERER, EXTRACTION_RECORD),
    RESEARCH_LEGACY_CONTRACT: (UNCONFIRMED_REVIEW_RENDERER, EXTRACTION_RECORD),
    SEGMENT_LEGACY_CONTRACT: (PASSAGE_LEGACY_REVIEW_RENDERER, PASSAGE_LEGACY_EXTRACTION_RECORD),
    PASSAGE_LEGACY_CONTRACT: (PASSAGE_LEGACY_EXTRACTION_RENDERER, PASSAGE_LEGACY_EXTRACTION_RECORD),
    EXTRACTION_LEGACY_CONTRACT: (LEGACY_EXTRACTION_RENDERER, LEGACY_EXTRACTION_RECORD),
}
# Versions whose turns carry a bounded extraction-recovery record.
_RECOVERY_CONTRACTS = (CONTRACT, UNCONFIRMED_LEGACY_CONTRACT, RESEARCH_LEGACY_CONTRACT,
                       SEGMENT_LEGACY_CONTRACT)
# Versions whose turns carry the private dispute-research record.
_RESEARCH_CONTRACTS = (CONTRACT, UNCONFIRMED_LEGACY_CONTRACT)


class BrainRefused(Exception):
    def __init__(self, why, *, status=503, code='brain_unavailable',
                 committed='not_committed', retryable=True):
        super().__init__(why)
        self.why, self.status, self.code = why, status, code
        self.committed, self.retryable = committed, retryable


@dataclass(frozen=True)
class BrainTurn:
    advocate_id: str
    message: str
    turn_id: str
    matter_id: str | None = None
    chat_id: str | None = None
    expected_version: int | None = None


@dataclass(frozen=True)
class BrainOutput:
    response: dict

    def as_dict(self):
        return deepcopy(self.response)


def chat_matter_id(advocate_id, chat_id):
    return 'chat_' + hashlib.sha256(json.dumps([advocate_id, chat_id]).encode()).hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _request(turn):
    return {'advocate_id': turn.advocate_id, 'message': turn.message,
            'turn_id': turn.turn_id, 'matter_id': turn.matter_id, 'chat_id': turn.chat_id}


def _accepted(release):
    """Unit IDs the independent review accepted; only these become saved items."""
    return {row['unit_id'] for row in release['proof'].get('unit_reviews', [])
            if row.get('verdict') == 'supported'}


def saved_items(rows):
    """The open saved disputes and objectives after these checked rows, with stable IDs."""
    return open_items([(row['release']['units'], _accepted(row['release'])) for row in rows])


def saved_rows(matter, advocate_id):
    """Validate the saved contract without rerunning or upgrading an old reply."""
    if matter.advocate_id != advocate_id:
        raise BrainRefused('Conversation not available.', status=404, retryable=False)
    rows = []
    try:
        # In this contract each committed version is exactly one conversation
        # turn. A readable prefix is not evidence that the history is complete.
        if matter.version != len(matter.brain_chat):
            raise ValueError('saved conversation tail is missing')
        for row in matter.brain_chat:
            if (row['contract'] not in (LEGACY_CONTRACT, *_EXTRACTION_BINDINGS) or row['matter_id'] != matter.id
                    or row['advocate_id'] != advocate_id or row['committed'] is not True
                    or row['release_state'] != 'released'
                    or row['request_digest'] != _digest(row['request'])
                    or row['request']['message'] != row['message']
                    or row['request']['advocate_id'] != advocate_id
                    or row['request']['turn_id'] != row['turn_id']
                    or chat_matter_id(advocate_id, row['chat_id']) != matter.id):
                raise ValueError('saved conversation binding')
            release = render_saved_release(row['release'])
            prepared = row['preparation']
            if row['contract'] in _EXTRACTION_BINDINGS:
                expected_renderer, expected_contract = _EXTRACTION_BINDINGS[row['contract']]
                if release['renderer_version'] != expected_renderer:
                    raise ValueError('saved extraction rendering contract')
                if prepared['contract'] != expected_contract:
                    raise ValueError('saved extraction projection contract')
                expected_units = extraction_units(prepared)
            else:
                if (release['renderer_version'] not in ('initial_brain_release_v1', 'initial_brain_release_v2')
                        or 'contract' in prepared):
                    raise ValueError('saved legacy preparation contract')
                expected_units = {
                    unit['id']: {'kind': kind, 'proposal': unit}
                    for kind in ('material', 'actions') for unit in prepared['proposal'][kind]}
            if (prepared['state'] != 'prepared_unreviewed'
                    or prepared['sources'] != release['sources']
                    or prepared['issues'] != release['issues']
                    or expected_units != release['units']):
                raise ValueError('saved preparation binding')
            if row['contract'] in _RECOVERY_CONTRACTS:
                _checked_recovery(row, *_EXTRACTION_BINDINGS[row['contract']])
            if prepared.get('contract') == EXTRACTION_RECORD:
                # A change must name an item that was open before this turn,
                # as derived from the earlier checked rows -- never re-guessed.
                before = saved_items(rows)
                check_targets(expected_units, before)
                if (row.get('recovery') or {}).get('before'):
                    check_targets(extraction_units(row['recovery']['before']['preparation']), before)
            if row['contract'] in _RESEARCH_CONTRACTS:
                _checked_research(row['research'], prepared, row['release'])
            elif 'research' in row:
                raise ValueError('historical turn cannot acquire fresh research metadata')
            response = row['response']
            fixed = {'route': 'current_brain', 'mode': 'conversation', 'mode_statement': '',
                     'blocked': False, 'blocked_reason': None, 'material': [],
                     'material_coverage': {}, 'briefing': {}, 'board_changes': [],
                     'composed': [], 'continuation': {}}
            if any(response.get(key) != value for key, value in fixed.items()):
                raise ValueError('saved public expression binding')
            if (response['elements'] != release['elements']
                    or response['turn_id'] != row['turn_id']
                    or response['chat_id'] != row['chat_id']
                    or response['at'] != row['at']
                    or response['committed'] != 'committed'
                    or response['input_admitted'] is not True
                    or response['matter_id'] is not None
                    or response['replayed'] is not False
                    or response['matter_version'] != len(rows) + 1
                    or response.get('service_status') != release['service_status']
                    or row['response_digest'] != _digest(response)):
                raise ValueError('saved response binding')
            history = _history(rows)
            expected_sources = [
                {'id': f'history_{index}', 'message': entry}
                for index, entry in enumerate(history, start=1)]
            expected_sources.append({'id': 'current', 'message': {'role': 'advocate', 'text': row['message']}})
            if release['sources'] != expected_sources:
                raise ValueError('saved original context binding')
            rows.append(deepcopy(row))
    except (KeyError, TypeError, ValueError, ModelError, SearchUnavailable) as exc:
        raise BrainRefused('This saved conversation could not be checked. Its records have not been changed.',
            status=409, code='history_unavailable', committed='previously_committed', retryable=False) from exc
    return rows


def _history(rows):
    history = []
    for row in rows:
        history.append({'role': 'advocate', 'text': row['message'], 'turn_id': row['turn_id']})
        text = '\n\n'.join(e['text'] for e in row['response']['elements'])
        if not text.strip():
            raise ValueError('saved reply is empty')
        prior = {'role': 'nm', 'text': text, 'turn_id': row['turn_id']}
        if row['response'].get('service_status'):
            prior['service_status'] = row['response']['service_status']
        history.append(prior)
    return history


def _checked_recovery(row, renderer, extraction_record):
    """Recovery lineage is durable evidence, never a substitute for final review."""
    recovery = row.get('recovery')
    if (not isinstance(recovery, dict) or set(recovery) != {'attempted', 'before', 'outcome', 'failure'}
            or type(recovery['attempted']) is not bool
            or recovery['outcome'] not in ('not_needed', 'allowance_unavailable', 'ready', 'partial', 'failed')
            or recovery['failure'] not in (None, 'model_error')):
        raise ValueError('saved extraction recovery contract')
    gaps = extraction_review_gaps(row['release'])
    if not recovery['attempted']:
        expected = 'allowance_unavailable' if gaps else 'not_needed'
        if recovery['before'] is not None or recovery['failure'] is not None or recovery['outcome'] != expected:
            raise ValueError('saved unused recovery binding')
        return
    before = recovery['before']
    if not isinstance(before, dict) or set(before) != {'preparation', 'release'}:
        raise ValueError('saved recovery original attempt')
    original = render_saved_release(before['release'])
    original_units = extraction_units(before['preparation'])
    if (original['renderer_version'] != renderer
            or before['preparation']['contract'] != extraction_record
            or original['sources'] != row['release']['sources']
            or before['preparation']['sources'] != original['sources']
            or original_units != original['units']
            or before['preparation']['issues'] != original['issues']
            or not extraction_review_gaps(original)):
        raise ValueError('saved recovery source/need binding')
    if recovery['failure'] is not None:
        if (recovery['outcome'] != 'failed' or row['preparation'] != before['preparation']
                or row['release'] != before['release']):
            raise ValueError('failed recovery cannot claim a replacement result')
    elif recovery['outcome'] != row['release']['state']:
        raise ValueError('saved recovery result differs from final checked state')
    for review in original['proof']['unit_reviews']:
        identity = review['unit_id']
        if review['verdict'] == 'supported' and row['release']['units'].get(identity) != original_units[identity]:
            raise ValueError('recovery discarded an independently supported proposal')


def _search_queries(subject, plan, sources):
    """Original words are code-owned; generated terminology remains hypotheses."""
    speakers = {s['id']: s['message']['role'] for s in sources}
    original = '\n'.join(dict.fromkeys(
        f"[{p['source_id']} {speakers[p['source_id']]} {p['purpose']}] {p['quote']}"
        for p in subject['passages']))
    queries = [{"query_id": q['query_id'], "text": q['text'], "context": original}
               for q in plan['queries']] if plan is not None else []
    return [*queries, {'query_id': subject['id'] + ':original', 'text': original,
                      'context': original}]


def _research_state(record, scope):
    if not scope['disputes']:
        return 'not_needed'
    if not record['configured']:
        return 'not_configured'
    if (record['planning_failure'] or record['failures']
            or record['planning']['issues']
            or any(s['state'] == 'partial' for s in record['searches'].values())):
        return 'partial'
    return 'ready'


def _checked_research(record, prepared, release):
    """Check private execution evidence without upgrading ranked candidates."""
    scope = research_input(prepared, release)
    if (not isinstance(record, dict) or set(record) != {'contract', 'input_digest',
            'configured', 'planning', 'planning_failure', 'searches', 'failures', 'state'}
            or record['contract'] != RESEARCH_CONTRACT
            or record['input_digest'] != _digest(scope) or type(record['configured']) is not bool
            or not isinstance(record['searches'], dict) or not isinstance(record['failures'], dict)):
        raise ValueError('research has no matching checked dispute scope')
    subjects = scope['disputes']
    if not subjects or not record['configured']:
        if any(record[key] for key in ('planning', 'planning_failure', 'searches', 'failures')):
            raise ValueError('unused research cannot carry execution results')
    else:
        planning = record['planning']
        failure = record['planning_failure']
        if failure is None:
            validate_queries(planning, prepared, release)
        elif (planning is not None or not isinstance(failure, dict)
                or set(failure) != {'stage', 'code'} or failure['stage'] != 'decomposition'
                or failure['code'] not in ('model_error', 'context_overflow', 'invalid_proposal')):
            raise ValueError('failed planning cannot claim checked queries')
        if (set(record['searches']) & set(record['failures'])
                or set(record['searches']) | set(record['failures']) != set(subjects)):
            raise ValueError('every checked dispute needs its own search disposition')
        for identity, search in record['searches'].items():
            plan = planning['plans'].get(identity) if planning else None
            try:
                validate_search(search, _search_queries(subjects[identity], plan, scope['sources']))
            except (KeyError, TypeError, ValueError, AttributeError, IndexError, SearchUnavailable) as exc:
                raise ValueError('saved research snapshot is malformed or detached') from exc
        for failure in record['failures'].values():
            if (not isinstance(failure, dict) or set(failure) != {'stage', 'code'}
                    or failure != {'stage': 'search', 'code': 'search_unavailable'}):
                raise ValueError('search failure has no owned execution disposition')
    if record['state'] != _research_state(record, scope):
        raise ValueError('research status differs from its actual execution dispositions')
    return deepcopy(record)


def _research(model, prepared, release, searcher, checked):
    scope = research_input(prepared, release)
    result = {'contract': RESEARCH_CONTRACT, 'input_digest': _digest(scope),
              'configured': searcher is not None, 'planning': None, 'planning_failure': None,
              'searches': {}, 'failures': {}, 'state': 'not_needed'}
    if scope['disputes'] and searcher is not None:
        def plan_current():
            proposal = prepare_queries(model, prepared, release)
            if proposal['issues'] and not proposal['plans']:
                raise SchemaViolation('No query route admitted: ' + '; '.join(
                    issue['reason'] for issue in proposal['issues']))
            return proposal
        try:
            result['planning'] = checked(plan_current)
        except ModelError as exc:
            code = ('context_overflow' if isinstance(exc, ContextOverflow) else
                    'invalid_proposal' if isinstance(exc, SchemaViolation) else 'model_error')
            result['planning_failure'] = {'stage': 'decomposition', 'code': code}
        for identity, subject in scope['disputes'].items():
            plan = result['planning']['plans'].get(identity) if result['planning'] else None
            queries = _search_queries(subject, plan, scope['sources'])
            try:
                # Search hypotheses failing cannot erase original-account search.
                candidate = searcher.search(queries)
                result['searches'][identity] = validate_search(candidate, queries)
            except Exception:
                # This boundary is read-only. Fail only this dispute's search;
                # identity, history, ownership and saving gates remain outside it.
                result['failures'][identity] = {'stage': 'search', 'code': 'search_unavailable'}
    result['state'] = _research_state(result, scope)
    return _checked_research(result, prepared, release)


class _MeasuredModel:
    """Request-local accounting, including rejected provider responses."""
    def __init__(self, inner):
        self.inner, self.calls = inner, []
        self.feedback = None
        self.last_output = None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def structured(self, prompt, schema, tier, *, max_tokens=None):
        if self.feedback:
            payload = json.loads(prompt.user)
            payload['correction_feedback'] = self.feedback
            prompt = Prompt(system=prompt.system, user=json.dumps(payload, ensure_ascii=False),
                            operation=prompt.operation)
            if (estimate_tokens((prompt.system or '') + prompt.user + json.dumps(schema))
                    + (max_tokens or 0) > self.inner.context_budget(tier)):
                raise ContextOverflow('The complete correction exceeds the model context budget')
        started = time.monotonic()
        receipt = None
        try:
            receipt = self.inner.structured(prompt, schema, tier, max_tokens=max_tokens)
            self.last_output = deepcopy(receipt.data)
            return receipt
        except ModelError as exc:
            receipt = exc
            rejected = getattr(exc, 'rejected_result', None)
            self.last_output = deepcopy(rejected.data) if rejected is not None else None
            raise
        finally:
            usage = getattr(receipt, 'usage', None)
            self.calls.append({'operation': prompt.operation,
                'latency_ms': round((time.monotonic() - started) * 1000),
                'tokens_in': usage.tokens_in if usage else 0,
                'tokens_out': usage.tokens_out if usage else 0,
                'cost_usd': usage.cost_usd if usage else 0,
                'retries': getattr(receipt, 'retries', 0)})

    def metrics(self):
        return {'llm_calls': len(self.calls), 'calls': deepcopy(self.calls),
                'cost_usd': sum(c['cost_usd'] for c in self.calls),
                'tokens_in': sum(c['tokens_in'] for c in self.calls),
                'tokens_out': sum(c['tokens_out'] for c in self.calls)}


class BrainService:
    def __init__(self, *, store, model_factory=None, model=None, session_current, legal_search=None):
        self.store, self.session_current = store, session_current
        self.legal_search = legal_search
        self.model_factory = model_factory or (lambda: model)

    def _authorised(self):
        if not self.session_current():
            raise BrainRefused('Sign in again to continue.', status=401, retryable=False)

    def run(self, turn: BrainTurn):
        self._authorised()
        if any(not isinstance(v, str) or not v.strip()
               for v in (turn.advocate_id, turn.turn_id, turn.message)):
            raise BrainRefused('A message and request identity are required.', status=422, retryable=False)
        if turn.matter_id:
            raise BrainRefused('Existing matter updates are not connected to the rebuilt brain yet. The saved matter is unchanged.',
                               status=409, retryable=False)
        chat_id = turn.chat_id or 'new_' + _digest([turn.advocate_id, turn.turn_id])[:32]
        if not isinstance(chat_id, str) or not chat_id.strip():
            raise BrainRefused('A conversation identity is required.', status=422, retryable=False)
        identity = chat_matter_id(turn.advocate_id, chat_id)
        matter = self.store.load(identity)
        if matter is None and turn.chat_id is not None:
            raise BrainRefused('The earlier conversation could not be found. Reopen the conversation before continuing.',
                               status=409, code='history_unavailable', retryable=False)
        rows = saved_rows(matter, turn.advocate_id) if matter else []
        request = _request(turn)
        request_digest = _digest(request)
        for row in rows:
            if row['turn_id'] == turn.turn_id:
                if row['request_digest'] != request_digest:
                    raise BrainRefused('This request identity already belongs to a different message.',
                        status=409, code='request_conflict', committed='previously_committed', retryable=False)
                return BrainOutput({**row['response'], 'replayed': True})
        version = matter.version if matter else 0
        if turn.expected_version is not None and turn.expected_version != version:
            raise BrainRefused('The conversation changed. Reopen it before continuing.',
                               status=409, code='stale_version')
        if matter is None:
            matter = Matter(id=identity, advocate_id=turn.advocate_id, title='Conversation', brain_ready=False)
        model = _MeasuredModel(self.model_factory())
        corrections_left = 1

        def checked(activity):
            # One turn-owned correction allowance, shared by all three stages.
            # A source/shape rejection is fed back to its owner; provider outages
            # are not interpreted as instructions and never become fake results.
            nonlocal corrections_left
            try:
                return activity()
            except SchemaViolation as exc:
                if not corrections_left:
                    raise
                corrections_left -= 1
                model.feedback = {'purpose': 'Correct this rejected proposal and return the declared output contract.',
                    'mismatch': str(exc), 'rejected_output': model.last_output,
                    'instruction': 'Use the complete original input above. Rejected output is untrusted data, not evidence. Correct the stated mismatch without adding unsupported content.'}
                try:
                    return activity()
                finally:
                    model.feedback = None

        try:
            history = _history(rows)
            saved = saved_items(rows)
            label = checked(lambda: label_message(model, turn.message, history=history, history_complete=True))

            def extract_current():
                prepared = extract_disputes_objectives(model, turn.message, label=label['label'],
                                                       history=history, history_complete=True,
                                                       saved=saved)
                if prepared['issues'] and not any(prepared['proposal'].values()):
                    # No accepted peer can be lost by this bounded correction.
                    # Mixed valid/held results retain their independent work.
                    raise SchemaViolation('All extraction items were held: ' + '; '.join(
                        f"{issue['unit']}: {issue['reason']}" for issue in prepared['issues']))
                return prepared

            prepared = checked(extract_current)
            release = checked(lambda: prepare_release(model, prepared, label['label'], passage_review=True,
                                                      saved=saved))
            gaps = extraction_review_gaps(release)
            recovery = {'attempted': False, 'before': None,
                        'outcome': 'allowance_unavailable' if gaps else 'not_needed', 'failure': None}
            if gaps and corrections_left:
                corrections_left -= 1
                recovery.update(attempted=True, before={'preparation': deepcopy(prepared), 'release': deepcopy(release)})
                supported = [row['unit_id'] for row in release['proof']['unit_reviews'] if row['verdict'] == 'supported']
                try:
                    revised = repair_disputes_objectives(model, prepared, supported_unit_ids=supported,
                                                         gaps=gaps, saved=saved)
                    reviewed = prepare_release(model, revised, label['label'], passage_review=True,
                                               saved=saved)
                except ModelError:
                    # Keep only the earlier independently checked scope. A
                    # failed repair cannot certify any new result or effect.
                    recovery.update(outcome='failed', failure='model_error')
                else:
                    prepared, release = revised, reviewed
                    recovery['outcome'] = release['state']
            if not release['elements']:
                raise BrainRefused('A response could not be prepared for this message. Please retry.',
                                   code='response_unavailable')
            research = _research(model, prepared, release, self.legal_search, checked)
        except ModelError as exc:
            raise BrainRefused('The response service could not finish this message. Please retry.') from exc
        self._authorised()
        at = datetime.now(timezone.utc).isoformat()
        response = {'turn_id': turn.turn_id, 'matter_id': None, 'chat_id': chat_id,
            'route': 'current_brain', 'mode': 'conversation', 'mode_statement': '',
            'blocked': False, 'blocked_reason': None, 'elements': release['elements'],
            'material': [], 'material_coverage': {}, 'metrics': model.metrics(),
            'replayed': False, 'committed': 'committed', 'input_admitted': True,
            'matter_version': version + 1, 'briefing': {}, 'board_changes': [],
            'at': at, 'composed': [], 'continuation': {}}
        response['service_status'] = release['service_status']
        row = {'contract': CONTRACT, 'turn_id': turn.turn_id, 'matter_id': identity,
            'chat_id': chat_id, 'advocate_id': turn.advocate_id, 'message': turn.message,
            'request': request, 'request_digest': request_digest, 'at': at,
            'label': label, 'preparation': prepared, 'release': release,
            'recovery': recovery,
            'research': research,
            'response': response, 'response_digest': _digest(response),
            'committed': True, 'release_state': 'released'}
        proposed = replace(matter, brain_chat=(*matter.brain_chat, row), version=version + 1)
        saved_rows(proposed, turn.advocate_id)
        # Both the exact original input and the reviewed display are in this one
        # compare-and-swap. Neither a provider success nor a draft is a receipt.
        try:
            committed = self.store.commit(proposed, expected_version=version)
        except (OSError, StaleWrite):
            # A lost acknowledgement may follow a successful replace. Lookup the
            # owned durable receipt; do not execute the three calls again here.
            try:
                committed = self.store.load(identity)
            except (OSError, ValueError):
                committed = None
            if committed is not None:
                for saved in saved_rows(committed, turn.advocate_id):
                    if saved['turn_id'] == turn.turn_id and saved['request_digest'] == request_digest:
                        return BrainOutput({**saved['response'], 'replayed': True})
            raise BrainRefused('The save could not be confirmed. Retry this same message to check it safely.',
                               code='save_unconfirmed', committed='unconfirmed') from None
        checked_rows = saved_rows(committed, turn.advocate_id)
        if not any(saved['turn_id'] == turn.turn_id and saved['request_digest'] == request_digest
                   for saved in checked_rows):
            raise BrainRefused('The save could not be confirmed.', committed='unconfirmed')
        return BrainOutput(response)
