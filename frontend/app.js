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
  // Working text stays in memory. Only authenticated ciphertext may survive
  // the tab, through the account/device-bound draft vault below.
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
  // A case-file response may return after the advocate has selected another
  // file. Only the newest read may paint, and its entries and currency must
  // become visible as one coherent primary snapshot.
  casefileGeneration: 0,
  // F-B-01/F-B-03. WHICH RIBBON TAB THE MATTER WORKSPACE BELONGS TO right now:
  // `home` for a matter started there, `advise` for one opened from My work.
  workTab: 'advise',
};

let registrationInFlight = false;
let registrationCapabilities = null;
let confirmationFlow = null;
let confirmationInFlight = false;
let resendTimer = null;
let outcomeReturn = 'register';
// THE EMAILED RESET LINK'S TOKEN. Implementation Plan F-A-03. Read once from the
// address fragment -- which a browser never sends to the server -- and removed
// from the address bar at once, so it is not left in history or on a shared
// screen. A variable, never storage, and dropped when it is spent or abandoned.
let resetToken = null;
let activeDelivery = null;
let retiringSession = null;

// In-memory work belongs to an advocate, workspace and file (or one unsaved
// opening), not to the composer DOM. The immutable pending request belongs to
// that same context, even if its acknowledgement or session is lost.
const intentContexts = new Map();
const INTAKE_INPUTS = [
  'in-title', 'in-client', 'in-client-type', 'in-adverse', 'in-others', 'in-scope',
  'in-instructing', 'in-instructor', 'in-instructor-role', 'in-authority',
  'in-other-state', 'in-proceedings', 'in-forum', 'in-reference', 'in-stage',
  'in-urgency', 'in-urgency-note', 'in-date', 'in-date-source',
];
let activeIntent = null;
let draftVault = null;
let draftWrite = 0;
let draftUnlock = Promise.resolve();
let storedDraftCount = 0;
let recoveryGeneration = 0;
let checkpointTimer = null;
let restoredTimer = null;
try { draftVault = new NMDraftVault(window.localStorage, window.crypto); }
catch { /* Unavailable storage is reported before any durable-save claim. */ }

function draftHasWork(intent) {
  return Boolean(intent && (intent.text.trim() || intent.pending.length
    || intent.intake || (intent.intakeOpen
      && Object.values(intent.fields || {}).some(value => String(value).trim()))));
}

async function saveProtectedDraft({previousKey = null} = {}) {
  if (!ownsIntent(activeIntent)) return;
  const held = activeIntent;
  const generation = state.sessionGeneration;
  const revision = ++draftWrite;
  const status = $('draft-status');
  clearTimeout(checkpointTimer);
  status.textContent = 'Saving draft…';
  try {
    // Sign-in reveals the workspace before its device-bound draft key finishes
    // importing. Early typing/opening must wait for that same account's unlock,
    // not report a false storage failure or borrow a later account's key.
    await draftUnlock;
    if (generation !== state.sessionGeneration || !ownsIntent(held)) return false;
    if (!draftVault?.key) throw new Error('Draft protection is not available.');
    // Pending entries carry a runtime back-reference to their intent. Persist
    // only the immutable retry envelope, never that circular object graph.
    if (!draftHasWork(held)) {
      await draftVault.removeOwn(held.key);
      if (previousKey) await draftVault.removeOwn(previousKey);
      if (generation === state.sessionGeneration && revision === draftWrite) status.textContent = '';
      return true;
    }
    const snapshot = {
      key:held.key, advocate:held.advocate, workspace:held.workspace,
      matterId:held.matterId, text:held.text, intake:held.intake,
      intakeOpen:held.intakeOpen, fields:held.fields, capacity:held.capacity,
      opening:held.opening || null,
      editedAt:held.editedAt || Date.now(),
      pending:held.pending.map(entry=>({turnId:entry.turnId, brief:entry.brief,
        request:entry.request, envelope:entry.envelope, state:'unknown',
        error:'A prior request needs reconciliation before retry.'})),
    };
    const savedAt = await draftVault.save(snapshot);
    if (previousKey && previousKey !== held.key) await draftVault.removeOwn(previousKey);
    if (generation !== state.sessionGeneration || revision !== draftWrite || !ownsIntent(held)) return;
    showDraftCheckpoint(savedAt);
    return true;
  } catch (error) {
    if (generation !== state.sessionGeneration || revision !== draftWrite || !ownsIntent(held)) return;
    status.textContent = 'Could not save this draft. Changes may not survive closing the page. '
      + error.message;
    return false;
  }
}

function showDraftCheckpoint(savedAt) {
  clearTimeout(checkpointTimer);
  $('draft-status').textContent = 'Saved on this device';
  $('draft-status').dataset.savedAt = String(savedAt);
  checkpointTimer = setTimeout(() => { $('draft-status').textContent = ''; }, 5000);
}

function clearDraftNotices() {
  clearTimeout(checkpointTimer);
  clearTimeout(restoredTimer);
  $('draft-status').textContent = '';
  $('draft-restored').textContent = '';
  delete $('draft-status').dataset.savedAt;
}

function showDraftRestored() {
  clearTimeout(restoredTimer);
  const anchor = activeIntent?.matterId ? $('message') : $('intake').querySelector('h2');
  anchor.insertAdjacentElement('beforebegin', $('draft-restored'));
  $('draft-restored').textContent = 'Draft restored';
  restoredTimer = setTimeout(() => { $('draft-restored').textContent = ''; }, 5000);
}

function closeDraftRecovery() {
  recoveryGeneration += 1;
  $('draft-dialog').close();
  $('draft-recovery').replaceChildren();
}

async function unlockDrafts() {
  const generation = state.sessionGeneration;
  const account = state.advocate;
  const workspace = state.workspace;
  try {
    // An older sign-in's delayed key import must never replace or lock the
    // current account's vault. Construct privately, then publish under its generation.
    const vault = new NMDraftVault(window.localStorage, window.crypto);
    const protection = await api('/api/drafts/key');
    if (generation !== state.sessionGeneration) return;
    await vault.unlock(protection);
    if (generation !== state.sessionGeneration) { vault.lock(); return; }
    draftVault = vault;
    const drafts = await vault.list();
    if (generation !== state.sessionGeneration) return;
    storedDraftCount = drafts.filter(saved => saved.intent.advocate === account
      && saved.intent.workspace === workspace && draftHasWork(saved.intent)).length;
  } catch (error) {
    if (generation === state.sessionGeneration) {
      $('draft-status').textContent = 'Draft protection is unavailable. ' + error.message;
    }
  }
}

async function openDraftRecovery() {
  if (!state.advocate || !activeIntent) return;
  $('workspace-more').open = false;
  const generation = ++recoveryGeneration;
  const session = state.sessionGeneration;
  const context = activeIntent;
  const current = () => generation === recoveryGeneration
    && session === state.sessionGeneration && ownsIntent(context);
  const panel = $('draft-recovery');
  $('draft-title').textContent = context.matterId ? 'Saved drafts for this matter' : 'Saved opening drafts';
  panel.textContent = 'Loading protected drafts…';
  $('draft-dialog').showModal();
  try {
    await draftUnlock;
    if (!current()) return;
    const vault = draftVault;
    if (!vault?.key) throw new Error('Draft protection is unavailable.');
    const drafts = await vault.list();
    if (!current()) return;
    panel.replaceChildren();
    let count = 0;
    for (const saved of drafts) {
      const intent = saved.intent;
      if (intent.advocate !== state.advocate || intent.workspace !== state.workspace
          || intent.key !== context.key || intent.matterId !== context.matterId
          || !draftHasWork(intent)) continue;
      count += 1;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'ghost';
      button.textContent = `Recover unsent draft saved ${new Date(saved.savedAt).toLocaleString()} · expires ${new Date(saved.expiresAt).toLocaleString()}`;
      button.addEventListener('click', async () => {
        const buttons = [...panel.querySelectorAll('button')];
        buttons.forEach(item => { item.disabled = true; });
        try {
          if (!current()) return;
          if (intent.matterId) await api(`/api/matters/${encodeURIComponent(intent.matterId)}`);
          if (!current()) return;
          snapshotIntent();
          if (draftHasWork(context) && !await saveProtectedDraft()) {
            throw new Error('Your current draft could not be protected. It has not been replaced.');
          }
          if (!current()) return;
          await vault.adopt(saved);
          if (!current()) return;
          intent.editedAt = saved.savedAt;
          intent.pending.forEach(entry=>{entry.context=intent;});
          // Recover explicitly, keeping other tab versions in protected storage.
          intentContexts.set(intent.key, intent);
          activeIntent = null;
          if (intent.matterId) { showTab('advise'); await showThreadBoard(intent.matterId); }
          else startMatter();
          if (session !== state.sessionGeneration || !ownsIntent(intent)) return;
          closeDraftRecovery();
          showDraftRestored();
          (intent.matterId ? $('message') : $('in-title')).focus();
        } catch (error) {
          if (current()) {
            panel.appendChild(stateBlock('loud', `Draft was not opened: ${error.message}`));
          }
        } finally { buttons.forEach(item => { item.disabled = false; }); }
      });
      panel.appendChild(button);
    }
    if (!count) panel.textContent = 'No recoverable drafts for this input.';
  } catch (error) {
    if (current()) {
      panel.replaceChildren(stateBlock('loud', 'Draft recovery is unavailable. ' + error.message));
    }
  }
}

window.addEventListener('storage', (event) => {
  if (draftVault && event.key === draftVault.epochKey && draftVault.key) {
    draftVault.lock();
    intentContexts.clear(); state.draft = null;
    clearPrivileged();
    showGate('This account signed out or discarded its drafts in another tab. Sign in again.');
  }
});

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

function snapshotIntent({ edited = false } = {}) {
  if (!ownsIntent(activeIntent)) return;
  activeIntent.text = $('message').value;
  activeIntent.intake = state.intake;
  activeIntent.intakeOpen = !$('intake').hidden;
  activeIntent.fields = Object.fromEntries(INTAKE_INPUTS.map((id) => [id, $(id).value]));
  activeIntent.capacity = $('in-capacity').checked;
  if (edited) { activeIntent.editedAt = Date.now(); saveProtectedDraft(); }
}

function restoreIntent() {
  const intent = activeIntent;
  $('message').value = intent ? intent.text : '';
  sizeComposer();
  state.intake = intent ? intent.intake : null;
  INTAKE_INPUTS.forEach((id) => {
    $(id).value = (intent && intent.fields[id]) || ($(id).tagName === 'SELECT' ? 'not_known' : '');
  });
  openingSections();
  $('in-capacity').checked = Boolean(intent && intent.capacity);
  $('intake-state').textContent = '';
  showIntake(Boolean(intent && intent.intakeOpen));
}

function selectIntent(matterId, { opening = false } = {}) {
  snapshotIntent();
  clearDraftNotices();
  closeDraftRecovery();
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
  saveProtectedDraft();
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
  if (draftVault) draftVault.lock();
  closeDraftRecovery();
  clearDraftNotices();
  stopIdleWatch();
  setAccountMenu(false);
  // A RECORDING IN PROGRESS BELONGS TO THE SESSION THAT STARTED IT (F-C-02),
  // and so does the socket carrying its live words (F-C-03).
  stopDictation({ discard: true });
  closeLiveWords();
  setPlusMenu(false);
  $('dictation-state').textContent = '';
  state.sessionGeneration += 1;
  state.searchGeneration += 1;
  state.historyGeneration += 1;
  state.historyListGeneration += 1;
  state.sessionsGeneration += 1;
  state.casefileGeneration += 1;
  $('sessions-dialog').close();
  $('ai-sharing-dialog').close();
  aiPermission = null;
  $('ai-sharing-status').textContent = '';
  $('ai-sharing-accept').checked = false;
  $('sessions-body').textContent = '';
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
  [...INTAKE_INPUTS, 'q', 'f-court', 'f-from', 'f-to']
    .forEach((id) => { $(id).value = ''; });
  $('opening-fields').replaceChildren();
  $('opening-record').hidden = true;
  $('in-capacity').checked = false;
  // THE RIBBON AND THE PERSON MENU FORGET WHO WAS HERE (F-A-17).
  ['who-name', 'workspace-name', 'profile-name', 'profile-email', 'profile-workspace']
    .forEach((id) => { const el = $(id); if (el) el.textContent = '—'; });
  $('work-links').hidden = true;
  const composer = $('message');
  if (composer) composer.value = '';
  const chooser = $('history-matter');
  if (chooser) chooser.innerHTML = '<option value="">Choose a matter…</option>';
  const cf = $('casefile-matter');
  if (cf) cf.innerHTML = '<option value="">Choose a matter…</option>';
  ['casefile-entries', 'currency-stale', 'currency-nodes', 'currency-history',
   'currency-state', 'casefile-state'].forEach((id) => {
    const el = $(id); if (el) el.textContent = '';
  });
  window.dispatchEvent(new Event('nm:session-ended'));
}

/* ------------------------------------------------------- idle sign-out --- */

// F-A-12. SIGNED OUT AFTER THIRTY MINUTES IN WHICH THE PAGE WAS NOT TOUCHED.
//
// The product owner's rule: no typing, no moving the pointer, no coming back to
// the tab -- the window not touched at all for thirty minutes -- and the
// advocate is signed out. Any activity starts the thirty minutes again.
//
// THE NUMBER IS THE SERVER'S. It arrives with the session as
// `session_idle_minutes` and is not written in this file, so the page and the
// server cannot hold two different limits.
//
// THE SERVER KEEPS THE SAME CLOCK. Every signed-in request restarts it there,
// and activity that makes no request is reported at most once a minute, with a
// trailing report -- so the server's last activity is never earlier than this
// page's, and the server never ends a session the page still counts as in use.
// A laptop shut mid-matter is refused by the server even if this page never
// runs again.
//
// EVERY OPEN TAB SHARES ONE CLOCK. They are one session and one person, so
// activity in any of them is broadcast to the rest.
const IDLE_WARNING_MS = 2 * 60 * 1000;
const IDLE_REPORT_MS = 60 * 1000;
const ACTIVITY_EVENTS = ['keydown', 'pointerdown', 'pointermove', 'wheel', 'touchstart',
  'scroll', 'input'];
const idle = { limitMs: 0, lastActivity: 0, lastReport: 0, timer: null, trailing: null,
  serverUntil: 0, serverMonotonicUntil: 0 };
const sessionChannel = typeof BroadcastChannel === 'function'
  ? new BroadcastChannel('nm-session') : null;

function idleWatching() {
  return idle.limitMs > 0 && Boolean(state.advocate) && !state.ended;
}

function startIdleWatch(minutes, accessWindow) {
  stopIdleWatch();
  if (!state.advocate || !(minutes > 0)) return;
  idle.limitMs = minutes * 60 * 1000;
  acceptAccessWindow(accessWindow);
  // The request that just opened or resolved the session already told the
  // server; opening this tab is activity the other tabs should hear about.
  idle.lastReport = Date.now();
  noteActivity(Date.now(), { report: false });
  sendActivityReport();
}

function acceptAccessWindow(window) {
  const remaining = Number(window?.remaining_seconds);
  const allowed = Number.isFinite(remaining) && remaining > 0 ? remaining * 1000 : 0;
  idle.serverUntil = Date.now() + allowed;
  idle.serverMonotonicUntil = performance.now() + allowed;
}

function accessWindowEnded() {
  return Date.now() >= idle.serverUntil || performance.now() >= idle.serverMonotonicUntil;
}

function stopIdleWatch() {
  clearTimeout(idle.timer);
  clearTimeout(idle.trailing);
  idle.timer = null;
  idle.trailing = null;
  idle.limitMs = 0;
  idle.lastActivity = 0;
  $('idle-warning').hidden = true;
}

// ACTIVITY AFTER THE LIMIT DOES NOT COUNT. Opening a laptop that has been shut
// for two hours makes the tab visible, and that must sign out -- not restart the
// clock for whoever lifted the lid while the last matter is still on the glass.
function noteActivity(at, { share = true, report = true } = {}) {
  if (!idleWatching()) return;
  if (accessWindowEnded()) {
    sessionEnded('Your last confirmed access window ended. Sign in again to recover your protected draft.');
    return;
  }
  if (idle.lastActivity && at - idle.lastActivity >= idle.limitMs) {
    idleSignOut();
    return;
  }
  // A pointer moving fires dozens of events a second; one a second is enough
  // to know the page is in use.
  if (at - idle.lastActivity < 1000) return;
  idle.lastActivity = at;
  $('idle-warning').hidden = true;
  if (share && sessionChannel) {
    sessionChannel.postMessage({ type: 'activity', at: at, advocate: state.advocate });
  }
  if (report) reportActivity();
  checkIdle();
}

function reportActivity() {
  const since = Date.now() - idle.lastReport;
  if (since >= IDLE_REPORT_MS) {
    sendActivityReport();
    return;
  }
  if (!idle.trailing) {
    idle.trailing = setTimeout(() => {
      idle.trailing = null;
      sendActivityReport();
    }, IDLE_REPORT_MS - since);
  }
}

async function sendActivityReport() {
  if (!idleWatching()) return;
  idle.lastReport = Date.now();
  try {
    // Only a user event sends this request. Background reads cannot renew it.
    const result = await api('/api/session/activity', {method:'POST'});
    acceptAccessWindow(result.access_window);
    if (sessionChannel) sessionChannel.postMessage({type:'access-window',
      advocate:state.advocate, until:idle.serverUntil});
    checkIdle();
  } catch { /* this page's own clock still ends the session on time */ }
}

