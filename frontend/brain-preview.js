/* Finite fictional preview. Private POST/progress never supplies visible model text. */
'use strict';

(() => {
  const MARKER = 'Private fictional-matter evaluation—not client advice or release.';
  const portable = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value);
  const matterId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,160}$/.test(value);
  const validVersion = value => Number.isInteger(value) && value >= 1;
  const INSTRUCTION_KIND = 'advocate_original_instruction';
  const INSTRUCTION_TRUST = 'user_instruction_not_established_fact_or_legal_authority';
  const PUBLIC_REASON_STATES = new Set(['work_stopped', 'wording_review_failed']);

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
      const article = textNode('article', '', 'message');
      if (!data.paragraphs.length) {
        article.appendChild(textNode('p', PUBLIC_REASON_STATES.has(data.result_state) ? data.message
          : 'This saved interaction is not yet fully checked for display.', 'meta'));
      } else {
        for (const paragraph of data.paragraphs) {
          article.appendChild(textNode('p', paragraph.text));
          if (paragraph.references.length) article.appendChild(textNode('div',
            `Recorded references: ${paragraph.references.join(' · ')}. `
              + 'A verified private-source reader is not available in this view.', 'references'));
        }
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
