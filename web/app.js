/* The client renders state. It computes nothing.
 *
 * Two rules from the PRD are enforced here rather than assumed:
 *
 *   1. A board that cannot be built renders an EXPLICIT FAILURE, never an
 *      empty one. An empty board tells the advocate they have no matters,
 *      which is defect shape S1 in its most visible possible form.
 *   2. A loud signal is never collapsed and never placed below the fold. The
 *      server marks them; the client must not quietly de-emphasise them.
 */
'use strict';

const $ = (id) => document.getElementById(id);

const state = {
  /* WHO THE SERVER SAYS WE ARE. Never typed, never a default: it is
   * filled from /api/session and cleared on sign-out. It used to be an
   * editable text box, which was the whole of authentication (B-082). */
  advocate: null,
  workspace: null,
  matterId: null,
  // BK-36. THE VERSION THIS TAB LAST SAW, sent with every brief so the server
  // can refuse a write built on a file this tab has never read.
  matterVersion: null,
  matterReady: false,
  // B3-B5. The intake answers, held from the form until the first brief
  // carries them onto the file.
  intake: null,
  turns: [],
  // BK-40. WHAT THE ADVOCATE WAS PART-WAY THROUGH WRITING, kept across a
  // session that ended under them, and SCOPED TO THE ADVOCATE IT BELONGS TO.
  // It is held in memory and deliberately not in `localStorage`: a draft that
  // survives the tab survives the next person to use the machine, and a
  // brief names a client.
  draft: null,
  // `none` | `signing_out` | `unconfirmed`. A logout the server did not
  // confirm is its own state, because the alternative is showing an ordinary
  // sign-in screen and letting that stand as proof.
  signOut: 'none',
  // Set once the session has been declared over, so a page with six panes
  // firing six requests reports it once rather than six times.
  ended: false,
  // BK-72. Every asynchronous rail render owns one generation. If the
  // advocate navigates again while its request is in flight, the old render
  // loses the right to paint or close anything.
  railGeneration: 0,
  sessionGeneration: 0,
  searchGeneration: 0,
  historyGeneration: 0,
  historyListGeneration: 0,
  sessionsGeneration: 0,
};

let pendingApplication = null;
let registrationInFlight = false;
let outcomeReturn = 'register';
let activeDelivery = null;
let retiringSession = null;

// In-memory work belongs to an advocate, workspace and file (or one unsaved
// opening), not to the composer DOM. The immutable pending request belongs to
// that same context, even if its acknowledgement or session is lost.
const intentContexts = new Map();
const INTAKE_INPUTS = ['in-client', 'in-adverse', 'in-others', 'in-scope'];
let activeIntent = null;

function intentKey(matterId) {
  return JSON.stringify([state.advocate, state.workspace, matterId || 'unsaved-opening']);
}

function ownsIntent(intent) {
  return intent && intent === activeIntent && intent.advocate === state.advocate
    && intent.workspace === state.workspace;
}

function matchesIntake(entry, intake) {
  return JSON.stringify(entry.request.parties) === JSON.stringify((intake && intake.parties) || {})
    && JSON.stringify(entry.request.release) === JSON.stringify((intake && intake.release) || {})
    && JSON.stringify(entry.request.capacity || null) === JSON.stringify((intake && intake.capacity) || null);
}

function snapshotIntent() {
  if (!ownsIntent(activeIntent)) return;
  activeIntent.text = $('message').value;
  activeIntent.intake = state.intake;
  activeIntent.intakeOpen = !$('intake').hidden;
  activeIntent.fields = Object.fromEntries(INTAKE_INPUTS.map((id) => [id, $(id).value]));
  activeIntent.capacity = $('in-capacity').checked;
}

function restoreIntent() {
  const intent = activeIntent;
  $('message').value = intent ? intent.text : '';
  state.intake = intent ? intent.intake : null;
  INTAKE_INPUTS.forEach((id) => { $(id).value = (intent && intent.fields[id]) || ''; });
  $('in-capacity').checked = Boolean(intent && intent.capacity);
  $('intake-state').textContent = '';
  showIntake(Boolean(intent && intent.intakeOpen));
}

function selectIntent(matterId, { opening = false } = {}) {
  snapshotIntent();
  if (!state.advocate || (!matterId && !opening)) activeIntent = null;
  else {
    const key = intentKey(matterId);
    if (!intentContexts.has(key)) intentContexts.set(key, {
      key, advocate: state.advocate, workspace: state.workspace,
      matterId: matterId || null, text: '', intake: null, intakeOpen: opening,
      fields: {}, capacity: false, pending: [],
    });
    activeIntent = intentContexts.get(key);
  }
  restoreIntent();
}

function reconcileIntent(transcript) {
  if (!activeIntent) return;
  snapshotIntent();
  const recorded = new Set(transcript.filter(turn => turn.committed === true
    && turn.release_state === 'released').map(turn => turn.turn_id).filter(Boolean));
  activeIntent.pending = activeIntent.pending.filter((entry) => {
    if (!recorded.has(entry.turnId)) return true;
    const receipt = transcript.find(turn => turn.turn_id === entry.turnId);
    if (receipt.input_admitted === true && activeIntent.text.trim() === entry.brief.trim()) {
      activeIntent.text = '';
    }
    if (matchesIntake(entry, activeIntent.intake)) activeIntent.intake = null;
    return false;
  });
  restoreIntent();
  state.turns.push(...activeIntent.pending);
}

/* --------------------------------------------------------------- fetch --- */

// EVERY 401 IN ONE PLACE (BK-40).
//
// This had none, so an expired session left the masthead claiming the
// advocate was signed in while each pane failed on its own. They were looking
// at their own name, their firm and their enrolment number above a product
// that could no longer do anything for them -- and the panes that had already
// painted still showed a matter list belonging to a session that was over.
//
// It fires only when we BELIEVE we are signed in. `boot()` gets a 401 as the
// ordinary answer for "nobody is signed in yet", and treating that as a
// session ending would greet every first-time visitor with a notice that
// their session expired.
function sessionEnded(message) {
  if (state.ended) return;
  state.ended = true;
  keepDraft();
  clearPrivileged();
  showGate(message);
}

// THE DRAFT IS FROZEN, NOT DISCARDED. An advocate half-way through a brief
// when the session lapses has typed the most expensive thing on the screen.
function keepDraft() {
  snapshotIntent();
  state.draft = activeIntent;
}

// PRIVILEGED CONTENT COMES OFF THE GLASS IMMEDIATELY, in one place, so a
// surface added later cannot be the one that keeps painting a matter after
// the session behind it is gone.
function clearPrivileged() {
  state.sessionGeneration += 1;
  state.searchGeneration += 1;
  state.historyGeneration += 1;
  state.historyListGeneration += 1;
  state.sessionsGeneration += 1;
  $('sessions-dialog').close();
  $('sessions-body').textContent = '';
  forgetRotationSecrets();
  clearRecoveryCodeDisplay();
  pendingApplication = null;
  if (activeDelivery) {
    activeDelivery.entry.state = 'unknown';
    activeDelivery.entry.error = 'The session ended before this request was confirmed.';
    activeDelivery.controller.abort();
  }
  activeDelivery = null;
  activeIntent = null;
  state.railGeneration += 1;
  state.advocate = null;
  state.workspace = null;
  state.matterId = null;
  state.turns = [];
  ['thread', 'rail-body', 'rail-meta', 'search-results', 'history-body',
   'who-detail', 'professional-approval', 'save-status', 'search-index', 'search-state', 'history-state']
    .forEach((id) => { const el = $(id); if (el) el.textContent = ''; });
  $('matter-heading').textContent = 'My work';
  $('workspace-eyebrow').textContent = 'YOUR WORKSPACE';
  state.matterVersion = null;
  state.matterReady = false;
  state.intake = null;
  ['in-client', 'in-adverse', 'in-others', 'in-scope', 'q', 'f-court', 'f-from', 'f-to']
    .forEach((id) => { $(id).value = ''; });
  $('in-capacity').checked = false;
  const who = $('who-name');
  if (who) who.textContent = '—';
  const workspace = $('workspace-name');
  if (workspace) workspace.textContent = '—';
  const composer = $('message');
  if (composer) composer.value = '';
  const chooser = $('history-matter');
  if (chooser) chooser.innerHTML = '<option value="">Choose a matter…</option>';
  window.dispatchEvent(new Event('nm:session-ended'));
}