function checkIdle() {
  clearTimeout(idle.timer);
  if (!idleWatching()) return;
  const now = Date.now();
  const endAt = Math.min(idle.lastActivity + idle.limitMs, idle.serverUntil);
  if (accessWindowEnded()) {
    sessionEnded('Your last confirmed access window ended. Sign in again to recover your protected draft.');
    return;
  }
  if (now >= endAt) {
    idleSignOut();
    return;
  }
  const warnAt = endAt - IDLE_WARNING_MS;
  if (now >= warnAt) showIdleWarning(endAt);
  idle.timer = setTimeout(checkIdle, Math.max(1000, (now < warnAt ? warnAt : endAt) - now));
}

function showIdleWarning(endAt) {
  const el = $('idle-warning');
  if (!el.hidden) return;
  const when = new Date(endAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  el.textContent = `Your current session is due to end at ${when}. If you are still working, `
    + 'continue here to refresh an idle session. At the maximum session lifetime, '
    + 'you will need to sign in again. Your protected unsent draft can be recovered.';
  el.hidden = false;
}

// THE DRAFT IS KEPT. `sessionEnded` freezes what was typed and puts it back
// after the advocate signs in again, exactly as for any other ended session.
async function idleSignOut({ fromAnotherTab = false } = {}) {
  const minutes = Math.round(idle.limitMs / 60000);
  stopIdleWatch();
  if (!state.advocate || state.ended) return;
  if (!fromAnotherTab && sessionChannel) {
    sessionChannel.postMessage({ type: 'idle-signed-out', minutes: minutes,
      advocate: state.advocate });
  }
  sessionEnded(`Nothing happened on Nyaymalaw for ${minutes} minutes, so you were `
    + 'signed out. Sign in again and I will put your unsent draft back where it was.');
  if (fromAnotherTab) return;
  // THE SERVER'S COPY ENDS NOW TOO. Its own idle clock would refuse this session
  // within a minute; ending it here closes that minute. If this request fails,
  // that clock still ends the session -- nothing here depends on it arriving.
  try {
    await api('/api/logout', { method: 'POST' }, { sessionBound: false });
  } catch { /* the server's idle limit ends the session regardless */ }
}

ACTIVITY_EVENTS.forEach((type) => {
  window.addEventListener(type, () => noteActivity(Date.now()), { capture: true, passive: true });
});
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') noteActivity(Date.now());
});
window.addEventListener('focus', () => noteActivity(Date.now()));
if (sessionChannel) {
  sessionChannel.addEventListener('message', (event) => {
    const data = event.data || {};
    if (!state.advocate || data.advocate !== state.advocate) return;
    if (data.type === 'activity') noteActivity(data.at, { share: false, report: false });
    if (data.type === 'access-window' && Number.isFinite(data.until)) {
      acceptAccessWindow({remaining_seconds:Math.max(0, data.until - Date.now()) / 1000});
      checkIdle();
    }
    if (data.type === 'idle-signed-out') {
      idle.limitMs = (data.minutes || 0) * 60000 || idle.limitMs;
      idleSignOut({ fromAnotherTab: true });
    }
  });
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
  if (['/api/login', '/api/register', '/api/password/reset'].includes(path)) {
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
  const sentAt = performance.now();
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (body?.access_window) {
    // A delayed response cannot lend its network transit time to authority.
    body.access_window.remaining_seconds = Math.max(0,
      Number(body.access_window.remaining_seconds) - (performance.now() - sentAt) / 1000);
  }
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
  // P18. STALE IS NOT A DATE. The window the file holds rested on something
  // the advocate has since corrected, and it must not lead the row however
  // near it is; the figure it used to be is shown under `stale` below.
  if (status === 'stale') {
    return { pill: 'blocked', text: 'STALE — awaiting recomputation' };
  }
  if (status === 'not_established') {
    return { pill: 'unknown', text: `${m.next_deadline} — currency not established` };
  }
  if (m.next_deadline && m.next_deadline_currency === 'not_established') {
    return { pill: 'unknown', text: `${m.next_deadline} — currency not established` };
  }
  if (['none_on_this_matter', 'none_on_this_thread'].includes(status)) {
    return { pill: 'ok', text };
  }
  return text;
}

// P18. THE WINDOW THAT STOPPED COUNTING, shown as the date it was. Hiding it
// would tell the advocate the file has no deadline; leading with it would
// tell them to work to a date they corrected. WHY it stopped is reasoning,
// and A2 keeps reasoning off the board -- the case file carries it.
function staleDeadlineFields(dl, t) {
  if (!t.stale_deadline) return;
  field(dl, 'stale', {
    pill: 'blocked',
    text: `${t.stale_deadline} — was the deadline; see the case file for why`,
  });
}

// F-B. THE THREE VIEWS OF THE MATTER WORKSPACE, and the stylesheet draws each:
//   list     My work's matters, and nothing else
//   opening  a new matter's intake form, and nothing else -- no list, no board
//   matter   the matter board on the left, the chat on the right
function setWorkView(view) {
  $('pane-advise').dataset.view = view;
}

// ONE WAY OUT OF AN OPEN MATTER, whether to My work's list or to a new
// opening. Any render still in flight for the old matter loses the right to
// paint, because the generation it holds is no longer current.
function closeOpenMatter() {
  state.railGeneration += 1;
  state.matterId = null;
  state.matterVersion = null;
  state.matterReady = false;
  state.turns = [];
  $('thread').textContent = '';
  $('pane-advise').dataset.matterId = '';
  $('back').hidden = true;
  $('matter-board').hidden = true;
  $('opening-fields').replaceChildren();
  $('opening-record').hidden = true;
  $('save-status').textContent = '';
}

// WHO THE FILE IS FOR AND WHO IT IS AGAINST. BK-33's acceptance is that ten
// similar matters stay distinguishable, and `threads: 1` on every row
// distinguishes nothing. ONE OWNER for My work's rows and the matter board
// (F-B-02), so a field added to one is on the other.
function matterFields(dl, m) {
  field(dl, 'client', m.client || 'not recorded');
  field(dl, 'against', m.opponent || 'not recorded');
  field(dl, 'deadline', deadlineField(m));
  field(dl, 'last worked', m.last_touched || 'never worked');
  field(dl, 'posture', m.blocked
    ? { pill: 'blocked', text: m.blocked }
    : { pill: 'unknown', text: 'no unresolved posture recorded' });
}

async function showMatterList({ preserveIntent = false } = {}) {
  if (!preserveIntent) selectIntent(null);
  closeOpenMatter();
  const generation = state.railGeneration;
  setWorkView('list');
  $('rail-title').textContent = 'Matters';
  $('matter-heading').textContent = 'My work';
  $('workspace-eyebrow').textContent = 'YOUR WORKSPACE';
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
    matterFields(dl, m);
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
    const previousKey = activeIntent.key;
    intentContexts.delete(activeIntent.key);
    activeIntent.matterId = matterId;
    activeIntent.key = intentKey(matterId);
    activeIntent.intakeOpen = false;
    intentContexts.set(activeIntent.key, activeIntent);
    restoreIntent();
    await saveProtectedDraft({previousKey});
  }
  selectIntent(matterId);
  const generation = ++state.railGeneration;
  // OPENING A MATTER CLOSES THE LIST at narrow widths. Leaving it up would
  // put the advocate on the answer they asked for with the index still over
  // it, which is the same unreachability wearing the other face.
  if (closeNavigator) toggleMatters(false);
  // F-B-02. AN OPEN MATTER IS ITS BOARD ON THE LEFT AND ITS CHAT ON THE RIGHT,
  // whether it was started from Home or opened from My work.
  setWorkView('matter');
  state.matterId = matterId;
  state.matterVersion = null;
  state.matterReady = false;
  updateWorkspace();
  $('matter-heading').textContent = 'Loading matter…';
  $('save-status').textContent = '';
  if (restore) {
    state.turns = [];
    $('thread').textContent = '';
  }
  window.dispatchEvent(new Event('nm:matter-changed'));
  $('pane-advise').dataset.matterId = matterId;
  $('rail-title').textContent = 'Matter board';
  $('back').hidden = false;
  $('matter-board').hidden = false;
  $('board-state').replaceChildren(stateBlock('building', 'Reading the matter board…'));
  // THE BOARD IS READ ON ITS OWN, so a thread board that fails to load does
  // not leave the matter's details saying they are still being read.
  renderMatterBoard(matterId, generation);
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
  renderOpeningBrief(data.opening_brief);
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
    staleDeadlineFields(dl, t);
    row.append(title, dl);
    return row;
  }));
}

function renderOpeningBrief(record) {
  const dl = $('opening-fields');
  dl.replaceChildren();
  $('opening-record').hidden = record?.state !== 'recorded';
  if (record?.state !== 'recorded') return;
  const brief = record.brief;
  for (const [name, role] of Object.entries(record.parties || {})) {
    field(dl, role === 'client' ? 'acting for' : role === 'adverse' ? 'opposing party' : 'other party', name);
  }
  const labels = { not_known: 'Not yet known', none_identified: 'None identified',
    none_reported: 'None reported', none: 'No proceedings reported',
    exists: 'Proceedings reported', stated: 'Urgency reported',
    representative: 'Through a representative', client: 'Client directly',
    identified: 'Parties recorded', individual: 'Individual', organisation: 'Organisation', mixed: 'Multiple types' };
  for (const [key, label] of [
    ['objective', 'immediate task'], ['client_type', 'client type'], ['instructing', 'instructions from'],
    ['instructor_name', 'instructor'], ['instructor_role', 'role'], ['authority_basis', 'stated authority'],
    ['other_party_state', 'other parties'], ['proceedings', 'current position'], ['forum', 'forum'],
    ['case_reference', 'reference'], ['stage', 'stage'], ['urgency', 'urgency'],
    ['urgency_details', 'reported urgency'], ['reported_date', 'reported date — not calculated'],
    ['date_source', 'date source'],
  ]) {
    const value = brief[key];
    if (value || key === 'objective') field(dl, label, labels[value] || value || 'To be discussed');
  }
  field(dl, 'capacity', (brief.capacity?.state || 'not_assessed').replaceAll('_', ' '));
}

// F-B-02. THE MATTER BOARD IS MY WORK'S ROW FOR THIS MATTER. It is read from
// the same `/api/matters` My work lists and drawn by the same `matterFields`,
// so the board and the list cannot say two different things about one file.
// It is read whenever the thread board is -- which includes after every
// message -- so what later messages add reaches it.
async function renderMatterBoard(matterId, generation) {
  const fields = $('board-fields');
  const st = $('board-state');
  let d;
  try {
    d = await api('/api/matters');
  } catch (e) {
    if (e.obsolete || generation !== state.railGeneration) return;
    fields.replaceChildren();
    st.replaceChildren(stateBlock('unbuildable',
      `The matter board could not be read: ${e.message}. This is a failure to read, `
      + 'not an empty file.'));
    return;
  }
  if (generation !== state.railGeneration) return;
  const m = (d.matters || []).find((row) => row.matter_id === matterId);
  fields.replaceChildren();
  if (!m) {
    st.replaceChildren(stateBlock('unbuildable',
      'This matter is not in the matter list, so its board cannot be shown. It has not '
      + 'been deleted; reload before relying on the board.'));
    return;
  }
  st.textContent = '';
  $('board-title').textContent = m.matter;
  matterFields(fields, m);
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
// The order and the headings come from `backend/nm/domain/brief.py`; this is the
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

// P24. THE BRIEFING READINESS SURFACE. Intake is READY only when no gap is
// open; a completed turn does not make it so. A need the advocate cannot get is
// paused with a resume trigger and not re-asked; the controls are the stop and
// resume decision, so the loop on unavailable material is the advocate's call.
function renderBriefing(brief, matterId, version) {
  const box = document.createElement('div');
  box.className = 'briefing';
  box.dataset.state = brief.state;
  const head = document.createElement('div');
  head.className = 'briefing-head';
  const pill = document.createElement('span');
  pill.className = 'pill ' + (brief.state === 'ready' ? 'ok'
    : brief.state === 'blocked' ? 'blocked' : 'unknown');
  pill.textContent = brief.state === 'ready' ? 'intake ready'
    : brief.state === 'blocked' ? 'paused — decision owed' : 'intake open';
  const why = document.createElement('span');
  why.className = 'briefing-why';
  why.textContent = ' ' + (brief.intake_complete_refused || brief.why || '');
  head.append(pill, why);
  box.appendChild(head);

  (brief.open_needs || []).forEach((need) => {
    const row = document.createElement('div');
    row.className = 'briefing-need';
    const t = document.createElement('span'); t.textContent = need;
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ghost'; btn.textContent = "I can't get this";
    const note = document.createElement('span'); note.className = 'hint';
    btn.addEventListener('click', async () => {
      note.textContent = 'Recording…';
      try {
        const out = await api(`/api/matters/${matterId}/briefing/unavailable`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ need, resume_when: 'new material or an instruction arrives',
            expected_version: ((state.matterId === matterId && state.matterVersion > version) ? state.matterVersion : version) }),
        });
        if (state.matterId === matterId) state.matterVersion = out.version;
        note.textContent = 'Paused. I will not ask again until it can be obtained.';
        btn.disabled = true;
      } catch (err) {
        note.textContent = (err.detail && err.detail.why) || err.message;
      }
    });
    row.append(t, btn, note);
    box.appendChild(row);
  });

  (brief.paused || []).forEach((p) => {
    const row = document.createElement('div');
    row.className = 'briefing-need paused';
    const t = document.createElement('span');
    t.textContent = `paused: ${p.need} — resumes when ${p.resume_when}`;
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ghost'; btn.textContent = 'Resume';
    const note = document.createElement('span'); note.className = 'hint';
    btn.addEventListener('click', async () => {
      note.textContent = 'Resuming…';
      try {
        const out = await api(`/api/matters/${matterId}/briefing/resume`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ need: p.need,
            expected_version: ((state.matterId === matterId && state.matterVersion > version) ? state.matterVersion : version) }),
        });
        if (state.matterId === matterId) state.matterVersion = out.version;
        note.textContent = 'Resumed. I will raise it again at the useful moment.';
        btn.disabled = true;
      } catch (err) {
        note.textContent = (err.detail && err.detail.why) || err.message;
      }
    });
    row.append(t, btn, note);
    box.appendChild(row);
  });
  return box;
}

// P24. The briefing readiness on the CASE FILE, from the cover, so it survives
// across turns and a restart. Reuses the same control as the Advise pane.
function renderBriefingPane(matterId, brief, version) {
  const pane = $('briefing-pane');
  const host = $('briefing-host');
  if (!pane || !host) return;
  host.textContent = '';
  if (!brief || brief.state === 'not_assessed') { pane.hidden = true; return; }
  pane.hidden = false;
  host.appendChild(renderBriefing(brief, matterId, version));
}

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

    if (refusal?.code === 'model_permission_required') {
      const why = document.createElement('p');
      why.textContent = refusal.why;
      const settings = document.createElement('button');
      settings.type = 'button'; settings.className = 'ghost';
      settings.textContent = 'Review AI data sharing';
      settings.addEventListener('click', openAiSharing);
      f.append(why, settings);
    } else if (refusal && refusal.withheld_by && refusal.withheld_by.length) {
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
      f.textContent = entry.state === 'unknown'
        ? `The response could not be received: ${entry.error}`
        : `The turn was refused: ${entry.error}`;
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
  // Grounds filed under Time or Risk are conclusions rather than support.
  // Older transcripts have no section and retain their prior folding rule.
  const foldsAsSupport = (el) => el.kind === 'ground'
    && !el.disclosure && el.signal === 'none'
    && (!el.section || el.section === 'authority');
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
  // THE SECTION COMES FROM THE SERVER (`backend/nm/domain/brief.py`), so this groups
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

  // Support is visible by default. The advocate may collapse ordinary support,
  // but material signals and disclosures stay outside that choice. This shows
  // the passages actually supplied; it does not claim full-source verification.
  if (support.length) {
    const fold = document.createElement('details');
    fold.className = 'support';
    fold.open = true;
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

  // P24. INTAKE READINESS, which the turn completing does not establish. The
  // block names whether the file is ready, the open needs, and the needs the
  // advocate marked unavailable with their resume trigger -- and offers the
  // stop ("I can't get this") and resume controls, so the loop is a decision.
  const brief = entry.answer.briefing;
  if (brief && brief.state && brief.state !== 'not_assessed'
      && (brief.state !== 'ready' || (brief.paused || []).length)) {
    wrap.appendChild(renderBriefing(brief, entry.answer.matter_id,
                                    entry.answer.matter_version));
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
  const follow = t.scrollHeight - t.scrollTop - t.clientHeight < 48;
  const top = t.scrollTop;
  t.replaceChildren(...state.turns.map(renderTurn));
  t.scrollTop = follow ? t.scrollHeight : top;
  $('jump-latest').hidden = follow;
  updateWorkspace();
}

function sizeComposer() {
  const box = $('message');
  box.style.height = 'auto';
  box.style.height = `${Math.min(Math.max(box.scrollHeight, 56), 180)}px`;
}

function updateWorkspace() {
  const intakeOpen = !$('intake').hidden;
  const nothingYet = !state.matterId && !state.turns.length && !state.intake && !intakeOpen;
  $('composer').hidden = nothingYet || intakeOpen;
  // F-A-17. Case file and History are offered for a matter that is open.
  $('work-links').hidden = !state.matterId;
  $('send').disabled = Boolean(activeDelivery || (state.matterId && !state.matterReady));
  if (!activeDelivery) $('send').textContent = state.matterId && !state.matterReady
    ? 'Loading file…' : 'Send';
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
    if (!await saveProtectedDraft()) {
      throw new Error('The retry details could not be saved on this device. No request was sent.');
    }
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
    // A reply belongs to the conversation that sent it. An unestablished
    // screen may ask for information, but prose must never navigate back to
    // the opening form or hide that question. Opening is an explicit user
    // action; correcting a saved cover uses the matter's own controls.
    intent.intakeOpen = false;
    // A saved opening acquires a file identity, but its original turn envelope
    // keeps matter_id:null for idempotent replay if this acknowledgement is lost.
    const previousKey = intent.key;
    if (answer.matter_id && !intent.matterId) {
      intentContexts.delete(intent.key);
      intent.matterId = answer.matter_id;
      intent.key = JSON.stringify([intent.advocate, intent.workspace, intent.matterId]);
      intentContexts.set(intent.key, intent);
    }
    if (!current()) return;
    restoreIntent();
    await saveProtectedDraft({previousKey});
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
      updateWorkspace();
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
  if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing && ev.keyCode !== 229) {
    ev.preventDefault();
    $('composer').requestSubmit();
  }
});


