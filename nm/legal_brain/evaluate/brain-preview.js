/* Finite fictional preview. Private POST/progress never supplies visible model text. */
'use strict';

(() => {
  const MARKER = 'Private fictional-matter evaluation—not client advice or release.';
  const portable = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
  const matterId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,160}$/.test(value);
  const validVersion = value => Number.isInteger(value) && value >= 1;
  const INSTRUCTION_KIND = 'advocate_original_instruction';
  const INSTRUCTION_TRUST = 'user_instruction_not_established_fact_or_legal_authority';
  const PUBLIC_REASON_STATES = new Set([
    'work_stopped', 'wording_review_failed', 'proposal_binding_failed',
  ]);
  const RATIONALE_AREAS = new Set(['understanding', 'disputes', 'act_passages',
    'case_law_passages', 'evidence_to_collect', 'case_to_prepare', 'arguments',
    'opposition', 'strengthen', 'cross_matter', 'questions']);
  const exactKeys = (row, keys) => row && typeof row === 'object' && !Array.isArray(row)
    && Object.keys(row).sort().join('|') === [...keys].sort().join('|');
  const identity = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

  function checkedWorkingExplanation(row) {
    const keys = ['version', 'state', 'client_ready', 'normal_cutover',
      'inventory_identity', 'checks', 'entries'];
    const counts = ['expected', 'present', 'checked', 'not_assessed', 'failed'];
    if (!exactKeys(row, keys) || row.version !== 'working-explanation-v1'
        || !['checked_private_rationale', 'unavailable'].includes(row.state)
        || row.client_ready !== false || row.normal_cutover !== false
        || !identity(row.inventory_identity) || !exactKeys(row.checks, counts)
        || counts.some(key => !Number.isSafeInteger(row.checks[key]) || row.checks[key] < 0)
        || row.checks.expected !== 24 || row.checks.present > 24
        || row.checks.checked + row.checks.not_assessed + row.checks.failed !== row.checks.present
        || !Array.isArray(row.entries) || row.entries.length > 100) {
      throw new Error('The checked working explanation could not be verified.');
    }
    if (row.state === 'unavailable') {
      if (row.entries.length) throw new Error('Unavailable working explanation cannot carry wording.');
      return row;
    }
    if (row.checks.present !== 24 || row.checks.checked !== 24 || !row.entries.length
        || new Set(row.entries.map(entry => entry?.id)).size !== row.entries.length
        || row.entries.some(entry => !exactKeys(entry,
          ['id', 'thread_id', 'area', 'package_identity', 'text'])
          || typeof entry.id !== 'string' || !entry.id.trim() || entry.id.length > 500
          || entry.thread_id !== null && (typeof entry.thread_id !== 'string'
            || !entry.thread_id.trim() || entry.thread_id.length > 500)
          || !RATIONALE_AREAS.has(entry.area) || !identity(entry.package_identity)
          || typeof entry.text !== 'string' || !entry.text.trim() || entry.text.length > 100000)) {
      throw new Error('The checked working explanation lacks its complete exact population.');
    }
    return row;
  }

  function checkedInstruction(row) {
    if (row === undefined) return null;
    if (!row || typeof row !== 'object' || Array.isArray(row)
        || Object.keys(row).sort().join('|') !== ['state', 'text', 'text_identity', 'provenance',
          'material_kind', 'trust'].sort().join('|')
        || row.material_kind !== INSTRUCTION_KIND || row.trust !== INSTRUCTION_TRUST) {
      throw new Error('The saved original instruction could not be verified.');
    }
    if (row.state === 'not_recorded') {
      if (row.text !== '' || row.text_identity !== '' || row.provenance !== 'not_recorded') {
        throw new Error('An unavailable instruction cannot supply reconstructed words.');
      }
      return null;
    }
    if (row.state !== 'recorded' || typeof row.text !== 'string' || !row.text.trim()
        || row.text.length > 100000 || typeof row.text_identity !== 'string'
        || !/^[a-f0-9]{64}$/.test(row.text_identity)
        || !['sealed_turn_admission', 'sealed_first_dispatch'].includes(row.provenance)) {
      throw new Error('The saved original instruction lacks its exact attributed record.');
    }
    return row;
  }

  function checkedPreview(data, matter, turn) {
    if (!data || data.matter_id !== matter || data.turn_id !== turn
        || !validVersion(data.matter_version) || data.evaluation_only !== true
        || data.released !== false || data.client_ready !== false || data.marker !== MARKER
        || !Array.isArray(data.paragraphs)) throw new Error('The checked preview could not be verified.');
    if (data.paragraphs.length && !['reviewed_private_candidate', 'checked_private_interaction']
        .includes(data.result_state)) throw new Error('Unchecked wording is not displayable.');
    if (PUBLIC_REASON_STATES.has(data.result_state) && (typeof data.message !== 'string'
        || !data.message.trim() || data.message.length > 2000)) {
      throw new Error('The public stopped-work explanation could not be verified.');
    }
    for (const row of data.paragraphs) {
      if (!row || typeof row.text !== 'string' || !row.text.trim()
          || !Array.isArray(row.references) || row.references.some(ref => typeof ref !== 'string')) {
        throw new Error('The checked paragraph population could not be verified.');
      }
    }
    checkedInstruction(data.original_instruction);
    if (data.working_explanation !== undefined) checkedWorkingExplanation(data.working_explanation);
    if (data.working_status !== undefined) {
      const work = data.working_status;
      const keys = ['state', 'total', 'checked', 'inapplicable', 'not_assessed',
        'closes_matter', 'establishes_facts_or_law', 'operations'];
      if (!work || Object.keys(work).sort().join('|') !== keys.sort().join('|')
          || !['complete_requested_work', 'work_outstanding', 'not_assessed'].includes(work.state)
          || ['total', 'checked', 'inapplicable', 'not_assessed'].some(key =>
            !Number.isSafeInteger(work[key]) || work[key] < 0)
          || work.total < 1 || work.checked + work.inapplicable + work.not_assessed !== work.total
          || work.state === 'complete_requested_work' && work.not_assessed !== 0
          || work.closes_matter !== false || work.establishes_facts_or_law !== false
          || !Array.isArray(work.operations) || work.operations.length > 2000
          || work.operations.some(row => !row || Object.keys(row).sort().join('|') !== 'label|state'
            || typeof row.label !== 'string' || !row.label.trim() || row.label.length > 400
            || typeof row.state !== 'string' || !row.state.trim() || row.state.length > 40)) {
        throw new Error('The saved working-status population could not be verified.');
      }
    }
    return data;
  }

  function parentLoops(data) {
    if (!data || !Array.isArray(data.loops)) throw new Error('The saved history could not be read.');
    const rows = data.loops.filter(row => row && portable(row.turn_id));
    if (rows.some(row => typeof row.terminal !== 'boolean')) {
      throw new Error('The saved original history lacks a checked completion state.');
    }
    if (new Set(rows.map(row => row.turn_id)).size !== rows.length) {
      throw new Error('The saved original history has ambiguous identities.');
    }
    return rows;
  }

  function create(env) {
    const doc = env.document, win = env.window;
    const get = id => doc.getElementById(id);
    const now = env.now || (() => performance.now());
    const state = {actor: null, session: 0, generation: 0, expires: 0, matter: null,
      version: null, pending: null, active: null, controllers: new Set(), timer: null,
      displayedInstructions: new Map()};
    const status = text => { get('status').textContent = text; };
    const textNode = (tag, text, className = '') => {
      const node = doc.createElement(tag); node.textContent = text; node.className = className;
      return node;
    };
    function abortAll() {
      state.controllers.forEach(controller => controller.abort()); state.controllers.clear();
    }
    function controls() {
      const enabled = Boolean(state.actor && state.matter && validVersion(state.version)
        && state.expires > now());
      get('message').disabled = !enabled || Boolean(state.active);
      get('send').disabled = !enabled || Boolean(state.active) || Boolean(state.pending);
      get('refresh').disabled = !enabled || Boolean(state.active) || Boolean(state.pending);
      get('open-matter').disabled = Boolean(state.active) || Boolean(state.pending);
      get('stop-waiting').hidden = !state.active;
      get('retry').hidden = !state.pending || Boolean(state.active) || !enabled;
    }
    function endSession(message) {
      win.NmSourceReader?.close(false);
      state.session += 1; state.generation += 1; abortAll();
      if (state.timer) win.clearTimeout(state.timer);
      state.actor = null; state.matter = null; state.version = null;
      state.active = null; state.pending = null;
      state.displayedInstructions.clear();
      for (const id of ['messages', 'history', 'matter-board']) get(id).replaceChildren();
      get('message').value = ''; get('message').style.height = 'auto';
      get('account-name').textContent = ''; get('workspace').hidden = true;
      get('signin').hidden = false; get('signin-message').textContent = message;
      controls();
    }
    function scope() { return {session: state.session, generation: state.generation, actor: state.actor}; }
    function current(captured) {
      return captured.session === state.session && captured.generation === state.generation
        && captured.actor === state.actor && state.expires > now();
    }
    win.NmSourceReader?.configure({
      scope: () => ({session: state.session, advocate: state.actor, pageMatter: state.matter}),
      read: path => request(path, {}, scope()),
    });
    async function request(path, options = {}, captured = null) {
      const controller = new AbortController(); state.controllers.add(controller);
      try {
        if (captured && !current(captured)) {
          const error = new Error('This request belongs to an earlier or expired view.');
          error.obsolete = true; throw error;
        }
        const headers = {'Accept': 'application/json', ...(options.headers || {})};
        if (options.method === 'POST') {
          const match = doc.cookie.match(/(?:^|;\s*)nm_csrf=([^;]*)/);
          if (!match) throw new Error('Your session protection is unavailable. Sign in again.');
          headers['X-NM-CSRF'] = decodeURIComponent(match[1]);
          headers['Content-Type'] = 'application/json';
        }
        const response = await env.fetch(path, {...options, headers, credentials: 'same-origin',
          cache: 'no-store', redirect: 'error', signal: controller.signal});
        if (response.status === 401) {
          endSession('Your session ended. Sign in to view the saved work.');
          const error = new Error('Your session ended.'); error.obsolete = true; throw error;
        }
        if (captured && !current(captured)) {
          const error = new Error('This response belongs to an earlier view.');
          error.obsolete = true; throw error;
        }
        if (!response.ok) {
          const error = new Error(response.status === 403
            ? 'No current fictional-evaluation approval permits this request.'
            : response.status === 409 ? 'The file changed or this saved work is not currently available.'
              : 'The server could not complete this request. No unchecked wording has been shown.');
          error.status = response.status; throw error;
        }
        const data = await response.json();
        if (captured && !current(captured)) {
          const error = new Error('This response belongs to an earlier view.');
          error.obsolete = true; throw error;
        }
        return data;
      } finally { state.controllers.delete(controller); }
    }
    function renderBoard(board, cover) {
      if (board.matter_id !== state.matter || cover.matter_id !== state.matter
          || !validVersion(board.version) || board.version !== cover.version
          || !Array.isArray(board.threads) || !Array.isArray(board.agenda?.disputes)) {
        throw new Error('The current matter board could not be read consistently. Refresh it.');
      }
      state.version = board.version;
      get('matter-title').textContent = typeof cover.title === 'string' ? cover.title : 'Recorded matter';
      get('matter-title').title = get('matter-title').textContent;
      const host = get('matter-board'); host.replaceChildren();
      const overview = textNode('section', '', 'card');
      overview.append(textNode('h3', 'Recorded file'), textNode('p',
        `Client: ${typeof cover.client === 'string' ? cover.client : 'Not recorded'}`));
      host.appendChild(overview);
      if (!board.agenda.disputes.length) host.appendChild(textNode('p',
        'No disputes have been established on the recorded board yet.', 'meta'));
      for (const dispute of board.agenda.disputes) {
        const card = textNode('section', '', 'card');
        card.append(textNode('h3', String(dispute.label || 'Recorded dispute')),
          textNode('p', String(dispute.next_need || 'Assessment not established.')));
        if (Array.isArray(dispute.requirements) && dispute.requirements.length) {
          const list = doc.createElement('ul'); list.className = 'checklist';
          const labels = {held: 'Information supplied', outstanding: 'Needs clarification',
            promised: 'Awaiting promised information', unavailable: 'Unavailable'};
          for (const row of dispute.requirements) list.appendChild(textNode('li',
            `${String(row.need || 'Recorded need')} — ${labels[row.state] || 'Not assessed'}`));
          card.appendChild(list);
        }
        host.appendChild(card);
      }
      controls();
    }
    async function board(captured) {
      const base = `/api/matters/${encodeURIComponent(state.matter)}`;
      const [result, cover] = await Promise.all([request(base, {}, captured),
        request(`${base}/cover`, {}, captured)]);
      if (current(captured)) renderBoard(result, cover);
    }
    function showPreview(data) {
      const rendered = scope();
      const article = textNode('article', '', 'message');
      if (!data.paragraphs.length) {
        article.appendChild(textNode('p', PUBLIC_REASON_STATES.has(data.result_state) ? data.message
          : 'This saved interaction is not yet fully checked for display.', 'meta'));
      } else {
        for (const [elementIndex, paragraph] of data.paragraphs.entries()) {
          article.appendChild(textNode('p', paragraph.text));
          if (paragraph.references.length) {
            const references = textNode('div', paragraph.references.join(' · '), 'references');
            if (win.NmSourceReader) {
              references.textContent = '';
              for (const [referenceIndex, reference] of paragraph.references.entries()) {
              const opener = textNode('button', `Read retrieved passage ${referenceIndex + 1}`);
              opener.type = 'button';
              opener.addEventListener('click', async () => {
                if (!current(rendered) || state.matter !== data.matter_id) return;
                const captured = scope(); opener.disabled = true;
                try {
                  const page = await request(`/api/matters/${encodeURIComponent(data.matter_id)}`
                    + `/brain/reviewed-preview/${encodeURIComponent(data.turn_id)}/sources/${elementIndex}`
                    + `?reference=${encodeURIComponent(reference)}`,
                    {}, captured);
                  if (!current(captured) || state.matter !== data.matter_id) return;
                  if (page.coverage !== 'saved_passage' || typeof page.digest !== 'string'
                      || !/^[a-f0-9]{64}$/.test(page.digest) || typeof page.label !== 'string') {
                    throw new Error('The captured private source identity could not be verified.');
                  }
                  win.NmSourceReader.open(data, {source: page}, elementIndex, opener,
                    {privatePreview: true});
                } catch (error) { if (!error.obsolete && current(captured)) status(error.message); }
                finally { if (current(captured)) opener.disabled = false; }
              });
              references.appendChild(opener);
              }
            }
            article.appendChild(references);
          }
        }
      }
      if (data.paragraphs.length && data.working_status) {
        const work = data.working_status, details = doc.createElement('details');
        details.appendChild(textNode('summary', 'Work recorded'));
        const explanation = work.state === 'complete_requested_work'
          ? 'The requested work has its recorded checks. This does not close the matter.'
          : work.state === 'work_outstanding'
            ? 'Some work remains outstanding. The current response does not complete the matter.'
            : 'Completeness of the requested work has not yet been assessed.';
        details.appendChild(textNode('p', explanation, 'meta'));
        for (const operation of work.operations) details.appendChild(textNode('p', operation.label, 'meta'));
        article.appendChild(details);
      }
      if (data.paragraphs.length && data.working_explanation?.state === 'checked_private_rationale') {
        const details = doc.createElement('details');
        details.appendChild(textNode('summary', 'Reasons supporting this work'));
        for (const entry of data.working_explanation.entries) {
          details.appendChild(textNode('p', entry.text));
        }
        article.appendChild(details);
      }
      get('messages').appendChild(article);
      get('messages').scrollTop = get('messages').scrollHeight;
      return article;
    }
    async function showInstruction(data, turn, captured, reopened) {
      const original = checkedInstruction(data.original_instruction);
      if (!original) {
        if (reopened || !state.displayedInstructions.has(turn)) get('messages').appendChild(textNode('p',
          'The original instruction is unavailable in this saved history.', 'meta'));
        return;
      }
      if (!env.crypto.subtle || typeof env.crypto.subtle.digest !== 'function') {
        throw new Error('This browser cannot verify the saved original input.');
      }
      const bytes = new TextEncoder().encode(JSON.stringify(original.text));
      const hash = Array.from(new Uint8Array(await env.crypto.subtle.digest('SHA-256', bytes)),
        value => value.toString(16).padStart(2, '0')).join('');
      if (!current(captured)) return;
      if (hash !== original.text_identity) throw new Error('The saved original input identity changed.');
      const existing = state.displayedInstructions.get(turn);
      if (existing) {
        if (existing.textContent !== original.text) {
          throw new Error('The saved instruction differs from the input shown for this interaction.');
        }
        return;
      }
      const bubble = textNode('article', original.text, 'message user');
      state.displayedInstructions.set(turn, bubble); get('messages').appendChild(bubble);
    }
    async function readPreview(turn, captured, {clear = false} = {}) {
      const matter = state.matter;
      const data = checkedPreview(await request(`/api/matters/${encodeURIComponent(matter)}`
        + `/brain/reviewed-preview/${encodeURIComponent(turn)}`, {}, captured), matter, turn);
      if (!current(captured)) return;
      if (clear) {
        state.displayedInstructions.clear();
        get('messages').replaceChildren(textNode('div',
          'Saved interaction. Original instructions are supplied words, not established facts.', 'history-label'));
      }
      await showInstruction(data, turn, captured, clear);
      if (!current(captured)) return;
      const article = showPreview(data);
      state.version = data.matter_version; controls();
      if (PUBLIC_REASON_STATES.has(data.result_state)) status(data.message);
      let displayRecorded = false;
      if (data.paragraphs.length) {
        try {
          const receipt = await request(`/api/matters/${encodeURIComponent(matter)}`
            + `/brain/reviewed-preview/${encodeURIComponent(turn)}/seen`,
          {method: 'POST', body: '{}'}, captured);
          if (receipt.matter_id !== matter || receipt.turn_id !== turn
              || !validVersion(receipt.matter_version) || receipt.matter_version < data.matter_version
              || receipt.result_state !== 'private_preview_display_recorded'
              || receipt.evaluation_only !== true || receipt.released !== false
              || receipt.client_ready !== false || typeof receipt.receipt_id !== 'string'
              || !receipt.receipt_id.trim() || typeof receipt.display_identity !== 'string'
              || !receipt.display_identity.trim()) throw new Error('The display receipt was not verified.');
          displayRecorded = true; state.version = receipt.matter_version;
        } catch (error) {
          if (error.obsolete || !current(captured)) throw error;
          article.appendChild(textNode('p',
            'The checked preview is shown, but its display history was not recorded. '
              + 'Later work may not know that this wording was displayed.', 'meta'));
        }
      }
      return {...data, displayRecorded};
    }
    async function history(captured) {
      const rows = parentLoops(await request(`/api/matters/${encodeURIComponent(state.matter)}/loops`,
        {}, captured));
      if (!current(captured)) return [];
      const host = get('history'); host.replaceChildren();
      const matter = state.matter;
      rows.forEach((row, index) => {
        const button = textNode('button', `Interaction ${index + 1}${row.terminal ? '' : ' — in progress'}`);
        button.type = 'button';
        button.addEventListener('click', async () => {
          if (state.active || state.pending || state.matter !== matter || !current(captured)) return;
          try { await readPreview(row.turn_id, captured, {clear: true}); }
          catch (error) { if (!error.obsolete) status(error.message); }
        });
        host.appendChild(button);
      });
      if (!rows.length) host.appendChild(textNode('p', 'No original evaluation interactions are saved yet.', 'meta'));
      return rows;
    }
    async function openMatter(ident) {
      if (!state.actor || !matterId(ident) || state.active) return;
      if (state.pending) {
        status('Check the earlier saved instruction before changing or refreshing the file.'); return;
      }
      win.NmSourceReader?.close(false);
      state.generation += 1; abortAll(); state.pending = null; state.version = null;
      state.displayedInstructions.clear();
      state.matter = ident; get('messages').replaceChildren(); get('history').replaceChildren();
      get('matter-board').replaceChildren(textNode('p', 'Reading the recorded board…', 'meta'));
      get('matter-id').value = ident; controls(); const captured = scope();
      try { await board(captured); await history(captured); status('Fictional evaluation file opened.'); }
      catch (error) {
        if (!error.obsolete && current(captured)) { state.version = null; controls(); status(error.message); }
      }
    }
    function resize() {
      const input = get('message'); input.style.height = 'auto';
      input.style.height = `${Math.min(180, Math.max(46, input.scrollHeight))}px`;
    }
    async function perform(work, retry = false) {
      if (state.active || !state.actor || state.matter !== work.matter || state.expires <= now()) return;
      const captured = scope(); state.active = work; controls(); status('The instruction is being checked.');
      try {
        if (retry) {
          const rows = await history(captured);
          const saved = rows.find(row => row.turn_id === work.body.turn_id);
          if (saved) {
            if (!saved.terminal) {
              status('The saved instruction is still in progress. Check it again; it has not been resent.');
              return;
            }
            const preview = await readPreview(work.body.turn_id, captured); await board(captured);
            state.pending = null; status(PUBLIC_REASON_STATES.has(preview.result_state) ? preview.message
              : preview.paragraphs.length
              ? preview.displayRecorded
                ? 'The checked saved work was reopened without sending the instruction again.'
                : 'The checked saved work was reopened, but display history was not recorded.'
              : 'The saved instruction finished, but its wording is not fully checked for display.');
            return;
          }
        }
        const meta = await request(`/api/matters/${encodeURIComponent(work.matter)}/brain/preview`,
          {method: 'POST', body: JSON.stringify(work.body)}, captured);
        if (meta.turn_id !== work.body.turn_id || meta.client_ready !== false
            || meta.result_state !== 'not_released' || !validVersion(meta.matter_version)) {
          throw new Error('The private work receipt could not be verified.');
        }
        state.version = meta.matter_version;
        const preview = await readPreview(work.body.turn_id, captured); await board(captured);
        const saved = (await history(captured)).find(row => row.turn_id === work.body.turn_id);
        if (!saved) throw new Error('The original saved instruction is not yet visible in protected history.');
        if (saved.terminal) state.pending = null;
        status(!saved.terminal ? 'The saved instruction is still in progress; check saved work before sending again.'
          : PUBLIC_REASON_STATES.has(preview.result_state) ? preview.message
            : preview.paragraphs.length ? preview.displayRecorded
            ? 'Checked saved wording opened. All work remains private evaluation.'
            : 'Checked saved wording opened, but display history was not recorded.'
            : 'The saved instruction finished, but its wording is not fully checked for display.');
      } catch (error) {
        if (!error.obsolete && current(captured)) {
          status(error.name === 'AbortError'
            ? 'You stopped waiting. Server work may continue; check saved work before sending again.'
            : error.message);
        }
      } finally { if (state.active === work) state.active = null; controls(); }
    }
    async function send() {
      const input = get('message'), words = input.value.trim();
      if (!words || state.active || !state.actor || !validVersion(state.version)
          || state.expires <= now()) return;
      if (state.pending) {
        status('Resolve or reopen the earlier saved instruction before starting another.'); return;
      }
      const turn = `pv_${env.crypto.randomUUID().replaceAll('-', '_')}`;
      const work = Object.freeze({matter: state.matter, body: Object.freeze({
        version: state.version, turn_id: turn, message: words, selected_issue_ids: Object.freeze([])})});
      state.pending = work;
      const bubble = textNode('article', words, 'message user');
      state.displayedInstructions.set(turn, bubble); get('messages').appendChild(bubble);
      input.value = ''; resize(); await perform(work);
    }
    async function start() {
      endSession('Checking your existing NM session…');
      const generation = state.session, sent = now();
      try {
        const session = await request('/api/session');
        if (generation !== state.session) return;
        const actor = session?.advocate?.id, seconds = session?.access_window?.remaining_seconds;
        if (typeof actor !== 'string' || !actor.trim() || !Number.isFinite(seconds) || seconds <= 0) {
          throw new Error('A current signed-in session could not be established.');
        }
        state.actor = actor; state.expires = sent + seconds * 1000;
        if (state.expires <= now()) throw new Error('The session expired while being checked.');
        get('account-name').textContent = session.advocate.name || session.advocate.email || 'Signed in';
        get('signin').hidden = true; get('workspace').hidden = false;
        state.timer = win.setTimeout(() => endSession('Your session expired. Sign in to continue.'),
          Math.max(0, state.expires - now()));
        const selected = new URLSearchParams(env.search || '').get('matter_id');
        if (selected && matterId(selected)) await openMatter(selected);
        controls();
      } catch (error) { if (!error.obsolete) endSession(error.message); }
    }
    get('matter-form').addEventListener('submit', event => {
      event.preventDefault(); void openMatter(get('matter-id').value.trim());
    });
    get('composer').addEventListener('submit', event => { event.preventDefault(); void send(); });
    get('message').addEventListener('input', resize);
    get('message').addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
        event.preventDefault(); void send();
      }
    });
    get('refresh').addEventListener('click', () => { if (state.matter) void openMatter(state.matter); });
    get('check-session').addEventListener('click', () => { void start(); });
    get('retry').addEventListener('click', () => { if (state.pending) void perform(state.pending, true); });
    get('stop-waiting').addEventListener('click', abortAll);
    win.addEventListener('pagehide', () => endSession('This evaluation view has closed.'));
    win.addEventListener('pageshow', event => { if (event.persisted) void start(); });
    return {start, openMatter, send, endSession, state};
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = {create, checkedPreview, checkedInstruction, parentLoops};
  else {
    const preview = create({document, window, fetch: window.fetch.bind(window), crypto: window.crypto,
      search: window.location.search});
    void preview.start();
  }
})();