// BK-31-AC20. The value the server hands this page so it can prove a request
// came from here. It is a SEPARATE, READABLE cookie: the session cookie is
// httponly and this script cannot see it, which is the whole point -- a
// cross-site page can read neither, and cannot set a custom header at all.
function cookie(name) {
  const match = document.cookie.match(
    new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

async function api(path, options, { sessionBound = true } = {}) {
  if (['/api/login', '/api/register', '/api/recover'].includes(path)) {
    await settleRetirementForLogin();
  }
  const sessionGeneration = state.sessionGeneration;
  // IN THE ONE HELPER, NOT AT THE CALL SITES. Every request in this file goes
  // through here, so no future caller can forget the header and discover it as
  // a 403 in a browser somebody else is using. CLAUDE.md §4: what refuses the
  // second copy is that there is nowhere else to put it.
  const method = ((options && options.method) || 'GET').toUpperCase();
  if (UNSAFE.has(method)) {
    const token = cookie('nm_csrf');
    if (token) {
      options = { ...(options || {}) };
      options.headers = { ...(options.headers || {}), 'X-NM-CSRF': token };
    }
  }
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (sessionBound && sessionGeneration !== state.sessionGeneration) {
    const err = new Error('The session changed before this response arrived.');
    err.obsolete = true;
    throw err;
  }
  if (res.status === 401 && state.advocate && !state.ended) {
    sessionEnded('Your session ended, so I signed you out and stopped work on '
                 + 'this matter. Sign in again and I will put your draft back '
                 + 'where it was.');
  }
  if (!res.ok) {
    const detail = (body && (body.detail || body.message)) || `HTTP ${res.status}`;
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    err.status = res.status;
    // Keep the STRUCTURE. A withheld turn carries which gate withheld it and
    // what could not be established, and flattening that to a message string
    // throws away the only part the advocate can act on.
    err.detail = detail;
    throw err;
  }
  return body;
}

/* --------------------------------------------------------------- health --- */

async function loadHealth() {
  const el = $('health');
  try {
    const h = await api('/api/health');
    // J-7. THE MASTHEAD SPEAKS THE ADVOCATE'S LANGUAGE.
    //
    // MEASURED: `openai/gpt-4o-mini-2024-07-18 · hard: not configured ·
    // judge: configured · store: fernet · corpus: readable · manifest: 22
    // acts`, on every screen. `hard: not configured` reads as something
    // broken; `store: fernet` is a cipher name; the model id is ours and not
    // theirs. None of it is a fact about their matter.
    //
    // WHAT AN ADVOCATE NEEDS FROM THIS LINE is whether the corpus can be
    // read, because that is the one thing that changes what the product can
    // tell them. The rest moves to the title, where it is one hover away for
    // whoever needs it and out of the reading line for everyone else.
    const readable = h.corpus === 'readable';
    el.textContent = readable
      ? 'Legal library available · check the scope of each result'
      : 'Legal library unavailable · authority-backed research is limited';
    el.title = 'Library availability does not establish legal coverage or currency.';
    el.classList.toggle('bad', !readable);
    $('rehearsal-warning').hidden = h.provider !== 'scripted';
  } catch (e) {
    if (e.obsolete) return;
    // A CONFIGURATION THAT WAS REFUSED IS AN ADVOCATE-FACING FACT: the
    // product cannot answer. The detail stays in the title.
    el.textContent = 'Not ready — I cannot answer on this matter yet';
    el.title = `configuration refused: ${e.message}`;
    el.classList.add('bad');
  }
}

/* ------------------------------------------------- the two board surfaces --- */

function stateBlock(kind, text) {
  const d = document.createElement('div');
  d.className = `state ${kind}`;
  d.textContent = text;
  return d;
}

function field(dl, label, value) {
  const dt = document.createElement('dt'); dt.textContent = label;
  const dd = document.createElement('dd');
  if (value && value.pill) {
    const s = document.createElement('span');
    s.className = `pill ${value.pill}`; s.textContent = value.text;
    dd.appendChild(s);
  } else {
    dd.textContent = value;
  }
  dl.append(dt, dd);
}

// BK-33. FOUR DEADLINE STATES, RENDERED AS FOUR THINGS.
//
// The API sends `next_deadline_status` as `not_assessed`, `none_on_this_
// matter`, `upcoming` or `passed`, and this rendered `m.next_deadline ||
// 'none recorded'` -- which turns the first two into the same sentence.
//
// "Nobody has worked out the deadlines on this file" and "this file has no
// deadlines" are opposite facts, and an advocate acting on the second when
// the first is true has been told the file is clear by a product that never
// looked. That is defect shape S1 at the top of the list an advocate scans
// first thing in the morning.
function deadlineField(m) {
  const status = m.next_deadline_status;
  const gone = Array.isArray(m.passed_deadlines) ? m.passed_deadlines : [];
  const uncomputed = Array.isArray(m.uncomputed_deadlines) ? m.uncomputed_deadlines : [];
  const unreadable = Array.isArray(m.deadline_unreadable) ? m.deadline_unreadable.length : 0;
  const unassessed = Array.isArray(m.deadline_unassessed) ? m.deadline_unassessed.length : 0;
  const incomplete = m.deadline_assessment === 'incomplete' || unreadable > 0
    || (unassessed > 0 && m.deadline_assessment !== 'not_assessed');
  const parts = [];
  if (m.next_deadline) parts.push(`${m.next_deadline}${status === 'near' ? ' — soon' : ''}`);
  if (gone.length) {
    parts.push(`${gone[0].on} — PASSED${gone.length > 1 ? ` (+${gone.length - 1} more)` : ''}`);
  } else if (status === 'passed') {
    parts.push('passed deadline — recorded date unavailable');
  }
  if (uncomputed.length) parts.push(`${uncomputed.length} deadline(s) with no date established`);
  else if (status === 'not_computed') parts.push('a deadline with no date established');
  if (!parts.length) {
    if (status === 'not_assessed' || m.deadline_assessment === 'not_assessed') {
      parts.push('deadline register not assessed');
    } else if (!incomplete && ['none_on_this_matter', 'none_on_this_thread'].includes(status)) {
      parts.push(status === 'none_on_this_thread' ? 'none on this thread' : 'none on this matter');
    } else parts.push('deadline position not established');
  }
  if (incomplete) parts.push('register incomplete');
  if (unreadable) parts.push(`${unreadable} unreadable record(s)`);
  if (unassessed) parts.push(`${unassessed} thread(s) not assessed`);
  const text = parts.join(' · ');
  if (gone.length || status === 'passed' || status === 'near') return { pill: 'blocked', text };
  if (incomplete || status === 'not_assessed' || status === 'not_computed') {
    return { pill: 'unknown', text };
  }
  if (['none_on_this_matter', 'none_on_this_thread'].includes(status)) return { pill: 'ok', text };
  return text;
}

async function showMatterList({ preserveIntent = false } = {}) {
  if (!preserveIntent) selectIntent(null);
  const generation = ++state.railGeneration;
  state.matterId = null;
  state.matterVersion = null;
  state.matterReady = false;
  state.turns = [];
  $('thread').textContent = '';
  $('pane-advise').dataset.matterId = '';
  $('rail-title').textContent = 'Matters';
  $('back').hidden = true;
  $('matter-heading').textContent = 'My work';
  $('workspace-eyebrow').textContent = 'YOUR WORKSPACE';
  $('save-status').textContent = '';
  updateWorkspace();
  window.dispatchEvent(new Event('nm:matter-changed'));
  const body = $('rail-body');
  body.replaceChildren(stateBlock('building', 'Loading matters…'));

  let data;
  try {
    data = await api('/api/matters');
  } catch (e) {
    if (generation !== state.railGeneration) return;
    // NEVER render an unreadable board as an empty one.
    body.replaceChildren(stateBlock(
      'unbuildable',
      `The matter list could not be built: ${e.message}. This is a failure to ` +
      `read, not a statement that you have no matters.`));
    $('rail-meta').textContent = 'Matter list unavailable';
    return;
  }
  if (generation !== state.railGeneration) return;

  $('rail-meta').textContent = `${data.row_count} matter${data.row_count === 1 ? '' : 's'}`;
  const incomplete = data.state !== 'ok';
  const notice = incomplete ? stateBlock('unbuildable',
    'Some matters could not be loaded. This list may be incomplete. Retry before relying on it.') : null;

  if (!data.matters.length) {
    body.replaceChildren(notice || stateBlock('empty', 'No matters yet. Start with a new brief.'));
    return;
  }

  body.replaceChildren(...data.matters.map((m) => {
    const row = document.createElement('div');
    row.className = 'row' + (m.blocked ? ' loud' : '');
    row.dataset.matterId = m.matter_id;
    row.setAttribute('role', 'button');
    row.tabIndex = 0;
    row.setAttribute('aria-label', `Open ${m.matter}`);
    const t = document.createElement('div');
    t.className = 'r-title'; t.textContent = m.matter;
    const dl = document.createElement('dl'); dl.className = 'r-fields';
    // WHO THE FILE IS FOR AND WHO IT IS AGAINST. BK-33's acceptance is that
    // ten similar matters stay distinguishable, and `threads: 1` on every row
    // distinguishes nothing.
    field(dl, 'client', m.client || 'not recorded');
    field(dl, 'against', m.opponent || 'not recorded');
    field(dl, 'deadline', deadlineField(m));
    field(dl, 'last worked', m.last_touched || 'never worked');
    field(dl, 'posture', m.blocked
      ? { pill: 'blocked', text: m.blocked }
      : { pill: 'unknown', text: 'no unresolved posture recorded' });
    row.append(t, dl);
    row.onclick = () => showThreadBoard(m.matter_id);
    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        showThreadBoard(m.matter_id);
      }
    });
    return row;
  }));
  if (notice) body.prepend(notice);
}

async function showThreadBoard(
  matterId, { restore = true, closeNavigator = true, adoptOpening = false } = {}) {
  // Only a confirmed opening operation may transfer its local draft to the
  // newly saved shell. Selecting a list row must never imply this transfer.
  if (adoptOpening && ownsIntent(activeIntent) && !activeIntent.matterId
      && !activeIntent.pending.length) {
    snapshotIntent();
    intentContexts.delete(activeIntent.key);
    activeIntent.matterId = matterId;
    activeIntent.key = intentKey(matterId);
    activeIntent.intakeOpen = false;
    intentContexts.set(activeIntent.key, activeIntent);
    restoreIntent();
  }
  selectIntent(matterId);
  const generation = ++state.railGeneration;
  // OPENING A MATTER CLOSES THE LIST at narrow widths. Leaving it up would
  // put the advocate on the answer they asked for with the index still over
  // it, which is the same unreachability wearing the other face.
  if (closeNavigator) toggleMatters(false);
  state.matterId = matterId;
  state.matterVersion = null;
  state.matterReady = false;
  $('matter-heading').textContent = 'Loading matter…';
  $('save-status').textContent = '';
  if (restore) {
    state.turns = [];
    $('thread').textContent = '';
  }
  window.dispatchEvent(new Event('nm:matter-changed'));
  $('pane-advise').dataset.matterId = matterId;
  $('rail-title').textContent = 'Issues in this matter';
  $('back').hidden = false;
  const body = $('rail-body');
  body.replaceChildren(stateBlock('building', 'Loading threads…'));

  let data;
  try {
    data = await api(`/api/matters/${matterId}`);
    if (generation !== state.railGeneration) return;
    // BK-36. THE VERSION THIS TAB HAS NOW SEEN. Every brief carries it, so a
    // tab that loaded the file and sat is refused rather than writing onto a
    // version it never read.
    if (!Number.isInteger(data.version) || data.version < 0) {
      throw new Error('The saved file version could not be established. Please reopen the matter.');
    }
    state.matterVersion = data.version;
    state.matterReady = true;
  } catch (e) {
    if (generation !== state.railGeneration) return;
    body.replaceChildren(stateBlock(
      'unbuildable', `The thread board could not be built: ${e.message}`));
    $('rail-meta').textContent = 'Matter could not be loaded';
    return;
  }

  $('rail-meta').textContent = `${data.row_count} recorded issue${data.row_count === 1 ? '' : 's'}`;
  $('matter-heading').textContent = data.title || 'Untitled matter';
  $('workspace-eyebrow').textContent = 'MATTER WORKSPACE';
  $('save-status').textContent = 'Recorded file';
  updateWorkspace();
  window.dispatchEvent(new Event('nm:matter-changed'));

  // BK-33. THE CONVERSATION COMES BACK WITH THE FILE.
  //
  // Opening a matter loaded its thread board and nothing else, so a reload of
  // a live authenticated session landed on a blank Advise pane: the advocate
  // was signed in, the file was there, and everything they had been told was
  // gone from the screen. The transcript is the only thing that keeps what
  // was SERVED -- the matter holds facts and the metrics hold counts with no
  // client words -- so this is the only place it can come from.
  // ONLY WHEN THERE IS NOTHING LIVE TO REPLACE.
  //
  // `showThreadBoard` runs after EVERY send, and restoring unconditionally
  // overwrote the turn that had just been served with its read-back copy --
  // which keeps what the advocate read and NOT the run's gates, latency or
  // cost. So a live answer silently became `read back from the record` the
  // moment its own board refreshed, and the working under it emptied.
  //
  // Caught by two journey phases at once: 5b found the gate states gone from
  // a turn it had just watched being served, and 9 found the restore working
  // perfectly in isolation and not in sequence.
  if (restore && !(await restoreConversation(matterId, generation))) return;
  if (generation !== state.railGeneration) return;

  body.replaceChildren(...data.threads.map((t) => {
    const row = document.createElement('div');
    // Unresolved posture renders LOUDLY, as a value, not as an empty field.
    row.className = 'row static' + (t.loud ? ' loud' : '');
    const title = document.createElement('div');
    title.className = 'r-title'; title.textContent = t.thread;
    const dl = document.createElement('dl'); dl.className = 'r-fields';
    field(dl, 'our client', t.our_client_is === 'unknown'
      ? { pill: 'unknown', text: 'unknown' } : t.our_client_is);
    field(dl, 'side', t.side === 'unknown'
      ? { pill: 'unknown', text: 'unknown — blocks advice' } : t.side);
    field(dl, 'against', t.against);
    field(dl, 'forum', t.forum);
    field(dl, 'stage', t.stage);
    field(dl, 'deadline', deadlineField(t));
    row.append(title, dl);
    return row;
  }));
}