/* ------------------------------------------------------- plus and mic --- */

// F-C-01. THE PLUS UNDER THE BRIEF. Its three items open the original-material
// window (`intake-materials.js`), which seals what it receives and reads none
// of it; this owns only the menu opening and closing.
function setPlusMenu(open) {
  $('plus-panel').hidden = !open;
  $('plus-toggle').setAttribute('aria-expanded', open ? 'true' : 'false');
}

$('plus-toggle').addEventListener('click', () => setPlusMenu($('plus-panel').hidden));
document.addEventListener('click', (ev) => {
  if (!$('plus-panel').hidden && !$('plus-menu').contains(ev.target)) setPlusMenu(false);
});
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !$('plus-panel').hidden) {
    setPlusMenu(false);
    $('plus-toggle').focus();
  }
});

// F-C-02. THE MIC BESIDE THE PLUS: say the brief instead of typing it.
//
// Press to start, press again to stop. The recording goes to this
// installation's own speech model (`/api/dictation`) -- no outside service --
// and the words come back INTO THE BRIEF BOX, where the advocate reads and
// corrects them before sending. Nothing is sent by itself, and the recording is
// not kept: a voice note meant to be kept goes through the plus menu instead.
const DICTATION_LIMIT_MS = 5 * 60 * 1000;
//: F-C-03. The rate the live speech model is built for. The audio context is
//: opened at it, so nothing is resampled on the way to the model.
const LIVE_SAMPLE_RATE = 16000;
const dictation = {
  recorder: null, stream: null, chunks: [], timer: null, busy: false,
  // THE LIVE HALF (F-C-03): the socket and audio graph feeding it, where the
  // provisional words sit in the brief box, and whether they are still ours to
  // replace -- they stop being ours the moment the advocate edits them.
  live: null, anchor: 0, provisional: '', ours: false,
};

function sayDictation(text) {
  $('dictation-state').textContent = text;
}

function releaseMicrophone() {
  clearTimeout(dictation.timer);
  dictation.timer = null;
  if (dictation.stream) dictation.stream.getTracks().forEach((track) => track.stop());
  dictation.stream = null;
}

// F-C-03. WHERE THE LIVE WORDS GO, and how they stop being ours.
//
// They are written into the brief box at the caret, and each update replaces
// exactly the span the last one wrote. If that span is no longer what we wrote,
// the advocate has edited it -- so the live words let go rather than overwrite
// their editing, and say so. What they said is still recorded either way: the
// final transcription arrives when they stop.
function beginProvisional() {
  const box = $('message');
  dictation.anchor = box.selectionStart ?? box.value.length;
  dictation.provisional = '';
  dictation.ours = true;
}

function replaceProvisional(words) {
  if (!dictation.ours) return false;
  const box = $('message');
  const held = box.value.slice(dictation.anchor, dictation.anchor + dictation.provisional.length);
  if (held !== dictation.provisional) {
    dictation.ours = false;
    return false;
  }
  const before = box.value.slice(0, dictation.anchor);
  const after = box.value.slice(dictation.anchor + dictation.provisional.length);
  const lead = before && !/\s$/.test(before) ? ' ' : '';
  const text = words ? lead + words : '';
  box.value = before + text + after;
  dictation.provisional = text;
  const caret = (before + text).length;
  box.setSelectionRange(caret, caret);
  box.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
}

function showLiveWords(words) {
  if (!replaceProvisional((words || '').trim())) {
    sayDictation('You edited the brief, so the live words stopped there. What you are '
      + 'saying is still recorded and will be added when you stop.');
  }
}

function closeLiveWords({ finish = false } = {}) {
  const live = dictation.live;
  dictation.live = null;
  if (!live) return;
  try {
    if (live.node) live.node.port.onmessage = null;
    if (live.node) live.node.disconnect();
    if (live.source) live.source.disconnect();
    if (live.silence) live.silence.disconnect();
    // `finish` asks the server for the last words; an abandoned dictation just
    // closes, and the server keeps nothing either way.
    if (live.socket.readyState === WebSocket.OPEN) {
      if (finish) live.socket.send('done');
      else live.socket.close();
    }
    if (live.context.state !== 'closed') live.context.close();
  } catch { /* a socket or graph already gone needs no closing */ }
}

// THE MICROPHONE, STRAIGHT TO THE LIVE MODEL. The audio graph is NOT connected
// to the speakers -- it feeds a silent gain node -- because a processor that
// has no output is not pulled, and connecting it to the speakers would play the
// advocate's own voice back at them.
async function openLiveWords(stream, session) {
  if (!window.AudioContext || !window.AudioWorkletNode || !window.WebSocket) return;
  let context;
  try {
    context = new AudioContext({ sampleRate: LIVE_SAMPLE_RATE });
    await context.audioWorklet.addModule('/static/dictation-worklet.js');
  } catch {
    sayDictation('Listening. The words will appear when you stop.');
    return;
  }
  if (session !== state.sessionGeneration || !dictation.recorder) {
    context.close();
    return;
  }
  const socket = new WebSocket(`${window.location.origin.replace(/^http/, 'ws')}/ws/dictation`);
  socket.binaryType = 'arraybuffer';
  const source = context.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(context, 'dictation');
  const silence = context.createGain();
  silence.gain.value = 0;
  node.port.onmessage = (ev) => {
    if (socket.readyState === WebSocket.OPEN) socket.send(ev.data);
  };
  source.connect(node);
  node.connect(silence);
  silence.connect(context.destination);
  dictation.live = { context, socket, node, source, silence };
  socket.addEventListener('message', (ev) => {
    let heard;
    try { heard = JSON.parse(ev.data); } catch { return; }
    if (heard.live === false) {
      sayDictation(`${heard.why} Listening.`);
      return;
    }
    if (typeof heard.words === 'string') showLiveWords(heard.words);
  });
  socket.addEventListener('error', () => {
    sayDictation('Listening. The live words stopped, so they will appear when you stop.');
  });
}

function stopDictation({ discard = false } = {}) {
  const recorder = dictation.recorder;
  if (!recorder) return;
  recorder.discard = discard;
  if (recorder.state !== 'inactive') recorder.stop();
  else releaseMicrophone();
}

async function startDictation() {
  if (dictation.recorder || dictation.busy || !state.advocate) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    sayDictation('Dictation needs a browser that can record audio. Type the brief instead.');
    return;
  }
  sayDictation('Waiting for permission to use the microphone…');
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    sayDictation('The microphone is unavailable or permission was declined. Nothing was recorded.');
    return;
  }
  const session = state.sessionGeneration;
  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
    .find((type) => MediaRecorder.isTypeSupported(type));
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
  dictation.recorder = recorder;
  dictation.stream = stream;
  dictation.chunks = [];
  recorder.addEventListener('dataavailable', (ev) => {
    if (ev.data.size) dictation.chunks.push(ev.data);
  });
  recorder.addEventListener('stop', () => {
    const blob = new Blob(dictation.chunks, { type: recorder.mimeType || 'audio/webm' });
    dictation.chunks = [];
    dictation.recorder = null;
    closeLiveWords({ finish: !recorder.discard });
    releaseMicrophone();
    $('dictate').setAttribute('aria-pressed', 'false');
    $('dictate').classList.remove('recording');
    if (recorder.discard || session !== state.sessionGeneration) return;
    if (!blob.size) {
      sayDictation('No audio was captured. Nothing was transcribed.');
      return;
    }
    transcribeDictation(blob, session);
  });
  recorder.start(1000);
  dictation.timer = setTimeout(() => {
    sayDictation('Five minutes is the limit for one dictation; stopping to transcribe it.');
    stopDictation();
  }, DICTATION_LIMIT_MS);
  $('dictate').setAttribute('aria-pressed', 'true');
  $('dictate').classList.add('recording');
  sayDictation('Listening. Press the mic again to stop.');
  // F-C-03. The words appear as they are spoken, from the live model, into the
  // brief box at the caret; the accurate transcription replaces them at the end.
  beginProvisional();
  await openLiveWords(stream, session);
}

async function transcribeDictation(blob, session) {
  dictation.busy = true;
  $('dictate').disabled = true;
  sayDictation('Turning your words into text…');
  try {
    const heard = await api('/api/dictation', {
      method: 'POST',
      headers: { 'content-type': blob.type.split(';')[0] || 'audio/webm' },
      body: blob,
    });
    if (session !== state.sessionGeneration) return;
    const words = (heard.text || '').trim();
    if (!words) {
      sayDictation('No words were recognised. Nothing was added; try again closer to the microphone.');
      replaceProvisional('');
      return;
    }
    // THE ACCURATE TEXT REPLACES THE LIVE WORDS it was standing in for, and is
    // inserted at the caret when those are no longer ours to replace.
    if (!replaceProvisional(words)) insertIntoBrief(words);
    dictation.ours = false;
    sayDictation(heard.device === 'cpu'
      ? 'Added to your brief; check it before sending. (Transcribed without the graphics card, so it was slower.)'
      : 'Added to your brief; check it before sending.');
  } catch (e) {
    if (e.obsolete || session !== state.sessionGeneration) return;
    sayDictation(`Your words were not added: ${e.message}`);
  } finally {
    dictation.busy = false;
    $('dictate').disabled = false;
  }
}

// AT THE CURSOR, with a space either side where one is missing, so dictation
// can fill a gap in a typed brief as well as start one.
function insertIntoBrief(words) {
  const box = $('message');
  const start = box.selectionStart ?? box.value.length;
  const end = box.selectionEnd ?? box.value.length;
  const before = box.value.slice(0, start);
  const after = box.value.slice(end);
  const lead = before && !/\s$/.test(before) ? ' ' : '';
  const trail = after && !/^\s/.test(after) ? ' ' : '';
  box.value = before + lead + words + trail + after;
  const caret = (before + lead + words).length;
  box.focus();
  box.setSelectionRange(caret, caret);
  box.dispatchEvent(new Event('input', { bubbles: true }));
}

$('dictate').addEventListener('click', () => {
  if (dictation.recorder) stopDictation();
  else startDictation();
});

// My matters: back to My work's list, under My work.
$('back').addEventListener('click', () => openTab('advise'));

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

// INSIDE MY WORK, NOT THE RIBBON (F-A-17). From any other page the way back to
// the matter list is the My work tab, which is on every page.
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
  const seen = new Set();
  for (const [id, role] of [['in-client', 'client'], ['in-adverse', 'adverse'], ['in-others', 'related']]) {
    for (const entry of $(id).value.split('\n')) {
      const name = entry.trim();
      if (!name) continue;
      const identity = name.toLocaleLowerCase();
      if (seen.has(identity)) throw new Error('A party is listed more than once. Give each party one role.');
      seen.add(identity);
      Object.defineProperty(parties, name, { value: role, enumerable: true });
    }
  }
  const capacity = {
    state: $('in-capacity').checked ? 'not_in_doubt' : 'not_assessed',
    basis: $('in-capacity').checked
      ? 'The advocate explicitly confirms that the client can give these instructions.'
      : 'The advocate has not assessed capacity to give these instructions.',
  };
  const text = (id) => $(id).value.trim();
  const representative = text('in-instructing') === 'representative';
  const proceedings = text('in-proceedings');
  const urgency = text('in-urgency');
  let otherState = text('in-other-state');
  if (otherState === 'not_known' && Object.values(parties).some(role => role !== 'client')) {
    otherState = 'identified';
  }
  const brief = {
    client_type: text('in-client-type'), instructing: text('in-instructing'),
    instructor_name: representative ? text('in-instructor') : '',
    instructor_role: representative ? text('in-instructor-role') : '',
    authority_basis: representative ? text('in-authority') : '',
    objective: text('in-scope'), other_party_state: otherState, proceedings,
    forum: proceedings !== 'none' ? text('in-forum') : '',
    case_reference: proceedings !== 'none' ? text('in-reference') : '',
    stage: proceedings !== 'none' ? text('in-stage') : '', urgency,
    urgency_details: urgency === 'stated' ? text('in-urgency-note') : '',
    reported_date: urgency === 'stated' ? text('in-date') : '',
    date_source: urgency === 'stated' ? text('in-date-source') : '', capacity,
  };
  return { parties, capacity, title: text('in-title'), brief,
    release: brief.objective ? { scope: brief.objective } : {} };
}

function openingSections() {
  $('in-representative').hidden = $('in-instructing').value !== 'representative';
  $('in-proceeding-details').hidden = $('in-proceedings').value === 'none';
  $('in-urgency-details').hidden = $('in-urgency').value !== 'stated';
}
['in-instructing', 'in-proceedings', 'in-urgency'].forEach(id =>
  $(id).addEventListener('change', openingSections));

let openingInFlight = false;

$('intake').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  if (openingInFlight) return;
  // THE ANSWERS STILL TRAVEL WITH THE FIRST BRIEF. The scope, capacity and
  // conflict screens run on that turn, before any fact is admitted (BK-34).
  try { state.intake = intakeFields(); }
  catch (error) {
    $('intake-state').replaceChildren(stateBlock('loud', error.message));
    return;
  }
  if (state.matterId) {
    // Intake asked again on a matter that already exists: nothing to open.
    showIntake(false);
    $('intake-state').textContent = '';
    $('message').focus();
    return;
  }
  // F-B-01. THE MATTER IS SAVED WHEN ITS CHAT OPENS, not at the first brief:
  // the product owner's rule is that a new matter is in My work from the
  // moment its chat and board appear, so it can be closed and resumed. The
  // server opens it with the parties the form gave and names it from them;
  // only once the server confirms it is saved do the chat and board open.
  const intent = activeIntent;
  const go = $('in-go');
  const payload = { title: state.intake.title, parties: state.intake.parties, brief: state.intake.brief };
  const offer = JSON.stringify(payload);
  if (intent.opening && intent.opening.offer !== offer && intent.opening.uncertain) {
    $('intake-state').replaceChildren(stateBlock('loud',
      'The earlier opening is awaiting confirmation. A changed brief cannot be submitted as a second matter until that opening is resolved.'));
    if (intent.opening.fields) {
      const restore = document.createElement('button');
      restore.type = 'button';
      restore.textContent = 'Restore original answers and retry';
      restore.addEventListener('click', () => {
        if (!ownsIntent(intent)) return;
        intent.fields = { ...intent.opening.fields };
        intent.capacity = intent.opening.capacity;
        restoreIntent();
        $('intake').requestSubmit();
      });
      $('intake-state').append(restore);
    }
    return;
  }
  if (!intent.opening || intent.opening.offer !== offer) {
    // ONE REQUEST KEY PER SET OF ANSWERS, so a retry after a lost response
    // reopens the same file rather than a second one.
    intent.opening = { offer, key: newTurnId(),
      fields: Object.fromEntries(INTAKE_INPUTS.map(id => [id, $(id).value])),
      capacity: $('in-capacity').checked };
  }
  openingInFlight = true;
  go.disabled = true;
  [...INTAKE_INPUTS, 'in-capacity'].forEach(id => { $(id).disabled = true; });
  $('intake-state').replaceChildren(stateBlock('building', 'Opening the matter…'));
  try {
    snapshotIntent();
    if (!await saveProtectedDraft()) {
      throw new Error('the retry details could not be saved on this device; no request was sent');
    }
    intent.opening.uncertain = true;
    if (!await saveProtectedDraft()) {
      intent.opening.uncertain = false;
      throw new Error('the retry state could not be saved on this device; no request was sent');
    }
    const opened = await api('/api/matters/intake', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ request_key: intent.opening.key, ...payload }),
    });
    if (!ownsIntent(intent)) return;
    if (!opened.matter_id || opened.state !== 'intake_opened') {
      throw new Error('the server did not confirm that the matter was saved');
    }
    intent.opening.uncertain = false;
    // These instructions are now on the server, not an unsent first-turn draft.
    // The turn engine reads their attributed record when the advocate returns.
    state.intake = null;
    intent.intake = null;
    showIntake(false);
    $('intake-state').textContent = '';
    await showThreadBoard(opened.matter_id, { adoptOpening: true, restore: false });
    // Adoption saves the protected draft before revealing the composer. Focus
    // only after that transition, and never steal it from a different context.
    if (ownsIntent(intent) && state.matterId === opened.matter_id && state.matterReady) {
      $('message').focus();
    }
  } catch (e) {
    if (e.obsolete || !ownsIntent(intent)) return;
    if ([400, 403, 413, 422].includes(e.status)) {
      intent.opening.uncertain = false;
      await saveProtectedDraft();
    }
    const recovery = intent.opening?.uncertain
      ? 'The server may have saved the matter. Your original answers and retry identity are kept; retry without changing them.'
      : 'Your answers remain here. Resolve the reported problem before retrying.';
    $('intake-state').replaceChildren(stateBlock('loud',
      `Opening was not confirmed: ${e.message}. ${recovery}`));
  } finally {
    openingInFlight = false;
    go.disabled = false;
    [...INTAKE_INPUTS, 'in-capacity'].forEach(id => { $(id).disabled = false; });
  }
});

// F-B-01. A NEW MATTER BELONGS TO HOME, and it opens on the intake form alone:
// no list of other matters and no board, because there is no matter yet.
function startMatter() {
  state.workTab = 'home';
  showTab('advise');
  setWorkView('opening');
  selectIntent(null, { opening: true });
  toggleMatters(false);
  closeOpenMatter();
  state.turns = [...activeIntent.pending];
  repaint();
  $('mode-line').hidden = true;
  $('rail-title').textContent = 'Matters';
  $('matter-heading').textContent = 'New matter';
  $('workspace-eyebrow').textContent = 'THE INSTRUCTION';
  $('save-status').textContent = 'Not yet saved';
  window.dispatchEvent(new Event('nm:matter-changed'));
  if (!$('intake').hidden) $('in-client').focus();
  else $('message').focus();
}

// F-A-18, F-B-01. Home's one button starts a new matter, under Home.
$('home-start').addEventListener('click', startMatter);

/* THE GATE RUNS FIRST.
 *
 * These two ran at load, unconditionally, so the board fetched and
 * painted before anything asked whether this browser was signed in.
 * `boot()` resolves the session and only then starts the application. */
let aiPermission = null;
let aiSharingRequest = 0;
for (const host of document.querySelectorAll('[data-ai-notice]')) {
  host.append($('openai-text-notice').content.cloneNode(true));
}
function syncAiSharing() {
  $('ai-sharing-save').disabled = !aiPermission || !$('ai-sharing-accept').checked;
  $('ai-sharing-withdraw').disabled = !aiPermission || !aiPermission.accepted;
}
async function openAiSharing() {
  setAccountMenu(false);
  const request = ++aiSharingRequest;
  aiPermission = null;
  $('ai-sharing-accept').checked = false;
  $('ai-sharing-status').textContent = 'Checking your current permission…';
  syncAiSharing();
  if (!$('ai-sharing-dialog').open) $('ai-sharing-dialog').showModal();
  try {
    const result = await api('/api/account/model-permission');
    if (request !== aiSharingRequest) return;
    if (result.notice_version !== $('openai-text-notice').dataset.noticeVersion) {
      throw new Error('The notice changed. Reload this page before accepting it.');
    }
    aiPermission = result;
    $('ai-sharing-status').textContent = result.accepted
      ? 'OpenAI text processing is enabled for your account.'
      : 'OpenAI text processing is not enabled. Your matters remain accessible.';
  } catch (err) {
    if (!err.obsolete && request === aiSharingRequest) $('ai-sharing-status').textContent = err.message;
  }
  if (request === aiSharingRequest) syncAiSharing();
}
async function saveAiSharing(accepted) {
  if (!aiPermission || (accepted && !$('ai-sharing-accept').checked)) return;
  const request = ++aiSharingRequest;
  const version = aiPermission.version;
  aiPermission = null;
  syncAiSharing();
  $('ai-sharing-status').textContent = 'Recording your choice…';
  try {
    const result = await api('/api/account/model-permission', {
      method: 'POST', headers: {'content-type': 'application/json'},
      body: JSON.stringify({accepted, expected_version: version,
        notice_version: $('openai-text-notice').dataset.noticeVersion}),
    });
    if (request !== aiSharingRequest) return;
    aiPermission = result;
    $('ai-sharing-accept').checked = false;
    $('ai-sharing-status').textContent = result.accepted
      ? 'Permission recorded for OpenAI text processing.'
      : 'Permission withdrawn. Subsequent OpenAI requests are blocked; your matters remain accessible.';
  } catch (err) {
    if (!err.obsolete && request === aiSharingRequest) {
      $('ai-sharing-status').textContent = 'Your choice was not confirmed. Reopen this panel to check. '
        + err.message;
    }
  }
  if (request === aiSharingRequest) syncAiSharing();
}
$('ai-sharing').addEventListener('click', openAiSharing);
$('ai-sharing-accept').addEventListener('change', syncAiSharing);
$('ai-sharing-save').addEventListener('click', () => saveAiSharing(true));
$('ai-sharing-withdraw').addEventListener('click', () => saveAiSharing(false));
$('ai-sharing-close').addEventListener('click', () => $('ai-sharing-dialog').close());
$('ai-sharing-dialog').addEventListener('close', () => { ++aiSharingRequest; aiPermission = null; });
boot();

/* ============================== THE TABS ==============================
 *
 * Three surfaces that deliberately do NOT share state. A hit found in the
 * corpus is not a fact on a matter until the advocate puts it there, and the
 * quickest way to break that is a shared object both panes write to.
 */

const PANES = ['home', 'advise', 'search', 'casefile', 'history', 'prepare'];

// F-A-17, F-B. THE RIBBON HAS FOUR TABS AND SIX PAGES. The matter workspace,
// and the Case file and History opened from a matter, belong to whichever tab
// the matter was reached from: Home for a new matter, My work for one opened
// from its list.
function tabFor(pane) {
  if (['advise', 'casefile', 'history'].includes(pane)) return state.workTab;
  return pane;
}

// F-B-03. THE MY WORK TAB IS THE LIST OF MATTERS, every time it is chosen.
function openTab(name) {
  if (name === 'advise') {
    state.workTab = 'advise';
    showTab('advise');
    showMatterList();
    return;
  }
  showTab(name);
}

function showTab(name) {
  PANES.forEach((p) => { $(`pane-${p}`).hidden = (p !== name); });
  const tab = tabFor(name);
  document.querySelectorAll('#tabs .tab').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.tab === tab);
    if (b.dataset.tab === tab) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  if (name === 'search') { researchEnabled(); $('q').focus(); }
  if (name === 'history') loadHistoryMatters();
  if (name === 'casefile') loadCasefileMatters();
  if (name === 'prepare') loadPrepareMatters();
}

document.querySelectorAll('#tabs .tab').forEach((b) => {
  b.addEventListener('click', () => openTab(b.dataset.tab));
});

$('work-links').addEventListener('click', (ev) => {
  const link = ev.target.closest('button[data-tab]');
  if (!link) return;
  // THE MATTER THAT IS OPEN, not whichever one the case file showed last.
  if (link.dataset.tab === 'casefile') $('casefile-matter').value = '';
  showTab(link.dataset.tab);
});

/* ================= PREPARATION — P29 to P32 ON ONE SCREEN. P36 ===========
 *
 * WHY THESE FOUR ARE ONE PANE AND NOT FOUR.
 * An advocate does not think "now I am in the action-authority feature". They
 * think: get the document right, work out how it goes out, get ready for
 * Tuesday, and know where this stands if somebody else picks it up. Splitting
 * them across four screens would make each one reachable and the SEQUENCE
 * unreachable, which is the reorientation cost BK-68 is about.
 *
 * NO RENDER EVER REBUILDS A FORM, AND THE BROWSER TAUGHT ME THAT HERE.
 * A first version created the witness, outcome and handover forms inside the
 * render. An in-flight render then landed after the advocate had typed, took
 * the form with it, and the submit that followed was rejected for a field they
 * had filled in — the exact defect BK-42 names and one this pane was written
 * to prove absent. Every form now lives in `index.html`; a render fills the
 * read-only `-host` divs and reveals a form with `hidden = false`, and nothing
 * on this screen replaces an element that holds what somebody typed.
 *
 * EVERY CONTROL IS LABELLED AND EVERY ERROR IS ASSOCIATED. The error boxes
 * carry `role="alert"` and sit inside the section they belong to, so a screen
 * reader reaching one has already heard the heading.
 *
 * THE PANE NEVER SAYS SOMETHING HAPPENED THAT DID NOT. The refusal for the
 * send/file route is printed from what the server sent, so if that route ever
 * stopped refusing, this screen would stop saying it refuses.
 */

let prepareGeneration = 0;
const prepared = { packageId: null, proposalId: null, packId: null,
                   handoverId: null, digest: '' };

const PREP_HOSTS = ['package-host', 'package-export', 'action-host',
                    'hearing-host', 'witness-host', 'incourt-host',
                    'continuity-host', 'handover-host'];
const PREP_ERRORS = ['package-error', 'action-error', 'hearing-error',
                     'continuity-error'];
const PREP_ON_DEMAND = ['pk-export', 'ac-confirm', 'ac-send', 'outcome-form',
                        'reconcile-form', 'witness-form', 'hp-incourt',
                        'handover-form'];

function prepareError(id, err) {
  const box = $(id);
  const detail = err && err.detail;
  let text = (err && err.message) || 'Something went wrong.';
  if (detail && typeof detail === 'object') {
    const why = Array.isArray(detail.why) ? detail.why.join(' ') : detail.why;
    text = [why, detail.said].filter(Boolean).join(' ') || text;
  }
  box.textContent = text;
  box.hidden = false;
}

function clearPrepareError(id) { const b = $(id); b.textContent = ''; b.hidden = true; }

function line(into, text, cls) {
  if (!text) return null;
  const p = document.createElement('p');
  if (cls) p.className = cls;
  p.textContent = text;
  into.appendChild(p);
  return p;
}

function bullets(into, heading, items) {
  if (!items || !items.length) return;
  const h = document.createElement('h3');
  h.className = 'section';
  h.textContent = heading;
  const ul = document.createElement('ul');
  ul.className = 'prep-list';
  items.forEach((t) => {
    const li = document.createElement('li');
    li.textContent = t;
    ul.appendChild(li);
  });
  into.append(h, ul);
}

async function loadPrepareMatters() {
  const sel = $('prepare-matter');
  const st = $('prepare-state');
  const keep = sel.value;
  let data;
  try {
    data = await api('/api/matters');
  } catch (err) {
    st.textContent = '';
    st.appendChild(stateBlock('loud',
      `The matter list could not be read: ${err.message}`));
    return;
  }
  const rows = data.matters || [];
  sel.textContent = '';
  const first = document.createElement('option');
  first.value = '';
  first.textContent = data.state !== 'ok'
    ? 'The matter list could not be read'
    : (rows.length ? 'Choose a matter…' : 'No matters yet');
  sel.appendChild(first);
  rows.forEach((m) => {
    const o = document.createElement('option');
    o.value = m.matter_id;
    // WHAT THE MATTER IS CALLED, NEVER ITS KEY. J-5. Where the list holds no
    // name, the option says so rather than falling back to the id: a fallback
    // is what makes a missing name invisible.
    o.textContent = m.matter || 'a matter with no name recorded';
    sel.appendChild(o);
  });
  const want = keep || state.matterId || '';
  if (want && rows.some((m) => m.matter_id === want)) {
    sel.value = want;
    await showPrepare(want);
  } else {
    await showPrepare('');
  }
}

async function showPrepare(matterId) {
  const mine = ++prepareGeneration;
  prepared.packageId = null; prepared.proposalId = null;
  prepared.packId = null; prepared.handoverId = null; prepared.digest = '';
  PREP_HOSTS.forEach((id) => { $(id).textContent = ''; });
  PREP_ERRORS.forEach(clearPrepareError);
  PREP_ON_DEMAND.forEach((id) => { $(id).hidden = true; });
  const st = $('prepare-state');
  st.textContent = '';
  if (!matterId) {
    st.appendChild(stateBlock('empty', 'Choose a matter to prepare.'));
    return;
  }
  let file;
  try {
    file = await api(`/api/matters/${encodeURIComponent(matterId)}/casefile`);
  } catch (err) {
    st.appendChild(stateBlock('loud',
      `This matter could not be read: ${err.message}`));
    return;
  }
  // THE GENERATION IS CHECKED AFTER THE AWAIT. An advocate who changes the
  // selection while a read is in flight must not have the older matter
  // painted over the newer one -- the shape BK-72 records for the rail.
  if (mine !== prepareGeneration) return;
  state.matterId = matterId;
  state.matterVersion = file.version;
  st.appendChild(stateBlock('empty',
    'Nothing on this screen has been filed, sent, offered or conceded.'));
}

function prepareVersion() { return state.matterVersion; }

/* --------------------------------------------------------- P29, package --- */

function renderPackage(pack) {
  const host = $('package-host');
  host.textContent = '';
  prepared.packageId = pack.package_id;
  const dl = document.createElement('dl');
  dl.className = 'r-fields';
  field(dl, 'Readiness',
        { pill: pack.readiness === 'ready_to_review' ? 'ok' : 'blocked',
          text: (pack.readiness || '').replace(/_/g, ' ') });
  host.appendChild(dl);
  // THE SENTENCE COMES FROM THE SERVER. If the product ever stopped refusing
  // to claim filing readiness, this screen would stop saying it does.
  line(host, pack.filing_note, 'prep-said');
  bullets(host, 'What is missing', pack.problems);
  bullets(host, 'Adverse material', pack.adverse);
  bullets(host, 'Reservations', pack.reservations);
  bullets(host, 'Instructions nobody has given', pack.missing_instructions);
  $('pk-export').hidden = false;
}

async function makePackage(ev) {
  ev.preventDefault();
  clearPrepareError('package-error');
  const matterId = $('prepare-matter').value;
  if (!matterId) {
    prepareError('package-error', new Error('Choose a matter first.'));
    return;
  }
  try {
    const out = await api('/api/drafting-packages', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        matter_id: matterId,
        document: $('pk-document').value.trim(),
        audience: $('pk-audience').value.trim(),
        purpose: $('pk-purpose').value.trim(),
        posture: $('pk-posture').value.trim(),
        cause_title: $('pk-court').value.trim()
          ? { court: $('pk-court').value.trim() } : {},
        theory_sentence: $('pk-theory').value.trim(),
        reliefs: $('pk-relief').value.trim() ? [$('pk-relief').value.trim()] : [],
        expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    renderPackage(out.package);
  } catch (err) { prepareError('package-error', err); }
}

async function exportPackage() {
  clearPrepareError('package-error');
  const matterId = $('prepare-matter').value;
  try {
    const out = await api(
      `/api/matters/${encodeURIComponent(matterId)}/drafting-packages/`
      + `${encodeURIComponent(prepared.packageId)}/export`);
    const ex = out.export || {};
    prepared.digest = ex.content_digest || '';
    const host = $('package-export');
    host.textContent = '';
    line(host, ex.filing_note, 'prep-said');
    bullets(host, 'Quotations nobody has checked', ex.unverified_quotations);
    if (ex.renditions) line(host, ex.renditions.why, 'prep-said');
  } catch (err) { prepareError('package-error', err); }
}

/* ---------------------------------------------------------- P30, action --- */

function renderAction(proposal, extra) {
  const host = $('action-host');
  host.textContent = '';
  prepared.proposalId = proposal.proposal_id;
  if (proposal.content_digest) prepared.digest = proposal.content_digest;
  const dl = document.createElement('dl');
  dl.className = 'r-fields';
  field(dl, 'Where this has got to',
        { pill: proposal.state === 'delivered' ? 'ok' : 'unknown',
          text: (proposal.state || '').replace(/_/g, ' ') });
  host.appendChild(dl);
  line(host, proposal.dispatch_note, 'prep-said');
  line(host, extra, 'prep-said');
  $('ac-confirm').hidden = false;
  $('ac-send').hidden = false;
  $('outcome-form').hidden = false;
  // RECONCILIATION IS OFFERED ONLY WHERE THERE IS SOMETHING TO RECONCILE, and
  // it is never hidden again once it is: an advocate who looked and found
  // nothing must be able to look again tomorrow.
  if (proposal.state === 'delivery_unknown') $('reconcile-form').hidden = false;
}

async function makeAction(ev) {
  ev.preventDefault();
  clearPrepareError('action-error');
  if (!prepared.packageId) {
    prepareError('action-error',
                 new Error('Prepare a drafting package first: an action needs '
                           + 'exact content to be about.'));
    return;
  }
  try {
    const out = await api('/api/action-proposals', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        matter_id: $('prepare-matter').value,
        package_id: prepared.packageId,
        authority: $('ac-authority').value.trim(),
        object: $('ac-object').value.trim(),
        destination: $('ac-destination').value.trim(),
        expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    renderAction(out.proposal);
  } catch (err) { prepareError('action-error', err); }
}

async function confirmAction() {
  clearPrepareError('action-error');
  try {
    const out = await api(
      `/api/action-proposals/${encodeURIComponent(prepared.proposalId)}`
      + '/confirmation', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matter_id: $('prepare-matter').value,
          content_digest: prepared.digest,
          expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    renderAction(out.proposal);
  } catch (err) { prepareError('action-error', err); }
}

async function trySend() {
  clearPrepareError('action-error');
  try {
    await api(
      `/api/action-proposals/${encodeURIComponent(prepared.proposalId)}`
      + '/execution', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matter_id: $('prepare-matter').value, content_digest: 'x',
          expected_matter_version: prepareVersion() }) });
  } catch (err) {
    // THE REFUSAL IS THE ANSWER, in the server's words rather than this
    // file's. A local string here would go on reassuring the advocate after
    // the day somebody wires a connector.
    prepareError('action-error', err);
  }
}