// BK-33. THE SERVED CONVERSATION, READ BACK.
//
// A RESTORED TURN SAYS IT WAS RESTORED. The transcript keeps what the
// advocate read; it does not keep the latency, the token counts or the cost,
// because those are facts about the RUN and not about the answer. Rendering
// them as zeros would put `latency 0ms · calls 0 · cost $0.000000` under a
// turn that really did cost something -- a measurement nobody made, shown as
// a measurement. So the audit line for a read-back turn says where it came
// from instead.
async function restoreConversation(matterId, generation = state.railGeneration) {
  state.turns = [];
  let d;
  try {
    d = await api(`/api/matters/${matterId}/transcript`);
  } catch (e) {
    if (generation !== state.railGeneration) return false;
    // NOT SILENT. A conversation that could not be read back is not a
    // conversation that did not happen, and an empty pane says the second.
    state.turns = [{
      brief: '',
      answer: {
        elements: [{
          kind: 'ground', disclosure: true, section: 'needed', refs: [],
          signal: 'none',
          text: `I could not read this matter's served conversation back: `
              + `${e.message}. I cannot verify the conversation's completeness `
              + `or integrity from this failed read. Do not assume missing records are intact.`,
        }],
        metrics: null, restored: true,
      },
    }];
    reconcileIntent([]);
    repaint();
    return true;
  }

  if (generation !== state.railGeneration) return false;

  state.turns = (d.turns || []).map(restoredTurn);

  reconcileIntent(d.turns || []);
  if (d.unreadable_reason) {
    state.turns.push({
      brief: '',
      answer: {
        elements: [{
          kind: 'ground', disclosure: true, section: 'needed', refs: [],
          signal: 'none', text: d.unreadable_reason,
        }],
        metrics: null, restored: true,
      },
    });
  }
  repaint();
  return true;
}

/* -------------------------------------------------------------- the answer --- */

const KIND_LABEL = {
  action: 'Action',
  finding: 'Finding',
  question: 'Blocking question',
  ground: 'Ground',
};

// Both matter re-entry and History consume the same release projection.
// Diagnostic presence alone never turns a withheld draft into ordinary advice.
function restoredTurn(turn) {
  if (turn.committed !== true || !['released', 'legacy_released'].includes(turn.release_state)) {
    return { brief: turn.message || turn.asked || '', state: 'not_established',
      error: turn.blocked_reason || 'Release and successful commitment could not be established.',
      refusal: { withheld_by: turn.withheld_by || [],
        why: turn.blocked_reason || 'This archival record is not a released answer.',
        not_established: turn.not_established || [] } };
  }
  return { brief: turn.message || turn.asked || '', answer: {
    elements: turn.elements || [], blocked: turn.blocked,
    blocked_reason: turn.blocked_reason, metrics: null, restored: true,
    at: turn.at || '', raw: turn,
  } };
}

// BK-37. THE SECTIONS, IN THE ORDER COUNSEL READS THEM.
//
// The order and the headings come from `nm/domain/brief.py`; this is the
// rendering of a decision made there, not a second one. A flat answer of 31
// elements was measured on one single-dispute brief (J-6) -- nothing in it
// wrong, and no order anyone chose, so the two lines an advocate acts on were
// somewhere in the middle of nine "they will say" paragraphs.
const SECTIONS = [
  ['position',  'Where this stands'],
  ['window',    'Time'],
  ['risk',      'What cuts against us'],
  ['next',      'Next step'],
  ['needed',    'What I still need'],
  ['because',   'Why'],
  ['authority', 'What it rests on'],
];

// WHAT THE ADVOCATE IS NOT SHOWN BY DEFAULT, and it is a door rather than a
// deletion. J-7: gate ids, rule ids, token counts and the trace line are
// engineering vocabulary on an advocate's screen. They are what makes every
// claim checkable and this whole product is an argument for keeping them --
// they answer HOW THIS WAS MADE, which counsel reading for the position is
// not asking. Present, checkable, out of the way.
let SHOW_AUDIT = false;