async function recordOutcome(ev) {
  ev.preventDefault();
  clearPrepareError('action-error');
  try {
    const out = await api(
      `/api/action-proposals/${encodeURIComponent(prepared.proposalId)}`
      + '/outcome', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matter_id: $('prepare-matter').value,
          state: $('oc-state').value,
          receipt: $('oc-receipt').value.trim(),
          because: $('oc-because').value.trim(),
          expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    renderAction(out.proposal);
  } catch (err) { prepareError('action-error', err); }
}

async function reconcileAction(ev) {
  ev.preventDefault();
  clearPrepareError('action-error');
  try {
    const out = await api(
      `/api/action-proposals/${encodeURIComponent(prepared.proposalId)}`
      + '/reconciliation', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matter_id: $('prepare-matter').value,
          basis: $('rc-basis').value.trim(),
          receipt: $('rc-receipt').value.trim(),
          expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    renderAction(out.proposal, out.resolved ? null
      : 'Still not known to have arrived. Nothing was sent again.');
  } catch (err) { prepareError('action-error', err); }
}

/* --------------------------------------------------------- P31, hearing --- */

function renderPack(pack) {
  const host = $('hearing-host');
  host.textContent = '';
  prepared.packId = pack.pack_id;
  Object.entries(pack.sections || {}).forEach(([name, text]) => {
    const h = document.createElement('h3');
    h.className = 'section';
    h.textContent = name.replace(/_/g, ' ');
    const p = document.createElement('p');
    p.textContent = text;
    host.append(h, p);
  });
  bullets(host, 'Nobody has assessed', pack.unassessed);
  bullets(host, 'Not yet fit to argue from', pack.blockers);
  line(host, pack.said, 'prep-said');
  $('witness-form').hidden = false;
  $('hp-incourt').hidden = false;
}

async function makePack() {
  clearPrepareError('hearing-error');
  if (!prepared.packageId) {
    prepareError('hearing-error',
                 new Error('Prepare a drafting package first: hearing '
                           + 'preparation is built from a verified package.'));
    return;
  }
  try {
    const out = await api('/api/hearing-packs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        matter_id: $('prepare-matter').value,
        package_id: prepared.packageId,
        expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    renderPack(out.pack);
  } catch (err) { prepareError('hearing-error', err); }
}

async function addWitness(ev) {
  ev.preventDefault();
  clearPrepareError('hearing-error');
  const topics = $('wt-topics').value.trim();
  try {
    const out = await api(
      `/api/hearing-packs/${encodeURIComponent(prepared.packId)}/witnesses`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matter_id: $('prepare-matter').value,
          witness: $('wt-witness').value.trim(),
          topics: topics ? [topics] : [],
          expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    renderPack(out.pack);
    const host = $('witness-host');
    host.textContent = '';
    bullets(host, 'What this plan still needs', out.problems);
  } catch (err) { prepareError('hearing-error', err); }
}

async function inCourt() {
  clearPrepareError('hearing-error');
  try {
    const out = await api(
      `/api/hearing-packs/${encodeURIComponent(prepared.packId)}/in-court`
      + `?matter_id=${encodeURIComponent($('prepare-matter').value)}`);
    const host = $('incourt-host');
    host.textContent = '';
    // THREE HEADINGS, NEVER ONE LIST. Under time pressure an advocate reads
    // the shortest thing in front of them, and a label inside a merged list
    // is not read at all.
    bullets(host, 'Verified — checked against its source', out.verified);
    bullets(host, 'Uncertain — analysis, not established', out.uncertain);
    bullets(host, 'Proposed — nobody has authorised this', out.proposed);
    line(host, out.concession_boundary, 'prep-said');
    line(host, out.said, 'prep-said');
  } catch (err) { prepareError('hearing-error', err); }
}

/* ------------------------------------------------------ P32, continuity --- */

async function reEntry() {
  clearPrepareError('continuity-error');
  const matterId = $('prepare-matter').value;
  if (!matterId) {
    prepareError('continuity-error', new Error('Choose a matter first.'));
    return;
  }
  try {
    const out = await api(
      `/api/matters/${encodeURIComponent(matterId)}/re-entry`);
    const host = $('continuity-host');
    host.textContent = '';
    line(host, `This matter is ${out.lifecycle}. The instruction on it is: `
               + `${out.instruction}`, 'prep-said');
    Object.entries(out.sections || {}).forEach(([name, text]) => {
      const h = document.createElement('h3');
      h.className = 'section';
      h.textContent = name.replace(/_/g, ' ');
      const p = document.createElement('p');
      p.textContent = text;
      host.append(h, p);
    });
    // UNASSESSED IS NAMED, never rendered as an empty section. BK-39-AC2: an
    // empty section reads as "there are none", and "nobody has looked" is a
    // different sentence the receiving advocate acts on differently.
    bullets(host, 'Nobody has looked at these', out.unassessed_sections);
    bullets(host, 'Check these again before working', out.reopen_checks);
    (out.handover_pending || []).forEach((h) => {
      line(host, `Offered to ${h.to_actor} and not yet accepted, so the `
                 + `outstanding work is still ${h.owner_of_outstanding}'s.`,
           'prep-said');
    });
    $('handover-form').hidden = false;
  } catch (err) { prepareError('continuity-error', err); }
}

async function offerHandover(ev) {
  ev.preventDefault();
  clearPrepareError('continuity-error');
  try {
    const out = await api('/api/handovers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        matter_id: $('prepare-matter').value,
        to_actor: $('ho-to').value.trim(),
        next_responsibility: $('ho-next').value.trim(),
        expected_matter_version: prepareVersion() }) });
    state.matterVersion = out.version;
    prepared.handoverId = out.handover.handover_id;
    const host = $('handover-host');
    host.textContent = '';
    line(host, out.handover.responsibility_moved
      ? 'Accepted, so responsibility has moved.'
      : 'Offered. Responsibility has NOT moved: it moves when they accept, and '
        + `until then the outstanding work is ${out.handover.owner_of_outstanding}'s.`,
      'prep-said');
    bullets(host, 'Travelling with the offer, unassessed',
            out.summary_unassessed);
  } catch (err) { prepareError('continuity-error', err); }
}


/* The handlers are bound ONCE, at load, against elements written in
 * `index.html`. Binding them inside a render would attach a second listener
 * every repaint, and the advocate would submit one form three times -- which
 * is the double-submit BK-42 asks about, arriving from our own side. */
$('prepare-matter').addEventListener('change', (e) => showPrepare(e.target.value));
$('package-form').addEventListener('submit', makePackage);
$('action-form').addEventListener('submit', makeAction);
$('pk-export').addEventListener('click', exportPackage);
$('ac-confirm').addEventListener('click', confirmAction);
$('ac-send').addEventListener('click', trySend);
$('outcome-form').addEventListener('submit', recordOutcome);
$('reconcile-form').addEventListener('submit', reconcileAction);
$('hp-make').addEventListener('click', makePack);
$('witness-form').addEventListener('submit', addWitness);
$('hp-incourt').addEventListener('click', inCourt);
$('re-entry').addEventListener('click', reEntry);
$('handover-form').addEventListener('submit', offerHandover);

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
  // P21. RESEARCH ON THE OPEN MATTER, when the advocate asked for it. The
  // same box, the same filters; what changes is that the round is RECORDED
  // on the file -- which index, what came back, what the adverse search did
  // -- and the results are cases the file can then read and attach from.
  if ($('r-on').checked) {
    await runResearchRound();
    return;
  }
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

/* ===================== P21 — RESEARCH ON THE MATTER =====================
 *
 * Finding is not verifying. A round of research surfaces CASES; a case is
 * opened to its paragraphs, read back by locator; a paragraph is attached to
 * the issue with its own words and comes back with five separate verdicts --
 * identity, quote, support, treatment, applicability -- none of which the
 * client computes and all of which it shows. The four outcomes of a search
 * are four different sentences, because a zero has four causes.
 */

const OUTCOME_SAID = {
  results: 'Results',
  searched_no_results: 'Searched — no case matched. This says what the index holds, not what the law is.',
  unsupported_coverage: 'Not searched — the court or jurisdiction asked for is outside what this corpus holds.',
  unavailable_index: 'Not searched — the index could not answer.',
};

function outcomeBlock(outcome, why) {
  const kind = outcome === 'results' ? 'quiet'
    : outcome === 'searched_no_results' ? 'quiet' : 'loud';
  const el = stateBlock(kind, `${OUTCOME_SAID[outcome] || outcome}${why ? ` ${why}` : ''}`);
  el.dataset.outcome = outcome;
  el.id = 'research-outcome';
  return el;
}

function researchEnabled() {
  const on = !!state.matterId;
  $('r-on').disabled = !on;
  if (!on) $('r-on').checked = false;
  $('research-fields').hidden = !$('r-on').checked;
  $('r-matter').textContent = on
    ? `on the open matter (v${state.matterVersion ?? '?'})`
    : 'open a matter to record research on it';
  loadResearchRecord();
}

// THE RECORD IS READ FROM THE FILE, not remembered by the page. Opening the
// pane on a matter shows the latest research need as the file holds it --
// rounds, adverse search, reliances -- so a reload, a second tab or a
// second day all show the same record. No matter open: the panel is hidden,
// which is a state and not an empty record.
async function loadResearchRecord() {
  const panel = $('research-record');
  if (!state.matterId) { panel.hidden = true; panel.textContent = ''; return; }
  let d;
  try {
    d = await api(`/api/matters/${state.matterId}/research`);
  } catch (err) {
    panel.hidden = false;
    panel.textContent = '';
    panel.appendChild(stateBlock('loud', `The research record could not be read: ${err.message}`));
    return;
  }
  const rows = d.research || [];
  if (!rows.length) { panel.hidden = true; panel.textContent = ''; return; }
  renderResearchRecord(rows[rows.length - 1]);
}

async function runResearchRound() {
  const st = $('search-state');
  const body = $('search-results');
  body.textContent = ''; st.textContent = '';
  $('search-index').hidden = true;
  const objective = $('r-objective').value.trim();
  const issue = $('r-issue').value.trim();
  if (!objective || !issue) {
    st.appendChild(stateBlock('loud', 'Say what this research is for and which issue it serves.'));
    return;
  }
  const payload = {
    objective, issue,
    query: $('q').value.trim(),
    citation: $('r-citation').value.trim(),
    expected_version: state.matterVersion,
  };
  const court = $('f-court').value.trim();
  const from = $('f-from').value.trim();
  const to = $('f-to').value.trim();
  if (court) payload.court = court;
  if (from) payload.from_year = Number(from);
  if (to) payload.to_year = Number(to);
  st.appendChild(stateBlock('quiet', 'Searching and recording…'));
  let out;
  try {
    out = await api(`/api/matters/${state.matterId}/research`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    st.textContent = '';
    const detail = err.detail || {};
    st.appendChild(stateBlock('loud',
      `The research round did not run: ${detail.why || err.message}. This says nothing about what the corpus holds.`));
    return;
  }
  state.matterVersion = out.version;
  st.textContent = '';
  st.appendChild(outcomeBlock(out.outcome, (out.discovery && out.discovery.why) || (out.resolution && out.resolution.why) || ''));
  if (out.discovery) {
    renderIndexLine(out.discovery);
    renderCases(out.research.id, out.discovery);
  } else if (out.resolution && out.resolution.case_id) {
    renderCases(out.research.id, { cases: [{
      case_id: out.resolution.case_id, case_name: `resolved from ${out.resolution.raw}`,
      court: '', year: null, paragraphs_matched: 0, snippet: '', origin: 'resolved',
      band: 'exact citation',
    }] });
  }
  renderResearchRecord(out.research);
}

function renderCases(researchId, discovery) {
  const body = $('search-results');
  const list = document.createElement('div');
  list.className = 'cases';
  list.id = 'research-cases';
  (discovery.cases || []).forEach((c) => {
    const card = document.createElement('article');
    card.className = 'case';
    card.dataset.caseId = c.case_id;
    const head = document.createElement('header');
    const name = document.createElement('span');
    name.className = 'hit-name'; name.textContent = c.case_name;
    const meta = document.createElement('span');
    meta.className = 'hit-meta';
    meta.textContent = `${c.court || ''}${c.year ? ` · ${c.year}` : ''}` +
      (c.paragraphs_matched ? ` · ${c.paragraphs_matched} paragraph${c.paragraphs_matched === 1 ? '' : 's'} matched` : '');
    const prov = document.createElement('span');
    prov.className = `pill ${c.origin === 'searched' ? 'searched' : 'resolved'}`;
    prov.textContent = `${c.origin} · ${c.band}`;
    head.append(name, meta, prov);
    const snippet = document.createElement('p');
    snippet.className = 'hit-text'; snippet.textContent = c.snippet || '';
    const open = document.createElement('button');
    open.type = 'button'; open.className = 'ghost open-case';
    open.textContent = 'Open the case';
    open.setAttribute('aria-label', `Open the case: ${c.case_name}`);
    const into = document.createElement('div');
    into.className = 'expansion';
    open.addEventListener('click', () => expandCase(researchId, c.case_id, into));
    card.append(head, snippet, open, into);
    list.appendChild(card);
  });
  body.appendChild(list);
}

async function expandCase(researchId, caseId, into) {
  into.textContent = '';
  into.appendChild(stateBlock('quiet', 'Reading the case back…'));
  let d;
  try {
    d = await api(`/api/matters/${state.matterId}/research/${researchId}/cases/${encodeURIComponent(caseId)}`);
  } catch (err) {
    into.textContent = '';
    into.appendChild(stateBlock('loud', `The case could not be read back: ${err.message}`));
    return;
  }
  into.textContent = '';
  if (d.coverage === 'not_assessed') {
    into.appendChild(stateBlock('loud', `NOT READ — ${d.why}`));
    return;
  }
  const cover = document.createElement('p');
  cover.className = 'case-cover';
  // THREE VALUES FOR COMPLETENESS, each its own sentence.
  const complete = d.complete === true ? 'every paragraph the source holds'
    : d.complete === false ? 'the attributable paragraphs only — facts and submissions are not here'
    : 'coverage of this case not measured';
  cover.textContent = `${d.paragraph_count} paragraph${d.paragraph_count === 1 ? '' : 's'} read back by locator · ${complete}` +
    (d.case ? ` · ${d.case.bench}` : '');
  into.appendChild(cover);
  (d.paragraphs || []).forEach((para) => {
    const row = document.createElement('div');
    row.className = 'para';
    row.dataset.locator = para.locator;
    const lab = document.createElement('div');
    lab.className = 'para-meta';
    lab.textContent = `${para.para_type} · ${para.locator} · ${para.origin}`;
    const text = document.createElement('p');
    text.className = 'para-text'; text.textContent = para.text;
    const attach = document.createElement('button');
    attach.type = 'button'; attach.className = 'ghost attach';
    attach.textContent = 'Attach to the issue';
    attach.setAttribute('aria-label', `Attach paragraph ${para.locator} to the issue`);
    const verdicts = document.createElement('div');
    verdicts.className = 'verdicts';
    attach.addEventListener('click', () => attachParagraph(researchId, para, verdicts));
    row.append(lab, text, attach, verdicts);
    into.appendChild(row);
  });
}

async function attachParagraph(researchId, para, verdicts) {
  verdicts.textContent = '';
  verdicts.appendChild(stateBlock('quiet', 'Attaching…'));
  let out;
  try {
    out = await api(`/api/matters/${state.matterId}/research/${researchId}/attach`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locator: para.locator, quote: para.text,
                             expected_version: state.matterVersion }),
    });
  } catch (err) {
    verdicts.textContent = '';
    const detail = err.detail || {};
    verdicts.appendChild(stateBlock('loud',
      `Not attached: ${detail.why || err.message}` +
      (detail.identity ? ` (identity: ${detail.identity}, quote: ${detail.quote_fidelity})` : '')));
    return;
  }
  state.matterVersion = out.version;
  verdicts.textContent = '';
  renderVerdicts(verdicts, out.reliance);
  renderResearchRecord(out.research);
}

// FIVE VERDICTS, FIVE ROWS. Never one word for all of them.
function renderVerdicts(into, a) {
  const dl = document.createElement('dl');
  dl.className = 'r-fields verdict-list';
  const pillFor = (v, good) => ({ pill: v === good ? 'ok' : v.includes('not_') ? 'unknown' : 'blocked', text: v });
  field(dl, 'identity', pillFor(a.identity, 'resolved'));
  field(dl, 'quote', pillFor(a.quote_fidelity, 'verbatim'));
  field(dl, 'support', pillFor(a.support, 'supports'));
  field(dl, 'treatment', { pill: a.treatment_state === 'clean' ? 'ok' : a.treatment_state === 'negative' ? 'blocked' : 'unknown', text: a.treatment_state });
  field(dl, 'applies here', pillFor(a.applicability, 'binding'));
  const note = document.createElement('p');
  note.className = 'verdict-note';
  note.textContent = `${a.verified_citation ? 'Verified citation — identity and words only.' : 'Not a verified citation.'} ` +
    `Support is ${a.support.replace(/_/g, ' ')}: nothing here reads meaning. ` +
    (a.treatment_scope ? `Treatment: ${a.treatment_scope} ` : '') +
    (a.applicability_because ? `Applicability: ${a.applicability_because}` : '');
  into.append(dl, note);
}