function renderTurn(entry) {
  const wrap = document.createElement('div');
  wrap.className = 'turn';

  if (entry.brief) {
    // THE ADVOCATE'S OWN SENTENCES, set apart as theirs. Everything else on
    // this screen is something the product wrote; a reader scanning back
    // through a long matter needs to find what THEY said without reading.
    const row = document.createElement('div');
    row.className = 'said-row';
    const b = document.createElement('div');
    b.className = 'brief';
    b.textContent = entry.brief;
    row.appendChild(b);
    wrap.appendChild(row);
  }

  if (entry.error) {
    // A WITHHELD TURN IS STRUCTURED, and dumping its JSON at the advocate
    // wastes the one thing that makes a refusal useful — what could not be
    // established. `not_established` asserts no law, so it is shown in full.
    const f = document.createElement('div');
    f.className = 'failure';
    const refusal = entry.refusal;

    if (refusal && refusal.withheld_by && refusal.withheld_by.length) {
      const h = document.createElement('div');
      h.className = 'refusal-head';
      h.textContent = `Withheld by ${refusal.withheld_by.join(', ')} — nothing was emitted.`;
      f.appendChild(h);
      const why = document.createElement('div');
      why.className = 'refusal-why';
      why.textContent = refusal.why || '';
      f.appendChild(why);
      for (const line of (refusal.not_established || [])) {
        const d = document.createElement('div');
        d.className = 'refusal-gap';
        d.textContent = line;
        f.appendChild(d);
      }
    } else {
      f.textContent = `The turn was refused: ${entry.error}`;
    }

    // BK-36. WAS IT SAVED, AND WHAT DO I DO NOW.
    //
    // `The turn was refused: HTTP 500` told the advocate nothing they could
    // act on and, worse, nothing about whether their brief had landed. The
    // three states are different actions: `not_committed` means send it
    // again, `stale` means the file moved and has been re-read, and `unknown`
    // means the server may or may not hold it -- which is precisely when a
    // retry must reuse the same turn id rather than write a second copy.
    const SAID = {
      not_committed: 'Your brief was NOT saved. Nothing was recorded on the '
                   + 'file, so sending it again adds it once.',
      stale: 'This matter moved while you were writing. I have re-read it — '
           + 'check the answer above, then send again if it still applies.',
      unknown: 'I could not tell whether your brief was saved. Sending again '
             + 'is safe: it carries the same turn id, so if it did land the '
             + 'server recognises it rather than recording it twice.',
      replay_refused: 'The earlier response remains saved, but cannot be replayed '
                     + 'under the current permission. No new answer was saved or released. '
                     + 'Review the current declaration before making a new request.',
    };
    if (SAID[entry.state]) {
      const d = document.createElement('div');
      d.className = 'refusal-gap';
      d.textContent = SAID[entry.state];
      f.appendChild(d);
    }
    if (entry.turnId && ['unknown', 'not_committed'].includes(entry.state)) {
      const again = document.createElement('button');
      again.className = 'ghost';
      again.textContent = 'Send this brief again';
      again.addEventListener('click', () => deliver(entry));
      f.appendChild(again);
    }
    wrap.appendChild(f);
    return wrap;
  }

  // In flight. The optimistic repaint happens BEFORE the answer arrives, so
  // this branch must exist -- without it the first repaint of every turn
  // throws on `entry.answer.elements` and the send silently does nothing.
  if (!entry.answer) {
    const pending = document.createElement('div');
    pending.className = 'el ground';
    pending.innerHTML = '<span class="k">Working</span>';
    const b = document.createElement('div');
    b.className = 'body';
    b.textContent = 'Settling the frame and checking the corpus…';
    pending.appendChild(b);
    wrap.appendChild(pending);
    return wrap;
  }

  if (entry.answer.replayed) {
    wrap.appendChild(stateBlock('quiet',
      'Earlier recorded response recovered. This is not a new assessment; the file may have changed since it was prepared.'));
  } else if (entry.answer.restored) {
    wrap.appendChild(stateBlock('quiet',
      'Recorded response. It has not been reassessed against later changes to the file.'));
  }

  // WHAT FOLDS AND WHAT MAY NEVER FOLD.
  //
  // A GROUND element carrying `disclosure` is what could not be established --
  // the screens that have not run, the corpus gap, the read that came back
  // empty. Folding those is B-128 in reverse: that defect WAS a disclosure the
  // advocate could not see. §9 wants the third state visible in the OUTPUT,
  // and behind a triangle is available rather than visible.
  //
  // A non-none signal is equally material, whatever kind carries it. Only
  // an explicitly unsignalled, non-disclosure GROUND can be support; missing
  // or unfamiliar signal metadata stays visible. One predicate owns both
  // halves, so a newly introduced signal or kind cannot fall between lists.
  const foldsAsSupport = (el) => el.kind === 'ground'
    && !el.disclosure && el.signal === 'none';
  let support = entry.answer.elements.filter(foldsAsSupport);
  let spoken = entry.answer.elements.filter((el) => !foldsAsSupport(el));

  // BK-37. AN ANSWER THAT IS ONLY GROUNDS IS NOT SUPPORT FOR ANYTHING.
  //
  // MEASURED (J-6): a courtesy "Hello" produced a single plain ground, every
  // plain ground is folded, and the ENTIRE REPLY disappeared under
  // "1 supporting passage". The same happens to a question-of-law answer,
  // which is grounds by construction -- the advocate asked what the law says
  // and the product read it back.
  //
  // The fold's argument is that support sits UNDER a claim and crowds it.
  // With no claim above it there is nothing to crowd, and folding is just
  // hiding the answer.
  if (!spoken.length) {
    spoken = support;
    support = [];
  }

  // BK-37. FILED UNDER THE QUESTION EACH ANSWERS, in reading order.
  //
  // THE SECTION COMES FROM THE SERVER (`nm/domain/brief.py`), so this groups
  // and does not judge. Anything the server did not label -- an older reply
  // still in the transcript, a courtesy answer -- lands in `position`, which
  // is the visible default rather than a silent drop.
  //
  // DEDUPLICATED, WITH THE COUNT KEPT. "I could not assess this" said once
  // and said nine times are different facts about the file, and an advocate
  // reading the shorter answer must not believe the product looked less hard
  // than it did. Nothing loud is ever collapsed.
  const filed = new Map();
  for (const el of spoken) {
    const key = el.section || 'position';
    if (!filed.has(key)) filed.set(key, []);
    const rows = filed.get(key);
    const same = (el.signal && el.signal !== 'none') ? -1
      : rows.findIndex((r) => r.el.kind === el.kind
                           && r.el.thread === el.thread
                           && r.el.text.trim() === el.text.trim());
    if (same >= 0) rows[same].said += 1;
    else rows.push({ el, said: 1 });
  }

  for (const [key, heading] of SECTIONS) {
    const rows = filed.get(key);
    if (!rows || !rows.length) continue;   // an empty heading answers nothing
    const h = document.createElement('h3');
    h.className = 'section';
    h.textContent = heading;
    wrap.appendChild(h);
    for (const row of rows) renderElement(wrap, row.el, row.said);
  }
  // Anything under a section this client does not know about still shows.
  // A renderer that dropped what it could not place would hide exactly the
  // element a newer server added.
  for (const [key, rows] of filed) {
    if (SECTIONS.some(([k]) => k === key) || key === 'audit') continue;
    for (const row of rows) renderElement(wrap, row.el, row.said);
  }

  function renderElement(into, el, said) {
    const d = document.createElement('div');
    // A loud signal is never collapsed, whatever the server says about
    // collapsibility -- the client does not get to quiet it.
    // A DISCLOSURE is not an assertion, and it must not look like one.
    // "Here is the law" and "here is what I could not establish" rendered
    // identically is how a gap becomes a finding in the reader's memory.
    d.className = `el ${el.kind}${el.disclosure ? ' disclosure' : ''}`;
    const k = document.createElement('span');
    k.className = 'k';
    k.textContent = el.disclosure
      ? 'Not established'
      : (el.signal && el.signal !== 'none'
        ? `${KIND_LABEL[el.kind]} · ${el.signal.replace(/_/g, ' ')}`
        : KIND_LABEL[el.kind]);
    const body = document.createElement('div');
    body.className = 'body'; body.textContent = el.text;
    d.append(k, body);

    if (el.by_when || el.no_deadline_reason) {
      const w = document.createElement('span');
      w.className = 'when';
      w.textContent = el.by_when ? `by ${el.by_when}` : `no deadline — ${el.no_deadline_reason}`;
      d.appendChild(w);
    }
    if (el.refs && el.refs.length) {
      const r = document.createElement('span');
      r.className = 'refs'; r.textContent = el.refs.join(' · ');
      d.appendChild(r);
    }
    if (said > 1) {
      const n = document.createElement('span');
      n.className = 'said-times';
      n.textContent = `said ${said} times on this turn`;
      d.appendChild(n);
    }
    into.appendChild(d);
  }

  // THE SUPPORT, FOLDED, WITH A COUNT. `left_out` is the precedent in this
  // product: a reader told something is hidden learns less than one told how
  // much. A bare "details" gives no reason to open it.
  if (support.length) {
    const fold = document.createElement('details');
    fold.className = 'support';
    const sum = document.createElement('summary');
    sum.textContent = support.length === 1
      ? '1 supporting passage'
      : `${support.length} supporting passages`;
    fold.appendChild(sum);
    for (const el of support) {
      const d = document.createElement('div');
      // THE SAME CLASS LOGIC AS THE OPEN HALF, not a hard-coded
      // 'el ground'. This said that flat, so a disclosure that ever
      // reached the fold rendered as an ordinary passage -- losing the
      // dashed rule and the "Not established" label on the way in.
      //
      // Worse than folding it: the partition would be wrong AND every
      // trace of it being wrong would be gone. Found by mutation --
      // deleting `!el.disclosure` from the partition left the
      // behavioural check GREEN, because the class it looks for was
      // being stripped at exactly the moment it mattered.
      d.className = `el ${el.kind}${el.disclosure ? ' disclosure' : ''}`;
      const k = document.createElement('span');
      k.className = 'k';
      k.textContent = el.disclosure
        ? 'Not established'
        : (el.signal && el.signal !== 'none'
          ? `${KIND_LABEL[el.kind]} \u00b7 ${el.signal.replace(/_/g, ' ')}`
          : KIND_LABEL[el.kind]);
      const body = document.createElement('div');
      body.className = 'body'; body.textContent = el.text;
      d.append(k, body);
      if (el.refs && el.refs.length) {
        const r = document.createElement('span');
        r.className = 'refs'; r.textContent = el.refs.join(' \u00b7 ');
        d.appendChild(r);
      }
      fold.appendChild(d);
    }
    wrap.appendChild(fold);
  }

  // THE GATES THAT FIRED. A gate whose response is `disclose` and which the
  // advocate cannot see has disclosed nothing -- and G-UNSCREENED fires on
  // every turn, because the conflict, competence and engagement screens are
  // slice 10 and are not built.
  // J-7. HOW THIS ANSWER WAS MADE, filed under its own heading and closed.
  //
  // MEASURED: `G-DUTY · clear`, `G-UNSCREENED · unscreened`, `G-CONSISTENT ·
  // consistent`, and `outcome ok · latency 69ms · calls 15 · tokens 6860/606
  // · cost $0.000000 · violations 1` were on the advocate's screen under
  // every answer. None of it is wrong and none of it is theirs: an advocate
  // cannot act on `G-UNSCREENED`, and the sentence beside it already says
  // what it means.
  //
  // A `<details>` AND NOT A DELETION, and not an operator-only route either.
  // Every one of these is what makes a claim checkable, and this product's
  // whole argument is for keeping them where the person relying on the answer
  // can reach them. What changes is that reaching them is a decision.
  // `metrics` IS NULL ON A RESTORED TURN. The transcript keeps what was
  // served and not the numbers about the run, so every read of it here
  // has to tolerate its absence -- this one did not, and threw
  // `Cannot read properties of null (reading 'gates_fired')` inside
  // `repaint`, which renders NOTHING and looks exactly like a matter
  // with no conversation on it.
  const fired = ((entry.answer.metrics || {}).gates_fired || []);
  const audit = document.createElement('details');
  audit.className = 'audit';
  const auditSum = document.createElement('summary');
  auditSum.textContent = 'How this answer was made';
  audit.appendChild(auditSum);

  if (fired.length) {
    const g = document.createElement('div');
    g.className = 'gates';
    for (const gate of fired) {
      const row = document.createElement('div');
      row.className = `gate ${gate.response}`;
      const id = document.createElement('span');
      id.className = 'gid';
      id.textContent = `${gate.gate} · ${gate.state}`;
      const detail = document.createElement('span');
      detail.className = 'gdetail';
      detail.textContent = gate.detail;
      row.append(id, detail);
      g.appendChild(row);
    }
    audit.appendChild(g);
  }

  const m = entry.answer.metrics;
  if (!m) {
    // A RESTORED TURN. It was served, it was recorded, and the numbers about
    // the run were not kept -- so the working says that rather than showing
    // zeros that would read as a measurement.
    const note = document.createElement('div');
    note.className = 'metrics';
    note.textContent = entry.answer.at
      ? `read back from the record · served ${entry.answer.at}`
      : 'read back from the record';
    audit.appendChild(note);
    // THE RAW TURN, for the review that needs it. BK-39 keeps it and moves
    // it: prompts, model answers, gates and ids are what this store exists
    // for, and they are not what an advocate opens History to read.
    if (entry.answer.raw) {
      const pre = document.createElement('pre');
      pre.className = 'recorded-raw';
      pre.textContent = JSON.stringify(entry.answer.raw, null, 2);
      audit.appendChild(pre);
    }
    wrap.appendChild(audit);
    return wrap;
  }
  const met = document.createElement('div');
  met.className = 'metrics';
  const add = (label, value, warn) => {
    const s = document.createElement('span');
    s.innerHTML = `${label} <span class="v${warn ? ' warn' : ''}"></span>`;
    s.querySelector('.v').textContent = value;
    met.appendChild(s);
  };
  add('outcome', m.outcome, m.outcome !== 'ok');
  add('latency', `${m.latency_ms}ms`);
  add('calls', String(m.llm_calls));
  add('tokens', `${m.tokens.in}/${m.tokens.out}`);
  add('cost', `$${m.cost_usd.toFixed(6)}`);
  if (m.violations.length) add('violations', String(m.violations.length), true);
  if (m.tier_downgrades.length) add('downgrades', String(m.tier_downgrades.length), true);
  if (entry.answer.replayed) add('replayed', 'yes', true);
  audit.appendChild(met);
  wrap.appendChild(audit);
  return wrap;
}

function repaint() {
  const t = $('thread');
  t.replaceChildren(...state.turns.map(renderTurn));
  t.scrollTop = t.scrollHeight;
  updateWorkspace();
}

function updateWorkspace() {
  const intakeOpen = !$('intake').hidden;
  const welcome = !state.matterId && !state.turns.length && !state.intake && !intakeOpen;
  $('welcome').hidden = !welcome;
  $('composer').hidden = welcome || intakeOpen;
}

/* ------------------------------------------------------------------ send --- */

// BK-36. THE TURN ID IS MINTED BEFORE THE REQUEST, NOT BY THE SERVER.
//
// THE DEFECT: the composer was cleared before the request and no `turn_id`
// was sent. If the server committed and the HTTP response was lost -- a
// dropped wifi, a closed laptop, a proxy timeout -- the retry was a NEW turn,
// and the same brief went onto the file twice. If the request failed BEFORE
// commitment, the only copy of what the advocate had written was the failed
// card in memory, gone on reload.
//
// Both are the same missing thing: an identity for the attempt that outlives
// the attempt. Minted here, kept on the entry, and reused by every retry, so
// the server can recognise the second arrival as the same turn -- which it
// already knew how to do and was never told.
function newTurnId() {
  if (window.crypto && crypto.randomUUID) return `turn_${crypto.randomUUID()}`;
  return `turn_${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
}

async function send(message, { workProduct } = {}) {
  if (activeDelivery || (state.matterId && !state.matterReady)) return;
  if (!activeIntent) selectIntent(state.matterId, { opening: !state.matterId });
  snapshotIntent();
  // Re-entering Send with an unresolved identical intent is also a retry.
  const pending = activeIntent.pending.find((entry) => entry.brief === message
    && entry.request.work_product === workProduct && matchesIntake(entry, state.intake)
    && ['unknown', 'not_committed', 'sending'].includes(entry.state));
  if (pending) { await deliver(pending); return; }
  const entry = { brief: message, turnId: newTurnId(), state: 'sending',
    context: activeIntent,
    request: { matter_id: state.matterId, expected_version: state.matterVersion,
      parties: { ...((state.intake && state.intake.parties) || {}) },
      release: { ...((state.intake && state.intake.release) || {}) },
      capacity: state.intake && state.intake.capacity ? { ...state.intake.capacity } : null,
      work_product: workProduct } };
  // This serialized envelope never changes across navigation, reauthentication
  // or retry. Only the rendering attempt receives a fresh lifetime.
  entry.envelope = JSON.stringify({
    message: entry.brief, matter_id: entry.request.matter_id, turn_id: entry.turnId,
    parties: entry.request.parties, release: entry.request.release,
    capacity: entry.request.capacity,
    expected_version: entry.request.expected_version, work_product: entry.request.work_product,
  });
  activeIntent.pending.push(entry);
  state.turns.push(entry);
  repaint();
  await deliver(entry);
}

async function deliver(entry) {
  if (activeDelivery || !ownsIntent(entry.context)) return;
  const intent = entry.context;
  const attempt = { session: state.sessionGeneration };
  entry.attempt = attempt;
  const current = () => entry.attempt === attempt && ownsIntent(intent)
    && attempt.session === state.sessionGeneration;
  const btn = $('send');
  // Writing remains available while delivery is in flight; only Send is held.
  btn.disabled = true;
  btn.textContent = 'Working…';
  const cancel = document.createElement('button');
  cancel.className = 'ghost cancel';
  cancel.textContent = 'Cancel';
  const stop = new AbortController();
  const delivery = { controller: stop, entry };
  activeDelivery = delivery;
  cancel.addEventListener('click', () => {
    entry.cancelled = true;
    stop.abort();
  });
  btn.parentElement.insertBefore(cancel, btn);
  entry.state = 'sending';
  entry.error = null;
  entry.refusal = null;
  entry.cancelled = false;
  repaint();
  try {
    const answer = await api('/api/turn', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      signal: stop.signal, body: entry.envelope,
    });
    if (entry.attempt !== attempt) return;
    if (current()) snapshotIntent();
    entry.answer = answer;
    entry.state = answer.replayed ? 'replayed' : 'committed';
    intent.pending = intent.pending.filter((item) => item !== entry);
    if (matchesIntake(entry, intent.intake)) intent.intake = null;
    if ((answer.input_admitted === true || answer.route === 'non_matter')
        && intent.text.trim() === entry.brief.trim()) intent.text = '';
    intent.intakeOpen = Boolean(answer.blocked && /screen|scope|capacity|part(y|ies)/i.test(
      answer.blocked_reason || ''));
    // A saved opening acquires a file identity, but its original turn envelope
    // keeps matter_id:null for idempotent replay if this acknowledgement is lost.
    if (answer.matter_id && !intent.matterId) {
      intentContexts.delete(intent.key);
      intent.matterId = answer.matter_id;
      intent.key = JSON.stringify([intent.advocate, intent.workspace, intent.matterId]);
      intentContexts.set(intent.key, intent);
    }
    if (!current()) return;
    restoreIntent();
    state.matterId = intent.matterId;
    if (Number.isInteger(answer.matter_version)) state.matterVersion = answer.matter_version;
    repaint();
    if (state.matterId) await showThreadBoard(state.matterId, {
      restore: false, closeNavigator: false,
    });
  } catch (e) {
    // clearPrivileged already freezes an abandoned attempt as unknown. Neither
    // that old response nor a later retry can rewrite one another's outcome.
    if (e.obsolete || entry.attempt !== attempt) return;
    entry.error = e.message;
    entry.refusal = (e.detail && typeof e.detail === 'object') ? e.detail : null;
    const said = entry.refusal && entry.refusal.committed;
    entry.state = said === 'not_committed' ? 'not_committed' : 'unknown';
    if (said === 'previously_committed' && entry.refusal.release_state === 'replay_refused') {
      entry.state = 'replay_refused';
    }
    if (entry.cancelled) {
      entry.state = 'unknown';
      entry.error = 'You cancelled this turn’s request; whether it was saved is not confirmed.';
    }
    if (e.status === 409) entry.state = 'stale';
    if (!current()) return;
    if (entry.state === 'stale' && state.matterId) {
      await showThreadBoard(state.matterId).catch(() => {});
    }
    if (ownsIntent(intent) && attempt.session === state.sessionGeneration) repaint();
  } finally {
    cancel.remove();
    if (activeDelivery === delivery) {
      activeDelivery = null;
      btn.disabled = false;
      btn.textContent = 'Send';
    }
  }
}

/* ------------------------------------------------------------------ wire --- */

$('composer').addEventListener('submit', (ev) => {
  ev.preventDefault();
  const box = $('message');
  const text = box.value.trim();
  if (!text) return;
  // BK-36. THE COMPOSER IS NOT CLEARED HERE ANY MORE.
  //
  // It was cleared before the request, so a request that failed before
  // commitment left the advocate's only copy of a long brief in a failed card
  // in memory -- gone on reload, gone on sign-out. It is cleared by `deliver`
  // once the server has said the brief is on the file, and not before.
  send(text);
});

$('message').addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter' && !ev.shiftKey) {
    ev.preventDefault();
    $('composer').requestSubmit();
  }
});


$('back').addEventListener('click', showMatterList);

// BK-32. THE MATTER LIST, AT EVERY WIDTH.
//
// `aria-expanded` is kept in step because the button IS the disclosure at
// this width -- a screen reader that cannot tell open from closed has the
// same problem the sighted advocate had: no way to know the list is there.
function toggleMatters(force) {
  const pane = $('pane-advise');
  const open = force === undefined ? !pane.classList.contains('show-rail') : force;
  pane.classList.toggle('show-rail', open);
  $('matters-toggle').setAttribute('aria-expanded', open ? 'true' : 'false');
}

$('matters-toggle').addEventListener('click', () => toggleMatters());

// B3-B5. INTAKE IS ASKED ONCE PER MATTER, AND ITS ANSWERS TRAVEL WITH THE
// FIRST BRIEF.
//
// The screens run in ADMIT-A, before any fact is admitted -- so the conflict
// screen cannot be run against parties read out of a brief it has not
// admitted. Asking who is involved when the file is opened is what makes the
// first brief screenable at all, which is why this is a form and not a read.
function showIntake(show) {
  $('intake').hidden = !show;
  updateWorkspace();
  if (show) $('in-client').focus();
}

function intakeFields() {
  const parties = {};
  const client = $('in-client').value.trim();
  const adverse = $('in-adverse').value.trim();
  if (client) parties[client] = 'client';
  if (adverse) parties[adverse] = 'adverse';
  for (const other of $('in-others').value.split(',')) {
    const name = other.trim();
    if (name) parties[name] = 'related';
  }
  return {
    parties,
    release: {
      scope: $('in-scope').value.trim(),
    },
    capacity: {
      state: $('in-capacity').checked ? 'not_in_doubt' : 'not_assessed',
      basis: $('in-capacity').checked
        ? 'The advocate explicitly confirms that the client can give these instructions.'
        : 'The advocate has not assessed capacity to give these instructions.',
    },
  };
}

$('intake').addEventListener('submit', (ev) => {
  ev.preventDefault();
  // RECORDED, THEN THE COMPOSER. The answers are held until the first brief
  // carries them, because a matter does not exist until there is one -- and
  // opening an empty file to hold an intake answer would put a matter on the
  // advocate's list that has nothing on it.
  state.intake = intakeFields();
  showIntake(false);
  $('intake-state').textContent = '';
  $('message').focus();
});

function startMatter() {
  showTab('advise');
  selectIntent(null, { opening: true });
  state.matterVersion = null;
  toggleMatters(false);
  state.matterId = null;
  $('pane-advise').dataset.matterId = '';
  state.turns = [...activeIntent.pending];
  repaint();
  $('mode-line').hidden = true;
  showMatterList({ preserveIntent: true });
  // The list refresh clears its transcript surface, not the opening's intent.
  state.turns = [...activeIntent.pending];
  repaint();
  $('matter-heading').textContent = 'New matter';
  $('workspace-eyebrow').textContent = 'THE INSTRUCTION';
  $('save-status').textContent = 'Not yet saved';
  if (!$('intake').hidden) $('in-client').focus();
  else $('message').focus();
}

$('new-matter').addEventListener('click', startMatter);
$('welcome-start').addEventListener('click', startMatter);
$('welcome-matters').addEventListener('click', () => {
  toggleMatters(true);
  const first = $('rail-body').querySelector('[role="button"]');
  (first || $('new-matter')).focus();
});

/* THE GATE RUNS FIRST.
 *
 * These two ran at load, unconditionally, so the board fetched and
 * painted before anything asked whether this browser was signed in.
 * `boot()` resolves the session and only then starts the application. */
boot();

/* ============================== THE TABS ==============================
 *
 * Three surfaces that deliberately do NOT share state. A hit found in the
 * corpus is not a fact on a matter until the advocate puts it there, and the
 * quickest way to break that is a shared object both panes write to.
 */

const PANES = ['advise', 'search', 'history'];

function showTab(name) {
  PANES.forEach((p) => { $(`pane-${p}`).hidden = (p !== name); });
  document.querySelectorAll('#tabs .tab').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.tab === name);
    if (b.dataset.tab === name) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  if (name === 'search') $('q').focus();
  if (name === 'history') loadHistoryMatters();
}

document.querySelectorAll('#tabs .tab').forEach((b) => {
  b.addEventListener('click', () => showTab(b.dataset.tab));
});

/* ========================= A4 — SEARCH THE CORPUS =====================
 *
 * The client renders what the server said and adds nothing. In particular it
 * NEVER renders an empty result on its own account: `coverage` and `index`
 * come down on every response and both are shown, because a bare "no results"
 * is read as "the law is not in the corpus" when it may mean the index was
 * never built.
 */

function renderIndexLine(d) {
  const el = $('search-index');
  if (!d.index) { el.hidden = true; return; }
  el.hidden = false;
  el.textContent = '';

  // THE QUERY, ON THE RESULTS. Hits that do not say what they answer are
  // read as answering whatever is in the box -- and the box changes before
  // the request returns. Naming it is the same rule as naming the index: a
  // result the advocate cannot attribute is a result they can misread.
  // J-7 / BK-38. WHAT WAS SEARCHED, IN THE ADVOCATE'S TERMS.
  //
  // This read `Searched: the authority index (authority.db) · ...`. A file
  // name is ours; an advocate cannot act on it and it tells them nothing
  // about whether the search covered their question. The scope and the
  // freshness do, and they are below.
  const what = document.createElement('span');
  what.textContent = d.coverage === 'not_assessed'
    ? `Search not performed · for “${d.query}”`
    : `Searched the case law · for “${d.query}”`;
  el.appendChild(what);

  // WHICH FILTERS ACTUALLY RAN. A zero beside `court: Supreme Court` reads
  // as "the corpus holds nothing from the Supreme Court"; it meant the
  // filter never matched a stored value.
  if (d.filters && d.filters.court_read_as) {
    const f = document.createElement('span');
    f.className = 'index-detail';
    f.textContent = ` · ${d.filters.court_read_as}`;
    el.appendChild(f);
  }

  if (d.identity) {
    const frac = d.identity.fraction_of_source;
    // GUARDED LIKE `of_source` ON THE NEXT LINE. This called
    // `.toLocaleString()` unconditionally while its neighbour was
    // guarded, so an identity carrying no index count crashed the
    // results renderer -- the guard sat one line from where it was
    // missing.
    const held = Number.isInteger(d.identity.held) ? d.identity.held.toLocaleString() : null;
    const of = Number.isInteger(d.identity.of_source) ? d.identity.of_source.toLocaleString() : null;
    const detail = document.createElement('span');
    detail.className = 'index-detail';
    // BOTH NUMBERS, because the RATIO is the disclosure. "451,548 paragraphs"
    // reads as the corpus; "451,548 of 1,015,780" does not.
    const size = `${held === null ? 'Indexed count not recorded' : `${held} indexed paragraphs`}`
      + (of === null ? ' · source size not recorded' : ` of ${of} source paragraphs`)
      + (typeof frac === 'number' ? ` (${(frac * 100).toFixed(1)}%)` : '');
    // SCOPE FIRST. It is the disclosure that changes whether the whole result
    // means anything: an empty answer to a Kerala question is not an answer
    // about Kerala law, and only this line says so.
    // A build timestamp is not a reviewed legal-currentness date. Naming it
    // "current to" would convert an operational fact into a legal assurance.
    const day = String(d.identity.built_at || '').slice(0, 10);
    detail.textContent = ` · ${d.identity.scope} · ${size}`
      + (day ? ` · index prepared ${day}` : '')
      + ' · legal currency is not established by the index date';
    el.appendChild(detail);
  }
}

// Where a hit sat in THIS search, in words. Never a measurement.
//
// Three bands and no number. Two would make the middle of a result
// set read as either strong or weak; a number invites exactly the
// reliance the underlying rank cannot support.
function rankBand(confidence) {
  if (typeof confidence !== 'number') return 'rank not recorded';
  if (confidence >= 0.85) return 'top of this search';
  if (confidence >= 0.5) return 'mid-ranked here';
  return 'lower-ranked here';
}

function renderSearch(d) {
  renderIndexLine(d);
  const st = $('search-state');
  const body = $('search-results');
  st.textContent = ''; body.textContent = '';

  if (d.coverage === 'not_assessed') {
    // NOT A ZERO. Nothing was searched, and saying "no results" here would be
    // the most repeated defect in this project, in the advocate's face.
    st.appendChild(stateBlock('loud',
      'NOT SEARCHED — this search could not be completed. This is not a finding that no relevant law exists.'));
    const detail = document.createElement('details');
    detail.className = 'search-diagnostic';
    const summary = document.createElement('summary');
    summary.textContent = 'Why the search did not run';
    const reason = document.createElement('p');
    reason.textContent = d.why;
    detail.append(summary, reason);
    st.appendChild(detail);
    return;
  }

  if (!d.hit_count) {
    st.appendChild(stateBlock('quiet', d.why || 'No paragraph matched.'));
    return;
  }

  const count = document.createElement('p');
  count.className = 'result-count';
  count.textContent = `${d.hit_count} ranked paragraph${d.hit_count === 1 ? '' : 's'}`;
  body.appendChild(count);

  d.hits.forEach((h) => {
    const card = document.createElement('article');
    card.className = 'hit';

    const head = document.createElement('header');
    const name = document.createElement('span');
    name.className = 'hit-name';
    name.textContent = h.case_name;
    const meta = document.createElement('span');
    meta.className = 'hit-meta';
    meta.textContent = `${h.court}${h.year ? ` · ${h.year}` : ''} · ${h.para_type}`;
    head.append(name, meta);

    // ORIGIN ON EVERY CARD. A ranked paragraph must never be readable as an
    // exact lookup, and the way that happens is a template that omits this.
    const prov = document.createElement('span');
    prov.className = `pill ${h.origin === 'searched' ? 'searched' : 'resolved'}`;
    // A BAND, NOT A PERCENTAGE.
    //
    // `confidence` is an FTS rank normalised to 0..1, and the
    // adapter's own docstring says it is comparable only WITHIN one
    // query. Rendered as `95%` it reads as calibrated confidence in
    // relevance -- and on a real search the top two hits BOTH showed
    // 95%, which is precision the number cannot carry. A band says
    // only what the rank supports: where this paragraph sat against
    // the others in THIS search.
    prov.textContent = `${h.origin} · ${rankBand(h.confidence)}`;
    head.appendChild(prov);

    const text = document.createElement('p');
    text.className = 'hit-text';
    text.textContent = h.snippet;

    card.append(head, text);
    body.appendChild(card);
  });
}

$('search-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const generation = ++state.searchGeneration;
  const params = new URLSearchParams({
    q: $('q').value,
    limit: '25',
  });
  const court = $('f-court').value.trim();
  const from = $('f-from').value.trim();
  const to = $('f-to').value.trim();
  if (court) params.set('court', court);
  if (from) params.set('from_year', from);
  if (to) params.set('to_year', to);

  // CLEARED BEFORE THE REQUEST, not after it. Leaving the previous hits up
  // while a new query runs shows the advocate an answer to a question they
  // have already replaced -- and if the request then fails, it stays up.
  $('search-results').textContent = '';
  $('search-index').hidden = true;
  $('search-state').textContent = '';
  $('search-state').appendChild(stateBlock('quiet', 'Searching…'));
  try {
    const result = await api(`/api/search?${params}`);
    if (generation !== state.searchGeneration) return;
    renderSearch(result);
  } catch (err) {
    if (err.obsolete || generation !== state.searchGeneration) return;
    // AN ERROR IS NOT A ZERO. Rendering a failed request as "no results" is
    // the same defect the coverage field exists to prevent.
    $('search-results').textContent = '';
    $('search-state').textContent = '';
    $('search-state').appendChild(stateBlock('loud',
      `The search did not run: ${err.message}. This says nothing about what the corpus holds.`));
  }
});

/* ============================ THE RECORD =============================
 *
 * Read back from the encrypted transcript store. An unreadable turn is
 * COUNTED and named rather than skipped: a review that renders nine of ten
 * turns and calls itself complete is reviewing a different conversation from
 * the one that ran.
 */

async function loadHistoryMatters() {
  const generation = ++state.historyListGeneration;
  const sel = $('history-matter');
  try {
    const d = await api('/api/matters');
    if (generation !== state.historyListGeneration) return;
    const rows = d.matters || [];
    sel.textContent = '';
    const first = document.createElement('option');
    first.value = '';
    // AN UNREADABLE LIST IS NOT AN EMPTY ONE. `state` says which, and a
    // dropdown reading "No matters yet" over a list that failed to build is
    // the same defect the rail already refuses.
    first.textContent = d.state !== 'ok'
      ? 'The matter list could not be read'
      : (rows.length ? 'Choose a matter…' : 'No matters yet');
    sel.appendChild(first);
    if (d.state !== 'ok') {
      $('history-state').appendChild(stateBlock('loud', d.unreadable_reason
        || 'The matter list could not be built.'));
    }
    rows.forEach((m) => {
      const o = document.createElement('option');
      o.value = m.matter_id;
      // `matter` is the projection's own name for it. Falling back to the id
      // was showing every row as `mat_65fc8d70d72a`, which is a list nobody
      // can choose from.
      o.textContent = m.matter || m.matter_id;
      sel.appendChild(o);
    });
  } catch (err) {
    if (err.obsolete || generation !== state.historyListGeneration) return;
    $('history-state').textContent = '';
    $('history-state').appendChild(stateBlock('loud',
      `The matter list could not be read: ${err.message}`));
  }
}

async function showHistory(matterId) {
  const generation = ++state.historyGeneration;
  const st = $('history-state');
  const body = $('history-body');
  st.textContent = ''; body.textContent = '';
  if (!matterId) return;

  let d;
  try {
    d = await api(`/api/matters/${matterId}/transcript`);
    if (generation !== state.historyGeneration) return;
  } catch (err) {
    if (err.obsolete || generation !== state.historyGeneration) return;
    st.appendChild(stateBlock('loud', `The history could not be read: ${err.message}`));
    return;
  }

  if (d.state !== 'ok') {
    // LOUD, and ABOVE the transcript rather than below it.
    st.appendChild(stateBlock('loud', d.unreadable_reason
      || 'Some turns on this matter could not be read back.'));
  }

  const head = document.createElement('p');
  head.className = 'result-count';
  head.textContent = `${d.turn_count} turn${d.turn_count === 1 ? '' : 's'} on ${d.title}`;
  body.appendChild(head);

  // BK-39. THE SAME RENDERER, AND THAT IS THE WHOLE FIX.
  //
  // History showed the advocate's message and a collapsed "The turn as it was
  // served" which, opened, printed the complete raw JSON: internal ids,
  // prompts, model answers, metrics, gates. The answer they were actually
  // given was not rendered at all -- so the surface that exists for REVIEW
  // showed a different thing from the surface that gave the advice, and only
  // one of them was readable.
  //
  // TWO RENDERERS FOR ONE ANSWER IS S9, and the drift is not hypothetical:
  // BK-37 filed the served answer into sections, and this one would still
  // have been printing JSON. `renderTurn` is now the only thing that renders
  // an answer, here and on the Advise pane, so a change to how an answer
  // reads changes both.
  //
  // THE RAW RECORD IS NOT DELETED. It moves inside the same `How this answer
  // was made` door every served turn already has -- forensic diagnosis is
  // what this store is FOR, and it stays one click away rather than being
  // the first thing an advocate meets.
  d.turns.forEach((t, i) => {
    const card = document.createElement('article');
    card.className = 'recorded-turn';

    const h = document.createElement('header');
    // NO TURN ID. It is one of this product's own keys and an advocate
    // cannot act on it (J-5); the ordinal is what they use to talk about a
    // turn, and the id stays in the raw record below.
    h.textContent = t.at ? `Turn ${i + 1} · ${t.at}` : `Turn ${i + 1}`;
    card.appendChild(h);

    card.appendChild(renderTurn(restoredTurn(t)));

    body.appendChild(card);
  });
}