function renderResearchRecord(r) {
  const panel = $('research-record');
  panel.hidden = false;
  panel.textContent = '';
  panel.dataset.researchId = r.id;
  const h = document.createElement('h3');
  h.textContent = `Research record — ${r.objective}`;
  const dl = document.createElement('dl');
  dl.className = 'r-fields';
  field(dl, 'issue', r.issue);
  field(dl, 'rounds', `${r.rounds} of ${r.round_limit}${r.stopped_because ? ` — ${r.stopped_because}` : ''}`);
  field(dl, 'adverse search', { pill: r.clean_bill === 'clean' ? 'ok' : r.clean_bill === 'adverse_found' ? 'blocked' : 'unknown',
    text: r.clean_bill === 'not_assessed' ? 'not assessed — no clean bill can be given' : r.clean_bill });
  panel.append(h, dl);
  (r.consulted || []).forEach((c) => {
    const li = document.createElement('div');
    li.className = 'consulted';
    li.textContent = `${c.index} — ${c.query} → ${c.outcome}` +
      (c.corpus_version ? ` · corpus ${c.corpus_version}` : '') +
      (c.court_read_as ? ` · ${c.court_read_as}` : '') +
      (c.held != null && c.of_source != null ? ` · ${c.held} of ${c.of_source} paragraphs held` : '');
    panel.appendChild(li);
  });
  (r.adverse || []).forEach((a) => {
    const li = document.createElement('div');
    li.className = 'adverse';
    li.textContent = `adverse search ${a.state}: ${a.target}` +
      (a.found && a.found.length ? ` — negative treatment found for ${a.found.join(', ')}` : '') +
      (a.why ? ` — ${a.why}` : '');
    panel.appendChild(li);
  });
  (r.reliances || []).forEach((a) => {
    const li = document.createElement('div');
    li.className = 'attached';
    li.dataset.locator = a.locator;
    li.textContent = `attached to ${a.issue}: ${a.locator} — identity ${a.identity}, quote ${a.quote_fidelity}, ` +
      `support ${a.support}, treatment ${a.treatment_state}, applies ${a.applicability}` +
      (a.source_version ? ` · source ${a.source_version}` : '');
    panel.appendChild(li);
  });
}

$('r-on').addEventListener('change', researchEnabled);

/* ============================ THE RECORD =============================
 *
 * Read back from the encrypted transcript store. An unreadable turn is
 * COUNTED and named rather than skipped: a review that renders nine of ten
 * turns and calls itself complete is reviewing a different conversation from
 * the one that ran.
 */

/* ===================== P17/P18 — THE CASE FILE =====================
 *
 * Renders what `/api/matters/{id}/casefile` and `/dependencies` say and adds
 * nothing. The one write on this pane is a CORRECTION, and it goes with the
 * version this pane read -- a file that moved under the advocate is refused
 * by the server with both versions, and the pane re-reads rather than retries.
 */

async function loadCasefileMatters() {
  const sel = $('casefile-matter');
  const st = $('casefile-state');
  try {
    const d = await api('/api/matters');
    const rows = d.matters || [];
    const held = sel.value;
    sel.textContent = '';
    const first = document.createElement('option');
    first.value = '';
    first.textContent = d.state !== 'ok'
      ? 'The matter list could not be read'
      : (rows.length ? 'Choose a matter…' : 'No matters yet');
    sel.appendChild(first);
    rows.forEach((m) => {
      const o = document.createElement('option');
      o.value = m.matter_id;
      o.textContent = m.matter || m.matter_id;
      sel.appendChild(o);
    });
    // THE FILE THE ADVOCATE IS IN, unless they chose another. A pane that
    // opens on "Choose a matter" over the matter they are working is a
    // pane that asks them what they just told it.
    const want = held || state.matterId || '';
    if (want && rows.some((m) => m.matter_id === want)) {
      sel.value = want;
      await showCasefile(want);
    }
  } catch (err) {
    st.textContent = '';
    st.appendChild(stateBlock('loud',
      `The matter list could not be read: ${err.message}`));
  }
}

async function showCasefile(matterId) {
  const generation = ++state.casefileGeneration;
  const st = $('casefile-state');
  const entries = $('casefile-entries');
  if (!matterId) {
    st.textContent = '';
    entries.replaceChildren();
    delete entries.dataset.matterId;
    renderCurrency(null);
    return;
  }

  let file; let deps;
  try {
    [file, deps] = await Promise.all([
      api(`/api/matters/${matterId}/casefile`),
      api(`/api/matters/${matterId}/dependencies`),
    ]);
  } catch (err) {
    if (generation !== state.casefileGeneration) return;
    st.textContent = '';
    st.appendChild(stateBlock('loud', `The case file could not be read: ${err.message}`));
    // Never leave a different matter under this error. When the failed read
    // was a refresh of the same file, retain its last coherent snapshot so a
    // transient failure does not erase the advocate's record from the glass.
    if (entries.dataset.matterId !== matterId) {
      entries.replaceChildren();
      delete entries.dataset.matterId;
      renderCurrency(null);
    }
    return;
  }
  if (generation !== state.casefileGeneration) return;

  // Build the entry population off-DOM, then publish entries before currency.
  // A consumer waiting on the currency pill can therefore never observe a
  // new dependency state beside an old or temporarily empty source record.
  const nextEntries = document.createDocumentFragment();
  const live = new Set((file.live || []).map((e) => e.fact_id));
  (file.entries || []).forEach((e) => {
    nextEntries.appendChild(
      renderEntry(matterId, e, live.has(e.fact_id), file.version));
  });
  if (!(file.entries || []).length) {
    nextEntries.appendChild(
      stateBlock('empty', 'Nothing has been recorded on this file yet.'));
  }

  st.textContent = '';
  if (file.state !== 'ok') {
    st.appendChild(stateBlock('loud', `The case file is ${file.state}.`));
  }
  entries.replaceChildren(nextEntries);
  entries.dataset.matterId = matterId;
  renderCurrency(deps);
  try {
    const cover = await api(`/api/matters/${matterId}/cover`);
    if (generation !== state.casefileGeneration) return;
    renderPremises(matterId, cover.premises, file.version);
    renderRelief(matterId, cover.relief, file.version);
    renderBriefingPane(matterId, cover.briefing, file.version);
    await renderBindings(matterId, file.version);
    await renderDecisions(matterId, file.version);
    await renderRetention(matterId, file.version);
  } catch (err) {
    $('premises').hidden = false;
    $('premises-state').textContent = '';
    $('premises-state').appendChild(stateBlock('loud',
      `The legal premises could not be read: ${err.message}`));
  }
}

// P22. THE LEGAL PREMISES, per thread, with a Confirm control for one the
// product INFERRED. The state pill is `established`, `conditional`,
// `inconsistent` or `not assessed` -- never a blank that reads as settled.
// Confirming an inferred accrual states it and the next brief makes the date
// a deadline; the control posts to the premise route and re-reads the file.
function renderPremises(matterId, prem, version) {
  const panel = $('premises');
  const stateEl = $('premises-state');
  const body = $('premises-threads');
  stateEl.textContent = ''; body.textContent = '';
  if (!prem || prem.state === 'not_assessed') { panel.hidden = true; return; }
  panel.hidden = false;

  const pill = document.createElement('span');
  pill.className = 'pill ' + (prem.state === 'established' ? 'ok'
    : prem.state === 'inconsistent' ? 'blocked' : 'unknown');
  pill.textContent = prem.state === 'established' ? 'established'
    : prem.state === 'inconsistent' ? 'INCONSISTENT'
    : prem.state === 'conditional' ? 'conditional' : prem.state;
  pill.dataset.premises = prem.state;
  const said = document.createElement('span');
  said.className = 'currency-said'; said.textContent = ' ' + (prem.said || '');
  stateEl.append(pill, said);

  (prem.threads || []).forEach((t) => {
    const card = document.createElement('div');
    card.className = 'premise-thread';
    card.dataset.threadId = t.thread_id;
    const h = document.createElement('h4'); h.textContent = t.thread;
    card.appendChild(h);
    (t.premises || []).forEach((p) => {
      const row = document.createElement('div');
      row.className = 'premise-row';
      row.dataset.kind = p.kind;
      const dl = document.createElement('dl'); dl.className = 'r-fields';
      field(dl, p.kind.replace(/_/g, ' '), p.statement || '—');
      field(dl, 'basis', {
        pill: p.basis === 'stated' ? 'ok' : p.basis === 'inferred' ? 'unknown' : 'searched',
        text: p.basis });
      field(dl, 'review', p.review_state === 'reviewed'
        ? `reviewed by ${p.reviewed_by}` : 'not assessed');
      row.appendChild(dl);
      if (p.basis === 'inferred') {
        (p.alternatives || []).forEach((a) => {
          const alt = document.createElement('div');
          alt.className = 'premise-alt'; alt.textContent = `alternative: ${a}`;
          row.appendChild(alt);
        });
        row.appendChild(premiseForm(matterId, t.thread_id, p.kind, version));
      }
      card.appendChild(row);
    });
    body.appendChild(card);
  });
}