$('history-matter').addEventListener('change', (ev) => showHistory(ev.target.value));

/* ========================= A1 — THE GATE =========================
 *
 * The application does not start until a session resolves. Not a redirect and
 * not an overlay dropped on a loaded board: `showMatterList()` used to run at
 * load, so the matters fetched and painted first and the question of who was
 * holding the laptop came second. A board that appears for an instant has
 * already been read.
 *
 * A FAILED SIGN-IN SAYS ONE THING. The server sends one message for an
 * unknown advocate and for a wrong password, and the client must not improve
 * on it — a helpful "no such advocate" here would undo the whole arrangement
 * from the outside.
 */

function showGate(message) {
  $('gate').hidden = false;
  $('masthead').hidden = true;
  PANES.forEach((p) => { $(`pane-${p}`).hidden = true; });
  // THE GATE IS ALWAYS THE SIGN-IN FORM. It is reached from a failed sign-in,
  // from Sign out, and from a session that did not resolve -- and whichever
  // card happened to be up last is not the answer to any of those. Called
  // BEFORE the message, because it clears the line the message goes on.
  showForm('login');
  if (message) $('login-state').appendChild(stateBlock('loud', message));
  $('login-id').focus();
}

function showApplication(advocate, workspace, professionalApproval) {
  if (!workspace || !workspace.id || !workspace.label) {
    clearPrivileged();
    showGate('I could not establish the active workspace. Matter content '
      + 'remains closed; ask the installation administrator to check this account.');
    return;
  }
  forgetRetirement();
  state.advocate = advocate.id;
  state.sessionGeneration += 1;
  $('send').disabled = false;
  $('send').textContent = 'Send';
  state.workspace = workspace && workspace.id;
  // A different person or workspace must not inherit even an invisible draft.
  for (const [key, intent] of intentContexts) {
    if (intent.advocate !== advocate.id || intent.workspace !== workspace.id) {
      intentContexts.delete(key);
    }
  }
  $('who-name').textContent = advocate.name;
  $('who-detail').textContent = [advocate.enrolment, advocate.practice]
    .filter(Boolean).join(' · ');
  $('professional-approval').textContent = professionalApproval?.state === 'approved'
    ? 'Professional profile approved' : 'Professional profile not approved';
  $('workspace-name').textContent = workspace.label;
  $('gate').hidden = true;
  $('masthead').hidden = false;
  state.ended = false;
  showTab('advise');
  loadHealth();
  showMatterList();

  // Restore the entire original intent, not a new instruction made from its
  // text. Transcript reconciliation may confirm a turn whose acknowledgement
  // was lost; unavailable read-back retains its exact retry envelope.
  if (state.draft && state.draft.advocate === advocate.id
      && state.draft.workspace === workspace.id) {
    const draft = state.draft;
    if (draft.matterId) showThreadBoard(draft.matterId);
    else startMatter();
  }
  state.draft = null;
}