function premiseForm(matterId, threadId, kind, version) {
  const form = document.createElement('form');
  form.className = 'premise-confirm';
  const lab = document.createElement('label');
  lab.htmlFor = `prem-${threadId}-${kind}`;
  lab.textContent = 'State it (and I will compute a deadline from it) ';
  const inp = document.createElement('input');
  inp.id = `prem-${threadId}-${kind}`; inp.name = 'statement';
  inp.placeholder = 'e.g. time runs from the date fixed for repayment';
  const go = document.createElement('button');
  go.type = 'submit'; go.className = 'primary'; go.textContent = 'Confirm premise';
  const stateEl = document.createElement('span'); stateEl.className = 'hint premise-state';
  form.append(lab, inp, go, stateEl);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const statement = inp.value.trim();
    if (!statement) { stateEl.textContent = 'Say what the premise is.'; return; }
    stateEl.textContent = 'Recording…';
    try {
      const out = await api(`/api/matters/${matterId}/threads/${threadId}/premises/${kind}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ statement, source: 'the advocate', expected_version: version }),
      });
      if (state.matterId === matterId) state.matterVersion = out.version;
      stateEl.textContent = 'Recorded. Brief me again and the date becomes a deadline.';
      await showCasefile(matterId);
    } catch (err) {
      const detail = err.detail || {};
      stateEl.textContent = detail.why || err.message;
      if (detail.code === 'STALE_VERSION') await showCasefile(matterId);
    }
  });
  return form;
}

// P23. RELIEF AND ENFORCEABILITY, per thread. The state pill is `serveable`,
// `no useful relief` or `not assessed` -- and a disproportionate route is shown
// ALONGSIDE, never hidden (E3). The form states a remedy's coordinates; the
// next brief re-reads them and the recommendation changes when the relief is
// unavailable, hollow, late or unenforceable. The panel stays visible so the
// advocate can state relief even before anything has been assessed.
const RELIEF_COORDS = {
  availability: ['not_assessed', 'available', 'unavailable'],
  value: ['not_assessed', 'substantial', 'hollow'],
  timing: ['not_assessed', 'timely', 'late'],
  enforceability: ['not_assessed', 'enforceable', 'unenforceable'],
  proportionality: ['not_assessed', 'proportionate', 'disproportionate'],
};

function renderRelief(matterId, rel, version) {
  const panel = $('relief');
  const stateEl = $('relief-state');
  const body = $('relief-threads');
  stateEl.textContent = ''; body.textContent = '';
  if (!rel || !(rel.threads || []).length) { panel.hidden = true; return; }
  panel.hidden = false;

  const pill = document.createElement('span');
  pill.className = 'pill ' + (rel.state === 'serveable' ? 'ok'
    : rel.state === 'no_useful_relief' ? 'blocked' : 'unknown');
  pill.textContent = rel.state === 'no_useful_relief' ? 'no useful relief'
    : rel.state;
  pill.dataset.relief = rel.state;
  const said = document.createElement('span');
  said.className = 'currency-said'; said.textContent = ' ' + (rel.said || '');
  stateEl.append(pill, said);

  (rel.threads || []).forEach((t) => {
    const card = document.createElement('div');
    card.className = 'premise-thread'; card.dataset.threadId = t.thread_id;
    const h = document.createElement('h4');
    h.textContent = t.thread
      + (t.objective ? ` — objective: ${t.objective.statement} (${t.objective.basis})` : '');
    card.appendChild(h);

    if (t.state === 'not_assessed') {
      card.appendChild(stateBlock('empty',
        'No relief has been assessed on this thread yet.'));
    }
    (t.reliefs || []).forEach((r) => {
      const row = document.createElement('div');
      row.className = 'premise-row'; row.dataset.remedy = r.remedy;
      const dl = document.createElement('dl'); dl.className = 'r-fields';
      field(dl, 'remedy', r.remedy);
      ['availability', 'value', 'timing', 'enforceability', 'proportionality']
        .forEach((c) => field(dl, c, {
          pill: (r[c] === 'available' || r[c] === 'substantial'
                 || r[c] === 'timely' || r[c] === 'enforceable'
                 || r[c] === 'proportionate') ? 'ok'
            : r[c] === 'not_assessed' ? 'searched' : 'blocked',
          text: r[c].replace(/_/g, ' ') }));
      field(dl, 'basis', { pill: r.basis === 'stated' ? 'ok'
        : r.basis === 'inferred' ? 'unknown' : 'searched', text: r.basis });
      if (r.reason) field(dl, 'reason', r.reason);
      row.appendChild(dl);
      card.appendChild(row);
    });
    (t.disproportionate || []).forEach((d) => {
      const alt = document.createElement('div');
      alt.className = 'premise-alt';
      alt.textContent = `cost against recovery: ${d.remedy} — ${d.why} (stated alongside, not withheld)`;
      card.appendChild(alt);
    });
    card.appendChild(reliefForm(matterId, t.thread_id, version));
    body.appendChild(card);
  });
}

function reliefForm(matterId, threadId, version) {
  const form = document.createElement('form');
  form.className = 'premise-confirm relief-confirm';
  const remedy = document.createElement('input');
  remedy.name = 'remedy'; remedy.placeholder = 'remedy, e.g. a money decree';
  const objective = document.createElement('input');
  objective.name = 'objective'; objective.placeholder = 'objective (optional)';
  const selects = {};
  Object.entries(RELIEF_COORDS).forEach(([name, opts]) => {
    const sel = document.createElement('select'); sel.name = name;
    opts.forEach((o) => {
      const opt = document.createElement('option');
      opt.value = o; opt.textContent = `${name}: ${o.replace(/_/g, ' ')}`;
      sel.appendChild(opt);
    });
    selects[name] = sel;
  });
  const reason = document.createElement('input');
  reason.name = 'reason'; reason.placeholder = 'why (optional)';
  const go = document.createElement('button');
  go.type = 'submit'; go.className = 'primary'; go.textContent = 'State relief';
  const stateEl = document.createElement('span');
  stateEl.className = 'hint premise-state';
  form.append(remedy, objective, ...Object.values(selects), reason, go, stateEl);
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!remedy.value.trim()) { stateEl.textContent = 'Name the remedy.'; return; }
    stateEl.textContent = 'Recording…';
    const payload = {
      remedy: remedy.value.trim(), objective: objective.value.trim(),
      reason: reason.value.trim(), source: 'the advocate',
      expected_version: version,
    };
    Object.keys(RELIEF_COORDS).forEach((c) => { payload[c] = selects[c].value; });
    try {
      const out = await api(`/api/matters/${matterId}/threads/${threadId}/relief`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (state.matterId === matterId) state.matterVersion = out.version;
      stateEl.textContent = 'Recorded. Brief me again and the recommendation weighs it.';
      await showCasefile(matterId);
    } catch (err) {
      const detail = err.detail || {};
      stateEl.textContent = detail.why || err.message;
      if (detail.code === 'STALE_VERSION') await showCasefile(matterId);
    }
  });
  return form;
}

// P18. THE CURRENCY BLOCK. Three states at the top and the third is a file
// with no ledger: `not assessed` is rendered as a value, never as a clean
// sheet, because an empty list of stale conclusions is not a certificate.
function renderCurrency(deps) {
  const stateEl = $('currency-state');
  const staleEl = $('currency-stale');
  const nodesEl = $('currency-nodes');
  const histEl = $('currency-history');
  stateEl.textContent = ''; staleEl.textContent = '';
  nodesEl.textContent = ''; histEl.textContent = '';
  if (!deps) return;

  const pill = document.createElement('span');
  pill.className = 'pill ' + (deps.state === 'current' ? 'ok'
    : deps.state === 'stale' ? 'blocked' : 'unknown');
  pill.textContent = deps.state === 'current' ? 'current'
    : deps.state === 'stale' ? 'NOT CURRENT' : 'not assessed';
  pill.dataset.currency = deps.state;
  const said = document.createElement('span');
  said.className = 'currency-said';
  said.textContent = ' ' + (deps.said || '');
  stateEl.append(pill, said);

  (deps.stale || []).forEach((n) => {
    const li = document.createElement('li');
    li.className = 'stale-node';
    li.dataset.node = n.name;
    const strong = document.createElement('strong');
    strong.textContent = n.shown || n.name;
    li.append(strong, document.createTextNode(
      ` — ${n.currency}: ${n.because}` +
      (n.value ? ` It read ${n.value}.` : '') +
      (n.rework_exhausted ? ' No further recomputation is scheduled.' : '')));
    staleEl.appendChild(li);
  });

  (deps.nodes || []).forEach((n) => {
    const row = document.createElement('div');
    row.className = 'node-row';
    row.dataset.node = n.name;
    row.dataset.currency = n.currency;
    const dl = document.createElement('dl'); dl.className = 'r-fields';
    field(dl, 'conclusion', n.shown || n.name);
    field(dl, 'value', n.value || '—');
    field(dl, 'currency', {
      pill: n.currency === 'current' ? 'ok' : n.currency === 'stale' ? 'blocked' : 'unknown',
      text: n.currency,
    });
    field(dl, 'rests on', (n.rests_on || []).map((r) => `${r.kind} ${r.id} v${r.version}`).join('; ') || 'nothing recorded');
    row.appendChild(dl);
    nodesEl.appendChild(row);
  });

  (deps.history || []).forEach((h) => {
    const row = document.createElement('div');
    row.className = 'revision';
    row.dataset.node = h.name;
    row.textContent =
      `${h.at || ''} — ${h.name}: was ${h.was || '—'}` +
      (h.now ? `, now ${h.now}` : ', not yet recomputed') +
      ` — ${h.reason || ''}`;
    histEl.appendChild(row);
  });
}

function renderEntry(matterId, e, isLive, version) {
  const row = document.createElement('div');
  row.className = 'entry' + (isLive ? '' : ' superseded');
  row.dataset.factId = e.fact_id;
  const text = document.createElement('div');
  text.className = 'entry-text';
  text.textContent = e.statement;
  const meta = document.createElement('div');
  meta.className = 'entry-meta';
  const bits = [e.date ? `dated ${e.date}` : 'undated', e.certainty, e.confirmed,
                e.attribution && e.attribution.said];
  if (e.superseded_by) bits.push(`superseded by ${e.superseded_by}`);
  meta.textContent = bits.filter(Boolean).join(' · ');
  row.append(text, meta);

  if (isLive) {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ghost correct';
    btn.textContent = 'Correct';
    btn.setAttribute('aria-label', `Correct: ${e.statement.slice(0, 60)}`);
    btn.addEventListener('click', () => {
      if (row.querySelector('form')) return;
      row.appendChild(correctionForm(matterId, e, version));
    });
    row.appendChild(btn);
  }
  return row;
}

function correctionForm(matterId, e, version) {
  const form = document.createElement('form');
  form.className = 'correction';
  const id = e.fact_id.replace(/[^a-zA-Z0-9_-]/g, '');
  const mk = (name, label, opt, type) => {
    const lab = document.createElement('label');
    lab.htmlFor = `corr-${name}-${id}`;
    lab.textContent = label + ' ';
    if (opt) {
      const o = document.createElement('span'); o.className = 'opt'; o.textContent = opt;
      lab.appendChild(o);
    }
    const inp = document.createElement('input');
    inp.name = name; inp.id = `corr-${name}-${id}`;
    if (type) inp.type = type;
    return [lab, inp];
  };
  const [l1, statement] = mk('statement', 'Corrected wording', '— leave blank to keep the words');
  statement.placeholder = e.statement.slice(0, 80);
  const [l2, date] = mk('date', 'Corrected date', '— or blank to keep it', 'date');
  const [l3, reason] = mk('reason', 'Why it changes', '');
  reason.required = true;
  reason.placeholder = 'the invoice is dated 2019, not 2023';
  const rowEl = document.createElement('div'); rowEl.className = 'composer-row';
  const stateEl = document.createElement('span'); stateEl.className = 'hint correction-state';
  const go = document.createElement('button'); go.type = 'submit'; go.className = 'primary';
  go.textContent = 'Record the correction';
  rowEl.append(stateEl, go);
  form.append(l1, statement, l2, date, l3, reason, rowEl);

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const why = reason.value.trim();
    if (!why) { stateEl.textContent = 'Say why it changes.'; return; }
    const body = { reason: why, expected_version: version };
    if (statement.value.trim()) body.statement = statement.value.trim();
    if (date.value) body.date = date.value;
    stateEl.textContent = 'Recording…';
    let out;
    try {
      out = await api(`/api/matters/${matterId}/facts/${e.fact_id}/corrections`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch (err) {
      // A REFUSAL IS SHOWN AS ONE, with what the server said. A file that
      // moved is re-read; nothing is retried on the advocate's behalf.
      const detail = err.detail || {};
      stateEl.textContent = detail.why || err.message;
      if (detail.code === 'STALE_VERSION') await showCasefile(matterId);
      return;
    }
    stateEl.textContent =
      `Recorded. Not current until reworked: ${(out.affected || []).length}; ` +
      `left alone: ${(out.unaffected || []).length}.`;
    if (state.matterId === matterId) state.matterVersion = out.version;
    await showCasefile(matterId);
    // THE BOARD SAYS SO TOO, if it is the file that is open.
    if (state.matterId === matterId) {
      showThreadBoard(matterId, { restore: false, closeNavigator: false });
    }
  });
  return form;
}

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
    // OPENED FROM A MATTER, IT OPENS ON THAT MATTER (F-A-17). History is
    // reached from inside My work, for the matter that is open there.
    if (state.matterId && rows.some((m) => m.matter_id === state.matterId)) {
      sel.value = state.matterId;
      showHistory(state.matterId);
    }
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
$('casefile-matter').addEventListener('change', (ev) => showCasefile(ev.target.value));

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
  document.cookie = 'nm_retirement=; Path=/; Max-Age=0; SameSite=Strict';
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
  // F-A-17. THE NAME THE ACCOUNT HOLDS, or its email while it has none: never
  // blank, and never anything this page made up.
  const shownName = advocate.name || advocate.email || advocate.id;
  $('who-name').textContent = shownName;
  $('profile-name').textContent = shownName;
  $('profile-email').textContent = advocate.email || 'Not recorded';
  $('who-detail').textContent = [advocate.enrolment, advocate.practice]
    .filter(Boolean).join(' · ') || 'Not recorded yet';
  $('professional-approval').textContent = professionalApproval?.state === 'approved'
    ? 'Professional profile approved' : 'Professional profile not approved';
  $('workspace-name').textContent = workspace.label;
  $('profile-workspace').textContent = workspace.label;
  $('gate').hidden = true;
  $('masthead').hidden = false;
  state.ended = false;
  // F-A-18. A SIGN-IN LANDS ON HOME -- unless it follows a session that ended
  // part-way through a brief, which goes straight back to that brief.
  const draftWaiting = Boolean(state.draft && state.draft.advocate === advocate.id
    && state.draft.workspace === workspace.id);
  // A brief interrupted in a saved matter returns under My work; one
  // interrupted before its matter was saved returns under Home (F-B).
  if (draftWaiting) state.workTab = state.draft.matterId ? 'advise' : 'home';
  showTab(draftWaiting ? 'advise' : 'home');
  loadHealth();
  showMatterList();

  // Restore the entire original intent, not a new instruction made from its
  // text. Transcript reconciliation may confirm a turn whose acknowledgement
  // was lost; unavailable read-back retains its exact retry envelope.
  if (draftWaiting) {
    const draft = state.draft;
    if (draft.matterId) showThreadBoard(draft.matterId);
    else startMatter();
  }
  state.draft = null;
  draftUnlock = unlockDrafts();
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

// THE RESET LINK OPENS THIS PAGE with `#reset=<token>`. Taken once, then
// removed from the address, before anything else on the page can read it.
function takeResetToken() {
  const match = window.location.hash.match(/^#reset=([A-Za-z0-9_-]+)$/);
  if (!match) return false;
  resetToken = match[1];
  history.replaceState(null, '', window.location.pathname + window.location.search);
  return true;
}

function openReset() {
  showGate(null);
  showForm('reset');
  $('reset-password').focus();
}

window.addEventListener('hashchange', () => {
  if (takeResetToken()) openReset();
});

async function boot() {
  checkBuild();
  if (takeResetToken()) {
    openReset();
    return;
  }
  if (cookie('nm_retirement') === 'pending') {
    state.signOut = 'unconfirmed';
    const token = {session:state.sessionGeneration, accepting:true, task:null, online:null};
    retiringSession = token;
    unconfirmedRetirement(token);
    return;
  }
  try {
    const me = await api('/api/session');
    showApplication(me.advocate, me.workspace, me.professional_approval);
    startIdleWatch(me.session_idle_minutes, me.access_window);
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
    // THE PASSWORD LEAVES THE PAGE, masked again. It stays in the DOM
    // otherwise, readable by anything running later on this document.
    concealPasswords(['login-password']);
    showApplication(r.advocate, r.workspace, r.professional_approval);
    startIdleWatch(r.session_idle_minutes, r.access_window);
  } catch (err) {
    concealPasswords(['login-password']);
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
      document.cookie = 'nm_retirement=; Path=/; Max-Age=0; SameSite=Strict';
      forgetRetirement();
      state.ended = false;
      showGate(null);
      $('login-state').appendChild(stateBlock('quiet',
        'The session is now closed on the server.'));
      if (token.localWarning) $('login-state').appendChild(stateBlock('loud', token.localWarning));
    } catch {
      unconfirmedRetirement(token);
    }
  })();
  try { await token.task; }
  finally { token.task = null; }
}

async function signOut() {
  const generation = state.sessionGeneration;
  await draftUnlock;
  if (generation !== state.sessionGeneration || !state.advocate) return;
  snapshotIntent();
  if ((storedDraftCount || [...intentContexts.values()].some(draftHasWork))
      && !window.confirm('Sign out and discard this account’s unsent drafts on this device? Saved matters are not deleted.')) return;
  const btn = $('signout');
  btn.disabled = true;
  // A non-secret refusal marker survives reload and browser closure. It can
  // only restrict this device; it is never authentication or proof of logout.
  document.cookie = 'nm_retirement=pending; Path=/; Max-Age=43200; SameSite=Strict';
  let localWarning = '';
  try {
    if (!draftVault?.key) throw new Error('Draft protection was not opened.');
    draftVault.discard();
    storedDraftCount = 0;
  } catch {
    localWarning = 'Draft removal could not be confirmed. Clear this site’s browser data before leaving a shared device.';
  }
  state.draft = null;
  intentContexts.clear();
  clearPrivileged();
  forgetRetirement();
  state.signOut = 'signing_out';
  const token = { session: state.sessionGeneration, accepting: true, task: null, online: null,
    localWarning };
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
['message', ...INTAKE_INPUTS, 'in-capacity'].forEach(id => {
  $(id).addEventListener('input', () => snapshotIntent({edited:true}));
});

$('message').addEventListener('input', sizeComposer);
$('draft-open').addEventListener('click', openDraftRecovery);
$('workspace-menu').addEventListener('click', event => {
  if (event.target.closest('button')) $('workspace-more').open = false;
});
$('draft-close').addEventListener('click', closeDraftRecovery);
$('draft-dialog').addEventListener('cancel', (event) => {
  event.preventDefault(); closeDraftRecovery();
});
$('jump-latest').addEventListener('click', () => {
  $('thread').scrollTop = $('thread').scrollHeight;
  $('jump-latest').hidden = true;
});

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
    const when = new Date(s.issued_at).toLocaleString();
    const label = s.this_one ? 'This device'
      : (s.live ? 'Another signed-in session' : `Ended — ${s.ended_because || 'reason unavailable'}`);
    const row = document.createElement('article');
    row.className = 'session-row';
    const title = document.createElement('strong'); title.textContent = label;
    const detail = document.createElement('p');
    detail.textContent = `${s.client_label}. Started ${when}. `
      + `Last active ${new Date(s.last_active_at).toLocaleString()}. Connection source: ${s.source}.`;
    row.append(title, detail);
    if (s.live && !s.this_one) {
      const end = document.createElement('button');
      end.type = 'button'; end.className = 'ghost'; end.textContent = 'End this session';
      end.addEventListener('click', async () => {
        end.disabled = true;
        try {
          await api('/api/sessions/revoke-one', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({reference:s.reference})});
          if (generation !== state.sessionsGeneration || !dialog.open) return;
          await showSessions();
        } catch (error) {
          if (!error.obsolete && generation === state.sessionsGeneration) {
            $('sessions-action-state').textContent = `Closure was not confirmed: ${error.message}`;
          }
        } finally { end.disabled = false; }
      });
      row.appendChild(end);
    }
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

// F-A-17. THE PERSON MENU. Opens and closes from its button; closes on Escape,
// on a click anywhere else, when a control inside it is used, and when the
// session ends (`clearPrivileged`).
function setAccountMenu(open) {
  $('account-panel').hidden = !open;
  $('account-toggle').setAttribute('aria-expanded', open ? 'true' : 'false');
}

$('account-toggle').addEventListener('click', () => {
  setAccountMenu($('account-panel').hidden);
});
document.addEventListener('click', (ev) => {
  if (!$('account-panel').hidden && !$('account-menu').contains(ev.target)) {
    setAccountMenu(false);
  }
});
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && !$('account-panel').hidden) {
    setAccountMenu(false);
    $('account-toggle').focus();
  }
});
$('devices').addEventListener('click', () => setAccountMenu(false));

// ------------------------------------------------------------- registration
//
// SELF-SERVICE, as of 6 September 2026. The sign-in page used to say enrolment
// was not, and pointed at a tool an advocate cannot run.
//
// TWO FORMS, NOT ONE IN TWO MODES. A single form that changes meaning by a
// flag is one where a mis-set flag posts a password to the wrong route.
function showForm(which) {
  // A pending account creation owns its result. Do not let public
  // navigation hand that result to a different form/person.
  if (registrationInFlight && which !== 'register') return;
  if (confirmationInFlight && which !== 'confirm-email') return;
  // Keep the non-secret email for corrections, never a hidden credential. A
  // PASSWORD IS NOT FORM STATE: a card that is merely hidden keeps its values,
  // and the next person on this machine would return to a filled form.
  if (which !== 'register') clearRegistrationPasswords();
  if (which !== 'reset') clearResetPasswords();
  // LEAVING THE SIGN-IN CARD PUTS ITS PASSWORD AWAY (F-A-10), shown or not.
  if (which !== 'login') concealPasswords(['login-password']);
  if (which !== 'confirm-email') {
    concealPasswords(['confirm-password', 'confirm-password2']);
    $('confirm-code').value = '';
  }
  $('login').hidden = which !== 'login';
  $('register').hidden = which !== 'register';
  $('forgot').hidden = which !== 'forgot';
  $('reset').hidden = which !== 'reset';
  $('outcome').hidden = which !== 'outcome';
  $('confirm-email').hidden = which !== 'confirm-email';
  $('login-state').textContent = '';
  if (which === 'register') loadAccountCapabilities();
}

// ONE WAY A PASSWORD IS PUT AWAY, for every card that has one (F-A-10). The
// value goes, the field is masked again and its eye says so -- so no card can
// be left showing a password to whoever uses this screen next. It was written
// twice, once per card, and the sign-in card would have been the third copy.
function concealPasswords(ids) {
  for (const id of ids) {
    const field = $(id);
    field.value = '';
    field.type = 'password';
    const eye = document.querySelector(`.pw-eye[data-for="${id}"]`);
    if (eye) eye.setAttribute('aria-pressed', 'false');
  }
}

function clearRegistrationPasswords() {
  concealPasswords(['reg-password', 'reg-password2']);
}

function clearResetPasswords() {
  concealPasswords(['reset-password', 'reset-password2']);
}

// THE TWO BOXES ARE READ AT THE MOMENT OF SENDING, with the version of the
// notice this page is showing. Implementation Plan F-A-09.
function consentGiven() {
  return {
    notice_version: $('privacy-notice').dataset.noticeVersion,
    agreed: $('reg-consent').checked,
    adult: $('reg-adult').checked,
    external_ai: $('reg-external-ai').checked,
    external_ai_notice_version: $('reg-external-ai').checked
      ? $('openai-text-notice').dataset.noticeVersion : null,
  };
}

// REGISTER WAITS FOR BOTH BOXES. The server refuses without them too; this is
// so nobody presses a button that can only be refused.
function syncRegisterReady() {
  if (registrationInFlight) return;
  $('register-go').disabled = !(registrationCapabilities?.public_registration
    && $('reg-consent').checked && $('reg-adult').checked);
}

async function loadAccountCapabilities() {
  registrationCapabilities = null;
  syncRegisterReady();
  try {
    registrationCapabilities = await api('/api/account-capabilities');
    $('registration-availability').textContent = !registrationCapabilities.public_registration
      ? 'New registration is unavailable while email delivery is disabled. Existing accounts can still sign in.'
      : registrationCapabilities.mail_delivery === 'local_outbox_only'
        ? 'Local rehearsal only: messages stay in the protected test outbox. No email will be sent.'
        : 'Register, confirm your email with a six-digit code, then sign in.';
  } catch (_) {
    $('registration-availability').textContent = 'Registration availability could not be checked. Try again later.';
  }
  syncRegisterReady();
}

function showConfirmation(email, flow = null, detail = '') {
  confirmationFlow = flow ? { email, flow } : null;
  $('confirm-address').value = email;
  $('confirmation-passwords').hidden = !!flow;
  for (const id of ['confirm-password', 'confirm-password2']) $(id).required = !flow;
  $('confirmation-detail').textContent = detail || 'Enter your code and choose your password. No account is activated until confirmation succeeds.';
  showForm('confirm-email');
  $('confirm-code').focus();
}

function pauseResend(seconds = 60) {
  clearTimeout(resendTimer);
  const button = $('confirm-resend');
  button.disabled = true;
  button.textContent = `Wait ${seconds} seconds before requesting another code`;
  resendTimer = setTimeout(() => {
    button.disabled = false;
    button.textContent = 'Request the code again';
  }, seconds * 1000);
}