// IS THE SERVER RUNNING THE CODE THAT IS ON DISK?
//
// The server answers this, because it is the only party holding both numbers:
// the fingerprint it froze at import and the fingerprint of the tree now. The
// browser cannot see the tree and the tree cannot see the process.
//
// RUN AT BOOT, BEFORE THE SESSION RESOLVES, because what this catches happens
// on the gate. On 6 September 2026 a registration was refused by a password
// rule that had been changed three commits earlier, and the screenshot of the
// old message was the only evidence that anything was wrong.
//
// THE THIRD STATE IS SHOWN. "Could not be checked" is not "current" -- a
// banner that appears only on a proven mismatch reads as an all-clear on
// every run where the check itself failed.
async function checkBuild() {
  const el = $('build-warning');
  try {
    // Build identity is public and independent of whichever session boot resolves.
    const h = await api('/api/health', undefined, { sessionBound: false });
    if (h.code_state === 'current') { el.hidden = true; return; }
    el.className = `build-warning${h.code_state === 'stale' ? '' : ' unknown'}`;
    el.textContent = h.code_state === 'stale'
      ? `This server is running code that is no longer on disk (${h.serving},`
        + ` tree is ${h.tree}). Everything below is the older build. Restart it.`
      : `The build could not be identified: ${h.why || 'no reason given'}.`;
    el.hidden = false;
  } catch (e) {
    // A HEALTH CALL THAT FAILS IS ALSO NOT AN ALL-CLEAR.
    el.className = 'build-warning unknown';
    el.textContent = `The build could not be identified: ${e.message}.`;
    el.hidden = false;
  }
}

async function boot() {
  checkBuild();
  try {
    const me = await api('/api/session');
    showApplication(me.advocate, me.workspace, me.professional_approval);
  } catch (err) {
    // 401 IS THE ORDINARY CASE, not an error to report. Anything else is a
    // server that could not answer, and saying so beats a bare sign-in box
    // that looks like a rejected password.
    showGate(err.status === 401 ? null
      : `The server could not be reached: ${err.message}`);
  }
}

$('login').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const go = $('login-go');
  go.disabled = true;
  $('login-state').textContent = '';
  try {
    const r = await api('/api/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        advocate_id: $('login-id').value.trim(),
        password: $('login-password').value,
      }),
    });
    // THE PASSWORD LEAVES THE PAGE. It stays in the DOM otherwise, readable
    // by anything running later on this document.
    $('login-password').value = '';
    if (r.recovery_codes && r.recovery_codes.length) {
      pendingApplication = r;
      showOutcome('good', 'Save your recovery codes',
        'This account predates self-service recovery. Save these codes before '
        + 'you continue; they will not be shown again.', r.recovery_codes, 'login');
    } else {
      showApplication(r.advocate, r.workspace, r.professional_approval);
    }
  } catch (err) {
    $('login-password').value = '';
    showGate(err.message);
  } finally {
    go.disabled = false;
  }
});

// SIGNING OUT IS A STATE MACHINE, NOT A REQUEST (BK-40).
//
//     signing_out  -> confirmed     the server ended the session
//                  -> unconfirmed   it did not answer, and says so
//
// THE MEASURED DEFECT. This cleared the screen in `finally` and showed the
// gate whether or not `/api/logout` succeeded. With the server stopped, the
// advocate saw the sign-in screen -- and after a restart, reload reopened the
// authenticated session and its matter, because the server token was still
// live. They had been shown the strongest possible evidence of being signed
// out, and they were not.
//
// The screen still clears IMMEDIATELY, and that part was always right: a
// matter list left on the glass after someone pressed Sign out is worse. What
// changes is that clearing the screen is no longer allowed to be the answer.
async function revoke() {
  const r = await api('/api/logout', { method: 'POST' });
  // `outcome` is `closed`, `already_ended` or `unknown` -- the route stopped
  // asserting `signed_out: true` over all three on 8 September 2026.
  if (!r || r.signed_out !== true) {
    throw new Error('The server did not confirm that the session ended.');
  }
  return true;
}

function retirementCurrent(token) {
  return retiringSession === token && token.session === state.sessionGeneration
    && !state.advocate;
}

function forgetRetirement() {
  if (retiringSession && retiringSession.online) {
    window.removeEventListener('online', retiringSession.online);
  }
  retiringSession = null;
  state.signOut = 'none';
}

async function settleRetirementForLogin() {
  const token = retiringSession;
  if (!token) return;
  // Stop new retries before waiting for one already dispatched. Waiting matters
  // even if its body is ignored: its Set-Cookie must precede the next login.
  token.accepting = false;
  if (token.online) window.removeEventListener('online', token.online);
  if (token.task) await token.task;
  if (retiringSession === token) forgetRetirement();
}

function unconfirmedRetirement(token) {
  if (!retirementCurrent(token)) return;
  state.signOut = 'unconfirmed';
  showGate(null);
  $('login-state').appendChild(stateBlock('loud',
    'The server did not confirm the end of your session, so YOU MAY STILL BE '
    + 'SIGNED IN on it. This screen is not proof that you are signed out. '
    + 'Retry before leaving a shared machine.'));
  const again = document.createElement('button');
  again.type = 'button';
  again.className = 'ghost';
  again.textContent = 'Try to end the session again';
  again.addEventListener('click', () => retryRevoke(token));
  $('login-state').appendChild(again);
  if (!token.online) {
    token.online = () => retryRevoke(token);
    window.addEventListener('online', token.online);
  }
}

async function retire(token) {
  if (!retirementCurrent(token) || !token.accepting) return;
  if (token.task) return token.task;
  token.task = (async () => {
    try {
      try { await revoke(); }
      catch (err) { if (err.status !== 401) throw err; }
      if (!retirementCurrent(token)) return;
      forgetRetirement();
      state.ended = false;
      showGate(null);
      $('login-state').appendChild(stateBlock('quiet',
        'The session is now closed on the server.'));
    } catch {
      unconfirmedRetirement(token);
    }
  })();
  try { await token.task; }
  finally { token.task = null; }
}

async function signOut() {
  const btn = $('signout');
  btn.disabled = true;
  keepDraft();
  clearPrivileged();
  forgetRetirement();
  state.signOut = 'signing_out';
  const token = { session: state.sessionGeneration, accepting: true, task: null, online: null };
  retiringSession = token;
  $('login-id').value = '';
  try { await retire(token); }
  finally { btn.disabled = false; }
}

async function retryRevoke(token = retiringSession) {
  if (!token || !retirementCurrent(token) || state.signOut !== 'unconfirmed') return;
  await retire(token);
}

$('signout').addEventListener('click', signOut);

// BK-31. THE SESSIONS AN ADVOCATE HOLDS, AND THE WAY TO END THEM.
//
// The list shows ended sessions too, and that is the interesting half: "one
// session, this device" is worth nothing to someone who cannot also see the
// one that ended an hour ago on a machine they do not recognise.
//
// THE COUNT COMES BACK FROM THE REVOKE. "Signed out everywhere" is
// unverifiable otherwise, and the case this is used in is exactly the case
// where they need to know it worked.
async function showSessions() {
  const generation = ++state.sessionsGeneration;
  const dialog = $('sessions-dialog');
  const body = $('sessions-body');
  const revokeButton = $('sessions-revoke');
  body.replaceChildren(stateBlock('quiet', 'Reading your sessions…'));
  $('sessions-action-state').textContent = '';
  revokeButton.hidden = true;
  dialog.showModal();
  let d;
  try {
    d = await api('/api/sessions');
  } catch (e) {
    if (e.obsolete || generation !== state.sessionsGeneration) return;
    body.replaceChildren(stateBlock('loud', `I could not read your sessions: ${e.message}`));
    return;
  }
  if (generation !== state.sessionsGeneration || !dialog.open) return;
  body.replaceChildren(...d.sessions.map((s) => {
    const when = String(s.issued_at).slice(0, 16).replace('T', ' ');
    const label = s.this_one ? 'This device'
      : (s.live ? 'signed in' : `ended — ${s.ended_because || 'no reason recorded'}`);
    const row = document.createElement('article');
    row.className = 'session-row';
    const title = document.createElement('strong'); title.textContent = label;
    const detail = document.createElement('p'); detail.textContent = `${when} · Device ${s.device}`;
    row.append(title, detail);
    return row;
  }));
  const live = d.sessions.filter((s) => s.live && !s.this_one).length;
  $('sessions-action-state').textContent = live
    ? `${live} other session${live === 1 ? '' : 's'} currently signed in.`
    : 'No other sessions are signed in.';
  revokeButton.hidden = !live;
  revokeButton.textContent = `End ${live} other session${live === 1 ? '' : 's'}`;
}

new ResizeObserver(() => {
  document.documentElement.style.setProperty('--build-warning-height',
    `${$('build-warning').getBoundingClientRect().height}px`);
}).observe($('build-warning'));

$('sessions-close').addEventListener('click', () => $('sessions-dialog').close());
$('sessions-dialog').addEventListener('close', () => {
  state.sessionsGeneration += 1;
  $('sessions-body').textContent = '';
  $('sessions-action-state').textContent = '';
});
$('sessions-revoke').addEventListener('click', async () => {
  const generation = state.sessionsGeneration;
  const button = $('sessions-revoke');
  button.disabled = true;
  try {
    const r = await api('/api/sessions/revoke', { method: 'POST' });
    if (generation !== state.sessionsGeneration) return;
    button.hidden = true;
    $('sessions-action-state').textContent = r.ended === 1
      ? 'Ended 1 other session.'
      : `Ended ${r.ended} other sessions.`;
    $('sessions-body').textContent = 'This device stays signed in. Reopen Sessions to review the updated record.';
  } catch (e) {
    if (e.obsolete || generation !== state.sessionsGeneration) return;
    $('sessions-action-state').replaceChildren(stateBlock('loud',
      `I could not end them: ${e.message}. They may still be signed in — this is not a confirmation.`));
  } finally {
    button.disabled = false;
  }
});

$('devices').addEventListener('click', showSessions);

// ------------------------------------------------ replacing recovery codes
//
// BK-31-AC20. Two steps, and the separation is the control: the password is
// proved at the moment of the change, so an unlocked laptop is not enough to
// replace the last-resort credential.
//
// THE PROOF NEVER LEAVES THIS CLOSURE. Not localStorage, not sessionStorage,
// not a data attribute -- a variable, spent once, dropped in `finally`. A
// closed tab loses it, which is the correct outcome: the advocate
// authenticates again. There is no read-back of either the proof or the codes,
// because a second place a secret lives is a second place it leaks from.
let rotationProof = null;

function forgetRotationSecrets() {
  rotationProof = null;
  const field = $('reauth-password');
  if (field) field.value = '';
}

$('replace-codes').addEventListener('click', () => {
  forgetRotationSecrets();
  $('gate').hidden = false;
  $('masthead').hidden = true;
  showForm('reauth');
  $('reauth-password').focus();
});

$('reauth-cancel').addEventListener('click', (ev) => {
  ev.preventDefault();
  forgetRotationSecrets();
  $('gate').hidden = true;
  $('masthead').hidden = false;
});