$('show-confirm').addEventListener('click', (event) => {
  event.preventDefault();
  showConfirmation($('reg-email').value.trim());
});
$('confirm-address').addEventListener('input', () => {
  $('confirmation-passwords').hidden = false;
  $('confirm-password').required = $('confirm-password2').required = true;
});
$('confirm-correct').addEventListener('click', async (event) => {
  event.preventDefault();
  if (confirmationInFlight) return;
  if (confirmationFlow) {
    confirmationInFlight = true;
    try {
      const result = await api('/api/register/cancel', {method:'POST',
        headers:{'content-type':'application/json'}, body:JSON.stringify(confirmationFlow)});
      if (!result.cancelled) throw new Error('The earlier pending registration could not be changed. Return to sign in or use its existing confirmation code.');
    } catch (error) {
      $('confirmation-detail').textContent = error.message;
      return;
    } finally { confirmationInFlight = false; }
  }
  $('reg-email').value = $('confirm-address').value;
  confirmationFlow = null;
  showForm('register');
  $('reg-email').focus();
});
$('confirm-signin').addEventListener('click', (event) => {
  event.preventDefault();
  if (confirmationInFlight) return;
  $('login-id').value = $('confirm-address').value;
  confirmationFlow = null;
  showForm('login');
});
$('confirm-email').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (confirmationInFlight) return;
  const email = $('confirm-address').value.trim().toLowerCase();
  const body = { email, code: $('confirm-code').value,
    flow: confirmationFlow?.email === email ? confirmationFlow.flow : '' };
  if (!$('confirmation-passwords').hidden) {
    body.password = $('confirm-password').value;
    body.password_again = $('confirm-password2').value;
  }
  concealPasswords(['confirm-password', 'confirm-password2']);
  $('confirm-code').value = '';
  confirmationInFlight = true;
  $('confirm-go').disabled = true;
  $('confirmation-detail').textContent = 'Confirming…';
  try {
    const result = await api('/api/register/confirm', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    confirmationInFlight = false;
    confirmationFlow = null;
    $('login-id').value = result.advocate_id;
    showOutcome('good', 'Email confirmed', result.detail, 'login');
  } catch (error) {
    $('confirmation-detail').textContent = error.status ? error.message
      : 'Confirmation could not be checked. Try signing in; if needed, confirm again. No automatic retry was sent.';
  } finally {
    confirmationInFlight = false;
    $('confirm-go').disabled = false;
  }
});
$('confirm-resend').addEventListener('click', async () => {
  if (!$('confirm-address').reportValidity()) return;
  pauseResend(registrationCapabilities?.resend_seconds || 60);
  try {
    const result = await api('/api/register/resend', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email: $('confirm-address').value.trim() }) });
    $('confirmation-detail').textContent = result.detail;
  } catch (error) {
    $('confirmation-detail').textContent = error.message;
  }
});

['reg-consent', 'reg-adult'].forEach((id) => $(id).addEventListener('change', syncRegisterReady));
syncRegisterReady();

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
function showOutcome(kind, title, body, returnTo = 'register') {
  $('outcome-title').textContent = title;
  $('outcome-body').textContent = body;
  $('outcome-title').className = `outcome-title ${kind}`;
  $('outcome-signin').hidden = kind !== 'good';
  $('outcome-back').hidden = kind === 'good';
  outcomeReturn = returnTo;
  showForm('outcome');
  (kind === 'good' ? $('outcome-signin') : $('outcome-back')).focus();
}

$('outcome-signin').addEventListener('click', () => {
  showForm('login');
  // THE PASSWORD FIELD, NOT THE EMAIL. The email is already filled from the
  // registration, and landing on a filled field means the first thing typed
  // goes to the end of it.
  $('login-password').focus();
});

$('outcome-back').addEventListener('click', () => {
  showForm(outcomeReturn);
  const first = { register: 'reg-password', forgot: 'forgot-email',
    reset: 'reset-password', login: 'login-id' };
  $(first[outcomeReturn] || 'login-id').focus();
});

$('show-register').addEventListener('click', (ev) => {
  ev.preventDefault();
  showForm('register');
});

$('show-login').addEventListener('click', (ev) => {
  ev.preventDefault();
  showForm('login');
});

// --------------------------------------------------------- forgot password
//
// Implementation Plan F-A-03. One email field, one answer whatever the address:
// the server says the same sentence for an account that exists and one that
// does not, and this page repeats it rather than guessing.
$('show-forgot').addEventListener('click', (ev) => {
  ev.preventDefault();
  const typed = $('login-id').value.trim();
  $('forgot-email').value = typed.includes('@') ? typed : '';
  showForm('forgot');
  $('forgot-email').focus();
});

$('forgot-login').addEventListener('click', (ev) => {
  ev.preventDefault();
  showForm('login');
  $('login-id').focus();
});

$('reset-login').addEventListener('click', (ev) => {
  ev.preventDefault();
  resetToken = null;
  showForm('login');
  $('login-id').focus();
});

$('forgot').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const go = $('forgot-go');
  const email = $('forgot-email').value.trim();
  go.disabled = true;
  try {
    const r = await api('/api/password/forgot', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email: email }),
    });
    $('login-id').value = email;
    showOutcome('good', 'Check your email', r.detail, 'login');
  } catch (err) {
    showOutcome('bad', 'Reset link not requested', err.message, 'forgot');
  } finally {
    go.disabled = false;
  }
});

$('reset').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const go = $('reset-go');
  const password = $('reset-password').value;
  const again = $('reset-password2').value;
  const token = resetToken;
  // Both passwords leave the DOM before any check or network wait.
  clearResetPasswords();
  if (!token) {
    showOutcome('bad', 'Password not changed',
      'This page has no reset link. Ask for a new one from Forgot password.', 'forgot');
    return;
  }
  if (password !== again) {
    showOutcome('bad', 'Password not changed',
      'The two passwords do not match. Nothing was changed.', 'reset');
    return;
  }
  go.disabled = true;
  try {
    const r = await api('/api/password/reset', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ token: token, password: password, password_again: again }),
    });
    resetToken = null;
    showOutcome('good', 'Password changed',
      `Your new password is set and ${r.sessions_ended} earlier session(s) were `
      + 'signed out. Sign in with the new password.', 'login');
  } catch (err) {
    // A refused LINK cannot be retried -- ask for a new one. A password the
    // rules refused can: the link was not spent.
    const linkRefused = /reset link/i.test(err.message || '');
    if (linkRefused) resetToken = null;
    showOutcome('bad', 'Password not changed', err.message,
      linkRefused ? 'forgot' : 'reset');
  } finally {
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
        consent: consentGiven(),
      }),
    });
    // THE BOXES BELONG TO THE PERSON WHO JUST REGISTERED. The next registration
    // on this screen ticks its own.
    $('reg-consent').checked = false;
    $('reg-adult').checked = false;
    $('reg-external-ai').checked = false;
    // REGISTERED, NOT SIGNED IN. A form post that created a session would mean
    // creating an account also logs in whatever machine sent it, and the
    // device binding is minted at sign-in for exactly that reason.
    //
    // Sign in with the canonical handle returned by the account owner.
    registrationInFlight = false;
    showConfirmation(r.email, r.flow, r.detail + (r.delivery === 'local_outbox_only'
      ? ' Local rehearsal: the code is in the protected test outbox, not your mailbox.' : ''));
    pauseResend(registrationCapabilities?.resend_seconds || 60);
  } catch (err) {
    registrationInFlight = false;
    if (err.obsolete) return;
    $('login-id').value = email;
    showOutcome('bad', 'Registration failed', !err.status
      ? 'Registration could not be confirmed. Check for a code before trying again. No automatic retry was sent.'
      : err.message, 'register');
  } finally {
    clearTimeout(timeout);
    registrationInFlight = false;
    $('register').removeAttribute('aria-busy');
    $('show-login').removeAttribute('aria-disabled');
    clearRegistrationPasswords();
    syncRegisterReady();
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


// ===================================================================== P25 ==
// SOURCE ATTRIBUTION. BK-94-AC5: every admitted document has a visible,
// correctable binding to ONE dispute before it contributes facts, and an
// unattached source never defaults to the first or largest thread. The pane
// shows the unbound ones FIRST, because a list of what is attached tells an
// advocate nothing about the document sitting there contributing nothing.
async function renderBindings(matterId, version) {
  const host = $('bindings-host');
  const stateEl = $('bindings-state');
  host.textContent = ''; stateEl.textContent = '';
  let data;
  try {
    data = await api(`/api/matters/${matterId}/source-bindings`);
  } catch (err) {
    stateEl.appendChild(stateBlock('loud',
      `Source attribution could not be read: ${err.message}`));
    return;
  }
  const rows = data.bindings || [];
  if (!rows.length) {
    host.appendChild(stateBlock('empty',
      'No admitted source has been attached to a dispute yet.'));
  }
  rows.forEach((b) => {
    const row = document.createElement('div');
    row.className = 'binding' + (b.refused ? ' unbound' : '');
    row.dataset.sourceId = b.source_id;
    const pill = document.createElement('span');
    pill.className = 'pill ' + (b.refused ? 'blocked'
      : b.provisional ? 'unknown' : 'ok');
    pill.textContent = b.refused ? 'contributes nothing'
      : b.provisional ? 'my reading' : 'you stated it';
    const text = document.createElement('span');
    text.className = 'binding-text';
    text.textContent = b.refused
      ? `${b.source_id} (${b.source_version}) — ${b.refused}`
      : `${b.source_id} (${b.source_version}) → ${b.thread_id}`;
    row.append(pill, text, bindingForm(matterId, b, version));
    host.appendChild(row);
  });
  keepForm(host, 'binding-form', () => bindingForm(matterId, null, version));
}


// THE FORM SURVIVES THE RE-RENDER. `host.textContent = ''` above clears the
// derived list, which is right; it must not also clear the control somebody
// is halfway through using. The existing node is detached before the wipe and
// put back after, so its values, focus and listeners are untouched.
function keepForm(host, className, make) {
  const kept = host.__keptForm;
  const form = (kept && kept.className.includes(className)) ? kept : make();
  host.__keptForm = form;
  host.appendChild(form);
}

function bindingForm(matterId, existing, version) {
  const form = document.createElement('form');
  form.className = 'binding-form';
  const src = document.createElement('input');
  src.type = 'text'; src.name = 'source_id'; src.required = true;
  src.placeholder = 'document id';
  src.setAttribute('aria-label', 'Document this binding is about');
  if (existing) { src.value = existing.source_id; src.readOnly = true; }
  const ver = document.createElement('input');
  ver.type = 'text'; ver.name = 'source_version'; ver.required = true;
  ver.placeholder = 'version';
  ver.setAttribute('aria-label', 'Version of the document');
  if (existing) { ver.value = existing.source_version; ver.readOnly = true; }
  const thread = document.createElement('input');
  thread.type = 'text'; thread.name = 'thread_id'; thread.required = true;
  thread.placeholder = 'which dispute';
  thread.setAttribute('aria-label', 'The dispute this document belongs to');
  const go = document.createElement('button');
  go.type = 'submit'; go.className = 'ghost';
  go.textContent = existing ? 'Re-attach' : 'Attach';
  const out = document.createElement('div');
  out.className = 'binding-out';
  form.append(src, ver, thread, go, out);

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    out.textContent = '';
    try {
      const said = await api('/api/source-bindings', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matter_id: matterId, source_id: src.value.trim(),
          source_version: ver.value.trim(), thread_id: thread.value.trim(),
          basis: 'stated',
          expected_matter_version: currentVersion(matterId, version),
        }),
      });
      // AFTER the re-render, not before it. Appending here and then calling
      // `showCasefile` wiped the note in the same tick -- the advocate was
      // told which dispute lost the source for a few milliseconds. The
      // sentence is the whole point of a correction: it says which thread's
      // work has to be reopened.
      if (state.matterId === matterId) state.matterVersion = said.version;
      await showCasefile(matterId);
      $('bindings-state').appendChild(stateBlock('quiet', said.reopen_note));
    } catch (err) {
      out.appendChild(stateBlock('loud',
        `Not attached: ${(err.detail && err.detail.why) || err.message}`));
    }
  });
  return form;
}

// ===================================================================== P27 ==
// DECISIONS ON ADVICE. BK-55-AC3. Every row carries the sentence saying what
// it does NOT do, because a consumer that has to ask separately will not.
async function renderDecisions(matterId, version) {
  const host = $('decisions-host');
  const stateEl = $('decisions-state');
  host.textContent = ''; stateEl.textContent = '';
  let data;
  try {
    data = await api(`/api/matters/${matterId}/advice-decisions`);
  } catch (err) {
    stateEl.appendChild(stateBlock('loud',
      `Decisions could not be read: ${err.message}`));
    return;
  }
  const rows = data.decisions || [];
  if (!rows.length) {
    host.appendChild(stateBlock('empty',
      'Nothing has been decided about the advice on this file. '
      + 'Silence is not acceptance.'));
  }
  rows.forEach((d) => {
    const row = document.createElement('div');
    row.className = 'decision' + (d.current ? '' : ' superseded');
    row.dataset.decisionId = d.decision_id;
    const pill = document.createElement('span');
    pill.className = 'pill ' + (d.current ? 'ok' : 'unknown');
    pill.textContent = d.current ? d.disposition : `${d.disposition} (superseded)`;
    const text = document.createElement('span');
    text.textContent = `advice ${d.advice_version} · ${d.scope} · owner `
      + `${d.owner} · review: ${d.review_trigger}`;
    const note = document.createElement('div');
    note.className = 'authority-note';
    note.textContent = d.authority_note;
    row.append(pill, text, note);
    host.appendChild(row);
  });
  keepForm(host, 'decision-form', () => decisionForm(matterId, version));
}

function decisionForm(matterId, version) {
  const form = document.createElement('form');
  form.className = 'decision-form';
  const pick = document.createElement('select');
  pick.name = 'disposition';
  pick.setAttribute('aria-label', 'What you decided about the advice');
  ['accept', 'reject', 'narrow', 'defer'].forEach((v) => {
    const o = document.createElement('option'); o.value = v; o.textContent = v;
    pick.appendChild(o);
  });
  const adviceVersion = document.createElement('input');
  adviceVersion.type = 'text'; adviceVersion.required = true;
  adviceVersion.name = 'advice_version';
  adviceVersion.placeholder = 'advice version';
  adviceVersion.setAttribute('aria-label', 'Which version of the advice');
  const scope = document.createElement('input');
  scope.type = 'text'; scope.required = true; scope.placeholder = 'scope';
  scope.name = 'scope';
  scope.setAttribute('aria-label', 'What this decision covers');
  const owner = document.createElement('input');
  owner.type = 'text'; owner.required = true; owner.placeholder = 'owner';
  owner.name = 'owner';
  owner.setAttribute('aria-label', 'Who owns this decision');
  const trigger = document.createElement('input');
  trigger.type = 'text'; trigger.required = true;
  trigger.name = 'review_trigger';
  trigger.placeholder = 'what brings it back';
  trigger.setAttribute('aria-label', 'What brings this decision back for review');
  const go = document.createElement('button');
  go.type = 'submit'; go.className = 'ghost'; go.textContent = 'Record decision';
  const out = document.createElement('div'); out.className = 'decision-out';
  form.append(pick, adviceVersion, scope, owner, trigger, go, out);

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    out.textContent = '';
    try {
      const said = await api('/api/advice-decisions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          matter_id: matterId, disposition: pick.value,
          advice_version: adviceVersion.value.trim(),
          scope: scope.value.trim(), owner: owner.value.trim(),
          review_trigger: trigger.value.trim(),
          expected_matter_version: currentVersion(matterId, version),
        }),
      });
      if (state.matterId === matterId) state.matterVersion = said.version;
      await showCasefile(matterId);
      $('decisions-state').appendChild(
        stateBlock('quiet', said.decision.authority_note));
    } catch (err) {
      out.appendChild(stateBlock('loud',
        `Not recorded: ${(err.detail && err.detail.why) || err.message}`));
    }
  });
  return form;
}

// ===================================================================== P33 ==
// RETENTION AND ERASURE. What is outstanding is named, never implied by a
// count that does not add up, and a held request says so on its face.
async function renderRetention(matterId, version) {
  const host = $('retention-host');
  const stateEl = $('retention-state');
  host.textContent = ''; stateEl.textContent = '';
  let cover;
  try {
    cover = await api(`/api/matters/${matterId}/cover`);
  } catch (err) {
    stateEl.appendChild(stateBlock('loud',
      `Retention could not be read: ${err.message}`));
    return;
  }
  const rows = (cover.retention || []);
  if (!rows.length) {
    host.appendChild(stateBlock('empty',
      'No retention or erasure has been requested on this file.'));
    return;
  }
  rows.forEach((r) => {
    const row = document.createElement('div');
    row.className = 'retention-row';
    row.dataset.requestId = r.request_id;
    const pill = document.createElement('span');
    pill.className = 'pill ' + (r.state === 'complete_for_declared_scope' ? 'ok'
      : r.state === 'under_hold' ? 'blocked' : 'unknown');
    pill.textContent = r.state.replace(/_/g, ' ');
    const text = document.createElement('span');
    text.textContent = `${r.resolved_asset_count} of ${r.expected_asset_count} `
      + `resolved · ${(r.retained_reason_codes || []).join(', ') || 'nothing retained'}`;
    row.append(pill, text);
    (r.outstanding || []).forEach((o) => {
      const li = document.createElement('div');
      li.className = 'retention-outstanding';
      li.textContent = o;
      row.appendChild(li);
    });
    host.appendChild(row);
  });
}

// THE VERSION THE SERVER LAST CONFIRMED. A second tab that moved the matter
// leaves this one holding a stale number, and posting it would lose the other
// tab's write -- so the fresher of the two is used, the same fix P24's
// briefing control needed.
function currentVersion(matterId, fallback) {
  return (state.matterId === matterId && state.matterVersion > fallback)
    ? state.matterVersion : fallback;
}