$('reauth-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const go = $('reauth-go');
  const problem = $('reauth-error');
  problem.hidden = true;
  go.disabled = true;
  try {
    // THE CURRENT GENERATION IS READ IMMEDIATELY BEFORE THE CHANGE, and sent
    // with it. If another device replaced the set between this page loading
    // and this button, the server refuses rather than silently replacing a set
    // this page never showed anybody.
    const who = await api('/api/session');
    // NULL IS NOT ZERO. A directory that cannot say which generation this
    // account is on must stop the rotation, not let the page guess a number
    // that a legacy account would happen to accept.
    if (who.recovery_generation === null || who.recovery_generation === undefined) {
      throw new Error('This installation cannot confirm which recovery codes '
        + 'are current, so nothing was changed. Your existing codes still work.');
    }
    const earned = await api('/api/reauthenticate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: $('reauth-password').value }),
    });
    rotationProof = earned.proof;
    $('reauth-password').value = '';

    const replaced = await api('/api/recovery-codes/rotate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        proof: rotationProof,
        expected_recovery_generation: who.recovery_generation,
      }),
    });
    showOutcome('good', 'Your new recovery codes',
      'The ten codes you held before are now dead. Save these before you '
      + 'continue; they will not be shown again.',
      replaced.recovery_codes, 'resume');
  } catch (err) {
    // ONE LINE, WHATEVER FAILED. The server already refuses to say which, and
    // a page that guessed a friendlier reason would reintroduce the oracle the
    // server just closed.
    problem.textContent = err.message
      || 'That did not work. Your existing recovery codes still work.';
    problem.hidden = false;
    $('reauth-password').value = '';
  } finally {
    // SPENT OR NOT, THE PROOF IS GONE. A failed rotation must not leave a
    // usable authorisation sitting in this tab.
    rotationProof = null;
    go.disabled = false;
  }
});

$('outcome-resume').addEventListener('click', () => {
  // The acknowledgement. The codes leave the document here -- hiding the card
  // would leave them readable to anything running later on this page.
  clearRecoveryCodeDisplay();
  forgetRotationSecrets();
  $('gate').hidden = true;
  $('masthead').hidden = false;
});

// ------------------------------------------------------------- registration
//
// SELF-SERVICE, as of 6 September 2026. The sign-in page used to say enrolment
// was not, and pointed at a tool an advocate cannot run.
//
// TWO FORMS, NOT ONE IN TWO MODES. A single form that changes meaning by a
// flag is one where a mis-set flag posts a password to the wrong route.
function showForm(which) {
  // A pending account creation owns its one-time recovery result. Do not
  // let public navigation hand that result to a different form/person.
  if (registrationInFlight && which !== 'register') return;
  // Keep the non-secret email for corrections, never a hidden credential.
  if (which !== 'register') clearRegistrationPasswords();
  $('login').hidden = which !== 'login';
  $('register').hidden = which !== 'register';
  $('recovery').hidden = which !== 'recovery';
  $('outcome').hidden = which !== 'outcome';
  // A PASSWORD IS NOT FORM STATE EITHER. Leaving the reauthentication field
  // filled while the card is merely hidden would let the next person on this
  // machine return to a form already carrying the credential.
  if (which !== 'reauth') {
    const field = $('reauth-password');
    if (field) field.value = '';
    const problem = $('reauth-error');
    if (problem) { problem.hidden = true; problem.textContent = ''; }
  }
  const reauth = $('reauth');
  if (reauth) reauth.hidden = which !== 'reauth';
  $('login-state').textContent = '';
}

function clearRegistrationPasswords() {
  for (const id of ['reg-password', 'reg-password2']) {
    const field = $(id);
    field.value = '';
    field.type = 'password';
    const eye = document.querySelector(`[data-for="${id}"]`);
    if (eye) {
      eye.setAttribute('aria-pressed', 'false');
      eye.setAttribute('aria-label', id === 'reg-password'
        ? 'Show password' : 'Show retype password');
    }
  }
}

// WHAT HAPPENED, ON ITS OWN CARD, in both directions.
//
// The result of a registration used to be one line appended to the sign-in
// form -- which is also where "wrong password" and "the server could not be
// reached" appear. So the sentence that means START HERE arrived in the same
// grey text, in the same place, as the one that means you got it wrong.
//
// The FAILURE goes to the same card rather than staying on the form, because
// an advocate who has just pressed Register is looking at the button they
// pressed and not at a line below it. The form keeps its values -- it is
// hidden, not reset -- so Back returns them to a filled form. The passwords
// are the exception and they are cleared, which is the rule the sign-in
// handler already follows.
function showOutcome(kind, title, body, recoveryCodes = [], returnTo = 'register') {
  $('outcome-title').textContent = title;
  $('outcome-body').textContent = body;
  $('outcome-title').className = `outcome-title ${kind}`;
  // THREE EXITS, NOT TWO. A rotation returns the advocate to the matters they
  // were already in; sending them to a sign-in screen they do not need would
  // make the control cost a login every time it is used.
  const resuming = returnTo === 'resume';
  $('outcome-signin').hidden = kind !== 'good' || resuming;
  $('outcome-back').hidden = kind === 'good';
  $('outcome-resume').hidden = !resuming;
  outcomeReturn = returnTo;
  const codes = $('recovery-codes');
  const list = $('recovery-code-list');
  list.replaceChildren(...recoveryCodes.map((code) => {
    const item = document.createElement('li');
    item.textContent = code;
    return item;
  }));
  codes.hidden = recoveryCodes.length === 0;
  $('outcome-signin').textContent = pendingApplication
    ? 'I saved them — continue to matters'
    : (recoveryCodes.length ? 'I saved them — sign in' : 'Sign in');
  showForm('outcome');
  (kind === 'good' ? $('outcome-signin') : $('outcome-back')).focus();
}

function clearRecoveryCodeDisplay() {
  $('recovery-code-list').replaceChildren();
  $('recovery-codes').hidden = true;
}

$('outcome-signin').addEventListener('click', () => {
  // Once the advocate leaves the one-time screen, the usable codes leave the
  // document too. Hiding the outcome would still leave them readable to any
  // script running later on this page.
  const current = pendingApplication;
  pendingApplication = null;
  clearRecoveryCodeDisplay();
  if (current) {
    showApplication(current.advocate, current.workspace, current.professional_approval);
    return;
  }
  showForm('login');
  // THE PASSWORD FIELD, NOT THE EMAIL. The email is already filled from the
  // registration, and landing on a filled field means the first thing typed
  // goes to the end of it.
  $('login-password').focus();
});

$('outcome-back').addEventListener('click', () => {
  showForm(outcomeReturn);
  $(outcomeReturn === 'recovery' ? 'recovery-password' : 'reg-password').focus();
});

$('show-register').addEventListener('click', (ev) => {
  ev.preventDefault();
  showForm('register');
});

$('show-login').addEventListener('click', (ev) => {
  ev.preventDefault();
  showForm('login');
});

$('show-recovery').addEventListener('click', (ev) => {
  ev.preventDefault();
  $('recovery-id').value = $('login-id').value.trim();
  showForm('recovery');
  ($('recovery-id').value ? $('recovery-code') : $('recovery-id')).focus();
});

$('recovery-login').addEventListener('click', (ev) => {
  ev.preventDefault();
  showForm('login');
  $('login-id').focus();
});

$('recovery').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const go = $('recovery-go');
  const advocate = $('recovery-id').value.trim();
  const code = $('recovery-code').value.trim();
  const password = $('recovery-password').value;
  const again = $('recovery-password2').value;

  // The bearer code leaves the DOM before the network wait, exactly like an
  // enrolment invitation. A refusal must not leave a usable code on a shared
  // screen or make it part of a later error report.
  $('recovery-code').value = '';
  if (password !== again) {
    $('recovery-password').value = '';
    $('recovery-password2').value = '';
    showOutcome('bad', 'Recovery failed',
      'The two passwords do not match. Nothing was changed.', [], 'recovery');
    return;
  }

  go.disabled = true;
  try {
    const result = await api('/api/recover', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        advocate_id: advocate,
        recovery_code: code,
        password: password,
        password_again: again,
      }),
    });
    $('login-id').value = advocate;
    showOutcome('good', 'Password changed',
      `Your password was changed and ${result.sessions_ended} existing `
      + 'session(s) were ended. Sign in with the new password.', [], 'login');
  } catch (err) {
    showOutcome('bad', 'Recovery failed', err.message, [], 'recovery');
  } finally {
    $('recovery-code').value = '';
    $('recovery-password').value = '';
    $('recovery-password2').value = '';
    go.disabled = false;
  }
});

$('register').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  if (registrationInFlight) return;
  const go = $('register-go');
  const password = $('reg-password').value;
  const again = $('reg-password2').value;
  const email = $('reg-email').value.trim();
  // Clear both credentials before validation or a network wait, including
  // mismatches and transport failures. Only the local request holds them.
  clearRegistrationPasswords();

  // CHECKED HERE AND ON THE SERVER. Not because the browser is trusted -- it
  // is not, and the route checks it again -- but because a typo that costs a
  // round trip and a stern sentence is a typo the advocate reads as a
  // rejection rather than as a slip.
  if (password !== again) {
    showOutcome('bad', 'Registration failed',
      'The two passwords do not match. Nothing was saved.');
    return;
  }

  registrationInFlight = true;
  go.disabled = true;
  go.textContent = 'Creating account…';
  $('register').setAttribute('aria-busy', 'true');
  $('show-login').setAttribute('aria-disabled', 'true');
  const stop = new AbortController();
  const timeout = setTimeout(() => stop.abort(), 30000);
  try {
    const r = await api('/api/register', {
      method: 'POST',
      signal: stop.signal,
      headers: {
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        email: email,
        password: password,
        password_again: again,
      }),
    });
    // REGISTERED, NOT SIGNED IN. A form post that created a session would mean
    // creating an account also logs in whatever machine sent it, and the
    // device binding is minted at sign-in for exactly that reason.
    //
    // Sign in with the canonical handle returned by the account owner.
    registrationInFlight = false;
    $('login-id').value = r.advocate_id;
    showOutcome('good', 'Registration successful',
      `Your private workspace is ready. Sign in with ${r.advocate_id} and the password `
      + 'you just chose.', r.recovery_codes || [], 'register');
  } catch (err) {
    registrationInFlight = false;
    if (err.obsolete) return;
    $('login-id').value = email;
    showOutcome('bad', 'Registration failed', !err.status
      ? 'The registration result could not be confirmed. The account may have been created. Try signing in before registering again.'
      : err.message, [], 'register');
  } finally {
    clearTimeout(timeout);
    registrationInFlight = false;
    $('register').removeAttribute('aria-busy');
    $('show-login').removeAttribute('aria-disabled');
    clearRegistrationPasswords();
    go.disabled = false;
    go.textContent = 'Register';
  }
});

// THE REVEAL. `type=button` on the control, or it submits the form -- a
// default-type button inside a form is a submit button, and clicking the eye
// would have posted a half-filled registration.
//
// The password is revealed, never LOGGED and never copied anywhere: the value
// stays in the input and only its `type` changes. Both handlers already clear
// the fields after a submit for the same reason.
document.querySelectorAll('.pw-eye').forEach((eye) => {
  eye.addEventListener('click', () => {
    const field = $(eye.dataset.for);
    const showing = field.type === 'text';
    field.type = showing ? 'password' : 'text';
    eye.setAttribute('aria-pressed', String(!showing));
    // FOCUS RETURNS TO THE FIELD with the caret where it was. Losing the
    // caret to the end is the small annoyance that makes people stop using a
    // reveal and type blind instead.
    const at = field.value.length;
    field.focus();
    field.setSelectionRange(at, at);
  });
});
