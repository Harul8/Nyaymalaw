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
  disputeFocus: null,
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
  matterListGeneration: 0,
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
// The registration this page made, until its email is confirmed: its email and AI choice (AN.15).
let registeredHere = null;
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
// A message waiting for its files to be read (plan AN.40); Send is then a turning ring that lets it go (AN.42, D75).
let heldSend = null;

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
window.NmBrainSources?.configure({request:api, scope:() => ({
  advocate:state.advocate, session:state.sessionGeneration,
  matter:state.matterId, chat:activeIntent?.chatId || null,
}), openAsk:(answer, element, ask, opener) => openAskedItem(answer, ask, opener)});
// F-B-02. The board's edit of the opening details, while its dialog is open.
let openingEdit = null;
let draftVault = null;
let draftWrite = 0;
let draftUnlock = Promise.resolve();
let storedDraftCount = 0;
let recoveryGeneration = 0;
let checkpointTimer = null;
let restoredTimer = null;
// The signed-in advocate's allowance as the server last said it (plan AN.17); see loadUsage.
let usage = null;
let usageRequest = 0;
let usageNoticeTimer = null;
// The Usage and plan window (AN.19); declared here, before boot() can reach a sign-out.
let usagePlanRequest = 0;
const TRIAL_NOTE = 'You are on the trial. Choose a plan below when you want more.';
try { draftVault = new NMDraftVault(window.localStorage, window.crypto); }
catch { /* Unavailable storage is reported before any durable-save claim. */ }

function draftHasWork(intent) {
  return Boolean(intent && ((intent.chatId && !intent.matterId)
    || intent.text.trim() || intent.pending.length
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
      matterId:held.matterId, chatId:held.chatId, text:held.text, intake:held.intake,
      intakeOpen:held.intakeOpen, fields:held.fields, capacity:held.capacity,
      opening:held.opening || null,
      editedAt:held.editedAt || Date.now(),
      pending:held.pending.map(entry=>({turnId:entry.turnId, brief:entry.brief,
        documents:entry.documents || [],
        request:entry.request, envelope:entry.envelope, endpoint:entry.endpoint || null, state:'unknown',
        error:'A prior request needs reconciliation before retry.'})),
    };
    const savedAt = await draftVault.save(snapshot);
    if (previousKey && previousKey !== held.key) await draftVault.removeOwn(previousKey);
    if (generation !== state.sessionGeneration || !ownsIntent(held)) return false;
    // A newer edit may have saved too. That does not undo protection of this
    // receipt; it only owns the latest status notice.
    if (revision === draftWrite) showDraftCheckpoint(savedAt);
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
  const anchor = $('message');
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
          || (intent.key !== context.key
            && (context.matterId || intent.matterId || !intent.chatId))
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
          // A turn may still be working on the server after a reload: follow it,
          // then fetch its saved answer under the same turn id.
          intent.pending.forEach(entry=>{
            if (!entry.answer && entry.turnId) watchProgress(entry, () => deliver(entry));
          });
          // Recover explicitly, keeping other tab versions in protected storage.
          intentContexts.set(intent.key, intent);
          activeIntent = null;
          if (intent.matterId) { showTab('advise'); await showThreadBoard(intent.matterId); }
          else {
            if (intent.chatId) await restorePendingChat(intent.chatId);
            else startMatter();
          }
          if (session !== state.sessionGeneration || !ownsIntent(intent)) return;
          closeDraftRecovery();
          showDraftRestored();
          $('message').focus();
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

function intentKey(matterId, chatId = null) {
  return JSON.stringify([state.advocate, state.workspace,
    matterId || chatId || 'unsaved-opening']);
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
  // While the board's edit borrows the opening form (F-B-02), its fields hold
  // the matter's recorded details, not this tab's unsent opening draft.
  if (!openingEdit) {
    activeIntent.intakeOpen = !$('intake').hidden;
    activeIntent.fields = Object.fromEntries(INTAKE_INPUTS.map((id) => [id, $(id).value]));
    activeIntent.capacity = $('in-capacity').checked;
  }
  if (edited) { activeIntent.editedAt = Date.now(); saveProtectedDraft(); }
}

function restoreIntent() {
  // Any change of context ends a board edit first; its unsaved changes go.
  if (openingEdit) closeOpeningEdit({ restore: false });
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
  showIntake(false);
}

function selectIntent(matterId, { opening = false, chatId = null } = {}) {
  snapshotIntent();
  clearDraftNotices();
  closeDraftRecovery();
  if (!state.advocate || (!matterId && !opening)) activeIntent = null;
  else {
    const key = intentKey(matterId, chatId);
    if (!intentContexts.has(key)) intentContexts.set(key, {
      key, advocate: state.advocate, workspace: state.workspace,
      matterId: matterId || null, chatId, text: '', intake: null, intakeOpen: false,
      fields: {}, capacity: false, pending: [],
    });
    activeIntent = intentContexts.get(key);
  }
  // Plan AN.40 (D64): a message waiting for its files never goes in another conversation than the one it was sent in.
  if (heldSend && heldSend.intent !== activeIntent) cancelHold();
  restoreIntent();
}

function reconcileIntent(transcript) {
  if (!activeIntent) return;
  snapshotIntent();
  const recorded = new Set(transcript.filter(turn => turn.committed === true
    && turn.release_state === 'released').map(turn => turn.turn_id).filter(Boolean));
  activeIntent.pending = activeIntent.pending.filter((entry) => {
    if (!recorded.has(entry.turnId)) return true;
    // The protected receipt and the current typing draft are independent.
    // Reconciliation must not consume a follow-up merely because its words
    // happen to match the acknowledged message.
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
  const adminEntry = $('admin-entry');
  if (adminEntry) adminEntry.hidden = true;
  closeDisputeReader(false);
  window.NmBrainSources?.close(false);
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
  // The borrowed form holds this matter's details; they leave with the session.
  closeOpeningEdit({ restore: false });
  $('dictation-state').textContent = '';
  // The allowance belongs to the advocate who signed in, and leaves with them.
  forgetUsage();
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
  $('dictation-setting-dialog').close();
  $('dictation-setting-status').textContent = '';
  $('usage-plan-dialog').close();
  $('sessions-body').textContent = '';
  if (activeDelivery) {
    activeDelivery.entry.state = 'unknown';
    activeDelivery.entry.error = 'The session ended before this request was confirmed.';
    activeDelivery.controller.abort();
  }
  activeDelivery = null;
  activeIntent = null;
  state.railGeneration += 1;
  state.matterListGeneration += 1;
  state.advocate = null;
  state.workspace = null;
  state.matterId = null;
  state.turns = [];
  ['thread', 'rail-body', 'rail-meta', 'matter-board-body', 'matter-board-meta',
   'search-results', 'history-body', 'who-name', 'account-initials', 'profile-name', 'profile-email', 'profile-workspace',
   'who-detail', 'files-menu', 'search-index', 'search-state', 'history-state']
    .forEach((id) => { const el = $(id); if (el) el.textContent = ''; });
  fitBoard();
  $('matter-heading').textContent = 'My work';
  $('matter-heading').removeAttribute('title');
  state.matterVersion = null;
  state.matterReady = false;
  state.intake = null;
  [...INTAKE_INPUTS, 'q', 'f-court', 'f-from', 'f-to']
    .forEach((id) => { $(id).value = ''; });
  $('opening-fields').replaceChildren();
  $('opening-record').hidden = true;
  $('in-capacity').checked = false;
  // THE RIBBON AND THE PERSON MENU FORGET WHO WAS HERE (F-A-17).
  ['who-name', 'profile-name', 'profile-email', 'profile-workspace']
    .forEach((id) => { const el = $(id); if (el) el.textContent = '—'; });
  closeFilesMenu();
  $('matter-files').hidden = true;
  window.NmBrainSources.close(false);
  $('board-status').hidden = true;
  $('board-status').textContent = '';
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

// PLAN AN.41 (D65; owner, 4 Nov 2026: idle is "where user didn't do anything and NM is also not doing thing"): from Send until the
// answer is saved or stops, the advocate counts as active - here, and on the server, which keeps the session active while NM works -
// and the thirty minutes start once NM has finished. The twelve-hour limit of a sign-in is unchanged: the server still ends it.
function nmWorking() {
  return Boolean(activeDelivery) || (Array.isArray(state.turns) && state.turns.some((entry) => entry && entry.following));
}

function nmFinished() {
  if (!idleWatching()) return;
  idle.lastActivity = Date.now();
  $('idle-warning').hidden = true;
  checkIdle();
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
  if (idle.lastActivity && at - idle.lastActivity >= idle.limitMs && !nmWorking()) {
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
  if (nmWorking()) {
    // D65: NM working is activity; the server's own window is asked for again as it moves on.
    idle.lastActivity = now;
    $('idle-warning').hidden = true;
    if (now - idle.lastReport >= IDLE_REPORT_MS) sendActivityReport();
    idle.timer = setTimeout(checkIdle, IDLE_REPORT_MS / 2);
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
    // Structured refusals carry recovery state, not display text. Keep the
    // object for callers, but never turn it into JSON in a visible error.
    const readable = typeof detail === 'string' ? detail
      : [detail?.why, detail?.message].find(value =>
        typeof value === 'string' && value.trim())
        || `The server could not complete this request (HTTP ${res.status}).`;
    const err = new Error(readable);
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
    const chatOnly = h.corpus === 'not_connected' && h.runtime === 'ready';
    el.textContent = chatOnly
      ? 'Chat available · legal research is not connected'
      : readable
        ? 'Legal library available · check the scope of each result'
        : 'Legal library unavailable · authority-backed research is limited';
    el.title = chatOnly
      ? 'Message labelling, response preparation and response review are connected.'
      : 'Library availability does not establish legal coverage or currency.';
    el.classList.toggle('bad', !readable && !chatOnly);
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

// The conversation window's views (owner, 16 Oct 2026): 'list' is the conversation
// history; 'opening' a new or saved conversation and 'matter' an earlier matter
// record, both the conversation with the matter board on its left once the board has
// something on it (P38, 21 Oct 2026).
function setWorkView(view) {
  $('pane-advise').dataset.view = view;
  if (view === 'list') $('top-history').setAttribute('aria-current', 'page');
  else $('top-history').removeAttribute('aria-current');
  updateWorkspace();
}

// ONE WAY OUT OF AN OPEN MATTER, whether to the conversation history or to a new
// opening. Any render still in flight for the old matter loses the right to
// paint, because the generation it holds is no longer current.
function closeOpenMatter() {
  closeDisputeReader(false);
  window.NmBrainSources.close(false);
  state.railGeneration += 1;
  state.boardGeneration = (state.boardGeneration || 0) + 1;
  state.matterId = null;
  state.matterVersion = null;
  state.matterReady = false;
  state.turns = [];
  $('thread').textContent = '';
  $('matter-board-body').replaceChildren();
  $('matter-board-meta').textContent = '';
  fitBoard();
  toggleMatterBoard(false);
  selectMatterRow();
  $('pane-advise').dataset.matterId = '';
  $('opening-board-status').hidden = true;
  $('opening-board-status').replaceChildren();
  $('opening-fields').replaceChildren();
  $('opening-record').hidden = true;
  closeFilesMenu();
}

async function restorePendingChat(chatId) {
  const session = state.sessionGeneration;
  const generation = ++state.railGeneration;
  const restored = await api(`/api/chats/${encodeURIComponent(chatId)}`);
  if (session !== state.sessionGeneration || generation !== state.railGeneration) return;
  if (restored.state !== 'ok' || restored.chat_id !== chatId) {
    throw new Error('The saved conversation is incomplete.');
  }
  if (!Number.isInteger(restored.matter_version) || restored.matter_version < 0) {
    throw new Error('The saved conversation version could not be established. Please reopen it.');
  }
  startMatter(chatId);
  if (session !== state.sessionGeneration || !activeIntent || activeIntent.chatId !== chatId) return;
  state.matterVersion = restored.matter_version;
  takeTitle(chatId, restored.title);
  state.turns = restored.turns.map(restoredTurn);
  reconcileIntent(restored.turns);
  // Plan AN.41 (D66): the turn being worked on is in the conversation from Send - followed while NM works, or said to have
  // stopped, in red, with Continue and Discard (D69); after a restart NM continues it by itself (D73).
  if (restored.pending) followPending(activeIntent, restored.pending, chatId);
  // Plan AN.42 (D77): what waits to be sent is kept with the conversation.
  if (Array.isArray(restored.queued) && restored.queued.length) await restoreQueued(activeIntent, restored.queued, restored.pending);
  repaint();
}

// The answer being worked on, followed by a page that did not send it (a reload, another tab, a restart): it is the answer this page
// waits for, so that the ring stops it (D78) and what is written meanwhile waits for it (D76-D77), as for one this page sent.
function followAs(entry) {
  if (activeDelivery) return;
  activeDelivery = { controller: { abort() {} }, entry, following: true };
  $('message').placeholder = COMPOSER_WAITING;
  paintSend();
}

function unfollow(entry) {
  if (!activeDelivery || activeDelivery.entry !== entry || !activeDelivery.following) return;
  activeDelivery = null;
  $('message').placeholder = COMPOSER_PROMPT;
  updateWorkspace();
}

function followPending(intent, pending, chatId) {
  let entry = state.turns.find((item) => item.turnId === pending.turn_id && !item.answer);
  if (!entry) {
    entry = { brief: pending.message, documents: pending.documents || [], turnId: pending.turn_id, context: intent,
      state: 'sending', chatId,
      request: { matter_id: null, chat_id: chatId, parties: {}, release: {}, capacity: null } };
    intent.pending.push(entry);
    state.turns.push(entry);
  }
  entry.chatId = chatId;
  takePending(entry, pending);
  if (pending.state === 'working') {
    if (activeDelivery && activeDelivery.entry === entry) return;
    entry.state = 'sending';
    entry.following = true;
    followAs(entry);
    checkIdle();
    // 53i (D224): its conversation is read again only while the advocate is still in it; opened later, it is read then.
    watchProgress(entry, () => { entry.following = false; unfollow(entry); nmFinished();
      if (ownsIntent(intent)) restorePendingChat(chatId); },
      () => { entry.following = false; unfollow(entry); nmFinished(); refreshStopped(entry, chatId); });
    return;
  }
  entry.state = 'stopped';
  if (pending.stopped && pending.stopped.by_itself) continueTurn(entry, { byItself: true });
}

// CONVERSATION HISTORY (owner, 16 Oct 2026): its own view, read fresh each time.
async function showMatterList({ preserveIntent = false } = {}) {
  if (!preserveIntent) selectIntent(null);
  closeOpenMatter();
  setWorkView('list');
  $('rail-title').textContent = 'Conversation history';
  $('matter-heading').textContent = 'My work';
  $('matter-heading').removeAttribute('title');
  updateWorkspace();
  window.dispatchEvent(new Event('nm:matter-changed'));
  await loadMatterList();
}

function selectMatterRow() {
  let current = null;
  const chatId = activeIntent && activeIntent.chatId;
  for (const row of $('rail-body').querySelectorAll('[data-matter-id], [data-chat-id]')) {
    const selected = row.dataset.matterId ? row.dataset.matterId === state.matterId
      : Boolean(chatId) && row.dataset.chatId === chatId;
    row.classList.toggle('selected', selected);
    row.setAttribute('aria-pressed', String(selected));
    if (selected) current = row;
  }
  return current;
}

// CONVERSATION HISTORY, TEN AT A TIME (owner decision O29, 26 Oct 2026): the first ten items come at once and
// Load more adds the next ten, so a long history does not make the first sight of it wait.
const HISTORY_PAGE = 10;

function historyCounts(data) {
  return `${data.chat_count} conversation${data.chat_count === 1 ? '' : 's'}`
    + (data.row_count ? ` · ${data.row_count} earlier matter record${data.row_count === 1 ? '' : 's'}` : '');
}

function historyWhen(at) {
  const when = at ? new Date(at) : null;
  return when && !Number.isNaN(when.getTime())
    ? ` · ${when.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}` : '';
}

// One saved conversation's row. The generation and the session are those of the list the row belongs to: a
// row left over from an earlier listing, or from a session that has ended, may not paint over what replaced it.
// PLAN AN.43 (D81-D82; owner, 5 Nov 2026: "put a small name to the matters in the list instead of large text"): each line under
// its title, which the model writes from the matter's details; until there is one, the message's first ten words. The first message
// itself on hover.
function historyTitle(chat) {
  if (typeof chat.title === 'string' && chat.title.trim()) return chat.title.trim();
  const words = String(chat.preview || '').split(/\s+/).filter(Boolean);
  return words.length ? words.slice(0, 10).join(' ') + (words.length > 10 ? '…' : '') : 'Conversation';
}

function historyChatRow(chat, generation, session) {
  const row = document.createElement('div');
  row.className = 'row';
  row.dataset.chatId = chat.chat_id;
  row.setAttribute('role', 'button');
  row.tabIndex = 0;
  const named = historyTitle(chat);
  row.setAttribute('aria-label', `Open conversation: ${named}`);
  const title = document.createElement('div');
  title.className = 'r-title';
  title.textContent = named;
  if (chat.preview) title.title = chat.preview;
  const details = document.createElement('div');
  details.className = 'hint';
  details.textContent = `${chat.turn_count} message${chat.turn_count === 1 ? '' : 's'}`
    + historyWhen(chat.last_updated);
  row.append(title, details);
  // Plan AN.48 (D164): where the conversation waits for the advocate, and for what.
  if (typeof chat.waiting === 'string' && chat.waiting) {
    const waiting = document.createElement('div');
    waiting.className = 'hint waiting-line';
    waiting.textContent = chat.waiting;
    row.appendChild(waiting);
  }
  const open = () => {
    const selection = restorePendingChat(chat.chat_id);
    const selectedGeneration = state.railGeneration;
    return selection.catch((error) => {
      if (selectedGeneration !== state.railGeneration
          || session !== state.sessionGeneration
          || generation !== state.matterListGeneration) return;
      $('rail-body').prepend(stateBlock('unbuildable', `The chat could not be read: ${error.message}`));
    });
  };
  row.onclick = open;
  row.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      open();
    }
  });
  return row;
}

function historyMatterRow(m) {
  const row = document.createElement('div');
  row.className = 'row matter-list-row';
  row.dataset.matterId = m.matter_id;
  row.setAttribute('role', 'button');
  row.tabIndex = 0;
  row.setAttribute('aria-label', `Open ${m.matter}`);
  const t = document.createElement('div');
  t.className = 'r-title'; t.textContent = m.matter;
  const kind = document.createElement('div');
  kind.className = 'hint';
  kind.textContent = `Earlier matter record${historyWhen(m.last_updated)}`;
  row.append(t, kind);
  row.onclick = () => showThreadBoard(m.matter_id);
  row.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      showThreadBoard(m.matter_id);
    }
  });
  return row;
}

// THE LOAD MORE BUTTON under the rows, with a line saying how many are shown of how many. Each press asks for
// the next ten; a press that fails says so and leaves what is shown where it is.
function offerMoreHistory(body, first, shownCount, rowsOf, stale) {
  if (!first.has_more || first.next_offset === null) return;
  const footer = document.createElement('div');
  footer.className = 'rail-more';
  const status = document.createElement('p');
  status.className = 'hint';
  status.setAttribute('role', 'status');
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'rail-more-button';
  button.textContent = 'Load more';
  footer.append(status, button);
  body.append(footer);
  let count = shownCount;
  let total = first.total;
  let next = first.next_offset;
  status.textContent = `Showing ${count} of ${total}`;
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = 'Loading more…';
    let page;
    try {
      page = await api(`/api/work?limit=${HISTORY_PAGE}&offset=${next}`);
    } catch (e) {
      if (stale()) return;
      status.textContent = `More could not be loaded: ${e.message}. What is shown stays.`;
      button.textContent = 'Try again';
      button.disabled = false;
      return;
    }
    if (stale()) return;
    const rows = rowsOf(page);
    footer.before(...rows);
    count += rows.length;
    total = page.total;
    next = page.next_offset;
    $('rail-meta').textContent = historyCounts(page);
    selectMatterRow();
    if (page.has_more && next !== null) {
      status.textContent = `Showing ${count} of ${total}`;
      button.textContent = 'Load more';
      button.disabled = false;
      if (!rows.length) button.focus();
    } else {
      footer.remove();
    }
    if (rows.length) rows[0].focus();
  });
}

async function loadMatterList() {
  const generation = ++state.matterListGeneration;
  const session = state.sessionGeneration;
  const body = $('rail-body');
  const stale = () => generation !== state.matterListGeneration || session !== state.sessionGeneration;
  body.replaceChildren(stateBlock('building', 'Loading your conversations…'));

  let data;
  try {
    data = await api(`/api/work?limit=${HISTORY_PAGE}&offset=0`);
  } catch (e) {
    if (stale()) return;
    // NEVER render an unreadable board as an empty one.
    body.replaceChildren(stateBlock(
      'unbuildable',
      `The matter list could not be built: ${e.message}. This is a failure to ` +
      `read, not a statement that you have no matters.`));
    $('rail-meta').textContent = 'Matter list unavailable';
    return;
  }
  if (stale()) return;

  $('rail-meta').textContent = historyCounts(data);
  const incomplete = data.state !== 'ok';
  const notice = incomplete ? stateBlock('unbuildable',
    'Some work could not be loaded. This list may be incomplete. Retry before relying on it.') : null;

  if (!data.matters.length && !data.chats.length) {
    body.replaceChildren(notice || stateBlock('empty', 'No conversations yet. Start one with + New matter.'));
    return;
  }

  // An item is listed once: a conversation answered while the list was open moves to the top, and the page
  // that follows would otherwise show the one it displaced again.
  const shown = new Set();
  const rowsOf = (page) => {
    const rows = [];
    for (const chat of page.chats) {
      if (shown.has(`chat:${chat.chat_id}`)) continue;
      shown.add(`chat:${chat.chat_id}`);
      rows.push(historyChatRow(chat, generation, session));
    }
    for (const m of page.matters) {
      if (shown.has(`matter:${m.matter_id}`)) continue;
      shown.add(`matter:${m.matter_id}`);
      rows.push(historyMatterRow(m));
    }
    return rows;
  };
  const firstRows = rowsOf(data);
  body.replaceChildren(...firstRows);
  offerMoreHistory(body, data, firstRows.length, rowsOf, stale);
  if (notice) body.prepend(notice);
  selectMatterRow();
}

async function showThreadBoard(
  matterId, { restore = true, closeNavigator = true, adoptOpening = false,
    deferBoard = false } = {}) {
  closeDisputeReader(false);
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
  if (state.matterId !== matterId) state.disputeFocus = null;
  const generation = ++state.railGeneration;
  // OPENING A MATTER CLOSES THE LIST at narrow widths. Leaving it up would
  // put the advocate on the answer they asked for with the index still over
  // it, which is the same unreachability wearing the other face.
  if (closeNavigator) toggleMatterBoard(false);
  setWorkView(deferBoard ? 'opening' : 'matter');
  state.matterId = matterId;
  selectMatterRow();
  state.matterVersion = null;
  state.matterReady = false;
  updateWorkspace();
  $('matter-heading').textContent = 'Loading matter…';
  $('matter-heading').removeAttribute('title');
  closeFilesMenu();
  if (restore) {
    state.turns = [];
    $('thread').textContent = '';
  }
  window.dispatchEvent(new Event('nm:matter-changed'));
  $('pane-advise').dataset.matterId = matterId;
  $('opening-board-status').hidden = true;
  $('opening-board-status').replaceChildren();
  if (deferBoard) showMatterStatus('building', 'Reading the matter board…');
  const body = $('matter-board-body');
  $('matter-board-meta').textContent = '';
  body.replaceChildren();

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
      'unbuildable', `The matter could not be loaded: ${e.message}`));
    fitBoard();
    $('matter-board-meta').textContent = 'Matter could not be loaded';
    if (deferBoard) showOpeningBoardFailure(matterId,
      `The saved matter could not be read: ${e.message}`);
    return;
  }

  if (deferBoard) {
    $('opening-board-status').hidden = true;
    $('opening-board-status').replaceChildren();
    setWorkView('matter');
  }

  $('matter-board-meta').textContent = '';
  $('matter-heading').textContent = data.title || 'Untitled matter';
  $('matter-heading').title = data.title || 'Untitled matter';
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

  renderDisputeBoard(body, data.agenda, data.proposed_disputes,
    data.material_record, data.requirements_record);
  fitBoard();
  const selected = selectMatterRow();
  if (selected) {
    selected.querySelector('.r-title').textContent = data.title || 'Untitled matter';
    selected.setAttribute('aria-label', `Open ${data.title || 'Untitled matter'}`);
  }
}

function requirementsFor(record, row) {
  const rows = record?.by_dispute?.[row.id || row.thread_id];
  return Array.isArray(rows) ? rows : [];
}

function requirementStatusFor(record, row) {
  const status = record?.status_by_dispute?.[row.id || row.thread_id];
  if (['ok', 'partial', 'unavailable', 'unassessed'].includes(status)) return status;
  return record && record.state !== 'ok' ? 'unavailable' : 'unassessed';
}

function requirementReviewPending(record, row) {
  return record?.coverage_by_dispute?.[row.id || row.thread_id]?.verification_current === false
    && requirementsFor(record, row).length > 0;
}

function renderDisputeBoard(body, agenda, projection, materialRecord = null,
                            requirementsRecord = null) {
  body.replaceChildren();
  const worked = Array.isArray(agenda?.disputes) ? agenda.disputes : null;
  const proposed = Array.isArray(projection?.rows) ? projection.rows : null;
  if (!worked) {
    body.appendChild(stateBlock('unbuildable', 'Dispute progress could not be read.'));
  }
  if (!proposed) {
    body.appendChild(stateBlock('unbuildable', 'Proposed disputes could not be read.'));
  } else if (projection.state !== 'ok') {
    body.appendChild(stateBlock('unbuildable',
      'Some proposed disputes could not be read. Reopen the matter before relying on this list.'));
  }
  if (worked && !worked.some((row) => row.thread_id === state.disputeFocus)) {
    state.disputeFocus = null;
  }
  if (!(worked?.length || proposed?.length)) {
    if (worked && proposed && projection.state === 'ok') {
      body.appendChild(stateBlock('empty', 'No disputes identified yet.'));
    }
    return;
  }
  const heading = document.createElement('h3');
  heading.textContent = 'Disputes';
  body.appendChild(heading);
  const instruction = document.createElement('p'); instruction.className = 'hint';
  instruction.textContent = 'Click or press Enter for details.';
  body.appendChild(instruction);
  const list = document.createElement('ul'); list.className = 'dispute-proposal-list';
  const focusButtons = [];
  const setFocus = (threadId) => {
    state.disputeFocus = threadId;
    for (const [button, id] of focusButtons) {
      button.setAttribute('aria-pressed', String(id === threadId));
    }
  };
  const addRow = (row, isWorked) => {
    const uncertain = !isWorked && row.identification === 'needs_clarification';
    const unassessed = !isWorked && row.identification !== 'identified' && !uncertain;
    const item = document.createElement('li');
    item.className = uncertain ? 'dispute-proposal-item uncertain' : 'dispute-proposal-item';
    const button = document.createElement('button'); button.type = 'button';
    button.className = isWorked ? 'dispute-proposal-button dispute-focus'
      : 'dispute-proposal-button';
    button.dataset.matterId = state.matterId || '';
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-controls', 'dispute-reader');
    button.title = 'Read dispute details';
    if (isWorked) {
      button.setAttribute('aria-pressed', String(state.disputeFocus === row.thread_id));
      focusButtons.push([button, row.thread_id]);
    }
    const label = document.createElement('span');
    label.textContent = row.label?.trim() || row.statement;
    button.appendChild(label);
    if (uncertain || unassessed) {
      const status = document.createElement('span');
      status.className = 'dispute-proposal-status';
      status.textContent = uncertain ? 'Provisional' : 'Not assessed';
      button.appendChild(status);
    }
    const open = () => openDisputeReader(
      row, button, isWorked ? setFocus : null, materialRecord, requirementsRecord);
    button.addEventListener('click', open);
    item.appendChild(button);
    const labels = requirementsFor(requirementsRecord, row)
      .map(need => typeof need?.label === 'string' ? need.label.trim() : '')
      .filter(Boolean);
    if (labels.length) {
      const requirements = document.createElement('ul');
      requirements.className = 'dispute-requirement-labels';
      for (const text of labels) {
        const labelItem = document.createElement('li');
        labelItem.textContent = text;
        requirements.appendChild(labelItem);
      }
      item.appendChild(requirements);
    }
    if (requirementReviewPending(requirementsRecord, row)
        || requirementStatusFor(requirementsRecord, row) === 'partial') {
      const coverage = document.createElement('p');
      coverage.className = 'hint';
      coverage.textContent = requirementReviewPending(requirementsRecord, row)
        ? 'Source review pending; see details.' : 'Legal research incomplete; see details.';
      item.appendChild(coverage);
    }
    list.appendChild(item);
  };
  for (const row of worked || []) addRow(row, true);
  for (const row of proposed || []) addRow(row, false);
  body.appendChild(list);
}

let disputeReaderTrigger = null;

function closeDisputeReader(restoreFocus = true) {
  if (!restoreFocus) {
    disputeReaderTrigger = null;
    $('dispute-reader-title').textContent = '';
    $('dispute-reader-body').replaceChildren();
  }
  if ($('dispute-reader').open) $('dispute-reader').close();
}

function appendMaterialRows(host, rows) {
  const list = document.createElement('ul');
  list.className = 'dispute-reader-material-list';
  const basisLabels = {
    stated: 'As stated in your message',
    attributed: 'Attributed to another person',
    described_record: 'Described record; not examined',
    inferred: 'Inference to check',
    uncertain: 'Uncertain account',
    hypothetical: 'Hypothetical',
  };
  const relationLabels = {
    adds: 'Adds to earlier account',
    corrects: 'Corrects earlier account',
    contradicts: 'Conflicts with earlier account',
    withdraws: 'Withdraws earlier account',
  };
  for (const detail of rows) {
    const item = document.createElement('li');
    const description = document.createElement('p');
    const category = typeof detail.kind === 'string' && detail.kind
      ? detail.kind[0].toUpperCase() + detail.kind.slice(1) : 'Detail';
    description.textContent = `${category}: ${detail.statement || ''}`;
    item.appendChild(description);
    const attribution = document.createElement('p');
    attribution.className = 'hint';
    attribution.textContent = [basisLabels[detail.basis] || 'Attribution unassessed',
      relationLabels[detail.relation]].filter(Boolean).join(' · ');
    item.appendChild(attribution);
    if (detail.why_material) {
      const relevance = document.createElement('p');
      relevance.textContent = `Relevance: ${detail.why_material}`;
      item.appendChild(relevance);
    }
    if (detail.quoted) {
      const sourceLabel = document.createElement('p');
      sourceLabel.className = 'dispute-reader-source';
      sourceLabel.textContent = 'Source: your saved message';
      sourceLabel.dataset.sourceTurnId = detail.source_turn_id || '';
      item.appendChild(sourceLabel);
      const source = document.createElement('blockquote');
      source.textContent = detail.quoted;
      item.appendChild(source);
    }
    for (const prior of detail.prior_references || []) {
      const reference = document.createElement('blockquote');
      reference.textContent = `Earlier ${prior.role === 'nm' ? 'NM reply' : 'your message'}: ${prior.quoted}`;
      item.appendChild(reference);
    }
    list.appendChild(item);
  }
  host.appendChild(list);
}

function openDisputeReader(row, trigger, setFocus = null, materialRecord = null,
                           requirementsRecord = null) {
  const dialog = $('dispute-reader');
  disputeReaderTrigger = trigger;
  const label = row.label?.trim() || row.statement;
  $('dispute-reader-title').textContent = label;
  const body = $('dispute-reader-body'); body.replaceChildren();
  if (row.statement && row.statement !== label) {
    const statement = document.createElement('p');
    statement.textContent = row.statement; body.appendChild(statement);
  }
  if (!setFocus && row.identification === 'needs_clarification') {
    const status = document.createElement('p');
    status.className = 'dispute-reader-status'; status.textContent = 'Provisional';
    body.appendChild(status);
  } else if (!setFocus && row.identification !== 'identified') {
    const status = document.createElement('p');
    status.className = 'dispute-reader-status';
    status.textContent = 'Identification has not been assessed.';
    body.appendChild(status);
  }
  if (row.why_material) {
    const reason = document.createElement('p');
    reason.textContent = `Why listed: ${row.why_material}`;
    body.appendChild(reason);
  }
  if (row.clarification && row.identification !== 'identified') {
    const clarification = document.createElement('p');
    clarification.textContent = `To clarify: ${row.clarification}`;
    body.appendChild(clarification);
  }
  if (row.quoted) {
    const sourceLabel = document.createElement('p');
    sourceLabel.className = 'dispute-reader-source';
    sourceLabel.textContent = 'Source: your saved message';
    sourceLabel.dataset.sourceTurnId = row.source_turn_id;
    body.appendChild(sourceLabel);
    const source = document.createElement('blockquote');
    source.textContent = row.quoted; body.appendChild(source);
  }
  for (const prior of row.prior_references || []) {
    const reference = document.createElement('blockquote');
    reference.textContent = `Earlier ${prior.role === 'nm' ? 'NM reply' : 'your message'}: ${prior.quoted}`;
    body.appendChild(reference);
  }
  renderLegalRequirements(body, row, requirementsRecord);
  if (setFocus && !row.why_material && !row.quoted) {
    const missing = document.createElement('p');
    missing.className = 'hint';
    missing.textContent = 'No identification reason or source passage is stored with this dispute.';
    body.appendChild(missing);
  }
  if (materialRecord?.state) {
    const linkedMaterial = materialRecord.by_dispute?.[row.id || row.thread_id] || [];
    const material = document.createElement('section');
    material.className = 'dispute-reader-material';
    const heading = document.createElement('h3');
    heading.textContent = 'Material from the conversation';
    material.appendChild(heading);
    const explanation = document.createElement('p');
    explanation.className = 'hint';
    explanation.textContent = 'Linked to this dispute. These sourced readings of the account are not findings.';
    material.appendChild(explanation);
    if (materialRecord.state !== 'ok') {
      const incomplete = document.createElement('p');
      incomplete.className = 'hint';
      incomplete.textContent = 'Some saved material could not be read. Reopen the matter before relying on this record.';
      material.appendChild(incomplete);
    }
    if (Array.isArray(linkedMaterial) && linkedMaterial.length) {
      appendMaterialRows(material, linkedMaterial);
    } else {
      const empty = document.createElement('p');
      empty.className = 'hint';
      empty.textContent = 'No material is linked to this dispute yet.';
      material.appendChild(empty);
    }
    body.appendChild(material);
    if (Array.isArray(materialRecord.matter) && materialRecord.matter.length) {
      const matterWide = document.createElement('section');
      matterWide.className = 'dispute-reader-material';
      const title = document.createElement('h3');
      title.textContent = 'Matter-wide material';
      matterWide.appendChild(title);
      const note = document.createElement('p');
      note.className = 'hint';
      note.textContent = 'Recorded for the matter as a whole; not specifically linked to this dispute.';
      matterWide.appendChild(note);
      appendMaterialRows(matterWide, materialRecord.matter);
      body.appendChild(matterWide);
    }
    if (Array.isArray(materialRecord.unresolved) && materialRecord.unresolved.length) {
      const unassigned = document.createElement('details');
      unassigned.className = 'dispute-reader-material';
      const title = document.createElement('summary');
      title.textContent = `Unassigned material (${materialRecord.unresolved.length})`;
      unassigned.appendChild(title);
      const note = document.createElement('p');
      note.className = 'hint';
      note.textContent = materialRecord.unverified_count > 0
        ? `${materialRecord.unverified_count} older ${materialRecord.unverified_count === 1 ? 'reading has' : 'readings have'} not been independently grounded. Shown from your saved words, they are excluded from legal research until checked.`
        : 'These details have not been assigned to a dispute.';
      unassigned.appendChild(note);
      appendMaterialRows(unassigned, materialRecord.unresolved);
      body.appendChild(unassigned);
    }
  }
  if (setFocus) {
    const work = document.createElement('section');
    work.className = 'dispute-reader-work';
    const heading = document.createElement('h3');
    heading.textContent = 'Current work'; work.appendChild(heading);
    const statuses = { not_assessed: 'Not yet reviewed', needs_review: 'Needs review',
      needs_information: 'Needs information', waiting: 'Waiting for information',
      paused: 'Paused', reviewed: 'Reviewed on current record' };
    const status = document.createElement('p');
    status.textContent = statuses[row.status] || 'Progress not established';
    work.appendChild(status);
    if (row.next_need) {
      const next = document.createElement('p');
      next.textContent = row.next_need; work.appendChild(next);
    }
    renderRequirements(work, row);
    body.appendChild(work);
    const focus = document.createElement('button');
    focus.type = 'button'; focus.className = 'ghost';
    focus.textContent = state.disputeFocus === row.thread_id
      ? 'Return to whole matter' : 'Focus next message on this dispute';
    focus.addEventListener('click', () => {
      setFocus(state.disputeFocus === row.thread_id ? null : row.thread_id);
      closeDisputeReader();
    });
    body.appendChild(focus);
  }
  if (!dialog.open) dialog.showModal();
  $('dispute-reader-close').focus();
  body.scrollTop = 0;
}

function renderLegalRequirements(host, row, record) {
  const section = document.createElement('section');
  section.className = 'dispute-reader-requirements';
  const heading = document.createElement('h3');
  heading.textContent = 'Legal requirements';
  section.appendChild(heading);
  const status = requirementStatusFor(record, row);
  const reviewPending = requirementReviewPending(record, row);
  if (reviewPending) {
    const review = document.createElement('p');
    review.className = 'hint';
    review.textContent = 'These saved items await the current source review. '
      + 'They remain available as history and are not used as checked law for a new response.';
    section.appendChild(review);
  }
  if (status !== 'ok' && status !== 'partial') {
    const unavailable = document.createElement('p');
    unavailable.className = 'hint';
    unavailable.textContent = status === 'unassessed'
      ? 'Legal requirements have not been assessed for this dispute yet. '
        + 'This is not a conclusion about the governing law.'
      : 'Legal requirements could not be read for this dispute right now. '
        + 'This does not establish that no law applies.';
    section.appendChild(unavailable);
    host.appendChild(section);
    return;
  }
  if (status === 'partial') {
    const coverage = document.createElement('p');
    coverage.className = 'hint';
    coverage.textContent = reviewPending ? 'Legal research is incomplete.'
      : 'Legal research is incomplete. Listed items use checked passages from the available corpus.';
    section.appendChild(coverage);
    const diagnostics = record?.diagnostics_by_dispute?.[row.id || row.thread_id];
    if (Array.isArray(diagnostics)) {
      for (const reason of diagnostics) {
        if (typeof reason !== 'string' || !reason.trim()) continue;
        const detail = document.createElement('p');
        detail.className = 'hint';
        detail.textContent = reason;
        section.appendChild(detail);
      }
    }
  }
  const rows = requirementsFor(record, row);
  if (!rows.length) {
    const empty = document.createElement('p');
    empty.className = 'hint';
    empty.textContent = 'No requirements are recorded for this dispute yet. '
      + 'This is not a conclusion about the governing law.';
    section.appendChild(empty);
    host.appendChild(section);
    return;
  }
  const list = document.createElement('ul');
  list.className = 'dispute-reader-requirements-list';
  for (const need of rows) {
    const item = document.createElement('li');
    const label = document.createElement('h4');
    label.textContent = need.label || 'Requirement';
    item.appendChild(label);
    for (const [title, value] of [
      ['What is needed', need.need], ['Why it matters', need.why],
      ['Legal force', reviewPending ? 'Saved interpretation; source review pending'
        : need.force === 'required' ? 'Required if cited law applies'
        : need.force === 'strengthening' ? 'Strengthening' : 'Not assessed'],
      ['Conversation record', need.record_status === 'mentioned'
        ? 'Related material was mentioned; it has not been examined.'
        : need.record_status === 'not_mentioned'
          ? 'No related material is linked in the current conversation record.'
          : 'Not assessed'],
    ]) {
      if (!value) continue;
      const detail = document.createElement('p');
      detail.textContent = `${title}: ${value}`;
      item.appendChild(detail);
    }
    if (Array.isArray(need.sources) && need.sources.length) {
      for (const source of need.sources) {
        const citation = document.createElement('p');
        citation.className = 'dispute-requirement-source';
        const label = window.NmBrainSources.labelFor(source);
        const readable = window.NmBrainSources?.isReadableRecordSource(source);
        if (readable) {
          const link = document.createElement('button');
          link.type = 'button'; link.className = 'citation-link';
          link.textContent = label;
          link.setAttribute('aria-label', `Open saved passage: ${label}`);
          link.addEventListener('click', () => window.NmBrainSources.openRecordSource(
            source, link, {reviewPending}));
          citation.appendChild(link);
        } else {
          citation.textContent = label;
        }
        item.appendChild(citation);
        const verification = source.verification;
        if (verification && verification.support_excerpt) {
          const support = document.createElement('p');
          support.textContent = `Supporting words: “${verification.support_excerpt}”`;
          item.appendChild(support);
        }
        if (verification && verification.scope_excerpt) {
          const scope = document.createElement('p');
          scope.textContent = `Limiting condition: “${verification.scope_excerpt}”`;
          item.appendChild(scope);
        }
        if (!readable) {
          const passage = document.createElement('blockquote');
          passage.textContent = source.text || '';
          item.appendChild(passage);
        }
      }
    } else {
      const missing = document.createElement('p');
      missing.className = 'hint';
      missing.textContent = 'No supporting passage is recorded for this item.';
      item.appendChild(missing);
    }
    list.appendChild(item);
  }
  section.appendChild(list);
  host.appendChild(section);
}

$('dispute-reader-close').addEventListener('click', () => closeDisputeReader());
$('dispute-reader').addEventListener('close', () => {
  const trigger = disputeReaderTrigger;
  disputeReaderTrigger = null;
  if (trigger?.isConnected && state.matterId === trigger.dataset.matterId) trigger.focus();
});

// F-B-17. WHAT THIS DISPUTE NEEDS, read in the worked dispute's detail pane.
//
// Every row states which passage requires it and shows those words, because a
// requirement an advocate cannot check is this product inventing law and
// asking them to chase it. The mark is DERIVED on the server from the file and
// from what the advocate answered; nothing here can set one.
const REQUIREMENT_MARK = {
  held: { mark: '\u2713', label: 'on the file' },
  promised: { mark: '\u25CF', label: 'promised' },
  unavailable: { mark: '\u2717', label: 'not available' },
  outstanding: { mark: '\u25CB', label: 'still outstanding' },
};

function renderRequirements(item, row) {
  if (row.requirements_state !== 'established') {
    const none = document.createElement('p');
    none.className = 'requirement-none';
    // Nothing retrieved is not the same as nothing needed, and the board must
    // not let the reader treat the first as the second.
    none.textContent = 'What this dispute needs has not been established yet.';
    item.appendChild(none);
    return;
  }
  const list = document.createElement('ul');
  list.className = 'requirement-list';
  for (const need of row.requirements || []) {
    const needsRelevanceReview = need.applicability_state === 'review_required';
    const mark = needsRelevanceReview ? { mark: '?', label: 'legal relevance needs re-review' }
      : REQUIREMENT_MARK[need.state] || REQUIREMENT_MARK.outstanding;
    const line = document.createElement('li');
    line.className = `requirement requirement--${need.state}`
      + (needsRelevanceReview ? ' requirement--review-required' : '');
    const tick = document.createElement('span');
    tick.className = 'requirement-mark'; tick.textContent = mark.mark;
    // The mark is decorative; the state is in words for anyone who cannot see
    // a colour or a glyph.
    tick.setAttribute('aria-hidden', 'true');
    line.appendChild(tick);
    const what = document.createElement('span');
    what.className = 'requirement-need';
    what.textContent = need.need;
    line.appendChild(what);
    const state = document.createElement('span');
    state.className = 'requirement-state';
    state.textContent = needsRelevanceReview ? 'legal relevance needs re-review'
      : need.state === 'promised' && need.due
      ? `promised by ${need.due}` : need.state === 'promised'
        ? 'promised — no confirmed date' : mark.label;
    line.appendChild(state);
    if (need.force === 'strengthening') {
      const force = document.createElement('span');
      force.className = 'requirement-force';
      force.textContent = 'strengthens';
      force.title = 'Read the quoted judgment for its conditions and applicability.';
      line.appendChild(force);
    }
    const basis = document.createElement('p');
    basis.className = 'requirement-basis';
    basis.textContent = (needsRelevanceReview
      ? 'Previously read passage; relevance to the corrected dispute is not established. '
      : '') + (need.basis ? `${need.source} \u00b7 ${need.basis}` : need.source);
    line.appendChild(basis);
    const span = document.createElement('blockquote');
    span.className = 'requirement-span';
    span.textContent = need.span;
    line.appendChild(span);
    list.appendChild(line);
  }
  item.appendChild(list);
  const state = document.createElement('p');
  state.className = 'requirement-summary';
  // A changed dispute needs a law-relevance review before any earlier
  // checklist can be presented as settled, even if no new question is due.
  const relevanceReviews = row.applicability_review_required || 0;
  state.textContent = relevanceReviews
    ? `${relevanceReviews} checklist item${relevanceReviews === 1 ? ' needs' : 's need'} legal relevance re-review`
      + (row.outstanding_requirements
        ? `; ${row.outstanding_requirements} still to ask about.` : '.')
    : row.requirements_settled
    ? 'Checklist follow-up complete on the available record; this is not a decision on the dispute.'
    : row.nothing_to_ask
      ? 'Nothing further to ask; waiting on what was promised.'
      : `${row.outstanding_requirements} still to ask about.`;
  item.appendChild(state);
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

function showMatterStatus(kind, message) {
  const status = $('opening-board-status');
  status.hidden = false;
  status.replaceChildren(stateBlock(kind, message));
}

function showOpeningBoardFailure(matterId, message) {
  const status = $('opening-board-status');
  status.hidden = false;
  const retry = document.createElement('button');
  retry.type = 'button';
  retry.className = 'ghost';
  retry.textContent = 'Retry matter board';
  retry.addEventListener('click', () => showThreadBoard(matterId, {
    restore: false, closeNavigator: false, deferBoard: true,
  }));
  status.replaceChildren(stateBlock('unbuildable', message), retry);
}

// BK-33. THE SERVED CONVERSATION, READ BACK.
//
// The read-back keeps what the advocate read. How each answer was made is
// not shown in the conversation (owner, 28 September 2026); it stays in the
// turn's sealed history record, and nothing here renders run numbers that
// the read-back does not carry.
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
    showConversationFromStart();
    return true;
  }

  if (generation !== state.railGeneration) return false;

  state.turns = withOpeningNotes((d.turns || []).map(restoredTurn), d.opening_changes);

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
  showConversationFromStart();
  return true;
}

/* -------------------------------------------------------------- the answer --- */


// Both matter re-entry and History consume the same release projection.
// Diagnostic presence alone never turns a withheld draft into ordinary advice.
function restoredTurn(turn) {
  // A turn whose words no record holds says so, rather than an answer to nothing.
  const briefMissing = !(turn.message || turn.asked) && turn.message_source === 'not_held';
  const documents = Array.isArray(turn.documents) ? turn.documents : [];
  if (turn.committed !== true || !['released', 'legacy_released'].includes(turn.release_state)) {
    return { brief: turn.message || turn.asked || '', briefMissing, documents, state: 'not_established',
      error: turn.blocked_reason || 'Release and successful commitment could not be established.',
      refusal: { withheld_by: turn.withheld_by || [],
        why: turn.blocked_reason || 'This archival record is not a released answer.',
        not_established: turn.not_established || [] } };
  }
  return { brief: turn.message || turn.asked || '', briefMissing, documents, answer: {
    matter_id: turn.matter_id, chat_id: turn.chat_id, turn_id: turn.turn_id,
    elements: turn.elements || [], blocked: turn.blocked,
    blocked_reason: turn.blocked_reason, metrics: null, restored: true,
    service_status: typeof turn.service_status === 'string' ? turn.service_status : null,
    // Plan AN.37: what NM asked while it worked, and how each answer came to stand.
    questions_asked: turn.questions_asked && typeof turn.questions_asked === 'object' ? turn.questions_asked : null,
    at: turn.at || '',
    board_changes: Array.isArray(turn.board_changes) ? turn.board_changes : [],
    composed: Array.isArray(turn.composed) ? turn.composed : [],
    // LB-83. The rating last saved on this reply, shown on its thumb.
    rating: typeof turn.rating === 'string' ? turn.rating : 'none',
  } };
}

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

// F-B-02. A CORRECTION OF THE OPENING DETAILS, in the conversation where it
// was made, so the record shows what changed and when. Not a turn: nothing
// was asked and nothing was answered.
function renderOpeningNote(note) {
  const wrap = document.createElement('div');
  wrap.className = 'turn opening-note';
  const head = document.createElement('p');
  head.className = 'opening-note-head';
  const when = Date.parse(note.at || '');
  head.textContent = 'You updated the matter details'
    + (Number.isNaN(when) ? '' : ` · ${new Date(when).toLocaleString()}`);
  const list = document.createElement('ul');
  for (const line of note.changes) {
    const item = document.createElement('li');
    item.textContent = line;
    list.appendChild(item);
  }
  const foot = document.createElement('p');
  foot.className = 'hint';
  foot.textContent = 'Kept beside the original details. The next reply works from these, '
    + 'and the parties are checked for conflicts again on your next message.';
  wrap.append(head, list, foot);
  return wrap;
}

// LB-83. WHEN THE ANSWER WAS SAVED, said quietly under it (owner, 28 September
// 2026), so an older reply is never mistaken for one given after later changes.
// The date and time alone -- no "Answered" (owner, the same evening).
function answeredAt(answer) {
  const when = Date.parse(answer?.at || '');
  if (Number.isNaN(when)) return null;
  const line = document.createElement('span');
  line.className = 'answered-at';
  line.textContent = new Date(when).toLocaleString(undefined, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  return line;
}

// A DISPUTE'S NAME IN BOLD (owner, 29 September 2026: the reply goes dispute by
// dispute). The one mark a composed reply may carry is **name**; it becomes a
// <strong> through the DOM, never through HTML, so no other text is ever read
// as markup. An unpaired mark is left as written.
function appendReplyBody(into, text, cites, citation) {
  // Parse the whole paragraph before dividing it around citations. A bold
  // span can contain a linked source label; parsing each side separately would
  // print its two ** markers and make the saved reply read differently.
  const words = String(text || '');
  const run = (parent, from, to) => {
    let at = from;
    for (const [start, end, index] of cites) {
      if (start < from || end > to || start < at) continue;
      if (start > at) parent.appendChild(document.createTextNode(words.slice(at, start)));
      parent.appendChild(citation(index, words.slice(start, end)));
      at = end;
    }
    if (at < to) parent.appendChild(document.createTextNode(words.slice(at, to)));
  };
  let at = 0;
  for (const mark of words.matchAll(/\*\*([^*\n]+?)\*\*/g)) {
    run(into, at, mark.index);
    const strong = document.createElement('strong');
    run(strong, mark.index + 2, mark.index + mark[0].length - 2);
    into.appendChild(strong);
    at = mark.index + mark[0].length;
  }
  run(into, at, words.length);
}

// A STEP'S DATE LINE, in one place: the reply shows it and the copy carries it.
function nextStepLine(el) {
  if (!el || !(el.by_when || el.no_deadline_reason)) return '';
  return el.by_when ? `Next step, by ${el.by_when}`
    : `Next step — no deadline: ${el.no_deadline_reason}`;
}

// LB-83, LB-98. WHAT THE COPY ICON COPIES: the reply as shown, in reading
// order, each paragraph with its next-step line and references, then one line
// naming it as NM's reply and when it was given, so a pasted copy keeps its
// date and is never mistaken for a later view (LB-83-AC4).
function replyText(answer, shown) {
  const blocks = shown.map(({ text, step, refs }) => [
    String(text || '').replace(/\*\*([^*\n]+?)\*\*/g, '$1'), nextStepLine(step),
    refs && refs.length ? `References: ${refs.join(' · ')}` : ''].filter(Boolean).join('\n'));
  const when = Date.parse(answer?.at || '');
  blocks.push(Number.isNaN(when) ? '— NM reply' : `— NM reply, ${new Date(when).toLocaleString(
    undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}`);
  return blocks.join('\n\n');
}

const REPLY_ICONS = {
  copy: 'M7.5 6.5h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z'
    + 'M13.5 6.5v-2a1 1 0 0 0-1-1h-8a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h2',
  up: 'M6 9.5v7.5H3.5V9.5z M6 9.5l3.2-6c1.1 0 1.9.9 1.9 2v2.7h4.1c.9 0 1.6.8 1.4 1.7'
    + 'l-1.1 5.9c-.1.7-.7 1.2-1.4 1.2H6',
};

function replyIcon(name, { filled = false } = {}) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 20 20');
  svg.setAttribute('width', '16'); svg.setAttribute('height', '16');
  svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
  const path = document.createElementNS(NS, 'path');
  path.setAttribute('d', REPLY_ICONS[name === 'down' ? 'up' : name]);
  if (name === 'down') path.setAttribute('transform', 'rotate(180 10 10)');
  path.setAttribute('fill', filled ? 'currentColor' : 'none');
  path.setAttribute('stroke', 'currentColor'); path.setAttribute('stroke-width', '1.5');
  path.setAttribute('stroke-linejoin', 'round'); path.setAttribute('stroke-linecap', 'round');
  svg.appendChild(path);
  return svg;
}

function replyIconButton(name, label) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'icon-btn';
  button.setAttribute('aria-label', label); button.title = label;
  button.appendChild(replyIcon(name));
  return button;
}

function closeRatePops(except = null) {
  for (const pop of document.querySelectorAll('.rate-pop:not([hidden])')) {
    if (pop === except) continue;
    pop.hidden = true;
    pop.parentElement.querySelector('.rate-toggle')?.setAttribute('aria-expanded', 'false');
  }
}

// LB-56, LB-83. THE RATING: one icon, and a pop-up holding a thumbs-up and a
// thumbs-down. Choosing the chosen thumb again withdraws it. The thumb shown
// as chosen is the rating the SERVER READ BACK after saving it, never the one
// merely clicked: a save that failed must not look like one that landed.
function rateControl(answer, status) {
  const box = document.createElement('div');
  box.className = 'rate';
  const toggle = replyIconButton('up', 'Rate this reply');
  toggle.classList.add('rate-toggle');
  toggle.setAttribute('aria-haspopup', 'true');
  toggle.setAttribute('aria-expanded', 'false');
  const pop = document.createElement('div');
  pop.className = 'rate-pop'; pop.hidden = true;
  pop.setAttribute('role', 'group'); pop.setAttribute('aria-label', 'Rate this reply');
  const up = replyIconButton('up', 'Good reply');
  const down = replyIconButton('down', 'Not a good reply');
  pop.append(up, down);

  const show = (rating) => {
    answer.rating = rating;
    up.setAttribute('aria-pressed', String(rating === 'up'));
    down.setAttribute('aria-pressed', String(rating === 'down'));
    up.replaceChildren(replyIcon('up', { filled: rating === 'up' }));
    down.replaceChildren(replyIcon('down', { filled: rating === 'down' }));
    const chosen = rating === 'up' || rating === 'down';
    toggle.dataset.rating = rating;
    toggle.replaceChildren(replyIcon(rating === 'down' ? 'down' : 'up', { filled: chosen }));
    const said = rating === 'up' ? 'You rated this reply good'
      : rating === 'down' ? 'You rated this reply not good'
      : rating === 'unknown' ? 'Your last rating of this reply could not be read back'
      : 'Rate this reply';
    toggle.title = said; toggle.setAttribute('aria-label', said);
  };
  show(answer.rating || 'none');

  const close = () => { pop.hidden = true; toggle.setAttribute('aria-expanded', 'false'); };
  toggle.addEventListener('click', () => {
    if (!pop.hidden) { close(); return; }
    closeRatePops(pop);
    pop.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    (answer.rating === 'down' ? down : up).focus();
  });
  box.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !pop.hidden) {
      event.stopPropagation();
      close();
      toggle.focus();
    }
  });
  const choose = async (want) => {
    const rating = answer.rating === want ? 'none' : want;
    up.disabled = true; down.disabled = true;
    status.textContent = '';
    try {
      const saved = await api(`/api/matters/${encodeURIComponent(answer.matter_id)}`
        + `/turns/${encodeURIComponent(answer.turn_id)}/feedback`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ rating }) });
      show(saved.rating);
      if (saved.rating === 'unknown') status.textContent = 'Your rating could not be read back.';
      close();
      toggle.focus();
    } catch (e) {
      if (e.obsolete) return;
      status.textContent = e.status === 404
        ? 'This reply cannot be rated: it is not saved as an answer on the file.'
        : 'Your rating was not saved. Try again.';
    } finally {
      up.disabled = false; down.disabled = false;
    }
  };
  up.addEventListener('click', () => choose('up'));
  down.addEventListener('click', () => choose('down'));
  box.append(toggle, pop);
  return box;
}

// LB-83, LB-98. THE FOOT OF EVERY REPLY (owner, 28 September 2026): at its left
// corner, copy, then rate, then the date and time. 'Copied' is said only once
// the browser confirms; a refused copy says so and stays said.
function replyFooter(entry, copyText) {
  const answer = entry.answer;
  const foot = document.createElement('div');
  foot.className = 'reply-foot';
  const status = document.createElement('span');
  status.className = 'reply-status';
  status.setAttribute('role', 'status');
  const copy = replyIconButton('copy', 'Copy this reply');
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(copyText());
      status.textContent = 'Copied';
      setTimeout(() => { if (status.textContent === 'Copied') status.textContent = ''; }, 2500);
    } catch {
      status.textContent = 'Copy was not permitted by the browser. The reply stays selectable.';
    }
  });
  foot.appendChild(copy);
  if (answer.matter_id && answer.turn_id) foot.appendChild(rateControl(answer, status));
  // THE NOTE OFFERED PLAINLY (plan AN.49, D186): the conversation shows the advice with the detail folded; the note holds
  // all of it opened out, with every source, so the foot of every answer says so.
  if (noteAvailable(answer)) foot.appendChild(noteControl(answer, status, 'The full note, with every source:'));
  const at = answeredAt(answer);
  if (at) foot.appendChild(at);
  // Plan AN.33 (D23): the model and the effort the answer ran with, as the turn recorded them.
  const chosen = answer.metrics && answer.metrics.chosen;
  if (chosen && chosen.model) {
    const names = { 'gpt-6-luna': '6 Luna', 'gpt-6.1-terra': '6.1 Terra', 'gpt-6.1-sol': '6.1 Sol' };
    const line = document.createElement('span');
    line.className = 'reply-chosen';
    line.textContent = `${names[chosen.model] || chosen.model} · ${String(chosen.effort || 'medium').replace(/^./, (c) => c.toUpperCase())}`;
    foot.appendChild(line);
  }
  foot.appendChild(status);
  return foot;
}

// A RESEARCH NOTE (owner decisions, 15 Oct 2026): one saved answer as a document, built
// by the server from the saved turn. Word by default, downloaded as a file; PDF as an
// option, printed from the same note so every script renders with this device's fonts.
function noteAvailable(answer) {
  return Boolean(answer && answer.chat_id && answer.turn_id && !answer.blocked
    && Array.isArray(answer.elements) && answer.elements.some((el) => el.kind !== 'HEADING'));
}

function noteUrl(answer) {
  return `/api/chats/${encodeURIComponent(answer.chat_id)}/turns/${encodeURIComponent(answer.turn_id)}/note`;
}

// called: what the control is called where it stands - under an answer, what the note holds (AN.49, D186); in the matter's
// files, under their heading 'Research notes', the plain name.
function noteControl(answer, status, called = 'Research note:') {
  const box = document.createElement('span');
  box.className = 'note-control';
  const label = document.createElement('span');
  label.className = 'note-label';
  label.textContent = called;
  const word = document.createElement('button');
  word.type = 'button'; word.className = 'ghost note-format';
  word.textContent = 'Word';
  word.setAttribute('aria-label', 'Save this answer as a research note in Word');
  word.addEventListener('click', () => downloadNoteWord(answer, status));
  const pdf = document.createElement('button');
  pdf.type = 'button'; pdf.className = 'ghost note-format';
  pdf.textContent = 'PDF';
  pdf.setAttribute('aria-label', 'Save this answer as a research note in PDF (opens the print window)');
  pdf.addEventListener('click', () => printNote(answer, status));
  box.append(label, word, pdf);
  return box;
}

function noteFileName(disposition) {
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition || '');
  if (encoded) {
    try { return decodeURIComponent(encoded[1]); } catch { /* fall back to the plain name */ }
  }
  const plain = /filename="([^"]+)"/i.exec(disposition || '');
  return plain ? plain[1] : 'Research note.docx';
}

async function downloadNoteWord(answer, status) {
  status.textContent = 'Preparing the Word file…';
  try {
    const res = await fetch(`${noteUrl(answer)}.docx`);
    if (!res.ok) {
      let why = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        why = (body.detail && (body.detail.why || body.detail)) || why;
      } catch { /* not a JSON refusal */ }
      throw new Error(typeof why === 'string' ? why : `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = noteFileName(res.headers.get('content-disposition'));
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 30000);
    status.textContent = 'Research note saved as a Word file';
  } catch (error) {
    status.textContent = `The research note could not be prepared: ${error.message}`;
  }
}

// The note laid out for printing; the print window's Save as PDF makes the file.
function noteDocument(doc, note) {
  const add = (parent, tag, text, className) => {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node);
    return node;
  };
  const style = doc.createElement('style');
  style.textContent = '@page { size: A4; margin: 18mm 20mm; }'
    + 'body { font-family: Calibri, "Segoe UI", "Nirmala UI", "Noto Sans", sans-serif; font-size: 11pt;'
    + ' line-height: 1.45; color: #1b1b1b; }'
    + 'h1 { font-family: Cambria, Georgia, serif; font-weight: 400; color: #185748; font-size: 22pt; margin: 0 0 4pt; }'
    + 'h2 { color: #185748; font-size: 14pt; margin: 18pt 0 6pt; } h3 { font-size: 12pt; margin: 12pt 0 4pt; }'
    + '.meta { color: #666; font-size: 9pt; } .refs { color: #555; font-size: 9pt; }'
    + 'blockquote { margin: 4pt 0 8pt 14pt; padding-left: 8pt; border-left: 2pt solid #bbb; color: #333;'
    + ' font-size: 10pt; white-space: pre-wrap; } .source { font-weight: 700; font-size: 10pt; margin: 10pt 0 2pt;'
    + ' break-after: avoid; } p { margin: 0 0 8pt; white-space: pre-wrap; }'
    + '.working { margin: 0 0 2pt 14pt; font-size: 10pt; } .working b { font-weight: 700; }';
  doc.head.appendChild(style);
  doc.title = note.file_name;
  const body = doc.body;
  add(body, 'h1', note.title);
  add(body, 'p', `Prepared for ${note.prepared_for} · ${note.prepared_at}`, 'meta');
  add(body, 'h2', 'Question');
  add(body, 'blockquote', note.question);
  if (note.documents.length) {
    add(body, 'h3', 'Documents sent with it');
    for (const item of note.documents) {
      const unread = item.pages_unread ? `, ${item.pages_unread} not read` : '';
      add(body, 'p', item.recording
        ? `• ${item.name} — recording, ${item.pages_read ? 'transcribed' : 'not transcribed'}`
        : `• ${item.name} — ${item.pages_read} page${item.pages_read === 1 ? '' : 's'} read${unread}`);
    }
  }
  add(body, 'h2', 'Answer');
  for (const block of note.blocks) {
    if (block.kind === 'heading') { add(body, 'h3', block.text); continue; }
    if (block.kind === 'working') {
      add(body, 'p', `Working: ${block.text}`, 'source');
      for (const [label, value] of block.rows) {
        const line = add(body, 'p', undefined, 'working');
        add(line, 'b', `${label}: `);
        add(line, 'span', value);
      }
      for (const [title, items] of block.lists) {
        add(body, 'p', `${title}:`, 'working');
        for (const item of items) add(body, 'p', `• ${item}`, 'working');
      }
      continue;
    }
    const paragraph = add(body, 'p', block.text);
    if (block.refs.length) add(paragraph, 'span', ` [${block.refs.join(', ')}]`, 'refs');
  }
  if (note.sources.length) {
    add(body, 'h2', 'Sources');
    for (const source of note.sources) {
      add(body, 'p', source.heading, 'source');
      for (const passage of source.passages) add(body, 'blockquote', passage);
    }
  }
  add(body, 'p', note.provenance, 'meta');
}

async function printNote(answer, status) {
  status.textContent = 'Preparing the PDF…';
  let note;
  try {
    note = await api(noteUrl(answer));
  } catch (error) {
    status.textContent = `The research note could not be prepared: ${error.message}`;
    return;
  }
  const frame = document.createElement('iframe');
  frame.className = 'note-print-frame';
  frame.setAttribute('aria-hidden', 'true');
  document.body.appendChild(frame);
  const doc = frame.contentDocument;
  doc.open();
  doc.write('<!doctype html><html lang="en"><head><meta charset="utf-8"><title></title></head><body></body></html>');
  doc.close();
  noteDocument(doc, note);
  frame.contentWindow.addEventListener('afterprint', () => frame.remove());
  frame.contentWindow.focus();
  frame.contentWindow.print();
  status.textContent = 'In the print window, choose “Save as PDF”.';
}

// LB-90. WHAT THIS MESSAGE CHANGED ON THE BOARD, and what waits for you
// (owner, 28 September 2026). Applied lines come from the saved file; a
// proposal changed nothing, and its button goes through the same attributed,
// version-checked owner every other correction uses.
const BOARD_APPLIED = new Set(['dispute_opened', 'statements_added', 'dated_event', 'corrected',
  'question_answered', 'party_added', 'side_recorded', 'kept_apart']);

function renderBoardNote(entry) {
  const changes = Array.isArray(entry.answer?.board_changes) ? entry.answer.board_changes : [];
  if (!changes.length) return null;
  const box = document.createElement('div');
  box.className = 'board-note';
  const applied = changes.filter((c) => BOARD_APPLIED.has(c.kind));
  const waiting = changes.filter((c) => !BOARD_APPLIED.has(c.kind));
  const section = (title, rows) => {
    if (!rows.length) return;
    const head = document.createElement('p');
    head.className = 'board-note-head';
    head.textContent = title;
    const list = document.createElement('ul');
    for (const change of rows) {
      const item = document.createElement('li');
      const text = document.createElement('span');
      text.textContent = change.text;
      item.appendChild(text);
      const act = boardAction(entry, change);
      if (act) item.appendChild(act);
      list.appendChild(item);
    }
    box.append(head, list);
  };
  section('On the matter board', applied);
  section('Waiting for you', waiting);
  return box;
}

function boardAction(entry, change) {
  const matterId = entry.answer?.matter_id || state.matterId;
  const button = (label, run) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'ghost board-act'; b.textContent = label;
    b.addEventListener('click', async () => {
      if (b.disabled) return;
      b.disabled = true;
      const said = document.createElement('span');
      said.className = 'board-act-state';
      said.textContent = ' Saving…';
      b.after(said);
      try {
        said.textContent = ` ${await run()}`;
        if (matterId === state.matterId) {
          await showThreadBoard(matterId, { restore: false, closeNavigator: false }).catch(() => {});
        }
      } catch (e) {
        if (e.obsolete) return;
        b.disabled = false;
        said.textContent = e.status === 409
          ? ' Not changed: the file has moved or this entry was already changed. The board shows it as it is now.'
          : ` Not changed: ${e.message}`;
      }
    });
    return b;
  };
  // THE VERSION IS READ FROM THE SERVER, not from this page: the note may be
  // in History, or on a reply older than the file the board now shows.
  const version = async () => {
    const current = await api(`/api/matters/${encodeURIComponent(matterId)}`);
    if (!Number.isInteger(current?.version)) throw new Error('the matter could not be read');
    return current;
  };
  const correct = async (factId, body) => {
    const current = await version();
    const out = await api(`/api/matters/${encodeURIComponent(matterId)}/facts/`
      + `${encodeURIComponent(factId)}/corrections`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ ...body, expected_version: current.version }),
    });
    if (matterId === state.matterId && Number.isInteger(out?.version)) {
      state.matterVersion = out.version;
    }
    return out;
  };
  const parties = async (change) => {
    const current = await version();
    const form = current.opening_form;
    if (!form) throw new Error('the matter details could not be read');
    const next = { ...(form.parties || {}) };
    if (change.kind === 'proposed_party_removal') delete next[change.target];
    else next[change.target] = change.value;
    // The recorded other-party state follows the parties, exactly as the form
    // requires: removing the last named other party leaves them unknown.
    const brief = { ...(form.brief || {}) };
    const others = Object.values(next).some((side) => side !== 'client');
    if (others) brief.other_party_state = 'identified';
    else if (brief.other_party_state === 'identified') brief.other_party_state = 'not_known';
    const out = await api(`/api/matters/${encodeURIComponent(matterId)}/opening`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ request_key: `opening_${newTurnId().slice(5)}`,
        expected_version: current.version, title: form.title, parties: next, brief }),
    });
    if (matterId !== state.matterId) return 'Done. The matter details now show it.';
    if (Number.isInteger(out?.version)) state.matterVersion = out.version;
    if (out?.state === 'opening_corrected' && Array.isArray(out.changes) && out.changes.length) {
      state.turns.push({ note: { at: new Date().toISOString(), changes: out.changes.map(String) } });
      repaint();
    }
    return 'Done. The matter details now show it, and the history keeps the change.';
  };
  if (!matterId) return null;
  if (change.kind === 'corrected' && change.target && change.was) {
    return button('Undo', async () => {
      await correct(change.target, { statement: change.was,
        ...(change.was_date ? { date: change.was_date } : {}),
        reason: 'Undo: the earlier entry was right' });
      return 'Undone. The earlier entry is back, and both remain in the history.';
    });
  }
  if (change.kind === 'proposed_withdrawal' && change.target) {
    return button('Withdraw it', async () => {
      await correct(change.target, { withdraw: true,
        reason: 'Withdrawn at the advocate’s request in the conversation' });
      return 'Withdrawn. It stays in the history, and nothing runs from it now.';
    });
  }
  if (['proposed_party_removal', 'proposed_party_move'].includes(change.kind) && change.target) {
    return button('Confirm', () => parties(change));
  }
  if (change.kind === 'held_other_matter') {
    const span = document.createElement('span');
    // Only on the open matter's own conversation, where the words are held and
    // a resend lands on this file.
    if (entry.brief && matterId === state.matterId
        && document.body.dataset.pane === 'advise') {
      span.appendChild(button('Keep it in this matter', async () => {
        await send(entry.brief, { keepInMatter: true });
        return 'Sent again, kept in this matter.';
      }));
    }
    const fresh = document.createElement('button');
    fresh.type = 'button'; fresh.className = 'ghost board-act';
    fresh.textContent = 'Start a new matter';
    fresh.addEventListener('click', startMatter);
    span.appendChild(fresh);
    return span;
  }
  return null;
}

// Each correction goes before the first turn known to come after it.
function withOpeningNotes(turns, changes) {
  const time = (value) => { const t = Date.parse(value || ''); return Number.isNaN(t) ? null : t; };
  const out = [...turns];
  for (const change of Array.isArray(changes) ? changes : []) {
    if (!change || !Array.isArray(change.changes) || !change.changes.length) continue;
    const at = time(change.at);
    const later = at === null ? -1 : out.findIndex((entry) => {
      const t = time(entry.note ? entry.note.at : entry.answer?.at);
      return t !== null && t > at;
    });
    out.splice(later < 0 ? out.length : later, 0,
      { note: { at: change.at, changes: change.changes.map(String) } });
  }
  return out;
}

function renderTurn(entry) {
  if (entry.note) return renderOpeningNote(entry.note);
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
    // The documents sent with this message, by name (owner decisions, 15 Oct 2026).
    if (Array.isArray(entry.documents) && entry.documents.length) {
      const sent = document.createElement('ul');
      sent.className = 'brief-documents';
      sent.setAttribute('aria-label', 'Documents sent with this message');
      // Each by its name (the design of 17 Oct 2026), with a note only where something
      // was not read.
      for (const item of entry.documents) {
        const li = document.createElement('li');
        const unread = item.pages_unread ? ` · ${item.pages_unread} page${item.pages_unread === 1 ? '' : 's'} not read`
          : '';
        li.textContent = item.recording ? `${item.name}${item.pages_read ? '' : ' · not transcribed'}`
          : `${item.name}${unread}`;
        sent.appendChild(li);
      }
      b.appendChild(sent);
    }
    row.appendChild(b);
    wrap.appendChild(row);
  } else if (entry.briefMissing) {
    const row = document.createElement('div');
    row.className = 'said-row';
    const b = document.createElement('div');
    b.className = 'brief brief-missing';
    b.textContent = 'The original message for this turn is not available in the '
      + 'conversation record.';
    row.appendChild(b);
    wrap.appendChild(row);
  }

  // PLAN AN.41 (D69-D71): AN ANSWER THAT STOPPED PART-WAY says so in the conversation, in red, in code's own words - why, what is
  // finished and what is not - with Continue and Discard in that message and nowhere else. What it finished is shown under it.
  if (entry.state === 'stopped' && !entry.answer) {
    wrap.appendChild(renderStopped(entry));
    if (Array.isArray(entry.shownElements) && entry.shownElements.length) wrap.appendChild(renderShownSoFar(entry.shownElements));
    return wrap;
  }
  if (entry.state === 'reconnecting' && !entry.answer) {
    const waiting = document.createElement('div');
    waiting.className = 'el ground turn-progress';
    waiting.textContent = 'NM is being restarted. Your message is saved; this answer goes on as soon as NM is back.';
    wrap.appendChild(waiting);
    if (Array.isArray(entry.shownElements) && entry.shownElements.length) wrap.appendChild(renderShownSoFar(entry.shownElements));
    return wrap;
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
    } else if (refusal?.code === 'usage_limit') {
      // THE AI ACCOUNT'S USAGE IS USED UP (owner decisions O18 and P51, 25 Oct 2026; plan AN.11
      // piece 4, AN.14): the owner's words as the server sent them, said plainly - not as a
      // message NM failed to complete. Whether the message was saved follows below, as for any
      // refusal.
      f.className = 'failure limit';
      const head = document.createElement('p');
      head.className = 'refusal-head';
      head.textContent = refusal.why;
      f.appendChild(head);
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
        ? `I couldn't confirm the response: ${entry.error}`
        : `I couldn't complete this message: ${entry.error}`;
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
      input_only: 'Your brief is saved. The proposed answer was withheld and no '
                + 'new conclusions were saved. Review the recorded file, then '
                + 'tell NM how you would like to continue.',
      stale: 'This matter moved while you were writing. I have re-read it — '
           + 'check the answer above, then send again if it still applies.',
      unknown: 'I could not tell whether your brief was saved. Sending again '
             + 'is safe: it carries the same turn id, so if it did land the '
             + 'server recognises it rather than recording it twice.',
      replay_refused: 'The earlier response remains saved, but cannot be replayed '
                     + 'under the current permission. No new answer was saved or released. '
                     + 'Review the current declaration before making a new request.',
    };
    if (entry.state === 'not_committed' && entry.refusal?.retryable === false) {
      SAID.not_committed = 'Your brief was NOT saved. Sending the same turn '
        + 'again will not resolve this limit.';
    }
    if (SAID[entry.state]) {
      const d = document.createElement('div');
      d.className = 'refusal-gap';
      d.textContent = SAID[entry.state];
      f.appendChild(d);
    }
    if (entry.turnId && ['unknown', 'not_committed'].includes(entry.state)
        && entry.refusal?.retryable !== false) {
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
  // A turn takes minutes (owner decision, 14 Oct 2026): while it works the
  // page shows the stage it has reached, the time so far and the stages done.
  if (!entry.answer) {
    const progress = entry.progress;
    // WHAT THE ANSWER HAS SHOWN SO FAR (owner decisions P26-P27, 19 Oct 2026): each part as
    // it passes its checks, saved with the conversation as it is shown.
    const soFar = Array.isArray(entry.shownElements) && entry.shownElements.length
      ? renderShownSoFar(entry.shownElements) : null;
    if (!progress || progress.state !== 'working') {
      const pending = document.createElement('div');
      pending.className = 'el ground';
      pending.textContent = 'Preparing a response…';
      wrap.appendChild(pending);
      if (soFar) wrap.appendChild(soFar);
      return wrap;
    }
    const took = (seconds) => {
      const s = Number.isInteger(seconds) && seconds > 0 ? seconds : 0;
      return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
    };
    const box = document.createElement('div');
    box.className = 'el ground turn-progress';
    const detail = progress.detail || {};
    let label = progress.label || 'Preparing a response';
    if (Number.isInteger(detail.total) && Number.isInteger(detail.done) && detail.total > 0) {
      label += `: question ${Math.min(detail.done + 1, detail.total)} of ${detail.total}`;
    } else if (Number.isInteger(detail.total) && detail.total > 0) {
      label += ` (${detail.total} legal ${detail.total === 1 ? 'question' : 'questions'})`;
    } else if (Number.isInteger(detail.round)) {
      label += ` (round ${detail.round})`;
    }
    const now = document.createElement('div');
    now.className = 'progress-now';
    now.textContent = `${label}…`;
    const time = document.createElement('div');
    time.className = 'progress-time';
    // Plan AN.48 (48e, D140): a step worked step by step says how long it should take - tentative.
    const tentative = Number.isInteger(progress.tentative_seconds) ? Math.max(1, Math.round(progress.tentative_seconds / 60)) : 0;
    time.textContent = tentative
      ? `${took(progress.elapsed_seconds)} so far. This step should take about ${tentative} minute${tentative === 1 ? '' : 's'} `
        + '(tentative).'
      : `${took(progress.elapsed_seconds)} so far. Most answers take a few minutes.`;
    box.append(now, time);
    if (entry.restartNote) box.appendChild(Object.assign(document.createElement('div'), {
      className: 'progress-note', textContent: entry.restartNote }));
    // D79: what the advocate added is in the answer being worked on.
    for (const steer of entry.steers || []) box.appendChild(Object.assign(document.createElement('div'), {
      className: 'progress-steer', textContent: `Added while NM worked: ${steer}` }));
    // D68: the work finished so far, read from the saved conversation; each part's state from the progress.
    const work = renderWork(entry.work, progress.parts || {},
      { chat_id: entry.chatId || (entry.context && entry.context.chatId) || null, turn_id: entry.turnId });
    if (work) box.appendChild(work);
    const done = (progress.steps || []).slice(0, -1);
    if (done.length) {
      const list = document.createElement('ol');
      list.className = 'progress-steps';
      for (const step of done) {
        const item = document.createElement('li');
        item.textContent = `${step.label} · ${took(step.seconds)}`;
        list.appendChild(item);
      }
      box.appendChild(list);
    }
    if (progress.asking) {
      // Plan AN.37: NM has asked something only the advocate can settle; the window opens from here too.
      const asked = document.createElement('div');
      asked.className = 'progress-question';
      asked.appendChild(document.createTextNode('NM has a question for you. '));
      const open = document.createElement('button');
      open.type = 'button';
      open.className = 'ghost';
      open.textContent = 'Answer';
      open.addEventListener('click', () => openTurnQuestions(entry));
      asked.appendChild(open);
      box.appendChild(asked);
    }
    wrap.appendChild(box);
    if (soFar) wrap.appendChild(soFar);
    return wrap;
  }

  // THE ANSWER'S OWN HEADER (plan AN.20; the signed-off design): who is speaking, and when this
  // answer was made - the NM mark, Nyaymalaw and the time. The time is the one saved with the
  // answer; an answer saved without one shows none, and nothing is made up in its place.
  const head = document.createElement('div');
  head.className = 'reply-head';
  const headMark = document.createElement('span');
  headMark.className = 'reply-head-mark';
  headMark.setAttribute('aria-hidden', 'true');
  headMark.textContent = 'NM';
  const headName = document.createElement('span');
  headName.className = 'reply-head-name';
  headName.textContent = 'Nyaymalaw';
  head.appendChild(headMark);
  head.appendChild(headName);
  const madeAt = Date.parse(entry.answer.at || '');
  if (!Number.isNaN(madeAt)) {
    const headTime = document.createElement('time');
    headTime.className = 'reply-head-time';
    headTime.dateTime = new Date(madeAt).toISOString();
    headTime.textContent = new Date(madeAt).toLocaleString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    head.appendChild(headTime);
  }
  wrap.appendChild(head);

  // A READ-BACK TURN IS SHOWN AS IT WAS SERVED, without a notice (owner, 28
  // September 2026). A retry that recovered the earlier saved answer instead
  // of making a new one still says so: the advocate asked just now.
  if (entry.answer.replayed) {
    wrap.appendChild(stateBlock('quiet',
      'Earlier recorded response recovered. This is not a new assessment; the file may have changed since it was prepared.'));
  }

  if (typeof entry.answer.service_status === 'string' && entry.answer.service_status.trim()) {
    const status = stateBlock('quiet service-status', entry.answer.service_status);
    status.setAttribute('role', 'status');
    wrap.appendChild(status);
  }
  if (entry.answer.questions_asked && Array.isArray(entry.answer.questions_asked.questions)) {
    wrap.appendChild(renderQuestionsAsked(entry.answer.questions_asked));
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
  // LB-76. THE REPLY, told from the checked findings as one colleague tells
  // another and checked again, on its own words, by the server. Where there is
  // one it is what the advocate reads; where there is none the checked
  // findings are shown as they are, exactly as before.
  const composed = Array.isArray(entry.answer.composed) ? entry.answer.composed : [];
  let support = composed.length ? [] : entry.answer.elements.filter(foldsAsSupport);
  let spoken = composed.length ? [] : entry.answer.elements.filter((el) => !foldsAsSupport(el));

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

  // The validated answer already has a reading order. Present its prose,
  // not its internal section/type/signal taxonomy, and never reclassify it
  // with another model. Metadata remains available in the response record.
  const rows = [];
  for (const el of spoken) {
    const same = (el.signal && el.signal !== 'none') ? -1
      : rows.findIndex((r) => r.el.kind === el.kind
                           && r.el.thread === el.thread
                           && r.el.section === el.section
                           && r.el.text.trim() === el.text.trim()
                           && JSON.stringify(r.el.refs) === JSON.stringify(el.refs)
                           && JSON.stringify(r.el.source) === JSON.stringify(el.source)
                           && r.el.disclosure === el.disclosure
                           && r.el.by_when === el.by_when
                           && r.el.no_deadline_reason === el.no_deadline_reason);
    if (same >= 0) rows[same].said += 1;
    else rows.push({ el, said: 1 });
  }
  renderParts(wrap, groupAnswerElements(rows.map((row) => row.el)), entry, renderElement);
  for (const paragraph of composed) renderParagraph(wrap, paragraph);

  // The step and the saved passage a composed paragraph points at, by index.
  function paragraphLinks(paragraph) {
    const at = (index) => (Number.isInteger(index) ? entry.answer.elements[index] : null) || null;
    return { carried: at(paragraph.carries), linked: at(paragraph.passage) };
  }

  // ONE PARAGRAPH OF THE REPLY. Plain prose. A paragraph that carries a step in
  // its own words keeps the step's date line; a paragraph that relies on a
  // saved passage links it, opening the same source reader as the finding.
  function renderParagraph(into, paragraph) {
    const d = document.createElement('div');
    d.className = 'el reply';
    const body = document.createElement('p');
    body.className = 'body';
    // LB-76 change 5. INLINE CITATIONS: each is the saved source's own label,
    // placed by the server, and opens the reader at that exact passage.
    const cites = (Array.isArray(paragraph.cites) ? paragraph.cites : [])
      .filter((c) => {
        if (!Array.isArray(c) || c.length !== 3) return false;
        const [start, end, index] = c;
        return Number.isInteger(start) && Number.isInteger(end) && Number.isInteger(index)
          && 0 <= start && start < end && end <= paragraph.text.length
          && entry.answer.elements[index]?.source?.label === paragraph.text.slice(start, end);
      })
      .sort((a, b) => a[0] - b[0]);
    appendReplyBody(body, paragraph.text, cites,
      (index, label) => inlineCitation(entry.answer.elements[index], label));
    d.appendChild(body);
    const { carried, linked } = paragraphLinks(paragraph);
    if (nextStepLine(carried)) {
      const w = document.createElement('span');
      w.className = 'when';
      w.textContent = nextStepLine(carried);
      d.appendChild(w);
    }
    if (linked && linked.refs && linked.refs.length && !linked.source?.brain) {
      const r = document.createElement('span');
      r.className = 'refs'; fillReferences(r, linked);
      d.appendChild(r);
    }
    into.appendChild(d);
  }

  // ONE PARAGRAPH OF THE ANSWER, its links kept; lead: words of code's own before it.
  function answerParagraph(el, lead) {
    const d = document.createElement('div');
    d.className = `el ${el.kind}`;
    const body = document.createElement('p');
    body.className = 'body';
    if (lead) {
      const strong = document.createElement('strong');
      strong.textContent = `${lead} `;
      body.appendChild(strong);
    }
    if (linkedBody(el)) window.NmBrainSources.appendBody(body, entry.answer, el);
    else body.appendChild(document.createTextNode(el.text));
    d.appendChild(body);
    return d;
  }

  function renderInShortTable(el) {
    const make = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const box = make('section', 'in-short');
    box.setAttribute('aria-label', el.text);
    box.appendChild(make('h3', 'in-short-title', el.text));
    const table = make('table', 'in-short-table');
    const head = make('tr');
    for (const label of ['Dispute', 'What to do', 'By when', 'Have ready']) head.appendChild(make('th', '', label));
    const thead = make('thead');
    thead.appendChild(head);
    const body = make('tbody');
    const asOf = new Set();
    const cell = (paragraph) => {
      const td = make('td', 'in-short-cell');
      if (!paragraph) td.textContent = '—';
      else if (linkedBody(paragraph)) window.NmBrainSources.appendBody(td, entry.answer, paragraph);
      else td.textContent = paragraph.text;
      return td;
    };
    const byWhen = (by) => {
      const td = make('td', 'in-short-when');
      if (!by) { td.textContent = '—'; return td; }
      if (by.not_assessed) { td.appendChild(make('span', 'limit-why', `Not worked out: ${by.not_assessed}`)); return td; }
      td.appendChild(make('strong', 'in-short-day', dayDate(by.last_day) || by.day));
      if (Number.isInteger(by.days) && by.days_label) {
        const count = `${by.days} ${by.days === 1 ? 'day' : 'days'} ${by.days_label.slice(5)}`;
        td.appendChild(make('span', 'in-short-left', by.result === 'Open' ? count : `${by.result} · ${count}`));
      } else if (by.result) {
        td.appendChild(make('span', 'in-short-left', by.result));
      }
      if (by.as_of) asOf.add(by.as_of);
      return td;
    };
    for (const { row, action, ready } of el.rows) {
      const line = make('tr');
      const name = make('th', 'in-short-dispute', row.text);
      name.scope = 'row';
      line.appendChild(name);
      const info = row.row || {};
      if (info.status === 'shown') {
        line.append(cell(action), byWhen(info.by_when), cell(ready));
      } else {
        const note = make('td', 'in-short-note', info.status === 'waiting' ? 'Still being written and checked.'
          : `Not a full answer: ${info.why}.`);
        note.colSpan = 3;
        line.appendChild(note);
      }
      body.appendChild(line);
    }
    table.append(thead, body);
    const scroll = make('div', 'in-short-scroll');
    scroll.appendChild(table);
    box.appendChild(scroll);
    if (asOf.size === 1) box.appendChild(make('p', 'time-limit-note', `Days are counted as of ${[...asOf][0]}.`));
    for (const line of el.lines) box.appendChild(answerParagraph(line, line.kind === 'DO_FIRST' ? 'Do first:' : ''));
    return box;
  }

  function renderElement(into, el) {
    if (el.kind === 'WORKING' && el.working) {
      into.appendChild(renderWorking(el));
      return;
    }
    // "IN SHORT" (owner decisions, 17 Oct 2026): each dispute's summary, together, before
    // the disputes themselves; each keeps its own links.
    if (el.kind === 'IN_SHORT') {
      const box = document.createElement('section');
      box.className = 'in-short';
      box.setAttribute('aria-label', 'In short');
      const title = document.createElement('h3');
      title.className = 'in-short-title';
      title.textContent = 'In short';
      box.appendChild(title);
      // One point for each dispute, as a short list (the design of 17 Oct 2026).
      const points = document.createElement('ul');
      points.className = 'in-short-list';
      for (const item of el.items) {
        const point = document.createElement('li');
        renderElement(point, item);
        points.appendChild(point);
      }
      box.appendChild(points);
      into.appendChild(box);
      return;
    }
    if (el.kind === 'TIME_LIMITS') {
      into.appendChild(renderTimeLimits(el.items));
      return;
    }
    // "IN SHORT" AS ONE TABLE (owner decision P40, 24 Oct 2026; rendering v18): a row for each
    // dispute - what to do, by when as code worked it out, what to have ready - then the line on
    // what to do first and what ties the disputes together. Each cell keeps its own links.
    if (el.kind === 'IN_SHORT_TABLE') {
      into.appendChild(renderInShortTable(el));
      return;
    }
    if (el.kind === 'SUBHEAD') {
      const title = document.createElement('h4');
      title.className = 'answer-subhead';
      title.textContent = el.text;
      into.appendChild(title);
      return;
    }
    // What could still go wrong as a list, the next steps numbered (P41).
    if (el.kind === 'RISKS' || el.kind === 'STEPS') {
      const list = document.createElement(el.kind === 'STEPS' ? 'ol' : 'ul');
      list.className = `answer-list ${el.kind === 'STEPS' ? 'steps' : 'risks'}`;
      for (const item of el.items) {
        const point = document.createElement('li');
        renderElement(point, item);
        list.appendChild(point);
      }
      into.appendChild(list);
      return;
    }
    // MORE ON THIS (P41): reasoning that does not change the advice, folded; every paragraph in
    // it keeps its links. A paragraph the review says the advice depends on is never here.
    if (el.kind === 'MORE_FOLD') {
      const fold = document.createElement('details');
      fold.className = 'more-fold';
      const opener = document.createElement('summary');
      opener.textContent = 'More on this';
      fold.appendChild(opener);
      for (const item of el.items) renderElement(fold, item);
      into.appendChild(fold);
      return;
    }
    // WHAT YOUR PAPERS RECORD (plan AN.33, D20; piece 33m): every point NM read from the papers, built by code from the
    // record and folded at the end, so that none is lost whatever the advice takes up; what NM could not check on a page, a
    // date found nowhere, the differences between papers and what was set aside are each said as such.
    // WHAT MAKES THE CASE STRONGER (plan AN.35; rendering v20), beside its dispute's section.
    // PLAN AN.49 (49a; D177, D185, D187a-b; owner, 12 Nov 2026: "a more crisper and sharper summary in the chat window"): the answer
    // opens on the advice. The whole account is folded, drawn closed, for every answer saved or new - nothing saved changes. What
    // must not be missed stands outside the fold, in code's words from the saved case: how the requirements stand, what there is to
    // get, a quotation NM could not find, a second look that could not be made, and how the list was checked. A case with no
    // requirement is one sentence and stays open.
    if (el.kind === 'CASE' && el.case) {
      const view = el.case;
      const listed = view.elements || [];
      const fold = document.createElement('details');
      fold.className = 'answer-checked answer-case';
      fold.open = !listed.length;
      const opener = document.createElement('summary');
      opener.textContent = listed.length ? `${el.text}: the whole list (${listed.length})` : el.text;
      fold.appendChild(opener);
      fold.append(...renderCaseBlock(view, caseHolderOf(entry.answer)));
      if (listed.length) {
        const say = (className, text) => {
          const line = document.createElement('p');
          line.className = className;
          line.textContent = text;
          return line;
        };
        const stand = (status) => listed.filter((item) => item.status === status).length;
        const shown = stand('shown');
        const weak = stand('weak');
        const toGet = (view.to_get || []).length;
        const unfound = [...listed, ...(view.other_side || [])].filter((item) => item.law && item.law.found === false).length;
        const summary = document.createElement('div');
        summary.className = 'case-summary';
        summary.appendChild(say('board-lede', `NM set out ${listed.length} ${listed.length === 1 ? 'thing' : 'things'} the law `
          + `requires for this dispute: ${shown} shown by the papers, ${weak} shown only weakly, `
          + `${listed.length - shown - weak} not yet shown.${toGet ? ` ${toGet} to get.` : ''}`
          + `${unfound ? ` For ${unfound} of its points NM could not find the quoted words in the law it read.` : ''}`));
        if (CASE_STATES[view.state]) summary.appendChild(say('check-none', CASE_STATES[view.state]));
        summary.appendChild(say('board-lede', caseCheckedLine(view)));
        if (el.dispute && el.dispute.name) {
          const where = document.createElement('button');
          where.type = 'button';
          where.className = 'cite';
          where.textContent = 'Show this dispute on the matter board';
          where.addEventListener('click', () => {
            const card = Array.from(document.querySelectorAll('.board-disputes .dispute'))
              .find((dispute) => dispute.getAttribute('aria-label') === el.dispute.name);
            if (!card) return;
            // A board of several disputes shows one open at a time (49c, D180): this one is opened, as its own button opens it.
            const toggle = card.querySelector('.dispute-toggle');
            if (toggle && toggle.getAttribute('aria-expanded') === 'false') toggle.click();
            card.scrollIntoView({ block: 'nearest' });
            const title = card.querySelector('.dtitle');
            if (title) title.focus();
          });
          const line = document.createElement('p');
          line.className = 'req-law';
          line.appendChild(where);
          summary.appendChild(line);
        }
        into.appendChild(summary);
      }
      into.appendChild(fold);
      return;
    }
    if (el.kind === 'PAPERS' && el.papers) {
      const make = (tag, className, text) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
      };
      const events = el.papers.events || [];
      const fold = make('details', 'answer-checked answer-papers');
      fold.appendChild(make('summary', '', `${el.text} (${events.length} ${events.length === 1 ? 'point' : 'points'})`));
      fold.appendChild(make('p', 'board-lede', 'Every point NM read from your papers, whether or not the advice above takes it '
        + 'up. Each is as its paper says it, not proved; check anything that matters against the paper itself.'));
      const dated = events.filter((event) => event.dated);
      const undated = events.filter((event) => !event.dated);
      if (dated.length) fold.append(make('h4', 'board-h', 'In date order'), ...eventRows(dated, make));
      if (undated.length) fold.append(make('h4', 'board-h', 'Not dated in the paper'), ...eventRows(undated, make));
      const where = (places) => places.map((place) => `${place.document}, page ${place.page}`).join('; ');
      const together = el.papers.together || [];
      if (together.length) {
        fold.appendChild(make('h4', 'board-h', 'Read side by side'));
        const list = make('ul', 'board-list');
        for (const item of together) {
          const said = `${SIDE_BY_SIDE[item.kind] || SIDE_BY_SIDE.other}: ${item.point}${item.why ? ` — ${item.why}` : ''}`;
          list.appendChild(make('li', item.located ? '' : 'board-status search_failed', item.located
            ? `${said} · ${where(item.places)}` : `${said} · its words were not found on the pages, so it rests on nothing yet`));
        }
        fold.appendChild(list);
      }
      const aside = el.papers.set_aside || [];
      if (aside.length) {
        fold.appendChild(make('h4', 'board-h', 'Set aside after checking'));
        const list = make('ul', 'board-list');
        for (const item of aside) list.appendChild(make('li', '', `${item.what} · ${item.document} · ${item.why}`));
        fold.appendChild(list);
      }
      const unread = el.papers.unread || [];
      if (unread.length) {
        fold.appendChild(make('h4', 'board-h', 'Not read'));
        const list = make('ul', 'board-list');
        for (const item of unread) {
          list.appendChild(make('li', 'board-status search_failed', `${item.document}, pages ${item.pages}: NM could not read these, `
            + 'so nothing on them is listed'));
        }
        fold.appendChild(list);
      }
      into.appendChild(fold);
      return;
    }
    // HOW NM CHECKED THIS ANSWER (P39): what the independent check still suggests could be
    // added, put better or go, in its own words, by part, folded at the end.
    if (el.kind === 'CHECKED' && Array.isArray(el.checked)) {
      const fold = document.createElement('details');
      fold.className = 'answer-checked';
      const opener = document.createElement('summary');
      opener.textContent = el.text;
      fold.appendChild(opener);
      const said = { better: 'Could add or put better', could_go: 'Could go' };
      for (const part of el.checked) {
        const name = document.createElement('p');
        name.className = 'checked-part';
        name.textContent = part.part;
        const list = document.createElement('ul');
        list.className = 'checked-list';
        for (const suggestion of part.suggestions || []) {
          const point = document.createElement('li');
          const kind = document.createElement('span');
          kind.className = 'checked-kind';
          kind.textContent = `${said[suggestion.kind] || 'Suggested'}: `;
          point.append(kind, document.createTextNode(suggestion.text));
          list.appendChild(point);
        }
        fold.append(name, list);
      }
      into.appendChild(fold);
      return;
    }
    // WHAT I NEED FROM YOU (the design of 17 Oct 2026; rendering v14): the questions to the
    // advocate, together at the end of the answer, each keeping its own links.
    if (el.kind === 'NEEDS' && Array.isArray(el.items)) {
      const box = document.createElement('section');
      box.className = 'need';
      box.setAttribute('aria-label', el.text);
      const title = document.createElement('h3');
      title.className = 'need-title';
      title.textContent = el.text;
      // From rendering v18 (P44): each dispute's items asked for, once, each opening its item,
      // and its questions for no item; then the advocate's choices under "Your call".
      const parts = [];
      let asks = null;
      for (const item of el.items) {
        if (item.kind === 'NEED_GROUP' || item.kind === 'YOUR_CALL') {
          const label = document.createElement('p');
          label.className = 'need-group';
          label.textContent = item.text;
          parts.push(label);
          asks = null;
          continue;
        }
        if (!asks) {
          asks = document.createElement('ul');
          asks.className = 'need-list';
          parts.push(asks);
        }
        const ask = document.createElement('li');
        if (item.kind === 'NEED_CASE' && item.need) {
          // Rendering v20: what to get for a dispute's case, from whom and why. Plan AN.39 (D55): its words open the point of the
          // case it is for, in the reading pane, as the board's point does.
          const point = caseElementFor(entry.answer, item.dispute, item.need.for);
          if (point) {
            const open = document.createElement('button');
            open.type = 'button';
            open.className = 'cite need-item';
            open.textContent = item.need.what;
            open.setAttribute('aria-label', `Open what it is for: ${point.item.label || point.item.element}`);
            open.addEventListener('click', () => window.NmBrainSources.showContent(point.item.label || point.item.element,
              renderCaseItem(point.item, point.view, item.dispute || {}, caseHolderOf(entry.answer)), open, false,
              `What the law requires · ${(item.dispute && item.dispute.name) || 'this dispute'}`));
            ask.append(open, document.createTextNode(` — from ${item.need.from_whom}. ${item.need.why}`));
          } else {
            ask.appendChild(document.createTextNode(`${item.need.what} — from ${item.need.from_whom}. ${item.need.why}`));
          }
        } else if (item.kind === 'NEED_ITEM' && item.item) {
          const open = document.createElement('button');
          open.type = 'button';
          open.className = 'cite need-item';
          open.textContent = item.text;
          open.setAttribute('aria-label', `Open the checklist item: ${item.text}`);
          open.addEventListener('click', () => openAskedItem(entry.answer, { dispute: item.dispute, item: item.item }, open));
          ask.appendChild(open);
        } else {
          renderElement(ask, item);
        }
        asks.appendChild(ask);
      }
      // Plan AN.37 (piece 37a): what NM asks here, answered in a window, each in a box of its own.
      const questions = needQuestions(el.items);
      if (questions.length) {
        const answer = document.createElement('button');
        answer.type = 'button';
        answer.className = 'ghost need-answer';
        answer.textContent = questions.length === 1 ? 'Answer this' : 'Answer these';
        answer.addEventListener('click', () => openNeedAnswers(entry, questions));
        parts.push(answer);
      }
      box.append(title, ...parts);
      into.appendChild(box);
      return;
    }
    // A NOTE IN A SECTION'S PLACE (owner decision P25, 19 Oct 2026; rendering v17): where
    // nothing of a dispute's section survived its rewrites, the server's own note, said to be
    // no full answer: why, the facts as the advocate gave them, the provisions found in their
    // own words, and what NM's working understanding says is still open.
    if (el.kind === 'FALLBACK' && el.fallback) {
      const box = document.createElement('section');
      box.className = 'el FALLBACK disclosure';
      box.setAttribute('aria-label', 'Not a full answer');
      const why = document.createElement('p');
      why.className = 'body';
      why.textContent = String(el.text || '').split('\n')[0];
      box.appendChild(why);
      const listed = (title, items, draw) => {
        if (!Array.isArray(items) || !items.length) return;
        const label = document.createElement('p');
        label.className = 'fallback-label';
        label.textContent = title;
        const list = document.createElement('ul');
        list.className = 'fallback-list';
        for (const item of items) {
          const row = document.createElement('li');
          draw(row, item);
          list.appendChild(row);
        }
        box.append(label, list);
      };
      listed('What you told me', el.fallback.facts, (row, words) => { row.textContent = `“${words}”`; });
      listed('Provisions found for this dispute', el.fallback.provisions, (row, provision) => {
        const where = document.createElement('span');
        where.className = 'fallback-where';
        where.textContent = `${provision.title}, ${provision.locator}${provision.in_force ? ` (${provision.in_force})` : ''}`;
        const words = document.createElement('blockquote');
        words.className = 'fallback-words';
        words.textContent = provision.words;
        row.append(where, words);
      });
      listed('Still needed, as NM understands it', el.fallback.still_needed, (row, need) => { row.textContent = need; });
      listed('Open questions', el.fallback.questions, (row, question) => { row.textContent = question; });
      into.appendChild(box);
      return;
    }
    // A SECTION EDITED AFTER IT WAS CHECKED (owner decision P27, 19 Oct 2026; rendering v17):
    // the label says what the check across the sections found; the section as first shown
    // stays to read under "See original".
    if (el.kind === 'EDITED' && el.edited) {
      const box = document.createElement('div');
      box.className = 'el EDITED disclosure';
      const label = document.createElement('p');
      label.className = 'body';
      const tag = document.createElement('span');
      tag.className = 'edited-tag';
      tag.textContent = 'Edited';
      label.append(tag, document.createTextNode(` ${el.text}`));
      const original = document.createElement('details');
      original.className = 'edited-original';
      const opener = document.createElement('summary');
      opener.textContent = 'See original';
      original.appendChild(opener);
      for (const paragraph of el.edited.original || []) {
        const shown = document.createElement('p');
        shown.textContent = paragraph.text;
        original.appendChild(shown);
      }
      box.append(label, original);
      into.appendChild(box);
      return;
    }
    const d = document.createElement('div');
    // A loud signal is never collapsed, whatever the server says about
    // collapsibility -- the client does not get to quiet it.
    // A DISCLOSURE is not an assertion, and it must not look like one.
    // "Here is the law" and "here is what I could not establish" rendered
    // identically is how a gap becomes a finding in the reader's memory.
    d.className = `el ${el.kind}${el.disclosure ? ' disclosure' : ''}`;
    const body = document.createElement('p');
    body.className = 'body';
    if (linkedBody(el)) window.NmBrainSources.appendBody(body, entry.answer, el);
    else body.textContent = el.text;
    d.appendChild(body);

    if (nextStepLine(el)) {
      const w = document.createElement('span');
      w.className = 'when';
      // SAID AS THE NEXT STEP. The section headings went with the plain-
      // language pass (602e3f0), and with them the only words that told the
      // advocate this paragraph is what to do next -- a recommended step with
      // no date read as one more paragraph of analysis. Every ACTION carries
      // this line, so this is where it is named.
      w.textContent = nextStepLine(el);
      d.appendChild(w);
    }
    if (el.refs && el.refs.length && !el.source?.brain) {
      const r = document.createElement('span');
      r.className = 'refs'; fillReferences(r, el);
      d.appendChild(r);
    }
    // A SECTION HELD BACK (owner decision, 17 Oct 2026): the advocate decides what next.
    // Trying again puts the request in the message box, to send as it is or with a fact,
    // a document or a narrower question added first.
    if (el.kind === 'HELD' && el.held && el.held.retry) {
      const again = document.createElement('button');
      again.type = 'button';
      again.className = 'ghost held-retry';
      again.textContent = 'Try this section again';
      again.setAttribute('aria-label', `Put a request to try the section on ${el.held.section} again in the message box`);
      again.addEventListener('click', () => {
        const box = $('message');
        box.value = box.value.trim() ? `${box.value.trim()}\n${el.held.retry}` : el.held.retry;
        box.dispatchEvent(new Event('input', { bubbles: true }));
        sizeComposer();
        box.focus();
      });
      d.appendChild(again);
    }
    into.appendChild(d);
  }

  // One inline citation: a link into the reader where the saved source is bound
  // to this answer, the label as plain words where it is not. Never a link
  // manufactured for a source the answer does not hold.
  function inlineCitation(el, label) {
    const bound = el && el.source && el.refs.includes(el.source.locator)
      && (entry.answer.matter_id || (el.source.brain && entry.answer.chat_id))
      && entry.answer.turn_id;
    if (!bound || !el.source.brain || !window.NmBrainSources) {
      return document.createTextNode(label);
    }
    const link = document.createElement('button');
    link.type = 'button'; link.className = 'citation-link';
    link.textContent = label;
    link.setAttribute('aria-label', `Open saved passage: ${label}`);
    link.addEventListener('click', () => window.NmBrainSources.open(
      entry.answer, el, entry.answer.elements.indexOf(el), 0, link));
    return link;
  }

  function fillReferences(row, el) {
    if (el.source?.brain) return;
    // Preserve historical references without linking a retired source reader.
    const label = document.createElement('span'); label.textContent = el.refs.join(' · ');
    row.appendChild(label);
    const note = document.createElement('span'); note.className = 'source-unavailable';
    note.textContent = ' · saved source inspection unavailable';
    row.appendChild(note);
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
      const body = document.createElement('p');
      body.className = 'body';
      if (linkedBody(el)) window.NmBrainSources.appendBody(body, entry.answer, el);
      else body.textContent = el.text;
      d.appendChild(body);
      if (el.refs && el.refs.length && !el.source?.brain) {
        const r = document.createElement('span');
        r.className = 'refs'; fillReferences(r, el);
        d.appendChild(r);
      }
      fold.appendChild(d);
    }
    wrap.appendChild(fold);
  }

  // P24's INTAKE-READINESS BLOCK ("intake open", "NM has not completed the
  // review of every dispute") is no longer drawn under a reply (owner, 28
  // September 2026, LB-166): the matter board's per-dispute view carries what
  // each dispute needs. The served `briefing` field is unchanged.

  const note = renderBoardNote(entry);
  if (note) wrap.appendChild(note);
  // The copy is built when the icon is pressed, from exactly what is shown.
  const shown = [
    ...rows.map(({ el }) => ({ text: el.text, step: el, refs: el.refs })),
    ...composed.map((paragraph) => {
      const { carried, linked } = paragraphLinks(paragraph);
      // Inline citation labels are already in these exact words. Their raw
      // locators were never printed beside the prose, so the copy must not
      // append them as a second, internal-looking reference list.
      return { text: paragraph.text, step: carried, refs: linked?.refs };
    }),
    ...support.map((el) => ({ text: el.text, step: null, refs: el.refs })),
  ];
  wrap.appendChild(replyFooter(entry, () => replyText(entry.answer, shown)));

  // HOW THIS ANSWER WAS MADE -- gates, reads, calls and cost -- is not shown
  // in the conversation (owner, 28 September 2026). It is kept, in full and
  // sealed with the matter, in the turn's own history record for review.
  // NOR IS THE RECORDED WORK BEHIND IT (owner, the same day: "Remove, keep
  // saved"; LB-139). The saved working stages stay sealed with the matter and
  // readable through the owned progress reads, for the owner's review.
  return wrap;
}

// WHAT I NEED FROM YOU, ANSWERED IN A WINDOW (plan AN.37, D37 and D43, piece 37a; owner, 3 Nov 2026: "ask a question to the
// user as a pop up with ... optional free text"): each thing NM asked for under "What I need from you", with the dispute it is
// for, gets a box of its own; the answers go to NM as the advocate's next message, each under the question it answers, in their
// own words. Nothing is sent for a question left blank.
function needQuestions(items) {
  const questions = [];
  let group = null;
  for (const item of items || []) {
    if (item.kind === 'NEED_GROUP') { group = String(item.text || '').trim() || null; continue; }
    // What is the advocate's call is asked across the disputes, not for one of them.
    if (item.kind === 'YOUR_CALL') { group = null; continue; }
    const text = item.kind === 'NEED_CASE' && item.need
      ? `${item.need.what} — from ${item.need.from_whom}` : String(item.text || '').trim();
    if (text) questions.push({ group, text });
  }
  return questions;
}

function needAnswersMessage(questions, answers) {
  const said = [];
  questions.forEach((question, index) => {
    const answer = String((answers || [])[index] || '').trim();
    if (!answer) return;
    said.push(`${question.group ? `On ${question.group}, you` : 'You'} asked: “${question.text}”\nMy answer: ${answer}`);
  });
  return said.length ? `My answers to your questions:\n\n${said.join('\n\n')}` : '';
}

// The same window for other rows (plan AN.49, 49f; D183): its title, the line under it, what it says when nothing is written and how
// what was written becomes the one message, as 'Tell NM about these' on a dispute uses it.
function openNeedAnswers(entry, questions, {
  called = 'Answer what NM asked',
  lede = 'Answer what you can and leave the rest blank. Your answers go to NM as your next message, each under the question it answers.',
  empty = 'Write an answer to at least one question.',
  compose = (answers) => needAnswersMessage(questions, answers),
} = {}) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  // What was written and not yet sent is kept with the answer it belongs to while the page is open.
  const key = JSON.stringify(questions);
  if (!entry.needDrafts) entry.needDrafts = {};
  const drafts = entry.needDrafts[key] || (entry.needDrafts[key] = questions.map(() => ''));
  const dialog = make('dialog', 'account-dialog need-answers');
  dialog.setAttribute('aria-labelledby', 'need-answers-title');
  const heading = make('div', 'dialog-heading');
  const title = make('h2', '', called);
  title.id = 'need-answers-title';
  const close = make('button', 'ghost', 'Close');
  close.type = 'button';
  close.addEventListener('click', () => dialog.close());
  heading.append(title, close);
  dialog.append(heading, make('p', '', lede));
  const boxes = questions.map((question, index) => {
    const box = make('textarea');
    box.id = `need-answer-${index}`;
    const label = make('label', 'need-answer-question');
    label.htmlFor = box.id;
    if (question.group) label.appendChild(make('strong', '', `${question.group}: `));
    label.appendChild(document.createTextNode(question.text));
    box.rows = 3;
    box.value = drafts[index];
    box.style.width = '100%';
    box.style.boxSizing = 'border-box';
    box.style.font = 'inherit';
    box.addEventListener('input', () => { drafts[index] = box.value; });
    label.style.display = 'block';
    label.style.margin = '0.9rem 0 0.3rem';
    dialog.append(label, box);
    return box;
  });
  if (attachments.length) {
    dialog.appendChild(make('p', 'quiet', 'The documents attached under the message box go with your answers.'));
  }
  const status = make('p', '');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const sendAnswers = make('button', 'primary', 'Send answers');
  sendAnswers.type = 'button';
  const cancel = make('button', 'ghost', 'Cancel');
  cancel.type = 'button';
  cancel.addEventListener('click', () => dialog.close());
  sendAnswers.addEventListener('click', () => {
    const message = compose(boxes.map((box) => box.value));
    if (!message) { status.textContent = empty; return; }
    if (usageUsedUp()) { status.textContent = (usage && usage.limit) || 'Sending is paused until you upgrade.'; return; }
    const blocked = attachmentsBlockSend({ reading: false });
    if (blocked) { status.textContent = blocked; return; }
    if (heldSend) { status.textContent = 'Another message is waiting for its files to be read. Send your answers once it has gone.'; return; }
    if (activeDelivery) {
      // A message of this conversation is being answered: the answers are sent as soon as it is saved, as anything added
      // meanwhile is (15 Oct 2026). Another conversation's message is never given them.
      if (activeDelivery.entry.context !== entry.context) {
        status.textContent = 'Another message is being answered. Send your answers once it is done.';
        return;
      }
      const intent = entry.context;
      if (!Array.isArray(intent.queued)) intent.queued = [];
      intent.queued.push(message);
    } else if (state.matterId && !state.matterReady) {
      status.textContent = 'This conversation is still loading. Try again in a moment.';
      return;
    }
    entry.needDrafts[key] = questions.map(() => '');
    dialog.close();
    if (activeDelivery) repaint();
    else send(message);
  });
  const actions = make('div', 'dialog-actions');
  actions.style.display = 'flex';
  actions.style.gap = '0.75rem';
  actions.style.marginTop = '1rem';
  actions.append(sendAnswers, cancel);
  dialog.append(status, actions);
  dialog.addEventListener('close', () => dialog.remove());
  document.body.appendChild(dialog);
  dialog.showModal();
  if (boxes.length) boxes[0].focus();
}

// WHAT NM ASKS WHILE IT WORKS (plan AN.37, D37-D40, D44; owner, 3 Nov 2026: "ask a question to the user as a pop up with MCQs,
// radial buttons, multicheck or optional free text -- same as Claude"). The progress says a window is open; the questions are
// read from the advocate's own turn, each shown with what depends on it, its choices - one, or several ticked - and a box for
// their own words. NM waits two minutes for the answers before going on with the defaults it names; the window stays open ten,
// and a later answer is still taken. Once the message is answered, the answers go as the next message instead.
function turnQuestionAnswers(questions, answered) {
  // As the next message: each question under its heading, with the answer chosen or written.
  return needAnswersMessage(questions.map((question) => ({ group: null, text: question.question })),
    questions.map((question) => answered[question.id] ? [...answered[question.id].chosen,
      ...(answered[question.id].other ? [answered[question.id].other] : [])].join('; ') : ''));
}

function askedLine(question, entry) {
  const said = [...(entry.chosen || []), ...(entry.other ? [entry.other] : [])].join('; ');
  return entry.how === 'assumed' ? `No answer came in time, so NM went on assuming: ${said}`
    : entry.how === 'late' ? `You answered after NM had gone on: ${said}` : `You answered: ${said}`;
}

// given (plan AN.48, 48d): a matter waiting for the advocate - { view, said, submit(answers) } - whose questions its stop shows and
// whose answers go to the matter; none - the window of a turn being worked on, as before.
async function openTurnQuestions(entry, given = null) {
  if (entry.questionsOpen || !entry.turnId) return;
  entry.questionsOpen = true;
  let view;
  try {
    view = given ? given.view : await api(`/api/turn-question?turn_id=${encodeURIComponent(entry.turnId)}`);
  } catch {
    entry.questionsOpen = false;  // nothing is asked now, or it could not be read; the progress says again if it is
    return;
  }
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const taken = Object.fromEntries((view.answers || []).filter((item) => item.how !== 'assumed')
    .map((item) => [item.id, item]));
  const dialog = make('dialog', 'account-dialog turn-questions');
  dialog.setAttribute('aria-labelledby', 'turn-questions-title');
  const heading = make('div', 'dialog-heading');
  const title = make('h2', '', view.questions.length === 1 ? 'NM has a question for you' : 'NM has questions for you');
  title.id = 'turn-questions-title';
  const later = make('button', 'ghost', 'Not now');
  later.type = 'button';
  later.addEventListener('click', () => dialog.close());
  heading.append(title, later);
  dialog.append(heading, make('p', '', given ? given.said : view.defaults_applied
    ? 'NM went on with the answers it names below. If yours differ, answer now and it will redo what depends on them.'
    : 'NM is waiting for your answer before it writes the parts that depend on it; after two minutes it goes on with the '
      + 'answer it names below.'));
  const fields = view.questions.map((question, number) => {
    const set = make('fieldset', 'turn-question');
    set.style.margin = '1rem 0 0';
    set.style.border = '0';
    set.style.padding = '0';
    set.appendChild(make('legend', '', `${question.header}: ${question.question}`));
    set.appendChild(make('p', 'quiet', question.why));
    const assumed = (view.answers || []).find((item) => item.id === question.id && item.how === 'assumed');
    set.appendChild(make('p', 'quiet', assumed ? askedLine(question, assumed) : given
      ? `NM's own answer, were you to go on end to end: ${question.default.join('; ')}`
      : `If you do not answer, NM goes on with: ${question.default.join('; ')}`));
    if (taken[question.id]) {
      set.appendChild(make('p', '', askedLine(question, taken[question.id])));
      dialog.appendChild(set);
      return { question, done: true };
    }
    const inputs = question.choices.map((choice, index) => {
      const label = make('label', 'consent');
      label.style.display = 'flex';
      label.style.gap = '0.5rem';
      const input = make('input');
      input.type = question.multiple ? 'checkbox' : 'radio';
      input.name = `turn-question-${number}`;
      input.value = choice.label;
      input.id = `turn-question-${number}-${index}`;
      label.htmlFor = input.id;
      const words = make('span', '', choice.label);
      if (choice.description) words.appendChild(make('span', 'quiet', ` — ${choice.description}`));
      label.append(input, words);
      set.appendChild(label);
      return input;
    });
    const own = make('textarea');
    own.rows = 2;
    own.placeholder = 'Or answer in your own words';
    own.setAttribute('aria-label', `Your own answer: ${question.question}`);
    own.style.width = '100%';
    own.style.boxSizing = 'border-box';
    own.style.font = 'inherit';
    set.appendChild(own);
    dialog.appendChild(set);
    return { question, inputs, own };
  });
  const status = make('p', '');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const sendAnswers = make('button', 'primary', 'Send answers');
  sendAnswers.type = 'button';
  sendAnswers.addEventListener('click', async () => {
    const answers = {};
    for (const field of fields) {
      if (field.done) continue;
      const chosen = field.inputs.filter((input) => input.checked).map((input) => input.value);
      const other = field.own.value.trim();
      if (chosen.length || other) answers[field.question.id] = { chosen, other };
    }
    if (!Object.keys(answers).length) { status.textContent = 'Choose an answer or write your own.'; return; }
    if (given) { dialog.close(); given.submit(answers); return; }
    sendAnswers.disabled = true;
    try {
      await api('/api/turn-question', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ turn_id: entry.turnId, answers }) });
      dialog.close();
    } catch (error) {
      sendAnswers.disabled = false;
      if (error.status === 409 && error.detail?.code === 'window_closed') {
        // NM has finished this message: the answers go as the next one (D44), as anything added meanwhile would.
        const message = turnQuestionAnswers(view.questions, answers);
        dialog.close();
        if (activeDelivery && activeDelivery.entry.context === entry.context) {
          if (!Array.isArray(entry.context.queued)) entry.context.queued = [];
          entry.context.queued.push(message);
          repaint();
        } else if (!activeDelivery) {
          send(message);
        } else {
          $('message').value = [message, $('message').value].filter((text) => text.trim()).join('\n\n');
          sizeComposer();
        }
        return;
      }
      status.textContent = error.message;
    }
  });
  const actions = make('div', 'dialog-actions');
  actions.style.display = 'flex';
  actions.style.gap = '0.75rem';
  actions.style.marginTop = '1rem';
  actions.append(sendAnswers);
  dialog.append(status, actions);
  dialog.addEventListener('close', () => {
    entry.questionsOpen = false;
    entry.questionsSeen = true;
    entry.questionsSeenCount = view.questions.length;
    dialog.remove();
    repaint();
  });
  document.body.appendChild(dialog);
  dialog.showModal();
}

// What a saved answer asked while it was worked on, above the answer it shaped (plan AN.37).
function renderQuestionsAsked(asked) {
  const box = document.createElement('section');
  box.className = 'questions-asked quiet';
  box.setAttribute('aria-label', 'What NM asked while working');
  const title = document.createElement('p');
  title.className = 'need-group';
  title.textContent = 'What NM asked while working';
  box.appendChild(title);
  const list = document.createElement('ul');
  list.className = 'need-list';
  const answers = Object.fromEntries((asked.answers || []).map((item) => [item.id, item]));
  for (const question of asked.questions || []) {
    const item = document.createElement('li');
    item.textContent = `${question.question} ${answers[question.id] ? askedLine(question, answers[question.id])
      : 'Not answered.'}`;
    list.appendChild(item);
  }
  box.appendChild(list);
  return box;
}

// Opening a saved matter starts with its first turn. New live replies still
// follow the latest turn through the send path.
function showConversationFromStart() {
  const t = $('thread');
  t.scrollTop = 0;
  $('jump-latest').hidden = t.scrollHeight <= t.clientHeight;
}

// THE MATTER BOARD ON THE LEFT (owner decisions, 16 Oct 2026), laid out as the readability
// design shows it (owner, 18 Oct 2026: "exactly the way your artifact has presented"). It is
// read from the conversation's saved understanding, read again after every answer, and while
// NM works it says what NM is doing. A dispute, a checklist item and the files open in the
// reading pane on the right, beside the answer.

// What NM is doing on this conversation's message, shown on its board.
function syncBoardStatus() {
  const status = $('board-status');
  const working = Boolean(activeDelivery && activeIntent && activeDelivery.entry.context === activeIntent);
  const label = working && activeDelivery.entry.progress && activeDelivery.entry.progress.label;
  status.hidden = !working;
  status.textContent = working
    ? `NM is working on your latest message${label ? `: ${label}.` : '…'} The board updates as each dispute's section is checked.`
    : '';
}

function renderBoardWaiting() {
  $('matter-board-meta').textContent = '';
  $('matter-board-body').replaceChildren(stateBlock('empty',
    'The board fills in as NM understands this matter from your messages and the documents you send.'));
  fitBoard();
}

// THE BOARD ONLY WHEN IT HAS SOMETHING ON IT (owner decision P38, 21 Oct 2026): a new matter
// shows the conversation alone, and the board appears once it holds what NM worked out - or
// says it could not be read, as a failure to read is never hidden as an empty board. A board
// waiting for its first content, or being read for the first time, is not shown. On a phone
// the board's button goes with it; a board opened there stays open across its re-reads.
function fitBoard() {
  const filled = Array.from($('matter-board-body').children).some((child) =>
    !/\bstate (empty|building)\b/.test(typeof child.className === 'string' ? child.className : ''));
  $('pane-advise').classList.toggle('has-board', filled);
}

async function loadChatBoard(chatId = activeIntent && activeIntent.chatId) {
  if (!chatId) { renderBoardWaiting(); return; }
  const host = $('matter-board-body');
  const generation = (state.boardGeneration = (state.boardGeneration || 0) + 1);
  // A board already shown stays in view while it is read again after an answer.
  if (!host.children.length || host.dataset.chatId !== chatId) {
    host.replaceChildren(stateBlock('building', 'Reading this matter’s board…'));
    fitBoard();
  }
  let board;
  try {
    board = await api(`/api/chats/${encodeURIComponent(chatId)}/board`);
  } catch (error) {
    if (generation !== state.boardGeneration) return;
    host.replaceChildren(stateBlock('unbuildable', `The board could not be read: ${error.message}. `
      + 'This is a failure to read, not an empty matter.'));
    fitBoard();
    return;
  }
  // A first answer still being written names its conversation before it is saved (P26).
  if (generation !== state.boardGeneration || !activeIntent
      || (activeIntent.chatId && activeIntent.chatId !== chatId)) return;
  host.dataset.chatId = chatId;
  state.chatBoard = board;
  host.replaceChildren(...renderChatBoard(board));
  fitBoard();
}

// THE FILES (owner decisions 4 and 5, 17 Oct 2026): the Files button beside the board's
// title opens, in the reading pane, the files sent in this conversation - each name opens the
// file as sent in a new tab, "Read here" what NM read - and each answer as a research note.
function openBoardFiles() {
  const chatId = activeIntent && activeIntent.chatId;
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const files = make('div', 'reader-files');
  const note = make('p', 'reader-note', 'The name opens the file as sent in a new tab. “Read here” shows what NM read.');
  const notes = make('section', 'detail-section');
  const notesBody = make('div');
  notes.append(make('h3', 'detail-h', 'Research notes'), notesBody);
  window.NmBrainSources.showContent('Files in this matter', [files, note, notes], $('board-files'), false,
    'Matter files');
  renderChatNotes(notesBody);
  if (!chatId) {
    files.replaceChildren(stateBlock('empty', 'Files appear here once this conversation is saved. '
      + 'Attach them with the + under your message.'));
    return Promise.resolve();
  }
  return loadChatDocuments(files);
}

$('board-files').addEventListener('click', () => openBoardFiles());

// The conversation's answers, each to keep as a research note (Word or PDF).
function renderChatNotes(host) {
  const answers = state.turns.filter((entry) => noteAvailable(entry.answer));
  if (!answers.length) {
    host.replaceChildren(stateBlock('empty', 'No answer in this matter can be kept as a research note yet.'));
    return;
  }
  const lede = document.createElement('p');
  lede.className = 'board-lede';
  lede.textContent = 'Each answer as a research note: the question, the answer and every source it cites, '
    + 'quoted as saved. Word by default; PDF opens the print window.';
  host.replaceChildren(lede, ...answers.map((entry) => {
    const card = document.createElement('article');
    card.className = 'board-card note-card';
    const question = document.createElement('p');
    question.className = 'note-question';
    question.textContent = entry.brief.length > 200 ? `${entry.brief.slice(0, 200)}…` : entry.brief;
    const foot = document.createElement('div');
    foot.className = 'reply-foot';
    const status = document.createElement('span');
    status.className = 'reply-status';
    status.setAttribute('role', 'status');
    foot.appendChild(noteControl(entry.answer, status));
    const at = answeredAt(entry.answer);
    if (at) foot.appendChild(at);
    foot.appendChild(status);
    card.append(question, foot);
    return card;
  }));
}

async function loadChatDocuments(host) {
  const chatId = activeIntent && activeIntent.chatId;
  if (!chatId) return;
  host.replaceChildren(stateBlock('building', 'Reading the files sent in this matter…'));
  let listing;
  try {
    listing = await api(`/api/chats/${encodeURIComponent(chatId)}/documents`);
  } catch (error) {
    if (!host.isConnected) return;
    host.replaceChildren(stateBlock('unbuildable', `The files could not be read: ${error.message}. `
      + 'This is a failure to read, not an empty list.'));
    return;
  }
  // Something else opened in the pane meanwhile: this list is no longer shown.
  if (!host.isConnected || !activeIntent || activeIntent.chatId !== chatId) return;
  host.replaceChildren(...renderChatDocuments(listing, (document_, turn, opener) =>
    window.NmBrainSources.showContent(document_.name, renderDocumentPages(document_, turn), opener, false,
      document_.recording ? 'Voice note you sent' : 'Document you sent')));
}

// THE MATTER'S FILES (owner decision 4, 17 Oct 2026): a plain list. Each name opens the
// file exactly as sent in a new tab (a Word file downloads, to open in Word); "Read here"
// shows what NM read. A note appears only when something needs attention.
const FILE_KINDS = { pdf: ['PDF', 'PDF'], docx: ['DOC', 'Word'], text: ['TXT', 'Text'], image: ['IMG', 'Photo'] };

// A file's size is written by the one fileSize below, with the matter's records.
function fileDate(iso) {
  const day = typeof iso === 'string' ? new Date(iso) : null;
  return day && !Number.isNaN(day.getTime())
    ? day.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
}

// A calendar day code saved ('2029-03-10'), as the design writes it: '10 Mar 2029'.
function dayDate(iso) {
  const day = typeof iso === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00Z`) : null;
  return day && !Number.isNaN(day.getTime())
    ? day.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '';
}

// The day and month of a moment saved, '18 Oct'.
function dayMonth(iso) {
  const day = typeof iso === 'string' ? new Date(iso) : null;
  return day && !Number.isNaN(day.getTime()) ? day.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '';
}

function fileAttention(document_) {
  const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
  if (document_.recording) return document_.pages.length ? '' : 'Not transcribed';
  const notes = [];
  if (document_.unread.length) notes.push(`${plural(document_.unread.length, 'page')} could not be read`);
  const partly = document_.pages.filter((page) => page.legible === 'part').length;
  if (partly) notes.push(`${plural(partly, 'page')} partly legible`);
  return notes.join(' · ');
}

function renderChatDocuments(listing, open) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const sent = listing && Array.isArray(listing.sent) ? listing.sent : [];
  if (!sent.length) {
    return [stateBlock('empty', 'No files have been sent in this matter yet. '
      + 'Attach them with the + under your message.')];
  }
  const list = make('ul', 'file-list');
  for (const turn of sent) {
    const preview = turn.message.length > 140 ? `${turn.message.slice(0, 140)}…` : turn.message;
    for (const document_ of turn.documents) {
      const file = document_.file || null;
      const format = file ? file.format : '';
      const [tile, kind] = FILE_KINDS[format] || (document_.recording ? ['REC', 'Recording'] : ['FILE', 'File']);
      const row = make('li', 'file-row');
      row.title = `Sent with: “${preview}”`;
      const mark = make('span', `file-tile file-${FILE_KINDS[format] ? format : (document_.recording ? 'audio' : 'other')}`, tile);
      mark.setAttribute('aria-hidden', 'true');
      const body = make('div', 'file-body');
      const name = document.createElement('a');
      name.className = 'file-name';
      name.textContent = document_.name;
      name.href = `/api/documents/${encodeURIComponent(document_.document_ref)}/original`;
      name.target = '_blank';
      name.rel = 'noopener';
      if (format === 'docx') name.setAttribute('aria-label', `${document_.name}, opens in Word`);
      const byAi = document_.pages.some((page) => page.read_by === 'ai');
      const when = file ? fileDate(file.received_at) : '';
      const meta = [kind, file ? fileSize(file.size) : '', when ? `sent ${when}` : '',
        format === 'docx' ? 'opens in Word' : '',
        byAi ? (document_.recording ? 'transcribed by AI' : 'read by AI') : ''].filter(Boolean).join(' · ');
      body.append(name, make('div', 'file-meta', meta));
      const attention = fileAttention(document_);
      if (attention) body.appendChild(make('div', 'file-attention', attention));
      const read = make('button', 'file-read', 'Read here');
      read.type = 'button';
      read.setAttribute('aria-label', `Read here: ${document_.name}`);
      read.addEventListener('click', () => open(document_, turn, read));
      body.appendChild(read);
      row.append(mark, body);
      list.appendChild(row);
    }
  }
  return [list];
}

// WHAT NM READ, AS ONE DOCUMENT (owner decision 5, 17 Oct 2026): every page in one flow,
// a small mark where each page begins and how it was read, and in place of a page that
// could not be read, why. The file as sent opens from the top.
function renderDocumentPages(document_, turn) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const entries = [...document_.pages.map((page) => ({ number: page.number, page })),
    ...document_.unread.map((unread) => ({ number: unread.number, unread }))]
    .sort((left, right) => left.number - right.number);
  const preview = turn.message.length > 140 ? `${turn.message.slice(0, 140)}…` : turn.message;
  const where = make('p', 'source-where', document_.recording ? 'As NM transcribed it'
    : `${entries.length} page${entries.length === 1 ? '' : 's'} · as NM read it`);
  const original = make('a', 'file-original', document_.recording ? 'Open the recording as sent' : 'Open the file as sent');
  original.href = `/api/documents/${encodeURIComponent(document_.document_ref)}/original`;
  original.target = '_blank';
  original.rel = 'noopener';
  const out = [where, original, make('p', 'hint', `Sent with: “${preview}”`)];
  if (document_.recording) {
    const player = document.createElement('audio');
    player.controls = true;
    player.preload = 'none';
    player.className = 'document-player';
    player.src = `/api/documents/${encodeURIComponent(document_.document_ref)}/recording`;
    player.setAttribute('aria-label', `Play ${document_.name}`);
    out.push(player);
  }
  const flow = make('div', 'document-flow whole');
  for (const { number, page, unread } of entries) {
    let label = document_.recording ? 'Transcript' : `Page ${number}`;
    if (page && page.read_by === 'ai') {
      label += document_.recording ? ' · transcribed by AI'
        : page.legible === 'part' ? ' · read by AI, partly legible' : ' · read by AI';
    }
    if (entries.length > 1 || (page && page.read_by === 'ai')) flow.appendChild(make('div', 'page-mark', label));
    if (unread) {
      flow.appendChild(make('p', 'document-unread', document_.recording
        ? `Not transcribed: ${unread.reason}` : `Not read: ${unread.reason}`));
      continue;
    }
    if (page.note) flow.appendChild(make('p', 'board-meta', page.note));
    flow.appendChild(make('div', 'document-text', page.text));
  }
  out.push(flow);
  return out;
}

const CERTAINTY = { reported: 'Reported', disputed: 'Disputed', uncertain: 'Uncertain', confirmed: 'Given' };
const QUESTION_STATUS = { researched: 'researched', search_failed: 'search failed', not_researched: 'not researched' };

// Where a fact's words were found, as the server found them (15 Oct 2026).
function factPlace(fact) {
  if (fact.from === 'advocate') return 'From your messages';
  if (fact.from === 'document' && Array.isArray(fact.places)) {
    return `From ${fact.places.map((place) => (place.recording
      ? `${place.document} (recording, transcribed by AI)`
      : `${place.document}, page ${place.page}` + (place.read_by === 'ai' ? ' (read by AI)' : ''))).join('; ')}`;
  }
  return 'Where these words were given was not found';
}

// THE TIMELINE OF THE PAPERS (plan AN.27, P10): what the papers record, event by event, in the order the server kept - the dated in
// date order, then those the papers leave undated - with the paper and page of each, and what NM could read of each paper. The page
// sorts, dates and locates nothing; an event whose words the server could not find on the page says so.
const EVENTS_SHOWN = 12;

function eventPlace(event) {
  const pages = Array.isArray(event.pages) ? event.pages : [];
  if (!pages.length) return event.document;
  return `${event.document}, ${event.recording ? 'part' : 'page'}${pages.length > 1 ? 's' : ''} ${pages.join(', ')}`;
}

// Plan AN.48 (48g, D148): a board item the advocate corrected shows their value, marked as theirs; the paper's own reading stays.
function correctedMark(corrected, make) {
  return make('span', 'board-corrected', ` · Corrected by you: ${corrected.value}`);
}

// The events as lists: the first few, and the rest folded under a line that says how many.
function eventRows(events, make) {
  const rows = (items) => {
    const ul = make('ul', 'board-list board-events');
    for (const event of items) {
      const item = make('li', 'board-event');
      if (event.dated) item.appendChild(make('span', 'board-when', `${event.date} `));
      item.appendChild(make('span', '', event.what));
      // Research v14 (plan AN.33, D18): a date NM finds nowhere in the papers is kept beside the event, never stated as the papers'.
      if (event.date_as_read) {
        item.appendChild(make('span', 'board-status', ` · read as ${event.date_as_read}, a date NM finds nowhere in your papers`));
      }
      if (event.kind === 'pending') item.appendChild(make('span', 'board-certainty', 'Pending'));
      // Plan AN.48 (48g, D148): the value the advocate gave in place of what NM read, marked as theirs.
      if (event.corrected) item.appendChild(correctedMark(event.corrected, make));
      // Research v14 (plan AN.33, D19): how the weighing of the points found it, for which dispute.
      if (event.weight) {
        const effect = { helps: 'helps your client', hurts: 'hurts your client', both: 'cuts both ways' }[event.effect];
        item.appendChild(make('span', 'board-certainty', `${event.weight === 'critical' ? 'Critical' : 'Material'}`
          + `${event.dispute ? ` to ${event.dispute}` : ''}${effect ? `, ${effect}` : ''}`));
      }
      const where = make('span', 'board-status', ` · ${eventPlace(event)}${event.said_by ? ` · said by ${event.said_by}` : ''}`);
      where.title = event.words;
      item.appendChild(where);
      // The same event, recorded again by a paper that is a copy of this one's page (plan AN.27, P22): where else it is.
      if (Array.isArray(event.also_in) && event.also_in.length) {
        item.appendChild(make('span', 'board-status', ` · also in ${event.also_in.map(eventPlace).join('; ')}`));
      }
      if (!event.located) {
        item.appendChild(make('span', 'board-status search_failed', ' · NM could not find these words on the page; check the paper.'));
      }
      ul.appendChild(item);
    }
    return ul;
  };
  const out = [rows(events.slice(0, EVENTS_SHOWN))];
  if (events.length > EVENTS_SHOWN) {
    const rest = events.length - EVENTS_SHOWN;
    const more = make('details', 'board-more');
    more.appendChild(make('summary', '', `Show the other ${rest} ${rest === 1 ? 'event' : 'events'}`));
    more.appendChild(rows(events.slice(EVENTS_SHOWN)));
    out.push(more);
  }
  return out;
}

// A PART OF THE BOARD BELOW THE DISPUTES (plan AN.39, D57; owner, 4 Nov 2026: the board "not lengthy and completely sentences but
// short phrases and details to follow in reading pane when clicked"): one line, its detail opening in the reading pane. Built as a
// fold was: what is appended to it is what the pane shows.
function boardPart(summary) {
  const content = [];
  const line = document.createElement('button');
  line.type = 'button';
  line.className = 'board-line';
  line.textContent = summary;
  line.addEventListener('click', () => window.NmBrainSources.showContent(summary, content, line, false, 'Matter board'));
  return { node: line, content, appendChild: (item) => { content.push(item); return item; }, append: (...items) => { content.push(...items); } };
}

function renderTimeline(timeline, make) {
  if (!timeline || timeline.state === 'none') return [];
  if (timeline.state !== 'ready') {
    return [make('p', 'board-lede', timeline.why || 'NM has no timeline of these papers to show.')];
  }
  const events = timeline.events || [];
  const papers = timeline.documents || [];
  const unfinished = papers.filter((paper) => paper.state !== 'read').length;
  const fold = boardPart(`Timeline of your papers (${events.length} ${events.length === 1 ? 'event' : 'events'})`
    + (unfinished ? ` · ${unfinished} ${unfinished === 1 ? 'paper' : 'papers'} not fully read` : ''));
  const repeated = events.some((event) => Array.isArray(event.also_in) && event.also_in.length);
  fold.appendChild(make('p', 'board-lede', 'What your papers record, event by event, as NM read them. Each is as its paper says it, '
    + 'not proved; check anything that matters against the paper itself.'
    + (repeated ? ' An event that more than one paper records, as a copy of a page does, is listed once, with the other papers named.' : '')));
  fold.appendChild(make('h3', 'board-h', 'Papers read'));
  const list = make('ul', 'board-list');
  for (const paper of papers) {
    const unit = paper.recording ? 'part' : 'page';
    const item = make('li', '', `${paper.name}: ${paper.pages_read} ${unit}${paper.pages_read === 1 ? '' : 's'} read, `
      + `${paper.events} ${paper.events === 1 ? 'event' : 'events'}`);
    if (paper.why) item.appendChild(make('span', `board-status${paper.state === 'not_read' ? ' search_failed' : ''}`, ` · ${paper.why}`));
    list.appendChild(item);
  }
  fold.appendChild(list);
  const dated = events.filter((event) => event.dated);
  const undated = events.filter((event) => !event.dated);
  if (dated.length) fold.append(make('h3', 'board-h', 'In date order'), ...eventRows(dated, make));
  if (undated.length) fold.append(make('h3', 'board-h', 'Not dated in the paper'), ...eventRows(undated, make));
  if (!events.length) fold.appendChild(make('p', 'board-lede', 'NM listed no events from these papers.'));
  return [fold.node];
}

// FIGURES TWO COPIES READ DIFFERENTLY (plan AN.27, P13): pages that are almost word for word the same but give a figure differently,
// found by code from the saved pages. The page chooses between nothing: it gives both readings and the words before them.
function renderCopies(copies, make) {
  if (!Array.isArray(copies) || !copies.length) return [];
  const fold = boardPart(`Figures two copies read differently (${copies.length})`);
  fold.appendChild(make('p', 'board-lede', 'These pages are almost word for word the same, but a figure on one is not the figure on the '
    + 'other. NM has not chosen between them: check the originals.'));
  const list = make('ul', 'board-list');
  for (const found of copies) {
    const item = make('li', '', `${found.first.document}, page ${found.first.page} and ${found.second.document}, page ${found.second.page}: `);
    found.figures.forEach((figure, index) => {
      const before = figure.after ? ` (after “${figure.after}”)` : '';
      item.appendChild(make('span', 'board-status', `${index ? '; ' : ''}“${figure.first}” and “${figure.second}”${before}`));
    });
    list.appendChild(item);
  }
  fold.appendChild(list);
  return [fold.node];
}

// TRANSACTIONS BY SUBJECT (plan AN.27, P13d; AN.28, D7; AN.29, D9): the transactions NM found in the papers, their figures added up
// by NM's code - never by a model - each kind of quantity with its own and sums of money with sums, giver by giver, with what a paper's
// stated whole leaves, and the server's caveat that a sum is only of what was found. What could not be read or added is listed and
// never added; a transaction dated after its giver's recorded death carries the server's remark.
function renderFigures(subjects, make) {
  if (!Array.isArray(subjects) || !subjects.length) return [];
  const fold = boardPart(`Transactions by asset or account (${subjects.length})`);
  fold.appendChild(make('p', 'board-lede', 'Added up by NM’s code from the transactions it found in your papers - each kind of quantity '
    + 'with its own, sums of money with sums of money - as the papers state them and whoever states them. Rival or repeated accounts are '
    + 'added as if each were true, so a sum is a figure to check against the papers, not what anyone holds, owes or has paid.'));
  // One line for a transaction, as the papers record it: where it is and - the same sale read on copies of one page, its receiver's
  // name read two ways (P20 (b)) - both readings.
  const said = (entry) => {
    const where = entry.papers.map((paper) => paper.document + (paper.pages.length
      ? `, page${paper.pages.length > 1 ? 's' : ''} ${paper.pages.join(', ')}` : '')).join('; ');
    const alike = entry.also_read_as && entry.also_read_as.length
      ? ` (also read as ${entry.also_read_as.map((name) => `“${name}”`).join(' and ')})` : '';
    return `${entry.date} ${entry.kind}: ${entry.figure}${entry.as ? ` (${entry.as})` : ''}`
      + `${entry.to ? ` to ${entry.to}` : ''}${alike} · ${where}`;
  };
  for (const subject of subjects) {
    fold.appendChild(make('h3', 'board-h', subject.subject));
    // Giver by giver (P20 (a)): a giver's figures are added to that giver's alone; there is no figure for the subject as a whole.
    for (const giver of subject.givers) {
      fold.appendChild(make('p', 'board-fact', `From: ${giver.names.length ? giver.names.join(' / ') : 'not named in the papers'}`));
      const list = make('ul', 'board-list');
      for (const entry of giver.counted) {
        const item = make('li', '', said(entry));
        if (entry.remark) item.appendChild(make('span', 'board-status search_failed', ` · ${entry.remark}`));
        list.appendChild(item);
      }
      for (const other of giver.listed) {
        const item = make('li', 'board-status search_failed', `Not added (${other.why}): ${said(other)}`);
        if (other.remark) item.appendChild(make('span', '', ` · ${other.remark}`));
        list.appendChild(item);
      }
      fold.appendChild(list);
      if (giver.added) {
        fold.appendChild(make('p', 'board-fact', `Added as stated: ${giver.added}`
          + (subject.complete ? '' : ' (a transaction could not be added, so the whole is more)')));
      }
    }
    if (subject.not_read.length) {
      const list = make('ul', 'board-list');
      for (const missed of subject.not_read) {
        list.appendChild(make('li', 'board-status search_failed', `Not added: “${missed.figure}” (${missed.why}) · ${missed.document}`));
      }
      fold.appendChild(list);
    }
    for (const total of subject.totals) {
      fold.appendChild(make('p', 'board-fact', `A paper states the whole as “${total.text}”`
        + `${total.as ? ` (${total.as})` : `; not used (${total.read_as})`}`));
      for (const against of total.by_giver) {
        if (against.exceeds) {
          fold.appendChild(make('p', 'board-status search_failed', `What ${against.giver} gave, as found, adds up to more than that `
            + `whole, by ${against.exceeds}: the papers cannot all be right.`));
        } else if (against.leaves) {
          fold.appendChild(make('p', 'board-fact', `If all of it was ${against.giver}’s, what they gave, as found, leaves ${against.leaves}.`));
        }
      }
      if (total.as && !subject.complete && !total.by_giver.some((against) => against.exceeds)) {
        fold.appendChild(make('p', 'board-fact', 'No remainder is named, because a transaction could not be added.'));
      }
    }
    fold.appendChild(make('p', 'board-lede', subject.caveat));
  }
  return [fold.node];
}

// READ SIDE BY SIDE (plan AN.28, pieces 3e and 3f): what matters to your client only when the papers are set side by side, each point
// with the pages the server found its words on, and where each of your client's people stands on the pages as the server's code found
// the name - a near spelling offered only as a candidate, never taken for the person. A point whose words were not found says so.
const SIDE_BY_SIDE = { client_appears: 'Your client’s people elsewhere', against_client: 'Against your client',
  after_death: 'After a death', after_time_limit: 'After a time limit or order', further_subject: 'A further asset, account or case',
  papers_differ: 'Where your papers differ', other: 'Read together' };
// SET ASIDE (plan AN.33, D18; piece 33m): what NM's reading gave that a second look found the papers do not record, with why. Listed so
// that nothing NM read disappears without trace; never used as a point.
function renderSetAside(items, make) {
  if (!Array.isArray(items) || !items.length) return [];
  const fold = boardPart(`Set aside after checking (${items.length})`);
  fold.appendChild(make('p', 'board-lede', 'What NM first read from your papers but, looking again at the pages, found they do not '
    + 'record. It is not used; check it against the papers if it matters.'));
  const list = make('ul', 'board-list');
  for (const item of items) list.appendChild(make('li', '', `${item.what} · ${item.document} · ${item.why}`));
  fold.appendChild(list);
  return [fold.node];
}

function renderPapersTogether(board, make) {
  const connections = board.connections || [];
  const appearances = (board.appearances || []).filter((one) => one.places.length || one.near.length);
  const failed = (board.connections_failures || []).length > 0;
  if (!connections.length && !appearances.length && !failed) return [];
  const where = (places) => places.map((place) => `${place.document}, page ${place.page}`).join('; ');
  const fold = boardPart(`Read side by side (${connections.length})`);
  fold.appendChild(make('p', 'board-lede', 'What matters to your client only when your papers are set side by side, as NM read them, '
    + 'each with the pages its words are on. Check each against the papers.'));
  if (failed) {
    fold.appendChild(make('p', 'board-status search_failed', 'Your papers could not be read together this time, so what shows only '
      + 'when they are set side by side was not looked for.'));
  }
  if (connections.length) {
    const points = make('ul', 'board-list');
    for (const item of connections) {
      const said = `${SIDE_BY_SIDE[item.kind] || SIDE_BY_SIDE.other}: ${item.point}${item.why ? ` — ${item.why}` : ''}`;
      points.appendChild(make('li', item.anchored ? '' : 'board-status search_failed', item.anchored
        ? `${said} · ${where(item.places)}` : `${said} · its words were not found on the pages, so it rests on nothing yet`));
    }
    fold.appendChild(points);
  }
  if (appearances.length) {
    fold.appendChild(make('h3', 'board-h', 'Where your client’s people appear'));
    const people = make('ul', 'board-list');
    for (const one of appearances) {
      people.appendChild(make('li', '', `${one.name}: ${one.places.length ? where(one.places) : 'not found as written'}`));
      for (const near of one.near) {
        people.appendChild(make('li', 'board-status', `Written “${near.as_written}” on ${near.document}, page ${near.page}: a near `
          + 'spelling, not taken to be the same person'));
      }
    }
    fold.appendChild(people);
  }
  return [fold.node];
}

// FROZEN (owner, 4 Nov 2026; plan AN.39, D60): the UI and structure of the matter board and of the reading pane change only with
// the owner's explicit approval, even as a by-product of other work. tests/js/board_and_pane_frozen.mjs pins them; a failure
// there means ask the owner first.
// The board as NM understood the matter from the advocate's own words. Nothing on it is
// presented as established: facts carry the certainty they were given with. The disputes
// come first, under the marks' legend; how NM understood the matter, the facts, the
// standing instructions and the related points fold below (the design of 17 Oct 2026).
function renderChatBoard(board) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const list = (items, className) => {
    const ul = make('ul', className);
    for (const item of items) ul.appendChild(make('li', '', item));
    return ul;
  };
  if (!board || board.state !== 'ready') {
    return [stateBlock('empty', 'Nothing here yet: the board fills in once NM has researched a message in this matter.')];
  }
  // The understanding's own summary is not shown: it is written before research and
  // can state legal conclusions no check has seen (16 Oct 2026).
  const out = [];
  // Where NM's own check of its understanding was not satisfied, say so (plan AN.27, P7): a working understanding, to be checked
  // against the papers. A board without the server's word on it says nothing.
  if (board.understanding && board.understanding.confirmed === false) {
    out.push(make('p', 'board-lede', 'NM’s own check of this understanding was not satisfied, so treat it as a working '
      + 'understanding and check it against your papers.'));
  }
  if (board.disputes.some((dispute) => dispute.checklist && dispute.checklist.items.length)) {
    out.push(renderCheckLegend());
  }
  // What a case's marks mean (plan AN.39), as the checklist's were said above the disputes on 31 October.
  if (board.disputes.some((dispute) => dispute.checklist && dispute.checklist.case && (dispute.checklist.case.elements || []).length)) {
    out.push(renderCheckLegend(CASE_MARKS));
  }
  const disputes = make('section', 'board-disputes');
  disputes.setAttribute('aria-label', board.disputes.length === 1 ? 'Dispute' : `Disputes (${board.disputes.length})`);
  // PLAN AN.49 (49c; D180): ONE DISPUTE OPEN AT A TIME on a board of several. The first, the most urgent, is open until the advocate
  // opens another or closes it; which one is the page's own for the visit (state.boardOpen: an id, or '' for none), never saved.
  const many = board.disputes.length > 1;
  const cards = [];
  const openId = !many ? null : state.boardOpen === '' ? ''
    : board.disputes.some((dispute) => dispute.id === state.boardOpen) ? state.boardOpen : board.disputes[0].id;
  const choose = (id) => {
    state.boardOpen = id;
    for (const [held, card] of cards) if (card.setOpen) card.setOpen(held.id === id);
  };
  board.disputes.forEach((dispute, index) => {
    const card = renderDisputeCard(dispute, board, many ? index + 1 : null, many ? { open: dispute.id === openId, choose } : null);
    cards.push([dispute, card]);
    disputes.appendChild(card);
  });
  out.push(disputes);
  out.push(...renderTimeline(board.timeline, make));
  out.push(...renderCopies(board.copies, make));
  out.push(...renderFigures(board.figures, make));
  out.push(...renderPapersTogether(board, make));
  out.push(...renderSetAside(board.set_aside, make));
  const points = (board.understanding && board.understanding.open_points) || [];
  const parts = (board.parties || []).flatMap((party) => (party.parts || []).map((part) => ({ party, part })));
  const subjects = board.subjects || [];
  const counted = [[board.facts.length, 'Facts as you gave them'], [parts.length, 'Parts in proceedings'],
    [subjects.length, 'Subjects in the papers'], [board.instructions.length, 'Standing instructions'],
    [board.related_points.length, 'Related points'], [points.length, 'Points NM’s own check raised']]
    .filter(([count]) => count)
    .map(([count, title]) => `${title} (${count})`);
  const fold = boardPart('How NM understood this matter');
  if (counted.length) fold.appendChild(make('p', 'source-where', counted.join(' · ')));
  fold.appendChild(make('p', 'board-lede', 'As NM understood this matter from your messages and the documents '
    + 'you sent. Facts are as you or a document gave them, not proved.'));
  if (board.facts.length) {
    fold.appendChild(make('h3', 'board-h', 'Facts, as you gave them'));
    for (const fact of board.facts) {
      const row = make('p', 'board-fact');
      row.appendChild(make('span', `board-certainty ${fact.certainty}`, CERTAINTY[fact.certainty] || fact.certainty));
      row.appendChild(make('span', '', ` ${fact.fact}`));
      if (fact.corrected) row.appendChild(correctedMark(fact.corrected, make));
      if (fact.from === 'document') row.appendChild(make('span', 'board-status', ` · ${factPlace(fact)}`));
      fold.appendChild(row);
    }
  }
  // Each party's part in each proceeding the papers name, and each subject they identify (plan AN.28, piece 3f), with where the
  // server found its words.
  if (parts.length) {
    fold.appendChild(make('h3', 'board-h', 'Who is who in each proceeding'));
    fold.appendChild(list(parts.map(({ party, part }) => `${party.who}${party.client ? ' (your client’s side)' : ''}: ${part.part} in `
      + `${part.proceeding} · ${factPlace(part)}`), 'board-list'));
  }
  if (subjects.length) {
    fold.appendChild(make('h3', 'board-h', 'Subjects the papers identify'));
    fold.appendChild(list(subjects.map((subject) => `${subject.identifier} — ${subject.what} · ${factPlace(subject)}`), 'board-list'));
  }
  if (board.instructions.length) {
    fold.appendChild(make('h3', 'board-h', 'Your standing instructions'));
    fold.appendChild(list(board.instructions, 'board-list'));
  }
  if (board.related_points.length) {
    fold.appendChild(make('h3', 'board-h', 'Related points for your decision'));
    fold.appendChild(list(board.related_points.map((r) => (r.why ? `${r.point} — ${r.why}` : r.point)), 'board-list'));
  }
  if (points.length) {
    fold.appendChild(make('h3', 'board-h', 'Points NM’s own check raised'));
    fold.appendChild(list(points, 'board-list'));
  }
  out.push(fold.node);
  return out;
}

// WHAT MAKES THE CASE STRONGER (plan AN.35, D31-D32; rendering v20, checklist v3): for one dispute, what the law requires,
// element by element - how the papers stand on it, who must prove it, why, the law's own words and where they stand, and the pages
// of the points that bear on it - what to get and from whom, and what the other side will rely on and what answers it. Every word
// and mark is the server's: an element is shown only where the server found its points on their pages, and words NM could not
// find in the law it read say so.
const CASE_MARKS = {
  shown: { mark: 'in_hand', label: 'Shown by the papers' },
  weak: { mark: 'coming_or_unclear', label: 'Shown only weakly' },
  missing: { mark: 'not_given', label: 'Not yet shown' },
};
const CASE_PROVES = { client: 'For your client to prove', other_side: 'For the other side to prove' };
const CASE_STATES = {
  unchecked: 'NM’s second look at this list could not be made, so it stands as first set out.',
  unavailable: 'NM could not set out what would make this case stronger this time. The rest stands as checked.',
};

// holder: the answer that holds the case ({chat_id, turn_id}), from whose saved record its law and its pages open (plan AN.39); none
// where the page does not hold it, and then the law is shown as its words alone.
function renderCaseBlock(view, holder = null) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const out = [];
  if (CASE_STATES[view.state]) out.push(make('p', 'check-none', CASE_STATES[view.state]));
  const law = (given, usedFor) => (given && given.found
    ? [make('blockquote', 'detail-words', given.words), ...caseLaw(given, holder, usedFor)] : caseLaw(given, holder, usedFor));
  const points = (said) => casePoints(said, holder);
  const elements = view.elements || [];
  if (elements.length) {
    out.push(make('h4', 'board-h', 'What the law requires'));
    const ul = make('ul', 'case-list');
    for (const item of elements) {
      const mark = CASE_MARKS[item.status] || CASE_MARKS.missing;
      const li = make('li', 'case-element');
      const head = make('p', 'case-head');
      const state = make('span', 'st st--' + mark.mark);
      state.setAttribute('aria-hidden', 'true');
      head.append(state, make('span', 't', item.element));
      li.appendChild(head);
      li.appendChild(make('p', 'board-meta', `${mark.label} · ${CASE_PROVES[item.proves] || ''}`));
      if (item.why) li.appendChild(make('p', '', item.why));
      if (item.called && item.called !== item.status) {
        li.appendChild(make('p', 'board-meta', 'Called shown, but none of its points was found on its page.'));
      }
      li.append(...law(item.law, item.element), ...points(item.points || []));
      ul.appendChild(li);
    }
    out.push(ul);
  } else if (view.state !== 'unavailable') {
    out.push(make('p', 'check-none', 'NM set out no element for this dispute from the law it read. That is what this '
      + 'research returned, not a finding that the law requires nothing.'));
  }
  const toGet = view.to_get || [];
  if (toGet.length) {
    out.push(make('h4', 'board-h', 'What to get'));
    const ul = make('ul', 'board-list');
    for (const ask of toGet) {
      const li = make('li');
      li.appendChild(make('p', 'detail-question', `${ask.what} — from ${ask.from_whom}`));
      li.appendChild(make('p', 'board-meta', `For: ${(ask.serves || [ask.for]).join('; ')}`));
      if (ask.why) li.appendChild(make('p', '', ask.why));
      if (ask.helps) li.appendChild(make('p', 'board-meta', ask.helps));
      ul.appendChild(li);
    }
    out.push(ul);
  }
  const other = view.other_side || [];
  if (other.length) {
    out.push(make('h4', 'board-h', 'What the other side will rely on'));
    const ul = make('ul', 'board-list');
    for (const item of other) {
      const li = make('li');
      li.appendChild(make('p', 'detail-question', item.relies_on));
      if (item.answer) li.appendChild(make('p', '', `What answers it: ${item.answer}`));
      li.append(...law(item.law, item.relies_on), ...points(item.points || []));
      ul.appendChild(li);
    }
    out.push(ul);
  }
  return out;
}

// A CASE'S LAW (plan AN.39, D53): the section and the Act, or the paragraph and the judgment, as a link that opens the passage in the
// reading pane - from the saved record of the answer that holds the case, its words marked - or, where the page holds no such answer,
// its words as the case kept them. Words NM could not find in the law it read say so.
function caseLaw(given, holder, usedFor) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  if (!given) return [];
  if (!given.found) return [make('p', 'board-meta', `NM could not find these words in the law it read: “${given.words}”`)];
  const open = make('button', 'cite', [given.locator, given.title].filter(Boolean).join(', ') || 'The law');
  open.type = 'button';
  open.addEventListener('click', () => (holder && given.source_id
    ? window.NmBrainSources.openPassage(holder, given.source_id, open, { words: given.words, phrase: usedFor, title: given.title })
    : openLaw(given, open)));
  const where = make('p', 'req-law');
  where.appendChild(open);
  const force = typeof given.in_force === 'string' && given.in_force.trim() ? given.in_force.trim() : '';
  return [where, ...(force ? [make('p', 'source-role warn', force.charAt(0).toUpperCase() + force.slice(1))] : [])];
}

// THE POINTS OF THE PAPERS A CASE'S ITEM RESTS ON (plan AN.39, D55): each with its pages, each page opening in the reading pane from
// the answer's saved record, the whole document a click away; a point whose words were not found on a page says so.
function casePoints(said, holder) {
  return said.map((point) => {
    const line = document.createElement('p');
    line.className = 'board-meta';
    line.appendChild(document.createTextNode(point.what));
    if (point.located && point.pages.length) {
      line.appendChild(document.createTextNode(' · '));
      point.pages.forEach((page, index) => {
        if (index) line.appendChild(document.createTextNode('; '));
        const label = `${page.document}, ${page.page}`;
        if (holder && page.source_id) {
          const open = document.createElement('button');
          open.type = 'button';
          open.className = 'cite';
          open.textContent = label;
          open.addEventListener('click', () => window.NmBrainSources.openPassage(holder, page.source_id, open,
            { phrase: point.what, title: page.document }));
          line.appendChild(open);
        } else {
          line.appendChild(document.createTextNode(label));
        }
      });
    } else if (!point.located) {
      line.appendChild(document.createTextNode(' · its words were not found on a page, so it rests on nothing yet'));
    }
    return line;
  });
}

// THE ANSWER THAT HOLDS A CASE (plan AN.39): an answer's own, or - for a dispute on the board - the newest answer on the page that set
// out that dispute's case, which is the case the board keeps for it.
function caseHolderOf(answer) {
  return answer && answer.chat_id && answer.turn_id ? { chat_id: answer.chat_id, turn_id: answer.turn_id } : null;
}

function caseEntry(dispute) {
  return [...(state.turns || [])].reverse().find((entry) => (entry.answer && entry.answer.elements || []).some((el) => el.kind === 'CASE'
    && el.case && el.dispute && el.dispute.id === dispute.id)) || null;
}

function caseHolder(dispute) {
  const entry = caseEntry(dispute);
  return entry ? caseHolderOf(entry.answer) : null;
}

// SEVERAL THINGS ANSWERED IN ONE REPLY (plan AN.49, 49f; D183; owner, 12 Nov 2026: the advocate "can respond to multiple aspects in
// one response"): 'Tell NM about these' on a dispute opens the answers window of 'What I need from you' (AN.37) with a row for each
// thing to get of a gathered case or, for a case saved earlier, each requirement not yet shown. What the advocate writes in each goes
// as one message, each part in the words the single 'Tell NM about this' puts in the message box. No new route, no new model step.
function caseTellRows(view) {
  if (!view || view.state === 'unavailable') return [];
  if (caseGathered(view)) {
    return (view.to_get || []).map((ask) => ({ group: null, about: ask.what,
      text: `${ask.what} — from ${ask.from_whom} (for: ${(ask.serves || [ask.for]).join('; ')})` }));
  }
  return (view.elements || []).filter((item) => item.status !== 'shown').map((item) => ({ group: null,
    about: item.label || item.element, text: `${item.label || item.element} · ${(CASE_MARKS[item.status] || CASE_MARKS.missing).label}` }));
}

function caseTellMessage(dispute, rows, answers) {
  return rows.map((row, index) => [row, String((answers || [])[index] || '').trim()]).filter(([, said]) => said)
    .map(([row, said]) => `About "${row.about}" (${dispute.name}): ${said}`).join('\n\n');
}

function caseTellButton(dispute, rows) {
  const tell = document.createElement('button');
  tell.type = 'button';
  tell.className = 'ghost case-tell';
  tell.textContent = 'Tell NM about these';
  // What was written and not sent is kept while the page is open: with the answer that holds the case, or the page's own.
  tell.addEventListener('click', () => openNeedAnswers(caseEntry(dispute) || (state.turns || []).at(-1)
    || (state.caseTell || (state.caseTell = {})), rows, {
    called: 'Tell NM about these',
    lede: 'Say what you have, do not have or will get, in your own words, and leave the rest blank. It goes to NM as your next '
      + 'message, each part under what it is about.',
    empty: 'Write about at least one of them.',
    compose: (answers) => caseTellMessage(dispute, rows, answers),
  }));
  return tell;
}

// The point of a dispute's case an answer's "what to get" is for, with the case it belongs to; none where the answer holds none.
function caseElementFor(answer, dispute, name) {
  const held = ((answer && answer.elements) || []).find((el) => el.kind === 'CASE' && el.case && el.dispute && dispute
    && el.dispute.id === dispute.id);
  const item = held && (held.case.elements || []).find((element) => element.element === name);
  return item ? { item, view: held.case } : null;
}

// A start put in the message box for the advocate to finish and send (the board's and the pane's "Tell NM" buttons).
function startMessage(words) {
  const box = $('message');
  box.value = box.value.trim() ? `${box.value.trim()}\n${words}` : words;
  box.dispatchEvent(new Event('input', { bubbles: true }));
  sizeComposer();
  box.focus();
}

// ONE POINT OF A DISPUTE'S CASE IN THE READING PANE (plan AN.39, D52; owner, 4 Nov 2026: "it should again only open data related to that
// particular point, with an option to share details about it"), as an item opened on 31 October: how it stands and who must prove it;
// why it is needed, with the law that requires it opening as its passage; where it stands in the papers, each page opening in the
// pane; what to get for it; and - not yet shown, or shown only weakly - "Tell NM about this" and "Not available", each putting a start
// in the message box. A point the papers show has no buttons (owner: OK).
function renderCaseItem(item, view, dispute, holder) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const block = (title, ...content) => {
    const section = make('section', 'req-block');
    section.appendChild(make('h4', '', title));
    section.append(...content);
    return section;
  };
  const mark = CASE_MARKS[item.status] || CASE_MARKS.missing;
  const status = make('p', `req-status item--${mark.mark}`);
  const sign = make('span', 'st st--' + mark.mark);
  sign.setAttribute('aria-hidden', 'true');
  status.append(sign, make('span', '', [mark.label, CASE_PROVES[item.proves]].filter(Boolean).join(' · ')));
  const name = item.label || item.element;
  const out = [status];
  if (item.label && item.label !== item.element) out.push(make('p', 'dispute-why', item.element));
  out.push(block('Why it is needed', ...(item.why ? [make('p', '', item.why)] : []), ...caseLaw(item.law, holder, name)));
  const stands = [];
  if (item.called && item.called !== item.status) {
    stands.push(make('p', '', 'Called shown, but none of its points was found on its page.'));
  }
  stands.push(...casePoints(item.points || [], holder));
  if (!(item.points || []).length) stands.push(make('p', '', 'Not in your messages or documents yet.'));
  out.push(block('Where it stands', ...stands));
  // A thing to get of a gathered case serves every requirement it names (plan AN.49, 49e); one saved earlier, the one it is for.
  const asks = ((view && view.to_get) || []).filter((ask) => (ask.serves || [ask.for]).includes(item.element));
  if (asks.length) {
    const ul = make('ul', 'board-list');
    for (const ask of asks) {
      const li = make('li');
      li.appendChild(make('p', 'detail-question', `${ask.what} — from ${ask.from_whom}`));
      if (ask.why) li.appendChild(make('p', '', ask.why));
      if (ask.helps) li.appendChild(make('p', 'board-meta', ask.helps));
      ul.appendChild(li);
    }
    out.push(block('What to get', ul));
  }
  if (item.status !== 'shown') {
    const actions = make('div', 'actions');
    const tell = make('button', 'act primary', 'Tell NM about this');
    tell.type = 'button';
    tell.addEventListener('click', () => startMessage(`About "${name}" (${dispute.name}): `));
    const unavailable = make('button', 'act ghost', 'Not available');
    unavailable.type = 'button';
    unavailable.addEventListener('click', () => startMessage(`About "${name}" (${dispute.name}): this is not available.`));
    actions.append(tell, unavailable);
    out.push(actions);
  }
  return out;
}

// WHAT THE OTHER SIDE WILL RELY ON, ONE THING IN THE READING PANE (plan AN.39, D56): what they will rely on, the law they would cite
// opening as its passage, what answers it, the points of the papers with their pages, and "Tell NM what answers it".
function renderOtherSideItem(item, dispute, holder) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const block = (title, ...content) => {
    const section = make('section', 'req-block');
    section.appendChild(make('h4', '', title));
    section.append(...content);
    return section;
  };
  const name = item.label || item.relies_on;
  const out = [];
  if (item.label && item.label !== item.relies_on) out.push(make('p', 'dispute-why', item.relies_on));
  const law = caseLaw(item.law, holder, name);
  if (law.length) out.push(block('The law they would rely on', ...law));
  if (item.answer) out.push(block('What answers it', make('p', '', item.answer)));
  if ((item.points || []).length) out.push(block('Where it stands', ...casePoints(item.points, holder)));
  const actions = make('div', 'actions');
  const tell = make('button', 'act primary', 'Tell NM what answers it');
  tell.type = 'button';
  tell.addEventListener('click', () => startMessage(`About what the other side will rely on, "${name}" (${dispute.name}): `));
  actions.appendChild(tell);
  out.push(actions);
  return out;
}

// WHAT EACH DISPUTE NEEDS (owner decisions, 17 Oct 2026): the dispute, its last days as code
// worked them out, how much is in hand, and under Needed and Would strengthen each item the
// law it holds requires, with its mark. The marks are shape, colour and words; the server's
// saved checklist decides every one, and nothing here can set one.
const CHECK_MARKS = {
  in_hand: { label: 'In hand' },
  coming_or_unclear: { label: 'Coming or unclear' },
  not_given: { label: 'Not yet given' },
  not_available: { label: 'Not available' },
};
const CHECK_GROUPS = [['needed', 'Needed'], ['would_strengthen', 'Would strengthen']];

// A mark drawn by shape and colour; its words are read out with the item it marks.
function checkMark(status) {
  const mark = document.createElement('span');
  mark.className = `st st--${CHECK_MARKS[status] ? status : 'not_given'}`;
  mark.setAttribute('aria-hidden', 'true');
  return mark;
}

// What the marks mean, said once above the disputes: the checklist's (marks), or a case's (CASE_MARKS, each naming the mark it draws).
function renderCheckLegend(marks = CHECK_MARKS) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const legend = make('p', 'legend');
  legend.setAttribute('aria-hidden', 'true');
  for (const [status, { label, mark }] of Object.entries(marks)) {
    const entry = make('span', 'legend-entry');
    entry.append(checkMark(mark || status), make('span', '', label));
    legend.appendChild(entry);
  }
  return legend;
}

// Each last day code worked out, as a chip - 'By 10 Mar 2029 · 84 days left', with 'Passed' or
// 'Late' where so (the design's 'File by' is said only of a filing, and not every time limit is
// one) - and a quiet word for those it could not work out. How near the day is shows in words
// and in the chip's colour (the signed-off design, plan AN.14): a week or less, a month or less,
// further, or passed. The days are the count code saved; nothing is counted here.
const NEAR_DAYS = { urgent: 7, soon: 30 };

function deadlineChips(limits) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const chips = [];
  let unworked = 0;
  for (const limit of limits || []) {
    const rows = new Map(limit.rows || []);
    if (!rows.has('Last day')) { unworked += 1; continue; }
    const result = rows.get('Result');
    const open = !result || result === 'Open';
    const saved = rows.get('Days left');
    const days = open && /^\d+$/.test(String(saved ?? '')) ? Number(saved) : null;
    const near = !open ? 'expired' : days === null ? 'open'
      : days <= NEAR_DAYS.urgent ? 'urgent' : days <= NEAR_DAYS.soon ? 'soon' : 'open';
    const said = !open ? ` · ${result}` : days === null ? '' : ` · ${days} ${days === 1 ? 'day' : 'days'} left`;
    const chip = make('span', `chip deadline ${near}`,
      `By ${dayDate(limit.last_day) || rows.get('Last day')}${said}`);
    chip.title = `${limit.what}: ${timeLimitStanding(rows)}`;
    chips.push(chip);
  }
  if (unworked) {
    chips.push(make('span', 'chip quiet', unworked === 1 ? 'Last day not worked out' : `${unworked} last days not worked out`));
  }
  return chips;
}

// HOW A CASE WAS CHECKED, IN CODE'S WORDS (plan AN.49, D185), ONE COPY: said wherever the account is shown, outside any fold. A second
// look is claimed only where one was made.
function caseCheckedLine(view) {
  return `This is NM’s working list: ${view && view.state === 'checked' ? 'a second look checked it and ' : ''}`
    + 'code looked for each quotation of law in the passage it names. It did not go through the independent review that the '
    + 'sections of an answer do.';
}

// ONE LINE OF A CASE (plan AN.39, D52): its mark and its short words - with, for a heading of a gathered case, its count (plan AN.49,
// 49e) - opening in the reading pane.
function caseLine(className, mark, words, srLabel, open, sub = '') {
  const make = (tag, name, text) => {
    const node = document.createElement(tag);
    if (name) node.className = name;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const li = make('li');
  const row = make('button', className);
  row.type = 'button';
  const said = make('span', 'item-words');
  said.appendChild(make('span', 't short', words));
  if (sub) said.appendChild(make('span', 'sub', sub));
  if (srLabel) said.appendChild(make('span', 'sr', ` · ${srLabel}`));
  const sign = make('span', 'st st--' + mark);
  sign.setAttribute('aria-hidden', 'true');
  row.append(sign, said);
  row.addEventListener('click', () => open(row));
  li.appendChild(row);
  return li;
}

// A thing the law requires, as one line opening alone in the pane; and a thing the other side will rely on, the same way.
function caseElementLine(item, view, dispute, place) {
  const mark = CASE_MARKS[item.status] || CASE_MARKS.missing;
  return caseLine(`item item--${mark.mark}`, mark.mark, item.label || item.element, mark.label,
    (row) => window.NmBrainSources.showContent(item.label || item.element, renderCaseItem(item, view, dispute, caseHolder(dispute)),
      row, false, `What the law requires · ${place}`));
}

function caseOtherLine(item, dispute, place) {
  return caseLine('item item--other', 'other', item.label || item.relies_on, '',
    (row) => window.NmBrainSources.showContent(item.label || item.relies_on, renderOtherSideItem(item, dispute, caseHolder(dispute)),
      row, false, `The other side will rely on · ${place}`));
}

// A case of the gathered version (core_case_v3) carries its headings; one saved before it does not, and is drawn as it was (P46).
function caseGathered(view) {
  return Boolean(view) && Array.isArray(view.headings);
}

// How the least-shown of several requirements stands: the mark a heading, or a thing that decides the dispute, carries.
function caseLeastShown(items) {
  const status = ['missing', 'weak', 'shown'].find((held) => items.some((item) => item.status === held));
  return CASE_MARKS[status] || CASE_MARKS.missing;
}

// THE CASE GATHERED (plan AN.49, 49e; D181-D182; owner, 12 Nov 2026: "consolidate and bring logically connected aspects into one
// bullet"): the few things that most decide the dispute, each opening in the pane with what it concerns; then each heading as one
// line with how many of its requirements the papers show, opening its requirements in the pane, where each opens alone as before.
// The headings and what decides it are the model's, checked by its second look; every count and mark is code's, from the saved case.
function caseGatheredLines(view, dispute, place) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const elements = view.elements || [];
  const out = [];
  const decides = view.decides || [];
  if (decides.length) {
    out.push(make('p', 'group', 'Most needs attention now'));
    const ul = make('ul', 'checklist');
    for (const item of decides) {
      const concerned = (item.elements || []).map((number) => elements[number - 1]).filter(Boolean);
      const mark = concerned.length ? caseLeastShown(concerned).mark : 'other';
      ul.appendChild(caseLine(`item item--${mark}`, mark, item.what, '', (row) => window.NmBrainSources.showContent(item.what,
        renderDecidingItem(item, view, dispute, place), row, false, `Most needs attention now · ${place}`)));
    }
    out.push(ul);
  }
  out.push(make('p', 'group', 'What the law requires'));
  const ul = make('ul', 'checklist');
  view.headings.forEach((heading, index) => {
    const under = elements.filter((item) => item.heading === index + 1);
    if (!under.length) return;
    const shown = under.filter((item) => item.status === 'shown').length;
    const mark = caseLeastShown(under);
    const list = make('ul', 'checklist');
    for (const item of under) list.appendChild(caseElementLine(item, view, dispute, place));
    ul.appendChild(caseLine(`item item--${mark.mark}`, mark.mark, heading, '',
      (row) => window.NmBrainSources.showContent(heading, [list], row, false, `What the law requires · ${place}`),
      `${shown} of ${under.length} shown`));
  });
  // Every requirement is drawn: one under no heading of the list (the server puts none there) is a line of its own.
  for (const item of elements) {
    if (!(item.heading >= 1 && item.heading <= view.headings.length)) ul.appendChild(caseElementLine(item, view, dispute, place));
  }
  out.push(ul);
  return out;
}

// WHAT MOST DECIDES THE DISPUTE, ONE THING IN THE READING PANE (plan AN.49, 49e; D182): why it decides it, then the requirements and
// the points of the other side it concerns, each opening alone as from the board.
function renderDecidingItem(item, view, dispute, place) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const block = (title, ...content) => {
    const section = make('section', 'req-block');
    section.appendChild(make('h4', '', title));
    section.append(...content);
    return section;
  };
  const out = [];
  if (item.why) out.push(make('p', '', item.why));
  const elements = (item.elements || []).map((number) => (view.elements || [])[number - 1]).filter(Boolean);
  if (elements.length) {
    const ul = make('ul', 'checklist');
    for (const element of elements) ul.appendChild(caseElementLine(element, view, dispute, place));
    out.push(block('What the law requires', ul));
  }
  const theirs = (item.other_side || []).map((number) => (view.other_side || [])[number - 1]).filter(Boolean);
  if (theirs.length) {
    const ul = make('ul', 'checklist');
    for (const other of theirs) ul.appendChild(caseOtherLine(other, dispute, place));
    out.push(block('What the other side will rely on', ul));
  }
  return out;
}

// A CASE AS ITS LINES (plan AN.39, D52, D56-D57), ONE COPY (plan AN.49, 49b): each thing the law requires, and each thing the other side
// will rely on, as one line with its mark that opens alone in the reading pane - or, for a case of the gathered version, what most
// decides it and its headings (49e). The board's card draws them under its dispute; the whole-dispute view draws the same lines
// inside its fold, so a point is opened the same way from either.
function caseLines(view, dispute, place, { otherAsLine = false } = {}) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const out = [];
  if (caseGathered(view)) {
    out.push(...caseGatheredLines(view, dispute, place));
  } else {
    out.push(make('p', 'group', 'What the law requires'));
    const ul = make('ul', 'checklist');
    for (const item of view.elements || []) ul.appendChild(caseElementLine(item, view, dispute, place));
    out.push(ul);
  }
  const other = view.other_side || [];
  if (other.length) {
    const theirs = make('ul', 'checklist');
    for (const item of other) theirs.appendChild(caseOtherLine(item, dispute, place));
    if (otherAsLine) {
      // Plan AN.49 (49c; D180): on the board the other side is one line with its count; its list opens in the reading pane, where
      // each thing opens alone as before.
      const all = make('button', 'board-line', `The other side will rely on (${other.length})`);
      all.type = 'button';
      all.addEventListener('click', () => window.NmBrainSources.showContent('The other side will rely on', [theirs], all, false, place));
      out.push(all);
    } else {
      out.push(make('p', 'group', 'The other side will rely on'), theirs);
    }
  }
  return out;
}

// fold (plan AN.49, 49c; D180; owner, 12 Nov 2026: the board "is listing quite a many bullets there under each dispute"): on a board
// of several disputes, {open, choose}: whether this card's lines are open, and what is called with the dispute's id (or '' to close it)
// when its button is pressed. The card's name, last days and counts always show; a board of one dispute has no fold.
function renderDisputeCard(dispute, board, number = null, fold = null) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const section = make('section', 'dispute');
  section.setAttribute('aria-label', dispute.name);
  const title = make('button', 'dtitle', number ? `${number} · ${dispute.name}` : dispute.name);
  title.type = 'button';
  title.addEventListener('click', () => window.NmBrainSources.showContent(dispute.name,
    renderDisputeDetail(dispute, board), title, false, number ? `Dispute ${number}` : 'Dispute'));
  section.appendChild(title);
  // The card's lines: straight under it on a board of one dispute; on a board of several, in a body its button opens and closes.
  const folded = (lines, count) => {
    if (!fold) {
      section.append(...lines);
      return section;
    }
    const body = make('div', 'dispute-body');
    body.append(...lines);
    const toggle = make('button', 'ghost dispute-toggle');
    toggle.type = 'button';
    section.setOpen = (open) => {
      section.isOpen = Boolean(open);
      body.hidden = !section.isOpen;
      toggle.textContent = section.isOpen ? 'Hide its points' : `Show its points (${count})`;
      toggle.setAttribute('aria-expanded', String(section.isOpen));
    };
    toggle.addEventListener('click', () => fold.choose(section.isOpen ? '' : dispute.id));
    section.setOpen(fold.open);
    section.append(toggle, body);
    return section;
  };
  const listed = dispute.checklist;
  if (!listed) {
    // An earlier conversation's board, before checklists, says what it said then.
    if (dispute.why_it_matters) section.appendChild(make('p', 'board-why', dispute.why_it_matters));
    // Where the law has not been assessed, say so rather than "0 legal questions" (plan AN.27, P7).
    if (dispute.law && dispute.law.state === 'not_assessed') {
      section.appendChild(make('p', 'check-none', `What the law requires: not yet assessed. ${dispute.law.why}`));
      if (!dispute.questions.length) return section;
    }
    const counts = {};
    for (const question of dispute.questions) counts[question.status] = (counts[question.status] || 0) + 1;
    const done = Object.entries(counts)
      .map(([status, count]) => `${count} ${QUESTION_STATUS[status] || status}`).join(' · ');
    section.appendChild(make('p', 'dmeta', `${dispute.questions.length} legal question`
      + `${dispute.questions.length === 1 ? '' : 's'}${done ? ` · ${done}` : ''}`));
    return section;
  }
  if ('case' in listed) {
    // Checklist v3 (plan AN.35, piece 35c3): what makes the case stronger. IN SHORT PHRASES (plan AN.39, D52, D56-D57; owner, 4 Nov
    // 2026): each element, and each thing the other side will rely on, one line - its short name, or (saved before it had one) its
    // own words on two lines - opening alone in the reading pane, where the detail is; the dispute's name opens the whole dispute.
    const meta = make('p', 'dmeta');
    meta.append(...deadlineChips(listed.time_limits));
    const view = listed.case;
    const elements = (view && view.elements) || [];
    if (elements.length) {
      const shown = elements.filter((item) => item.status === 'shown').length;
      meta.appendChild(make('span', 'count', `${shown} of ${elements.length} shown by the papers`));
    }
    if (view && (view.to_get || []).length) meta.appendChild(make('span', 'count', `${view.to_get.length} to get`));
    if (meta.children.length) section.appendChild(meta);
    if (!view || view.state === 'unavailable' || !elements.length) {
      section.appendChild(make('p', 'check-none', !view || view.state === 'unavailable'
        ? 'NM could not set out what would make this case stronger when it last answered.'
        : 'NM set out no element for this dispute from the law it read. That is what this research returned, not a '
          + 'finding that the law requires nothing.'));
      return section;
    }
    const lines = caseLines(view, dispute, number ? `Dispute ${number}` : dispute.name, { otherAsLine: true });
    if (caseGathered(view)) {
      // Plan AN.49 (49e; D185): with the gathered account, code's line on how it was checked - and that the second look was not made,
      // where it was not - stands above its lines.
      lines.unshift(make('p', 'board-lede', caseCheckedLine(view)));
      if (CASE_STATES[view.state]) lines.unshift(make('p', 'check-none', CASE_STATES[view.state]));
    }
    // Plan AN.49 (49f; D183): several things told in one reply.
    const rows = caseTellRows(view);
    if (rows.length) lines.push(caseTellButton(dispute, rows));
    return folded(lines, elements.length);
  }
  const meta = make('p', 'dmeta');
  meta.append(...deadlineChips(listed.time_limits));
  if (listed.items.length) meta.appendChild(make('span', 'count', `${listed.in_hand} of ${listed.items.length} in hand`));
  if (meta.children.length) section.appendChild(meta);
  if (!listed.items.length) {
    section.appendChild(make('p', 'check-none', 'NM found nothing this dispute needs in the law it holds. '
      + 'That is what this research returned, not a finding that the law requires nothing.'));
    return section;
  }
  const place = number ? `Dispute ${number}` : dispute.name;
  const lines = [];
  for (const [group, groupTitle] of CHECK_GROUPS) {
    const items = listed.items.filter((item) => item.group === group);
    if (!items.length) continue;
    lines.push(make('p', 'group', groupTitle));
    const ul = make('ul', 'checklist');
    for (const item of items) {
      const li = make('li');
      const row = make('button', `item item--${item.status}`);
      row.type = 'button';
      const words = make('span', 'item-words');
      words.appendChild(make('span', 't', item.need));
      // Under the need, when NM asked for it, or the writer's few words on where it stands.
      const sub = item.status === 'not_given' ? (item.asked_at ? `Asked on ${dayMonth(item.asked_at)}` : '')
        : item.status === 'in_hand' ? '' : (item.note || '');
      if (sub) words.appendChild(make('span', 'sub', sub));
      words.appendChild(make('span', 'sr', ` · ${checkState(item)}`));
      row.append(checkMark(item.status), words);
      row.addEventListener('click', () => window.NmBrainSources.showContent(item.need,
        renderChecklistItem(item, dispute), row, false, `${groupTitle} · ${place}`));
      li.appendChild(row);
      ul.appendChild(li);
    }
    lines.push(ul);
  }
  return folded(lines, listed.items.length);
}

function checkState(item) {
  const mark = CHECK_MARKS[item.status] || CHECK_MARKS.not_given;
  return item.status === 'not_given' && item.asked_at ? `${mark.label} · asked ${fileDate(item.asked_at)}` : mark.label;
}

// An item in the reading pane (owner decision 2, 17 Oct 2026; the design of that day): where
// it stands, why it is needed with the law that requires it (which opens in the pane), what
// shows it or what the advocate said, and what they can do - tell NM about it, or say it
// cannot be had - each putting a start in the message box.
function renderChecklistItem(item, dispute) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const block = (title, ...content) => {
    const section = make('section', 'req-block');
    section.appendChild(make('h4', '', title));
    section.append(...content);
    return section;
  };
  const status = make('p', `req-status item--${item.status}`);
  status.append(checkMark(item.status), make('span', '', checkState(item)));
  const out = [status];
  const law = item.law || {};
  const lawLink = make('button', 'cite', [law.locator, law.title].filter(Boolean).join(', ') || 'The law that requires it');
  lawLink.type = 'button';
  lawLink.addEventListener('click', () => openLaw(law, lawLink));
  const cite = make('p', 'req-law');
  cite.appendChild(lawLink);
  // The law's Act, where India Code does not list it as in force (P21, 19 Oct 2026).
  const force = typeof law.in_force === 'string' && law.in_force.trim() ? law.in_force.trim() : '';
  const marked = force ? make('p', 'source-role warn', force.charAt(0).toUpperCase() + force.slice(1)) : null;
  // Before writer v9 an item gave no reason of its own: the law's words say why.
  out.push(block('Why it is needed', item.why ? make('p', '', item.why) : make('blockquote', 'quote', law.words || ''),
    cite, ...(marked ? [marked] : [])));
  const stands = [];
  if (item.status === 'not_given') {
    stands.push(make('p', '', `Not in your messages or documents yet.${item.asked_at
      ? ` NM asked for it on ${fileDate(item.asked_at)}.` : ''}`));
  } else if (item.note && item.status !== 'in_hand') {
    stands.push(make('p', '', item.note));
  }
  const evidence = item.evidence;
  if (evidence) {
    const where = evidence.from === 'document' ? `From ${evidence.document}, ${evidence.page}`
      : `From your message${evidence.given_at ? ` of ${fileDate(evidence.given_at)}` : ''}`;
    stands.push(make('blockquote', 'quote', evidence.words),
      make('p', 'source-where', item.status === 'in_hand' ? where : `${where}, in your words`));
  }
  out.push(block(item.status === 'in_hand' ? 'What shows it' : item.status === 'not_available' ? 'What you said'
    : 'Where it stands', ...stands));
  if (item.status !== 'in_hand') {
    const fill = startMessage;
    const actions = make('div', 'actions');
    const tell = make('button', 'act primary', 'Tell NM about this');
    tell.type = 'button';
    tell.addEventListener('click', () => fill(`About "${item.need}" (${dispute.name}): `));
    actions.appendChild(tell);
    if (item.status !== 'not_available') {
      const unavailable = make('button', 'act ghost', 'Not available');
      unavailable.type = 'button';
      unavailable.addEventListener('click', () => fill(`About "${item.need}" (${dispute.name}): this is not available.`));
      actions.appendChild(unavailable);
    }
    out.push(actions);
  }
  return out;
}

// WHAT AN ASK OPENS (rendering v16; the readability design, owner 18 Oct 2026): the checklist
// item it asks for, in the reading pane - as the board of the same conversation now holds it
// (the same dispute and need), or else as the answer admitted it.
function openAskedItem(answer, ask, opener) {
  const board = state.chatBoard && state.chatBoard.chat_id === answer.chat_id ? state.chatBoard : null;
  const disputes = board && Array.isArray(board.disputes) ? board.disputes : [];
  const number = disputes.findIndex((dispute) => dispute.id === ask.dispute?.id);
  const dispute = number >= 0 ? disputes[number] : null;
  const item = (dispute?.checklist?.items || []).find((held) => held.need === ask.item.need) || ask.item;
  const group = (CHECK_GROUPS.find(([key]) => key === item.group) || [null, 'Needed'])[1];
  const place = number >= 0 && disputes.length > 1 ? `Dispute ${number + 1}` : (dispute || ask.dispute || {}).name;
  return window.NmBrainSources.showContent(item.need, renderChecklistItem(item, dispute || ask.dispute || {}),
    opener, false, `${group} · ${place || 'this dispute'}`);
}

// A paragraph drawn with its links: a source the reading pane can open, or an ask that opens
// what it asks for (rendering v16).
function linkedBody(el) {
  return Boolean(el.source?.brain) || (Array.isArray(el.asks) && el.asks.length > 0);
}

// The law an item rests on, in the reading pane: the saved passage of the answer that held
// it, read through its own route, where a paragraph of that answer used it; otherwise its
// words as the checklist kept them.
function openLaw(law, opener) {
  const entry = state.turns.find((turn) => turn.answer && turn.answer.turn_id === law.held_in);
  const elements = entry ? entry.answer.elements || [] : [];
  for (const [index, element] of elements.entries()) {
    const at = (element.sources || []).findIndex((source) => source && source.id === law.source_id);
    if (at >= 0 && element.sources[at].brain) {
      return window.NmBrainSources.open(entry.answer, element, index, at, opener);
    }
  }
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const passage = make('div', 'brain-source-text passage');
  passage.appendChild(make('mark', '', law.words || ''));
  const force = typeof law.in_force === 'string' && law.in_force.trim() ? law.in_force.trim() : '';
  return window.NmBrainSources.showContent(law.title || 'The law', [make('p', 'source-where', law.locator || ''),
    make('p', 'source-role', law.kind === 'judgment' ? 'Held judgment' : 'Legislative text'),
    ...(force ? [make('p', 'source-role warn', force.charAt(0).toUpperCase() + force.slice(1))] : []), passage],
  opener, false, law.kind === 'judgment' ? 'Held judgment' : 'Held law');
}

// A DISPUTE IN DETAIL (owner, 16 Oct 2026), in the reading pane (18 Oct 2026): who it is
// between, why it matters, its last days, each time limit in full, where it was picked up
// from, each legal question with why it was asked and what research did, what is at stake
// and sought, what is still needed, and the related points for it. Each part is shown only
// when the saved understanding holds it; an earlier conversation shows no "why it matters".
function renderDisputeDetail(dispute, board) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const list = (items) => {
    const ul = make('ul', 'detail-list');
    for (const item of items) ul.appendChild(make('li', '', item));
    return ul;
  };
  const part = (title, ...content) => {
    const section = make('section', 'detail-section');
    section.appendChild(make('h3', 'detail-h', title));
    section.append(...content);
    return section;
  };
  const out = [];
  if (dispute.between.length) out.push(make('p', 'source-where', `Between ${dispute.between.join(' · ')}`));
  if (dispute.why_it_matters) out.push(make('p', 'dispute-why', dispute.why_it_matters));
  if (dispute.law && dispute.law.state === 'not_assessed') {
    out.push(part('What the law requires', make('p', 'check-none', `Not yet assessed. ${dispute.law.why}`)));
  }
  // PLAN AN.49 (49b; D179; owner, 12 Nov 2026: the pane "is a bit cluttered today and difficult to follow"): A SUMMARY WITH FOLDS. Open
  // at the top: who it is between, why it matters and the last days. Below, each part closed under its name and count; nothing is
  // removed. The case is its lines, each opening alone as from the board, never the whole account again. What discloses - the law
  // not assessed, a case NM could not set out, a second look not made, how the case was checked - stays outside every fold.
  const fold = (title, ...content) => {
    const section = make('details', 'how-checked detail-fold');
    section.appendChild(make('summary', '', title));
    section.append(...content);
    return section;
  };
  const limits = (dispute.checklist && dispute.checklist.time_limits) || [];
  const chips = deadlineChips(limits);
  if (chips.length) {
    const meta = make('p', 'dmeta');
    meta.append(...chips);
    out.push(meta);
  }
  if (dispute.checklist && 'case' in dispute.checklist) {
    const view = dispute.checklist.case;
    const elements = (view && view.elements) || [];
    if (!view) {
      out.push(make('p', 'check-none', 'NM could not set out what would make this case stronger when it last answered.'));
    } else {
      if (CASE_STATES[view.state]) out.push(make('p', 'check-none', CASE_STATES[view.state]));
      if (elements.length) {
        out.push(make('p', 'board-lede', caseCheckedLine(view)));
        const shown = elements.filter((item) => item.status === 'shown').length;
        const toGet = (view.to_get || []).length;
        const number = (board.disputes || []).length > 1 ? board.disputes.findIndex((held) => held.id === dispute.id) + 1 : 0;
        out.push(fold(`The case (${shown} of ${elements.length} shown by the papers${toGet ? ` · ${toGet} to get` : ''})`,
          ...caseLines(view, dispute, number ? `Dispute ${number}` : dispute.name)));
      } else if (view.state !== 'unavailable') {
        out.push(make('p', 'check-none', 'NM set out no element for this dispute from the law it read. That is what this '
          + 'research returned, not a finding that the law requires nothing.'));
      }
    }
  }
  // Each time limit as code worked it out, or why it could not be (18 Oct 2026).
  if (limits.length) {
    const ul = make('ul', 'detail-list');
    for (const limit of limits) {
      const rows = new Map(limit.rows || []);
      const li = make('li');
      li.appendChild(make('p', 'detail-question', limit.what));
      li.appendChild(make('p', 'board-meta', rows.has('Last day')
        ? `Last day ${rows.get('Last day')} · ${timeLimitStanding(rows)}` : timeLimitStanding(rows)));
      ul.appendChild(li);
    }
    out.push(fold(`Time limits (${limits.length})`, ul));
  }
  const facts = (dispute.fact_ids || []).map((id) => board.facts.find((fact) => fact.id === id)).filter(Boolean);
  if (facts.length) {
    const ul = make('ul', 'detail-list');
    for (const fact of facts) {
      const li = make('li');
      li.appendChild(make('span', `board-certainty ${fact.certainty}`, CERTAINTY[fact.certainty] || fact.certainty));
      li.appendChild(make('span', '', ` ${fact.fact}`));
      if (fact.corrected) li.appendChild(correctedMark(fact.corrected, make));
      if (fact.words) li.appendChild(make('blockquote', 'detail-words', fact.words));
      li.appendChild(make('p', 'board-meta', factPlace(fact)));
      ul.appendChild(li);
    }
    out.push(fold(`The facts it rests on (${facts.length})`, ul));
  }
  if (dispute.questions.length) {
    const ol = make('ol', 'detail-list');
    for (const question of dispute.questions) {
      const li = make('li');
      li.appendChild(make('p', 'detail-question', question.question));
      li.appendChild(make('p', `board-status ${question.status}`,
        `Research: ${QUESTION_STATUS[question.status] || question.status}`));
      if (question.why) li.appendChild(make('p', 'board-meta', `Why it was asked: ${question.why}`));
      if (question.open) li.appendChild(make('p', 'board-meta', `Still open: ${question.open}`));
      ol.appendChild(li);
    }
    out.push(fold(`The legal questions researched (${dispute.questions.length})`, ol));
  }
  const related = board.related_points.filter((point) => (point.dispute_id
    ? point.dispute_id === dispute.id : point.dispute === dispute.name));
  const stake = [];
  if (dispute.rights_at_stake.length) stake.push(part('Rights at stake', list(dispute.rights_at_stake)));
  if (dispute.relief_sought.length) stake.push(part('Relief sought', list(dispute.relief_sought)));
  if (dispute.still_needed.length) stake.push(part('Still needed', list(dispute.still_needed)));
  if (related.length) {
    stake.push(part('Related points for your decision',
      list(related.map((point) => (point.why ? `${point.point} — ${point.why}` : point.point)))));
  }
  if (stake.length) {
    out.push(fold(`What is at stake (${dispute.rights_at_stake.length + dispute.relief_sought.length
      + dispute.still_needed.length + related.length})`, ...stake));
  }
  out.push(make('p', 'board-lede', 'NM’s understanding from your messages and documents. Facts are as you '
    + 'or a document gave them, not proved.'));
  return out;
}

// A TIME LIMIT'S WORKING (item 9, owner decisions 15 Oct 2026): the labelled rows and
// lists the server saved with the answer (the Act's own words, what time runs from and
// whose words give it, each date code counted, the assumptions, what is missing and what
// may extend time), drawn exactly as given. Nothing is computed, labelled or put into
// sentences here: the answer's own words explain it, and the research note shows the
// same rows.
function renderWorking(el) {
  const work = el.working;
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const box = make('section', 'el WORKING working-box');
  box.setAttribute('aria-label', `Working: ${work.what}`);
  box.appendChild(make('p', 'working-label', 'Working'));
  box.appendChild(make('p', 'working-result', work.what));
  const rows = make('dl', 'working-rows');
  for (const [label, value] of work.rows || []) {
    rows.appendChild(make('dt', '', label));
    rows.appendChild(make('dd', '', value));
  }
  box.appendChild(rows);
  for (const [title, items] of work.lists || []) {
    box.appendChild(make('p', 'working-label', title));
    const list = make('ul', 'working-list');
    for (const item of items) list.appendChild(make('li', '', item));
    box.appendChild(list);
  }
  return box;
}

// IN SHORT, THE TIME LIMITS AND WHAT NM NEEDS (owner decisions, 17 Oct 2026; the design of
// that day): each run of dispute summaries reads as one "In short" box, each run of code's
// time-limit boxes as one small table, and the questions the server gathers under "What I
// need from you" (rendering v14) as one block. Nothing is dropped or reordered; runs are
// only gathered.
// THE ANSWER AS THE ADVOCATE READS IT (owner decisions P39-P41 and P44, 24 Oct 2026; rendering
// v18): "In short" as one table, a row for each dispute, with the line on what to do first under
// it; each section's risks and next steps as lists; "More on this" folded; what NM needs grouped
// by dispute. Earlier answers group as before.
function groupAnswerElements(elements) {
  const IN_SHORT_PARTS = new Set(['ROW', 'ROW_ACTION', 'ROW_READY', 'DO_FIRST', 'TIES']);
  const NEED_PARTS = new Set(['QUESTION', 'NEED_GROUP', 'NEED_ITEM', 'NEED_CASE', 'ASK', 'YOUR_CALL']);
  const ANSWER_RUNS = { RISK: 'RISKS', STEP: 'STEPS', MORE: 'MORE_FOLD' };
  const out = [];
  for (const el of elements) {
    const last = out[out.length - 1];
    if (el.kind === 'NEEDS') { out.push({ kind: 'NEEDS', text: el.text, items: [] }); continue; }
    if (NEED_PARTS.has(el.kind) && last && last.kind === 'NEEDS' && Array.isArray(last.items)) {
      last.items.push(el);
      continue;
    }
    if (el.kind === 'IN_SHORT' && !Array.isArray(el.items)) {
      out.push({ kind: 'IN_SHORT_TABLE', text: el.text, rows: [], lines: [] });
      continue;
    }
    if (IN_SHORT_PARTS.has(el.kind) && last && last.kind === 'IN_SHORT_TABLE') {
      const row = last.rows[last.rows.length - 1];
      if (el.kind === 'ROW') last.rows.push({ row: el, action: null, ready: null });
      else if (el.kind === 'ROW_ACTION' && row) row.action = el;
      else if (el.kind === 'ROW_READY' && row) row.ready = el;
      else last.lines.push(el);
      continue;
    }
    const kind = el.kind === 'SUMMARY' ? 'IN_SHORT'
      : (el.kind === 'WORKING' && el.working ? 'TIME_LIMITS' : ANSWER_RUNS[el.kind] || null);
    if (kind && last && last.kind === kind) last.items.push(el);
    else if (kind) out.push({ kind, items: [el] });
    else out.push(el);
  }
  return out;
}

// THE TIME LIMITS AS ONE SMALL TABLE (owner decisions, 17 Oct 2026; the design of that
// day): each limit, its last day and what is left, from the rows the server saved; its
// working opens in the reading pane. Why a limit was not worked out stays in view under its
// name, and what the counting assumes is said once under the table, never folded away.
const TIME_LIMIT_CAVEATS = ['Court closed on the last day'];

function timeLimitStanding(rows) {
  if (rows.has('Not assessed')) return `Not assessed: ${rows.get('Not assessed')}`;
  const days = [...rows.keys()].find((label) => /^Days /.test(label));
  const count = days ? `${rows.get(days)} ${rows.get(days) === '1' ? 'day' : 'days'} ${days.slice(5)}` : '';
  return [rows.get('Result'), count, rows.get('As of') ? `as of ${rows.get('As of')}` : '']
    .filter(Boolean).join(' · ');
}

// What is left of a time limit, in the saved count's own words: '874 days left', or the
// result first where it is not open ('Passed · 17 days since the last day').
function timeLimitLeft(rows) {
  if (rows.has('Not assessed')) return '—';
  const days = [...rows.keys()].find((label) => /^Days /.test(label));
  const count = days ? `${rows.get(days)} ${rows.get(days) === '1' ? 'day' : 'days'} ${days.slice(5)}` : '';
  const result = rows.get('Result');
  return result === 'Open' ? count || result : [result, count].filter(Boolean).join(' · ');
}

// A time limit's working in the reading pane: the provision, then each labelled row and
// list exactly as the server saved them.
function renderWorkingView(el) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const rows = el.working.rows || [];
  const provision = rows.find(([label]) => label === 'Provision');
  const out = [];
  if (provision) out.push(make('p', 'source-where', provision[1]));
  const table = make('table', 'working-table');
  const body = make('tbody');
  for (const [label, value] of rows) {
    if (label === 'Provision') continue;
    const row = make('tr');
    row.append(make('th', '', label), make('td', '', value));
    body.appendChild(row);
  }
  table.appendChild(body);
  const scroll = make('div', 'time-limit-scroll');
  scroll.appendChild(table);
  out.push(scroll);
  for (const [title, items] of el.working.lists || []) {
    out.push(make('h4', 'working-label', title));
    const list = make('ul', 'working-list');
    for (const item of items) list.appendChild(make('li', '', item));
    out.push(list);
  }
  return out;
}

function renderTimeLimits(items) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const box = make('section', 'el time-limits');
  box.setAttribute('aria-label', 'Time limits');
  const table = make('table', 'time-limit-table');
  const head = make('tr');
  for (const label of ['Time limit', 'Last day', 'Left']) head.appendChild(make('th', '', label));
  const thead = make('thead');
  thead.appendChild(head);
  const body = make('tbody');
  const caveats = [];
  const asOf = new Set();
  for (const el of items) {
    const rows = new Map(el.working.rows || []);
    for (const label of TIME_LIMIT_CAVEATS) {
      if (rows.has(label) && !caveats.includes(rows.get(label))) caveats.push(rows.get(label));
    }
    if (rows.has('As of')) asOf.add(rows.get('As of'));
    const row = make('tr');
    const what = make('td', 'time-limit-what');
    what.appendChild(make('span', '', `${el.working.what} · `));
    const working = make('button', 'cite', 'working');
    working.type = 'button';
    working.setAttribute('aria-label', `The working: ${el.working.what}`);
    working.addEventListener('click', () => window.NmBrainSources.showContent(el.working.what,
      renderWorkingView(el), working, false, 'Time limit · worked out by code'));
    what.appendChild(working);
    if (rows.has('Not assessed')) what.appendChild(make('span', 'limit-why', `Not worked out: ${rows.get('Not assessed')}`));
    row.append(what, make('td', 'num', dayDate(el.working.last_day) || rows.get('Last day') || '—'),
      make('td', 'num', timeLimitLeft(rows)));
    body.appendChild(row);
  }
  table.append(thead, body);
  const scroll = make('div', 'time-limit-scroll');
  scroll.appendChild(table);
  box.appendChild(scroll);
  if (asOf.size === 1) box.appendChild(make('p', 'time-limit-note', `Days are counted as of ${[...asOf][0]}.`));
  for (const caveat of caveats) box.appendChild(make('p', 'time-limit-note', caveat));
  return box;
}

// A REPLY ANSWERING SEVERAL DISPUTES (owner decision, 15 Oct 2026; laid out as the design
// shows it, 18 Oct 2026): each dispute's part under its numbered heading, all open. The
// headings are the server's, in the answer's own order.
function renderParts(into, elements, entry, render) {
  if (elements.filter((el) => el.kind === 'HEADING').length < 2) {
    for (const el of elements) render(into, el);
    return;
  }
  let body = into;
  let number = 0;
  for (const el of elements) {
    // Code's notices about the whole answer, and what NM needs from the advocate, stand
    // outside the parts (17 and 18 Oct 2026).
    // From rendering v18 the checks folded last and the time limits no section names stand
    // outside the parts too (P39, P40).
    if (el.kind === 'NOTICE' || el.kind === 'NEEDS' || el.kind === 'CHECKED' || el.kind === 'PAPERS' || el.outside
        || (el.kind === 'TIME_LIMITS' && el.items.every((item) => item.outside))) { render(into, el); continue; }
    if (el.kind !== 'HEADING') { render(body, el); continue; }
    number += 1;
    const section = document.createElement('section');
    section.className = 'answer-part';
    const head = document.createElement('div');
    head.className = 'part-h';
    const n = document.createElement('span');
    n.className = 'n';
    n.textContent = String(number);
    const title = document.createElement('h3');
    title.className = 'part-title';
    title.textContent = el.text;
    head.append(n, title);
    body = document.createElement('div');
    body.className = 'part-body';
    section.append(head, body);
    into.appendChild(section);
  }
}

// WHAT AN ANSWER HAS SHOWN SO FAR, while it is still being written (owner decisions P26-P27,
// 19 Oct 2026): each dispute's section as it passes its checks, drawn plainly - its sources
// open from the answer once it is saved, which replaces this.
// PLAN AN.41 (D68; owner, 4 Nov 2026: "show the work in pieces as they are done instead of waiting for everything to be done"):
// the work as it finishes, from the saved conversation - about a minute in, the disputes and the legal questions NM found, a short
// line each, so that a misunderstanding can be put right early; each dispute's law as its research finishes; each section written,
// being checked, rewritten after its check asked for corrections, then shown below. Never the AI's words before their check (D72).
const PART_SAID = { writing: 'being written', checking: 'written - being checked' };
const LAW_SHOWN = 4;
// where: the answer being worked on ({chat_id, turn_id}); each law its research chose opens in the reading pane, as the board's does.
function renderWork(work, parts, where = null) {
  if (!work || !work.understood) return null;
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const box = make('div', 'progress-work');
  const list = make('ul', 'progress-disputes');
  for (const dispute of work.disputes || []) {
    const item = make('li', 'progress-dispute');
    item.appendChild(make('span', 'progress-dispute-name', dispute.name));
    const questions = (dispute.questions || []).filter(Boolean);
    if (questions.length) item.appendChild(make('span', 'progress-questions', ` · ${questions.join(' · ')}`));
    if (dispute.researched) {
      const law = (dispute.law || []).map((found) => ({ found, said: found.kind === 'provision'
        ? [found.section ? `s. ${found.section}` : '', found.act].filter(Boolean).join(', ') : found.title }))
        .filter((entry) => entry.said)
        .sort((a, b) => (a.found.kind === 'provision' ? 0 : 1) - (b.found.kind === 'provision' ? 0 : 1));
      const line = make('div', 'progress-law', law.length ? 'Law chosen: ' : 'Researched: no held law chosen');
      // A short line (D68): the first few, the rest behind 'and N more'.
      const draw = (count) => {
        line.replaceChildren();
        line.appendChild(make('span', '', law.length ? 'Law chosen: ' : 'Researched: no held law chosen'));
        law.slice(0, count).forEach(({ found, said }, index) => {
          if (index) line.appendChild(make('span', '', '; '));
          if (!where || !where.chat_id || !found.tag || !window.NmBrainSources) { line.appendChild(make('span', '', said)); return; }
          const open = make('button', 'cite', said);
          open.type = 'button';
          open.addEventListener('click', () => window.NmBrainSources.openPassage(where, found.tag, open,
            { phrase: `Chosen by the research for ${dispute.name}`, title: said }));
          line.appendChild(open);
        });
        if (law.length > count) {
          const more = make('button', 'ghost', `and ${law.length - count} more`);
          more.type = 'button';
          more.addEventListener('click', () => draw(law.length));
          line.append(make('span', '', ' '), more);
        }
      };
      draw(LAW_SHOWN);
      item.appendChild(line);
    }
    const section = (work.sections || []).find((part) => part.dispute_id === dispute.id);
    if (section) {
      const now = parts[section.part];
      const said = section.done ? 'Section shown below'
        : now && now.state === 'rewriting'
          ? `The check asked for ${now.corrections || 'some'} correction${now.corrections === 1 ? '' : 's'} - rewriting`
          : now ? `Section ${PART_SAID[now.state] || 'being written'}` : '';
      if (said) item.appendChild(make('div', 'progress-section', said));
    }
    list.appendChild(item);
  }
  box.appendChild(list);
  if (work.checked_across) box.appendChild(make('div', 'progress-section', 'The sections are checked against each other'));
  return box;
}

// PLAN AN.48 (48a4; D134-D135, D147, D164): A MATTER WORKED STEP BY STEP WAITS FOR THE ADVOCATE. Not a failure, so not red: what
// NM has done, what comes next, the go-aheads it offers - the next step, End to end, Done - and what it noticed that was not asked,
// offered and never done. In the conversation area only: the board and the reading pane are unchanged (D60).
function renderWaiting(entry) {
  const card = entry.stopped.waiting;
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const box = make('div', 'waiting-card');
  box.setAttribute('role', 'status');
  // Plan AN.48 (D175): how NM took a follow-up - from its earlier understanding of the matter, or with the whole matter read again.
  if (typeof card.taken === 'string' && card.taken) box.appendChild(make('p', 'waiting-taken', card.taken));
  // Plan AN.48 (48c; D146): the messages sent while the matter waited, and how NM took each - for the advocate to correct.
  for (const heard of Array.isArray(card.heard) ? card.heard : []) {
    const line = make('p', 'waiting-heard');
    line.append(make('span', 'waiting-heard-you', `You: ${heard.text}`), make('span', 'waiting-heard-nm', ` NM: ${heard.said}`));
    box.appendChild(line);
  }
  box.appendChild(make('p', 'waiting-head', card.done_said));
  box.appendChild(make('p', 'waiting-next', card.next_said));
  // Plan AN.48 (48d; D142): NM's questions wait for the advocate's answers - no default - answered here.
  const asked = Array.isArray(card.questions) ? card.questions : [];
  const open = asked.filter((question) => !question.answer);
  if (open.length) {
    const ask = make('p', 'waiting-asked', `NM asks ${open.length === 1 ? 'a question' : `${open.length} questions`} before it `
      + 'writes what depends on the answers:');
    const answer = make('button', '', open.length === 1 ? "Answer NM's question" : "Answer NM's questions");
    answer.type = 'button';
    answer.disabled = Boolean(activeDelivery);
    answer.addEventListener('click', () => openTurnQuestions(entry, {
      view: { questions: asked, defaults_applied: false,
        answers: asked.filter((question) => question.answer).map((question) => ({ id: question.id,
          chosen: question.answer.chosen, other: question.answer.other, how: 'answered' })) },
      said: 'NM waits for your answer before it writes what depends on it; it does not go on with a default.',
      submit: (answers) => answerTurn(entry, answers) }));
    ask.appendChild(make('span', '', ' '));
    ask.appendChild(answer);
    box.appendChild(ask);
  }
  if (Array.isArray(card.noticed) && card.noticed.length) {
    box.appendChild(make('p', 'waiting-noticed-head', 'NM noticed, though you did not ask - say if you want it looked at:'));
    const list = make('ul', 'waiting-noticed');
    for (const item of card.noticed) list.appendChild(make('li', '', item));
    box.appendChild(list);
  }
  if (entry.goError) box.appendChild(make('p', 'refusal-gap', `Not taken: ${entry.goError}`));
  const buttons = make('div', 'waiting-actions');
  (card.gos || []).forEach((go, index) => {
    const button = make('button', index === 0 ? '' : 'ghost', go.said);
    button.type = 'button';
    button.dataset.choice = go.choice;
    button.disabled = Boolean(activeDelivery);
    // Plan AN.48 (48b): a go-ahead for research or an analysis names its disputes; none means every dispute it can take.
    button.addEventListener('click', () => goTurn(entry, go.choice, Array.isArray(go.disputes) ? go.disputes : null));
    buttons.appendChild(button);
  });
  box.appendChild(buttons);
  // Plan AN.48 (48e, D140): how long each go-ahead should take - tentative.
  const timed = (card.gos || []).filter((go) => go.tentative);
  if (timed.length) {
    box.appendChild(make('p', 'waiting-tentative', `Tentative times - ${timed.map((go) => `${go.said}: ${go.tentative}`)
      .join('; ')}.`));
  }
  return box;
}

// The red message (D69): why, what is finished and what is not, what must be put right first; Continue and Discard (D70, D71).
function renderStopped(entry) {
  const stopped = entry.stopped || {};
  if (stopped.code === 'waiting' && stopped.waiting) return renderWaiting(entry);
  const box = document.createElement('div');
  box.className = 'failure stopped';
  box.setAttribute('role', 'status');
  const head = document.createElement('p');
  head.className = 'refusal-head';
  head.textContent = `NM stopped before finishing this answer. ${stopped.why || (entry.refusal && entry.refusal.why) || ''}`.trim();
  box.appendChild(head);
  const said = (label, items) => {
    if (!Array.isArray(items) || !items.length) return;
    const line = document.createElement('p');
    line.className = 'refusal-gap';
    line.textContent = `${label}: ${items.join('; ')}.`;
    box.appendChild(line);
  };
  said('Finished', stopped.finished);
  said('Not finished', stopped.unfinished);
  if (stopped.needs) {
    const needs = document.createElement('p');
    needs.className = 'refusal-gap';
    needs.textContent = stopped.needs;
    box.appendChild(needs);
  }
  if (entry.discardError) {
    const failed = document.createElement('p');
    failed.className = 'refusal-gap';
    failed.textContent = `Not discarded: ${entry.discardError}`;
    box.appendChild(failed);
  }
  const buttons = document.createElement('div');
  buttons.className = 'stopped-actions';
  const go = document.createElement('button');
  go.type = 'button';
  go.textContent = 'Continue';
  go.disabled = Boolean(activeDelivery) || Boolean(entry.discarding);
  go.addEventListener('click', () => continueTurn(entry));
  const drop = document.createElement('button');
  drop.type = 'button';
  drop.className = 'ghost';
  drop.textContent = 'Discard';
  drop.title = 'Keep the answer as it stopped, without finishing it';
  drop.disabled = Boolean(activeDelivery) || Boolean(entry.discarding);
  drop.addEventListener('click', () => discardTurn(entry));
  buttons.append(go, drop);
  if (stopped.code === 'model_permission_required') {
    // What must be put right first, where it is put right.
    const settings = document.createElement('button');
    settings.type = 'button';
    settings.className = 'ghost';
    settings.textContent = 'Review AI data sharing';
    settings.addEventListener('click', openAiSharing);
    buttons.appendChild(settings);
  }
  box.appendChild(buttons);
  return box;
}

function renderShownSoFar(elements) {
  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const box = make('section', 'shown-so-far');
  box.setAttribute('aria-label', 'Shown so far');
  box.appendChild(make('p', 'shown-so-far-label', 'Shown as each part is checked; the full answer replaces this when it is ready.'));
  for (const el of groupAnswerElements(elements)) {
    if (el.kind === 'HEADING') { box.appendChild(make('h3', 'part-title', el.text)); continue; }
    if (el.kind === 'IN_SHORT' || el.kind === 'NEEDS') {
      box.appendChild(make('h4', 'shown-so-far-title', el.kind === 'IN_SHORT' ? 'In short' : el.text));
      const list = make('ul', el.kind === 'IN_SHORT' ? 'in-short-list' : 'need-list');
      for (const item of el.items) list.appendChild(make('li', '', item.text));
      box.appendChild(list);
      continue;
    }
    if (el.kind === 'TIME_LIMITS') { box.appendChild(renderTimeLimits(el.items)); continue; }
    // Rendering v18: In short's rows as lines, lists as lists; the checks wait for the answer.
    if (el.kind === 'IN_SHORT_TABLE') {
      box.appendChild(make('h4', 'shown-so-far-title', el.text));
      const list = make('ul', 'in-short-list');
      for (const { row, action } of el.rows) {
        const waiting = row.row && row.row.status === 'waiting';
        list.appendChild(make('li', '', action ? `${row.text}: ${action.text}`
          : waiting ? `${row.text}: still being written and checked` : row.text));
      }
      box.appendChild(list);
      for (const line of el.lines) box.appendChild(make('p', `el ${line.kind}`, line.text));
      continue;
    }
    if (el.kind === 'RISKS' || el.kind === 'STEPS' || el.kind === 'MORE_FOLD') {
      if (el.kind === 'MORE_FOLD') box.appendChild(make('h4', 'shown-so-far-title', 'More on this'));
      const list = make(el.kind === 'STEPS' ? 'ol' : 'ul', 'need-list');
      for (const item of el.items) list.appendChild(make('li', '', item.text));
      box.appendChild(list);
      continue;
    }
    if (el.kind === 'CHECKED' || el.kind === 'PAPERS' || el.kind === 'CASE') continue;
    const text = el.kind === 'FALLBACK' ? String(el.text || '').split('\n')[0] : el.text;
    box.appendChild(make('p', `el ${el.kind}${el.disclosure ? ' disclosure' : ''}`, text));
  }
  return box;
}

// PLAN AN.43 (D84; owner, 5 Nov 2026: "put the heading just once in the begining, after the first message is saved, till the NM
// names it, we can put <empty title> and once NM names it, let it stay that way"): the conversation's title once, at its beginning,
// from when its first message is sent (saved at Send, AN.41 D66) - empty until NM names it, then as NM named it.
function threadTitle() {
  if (!state.turns.some((entry) => entry.turnId || entry.answer)) return [];
  // A first message's conversation is known by the turn's progress before its answer names it on the page.
  const chatId = (activeIntent && activeIntent.chatId) || (state.turns.find((entry) => entry.chatId) || {}).chatId || null;
  const known = state.chatTitle && state.chatTitle.chatId === chatId ? state.chatTitle.text : null;
  const heading = document.createElement('h2');
  heading.className = known ? 'thread-title' : 'thread-title unnamed';
  heading.textContent = typeof known === 'string' ? known : '';
  return [heading];
}

// The title as the conversation now says it (D84): kept once named; asked for again only while it is not.
function takeTitle(chatId, title) {
  if (!chatId) return;
  if (state.chatTitle && state.chatTitle.chatId === chatId && state.chatTitle.text) return;
  state.chatTitle = { chatId, text: typeof title === 'string' && title.trim() ? title.trim() : null };
}

async function refreshTitle(chatId) {
  if (!chatId || (state.chatTitle && state.chatTitle.chatId === chatId && state.chatTitle.text)) return;
  try {
    const said = await api(`/api/chats/${encodeURIComponent(chatId)}/title`);
    if (!activeIntent || activeIntent.chatId !== chatId) return;
    takeTitle(chatId, said.title);
    repaint();
  } catch (error) { /* the conversation goes on untitled here; it is named on the next reading */ }
}

function repaint() {
  const t = $('thread');
  const follow = t.scrollHeight - t.scrollTop - t.clientHeight < 48;
  const top = t.scrollTop;
  t.replaceChildren(...threadTitle(), ...state.turns.map(renderTurn));
  t.scrollTop = follow ? t.scrollHeight : top;
  $('jump-latest').hidden = follow;
  updateWorkspace();
}

function sizeComposer() {
  const box = $('message');
  box.style.height = 'auto';
  // CSS owns the viewport-aware maximum. Recompute after both input and clear.
  box.style.height = `${Math.max(box.scrollHeight, 44)}px`;
}

function updateWorkspace() {
  const intakeOpen = !$('intake').hidden && !openingEdit;
  $('composer').hidden = intakeOpen || $('pane-advise').dataset.view === 'list';
  // The board's file icon is the conversation's; an earlier matter record keeps its
  // own file icon in its header.
  $('board-files').hidden = Boolean(state.matterId);
  // With the count of the files sent in this conversation (the design of 17 Oct 2026).
  const sent = state.turns.reduce((count, entry) => count + (Array.isArray(entry.documents) ? entry.documents.length : 0), 0);
  $('board-files-count').textContent = sent ? `Files · ${sent}` : 'Files';
  $('board-files').setAttribute('aria-label', `Files${sent ? ` (${sent})` : ''}: documents and research notes`);
  syncBoardStatus();
  $('pane-advise').classList.toggle('empty-chat',
    $('pane-advise').dataset.view === 'opening' && !state.turns.length);
  // F-B-04. The file icon is offered for an open matter, and on a new matter's
  // form, where Recover a draft is the one record that already applies.
  const filesShown = Boolean(state.matterId) || intakeOpen;
  $('matter-files').hidden = !filesShown;
  if (!filesShown) closeFilesMenu();
  paintSend();
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

function consumeComposer(entry) {
  // Only explicit Send consumes the field. A receipt retry preserves even an
  // identical follow-up draft typed since the original submission.
  if ($('message').value !== entry.brief) return;
  $('message').value = '';
  entry.context.text = '';
  sizeComposer();
}

// fromBox (plan AN.40, D62): the message is the message box's, so that if it waits for its files what goes is what the box holds then.
async function send(message, { workProduct, keepInMatter = false, fromBox = false } = {}) {
  if (activeDelivery || (state.matterId && !state.matterReady)) return;
  // One message waits for the files at a time; it goes as soon as they are read.
  if (heldSend) { $('attachments-status').textContent = HOLD_SAID; return; }
  if (!activeIntent) selectIntent(state.matterId, { opening: !state.matterId });
  snapshotIntent();
  // Re-entering Send with an unresolved identical intent is also a retry.
  const pending = activeIntent.pending.find((entry) => entry.brief === message
    && (entry.request.thread_id || null) === (state.disputeFocus || null)
    && entry.request.work_product === workProduct && matchesIntake(entry, state.intake)
    && ['unknown', 'not_committed', 'sending'].includes(entry.state)
    && entry.refusal?.retryable !== false);
  if (pending) { consumeComposer(pending); await deliver(pending); return; }
  // The documents attached under the brief travel with this message only.
  const blocked = attachmentsBlockSend({ reading: false });
  if (blocked) { $('attachments-status').textContent = blocked; return; }
  // Plan AN.40 (D61): a file still being uploaded or read holds the message, which goes by itself once it is read.
  if (attachmentsReading()) { holdSend(message, { workProduct, keepInMatter, fromBox }); return; }
  if (attachments.length > 1) await relookAttachments();
  // Plan AN.48 (48c; D146): while a matter waits for the advocate, a message belongs to it - NM reads how it was meant.
  const waitingEntry = activeIntent.pending.find((entry) => entry.state === 'stopped' && entry.stopped
    && entry.stopped.code === 'waiting');
  if (waitingEntry) { messageTurn(waitingEntry, message); return; }
  const documents = attachments.map((item) => ({ document_ref: item.summary.document_ref,
    name: item.summary.name, recording: Boolean(item.summary.recording), pages_read: item.summary.pages_read,
    pages_read_by_ai: item.summary.pages_read_by_ai, pages_unread: item.summary.unread.length }));
  const entry = { brief: message, turnId: newTurnId(), state: 'sending',
    context: activeIntent, documents,
    request: { matter_id: state.matterId, chat_id: activeIntent.chatId || null,
      thread_id: state.disputeFocus, expected_version: state.matterVersion,
      parties: { ...((state.intake && state.intake.parties) || {}) },
      release: { ...((state.intake && state.intake.release) || {}) },
      capacity: state.intake && state.intake.capacity ? { ...state.intake.capacity } : null,
      work_product: workProduct } };
  // This serialized envelope never changes across navigation, reauthentication
  // or retry. Only the rendering attempt receives a fresh lifetime.
  entry.envelope = JSON.stringify({
    message: entry.brief, matter_id: entry.request.matter_id,
    chat_id: entry.request.chat_id, thread_id: entry.request.thread_id, turn_id: entry.turnId,
    parties: entry.request.parties, release: entry.request.release,
    capacity: entry.request.capacity,
    expected_version: entry.request.expected_version, work_product: entry.request.work_product,
    // F-C-04. Only the advocate's explicit choice travels; its absence is the
    // ordinary offer, spelled as it always was.
    ...(keepInMatter ? { keep_in_matter: true } : {}),
    ...(documents.length ? { document_refs: documents.map((document) => document.document_ref) } : {}),
    // Plan AN.33 (D23): the model and the effort chosen for this message travel where they are not the defaults.
    ...(state.turnChoice || {}),
    // Plan AN.48 (D134): every message is worked step by step, stopping for the advocate's go-ahead after each step; End to end
    // is given at a stop (D135).
    steps: 'interactive',
  });
  activeIntent.pending.push(entry);
  state.turns.push(entry);
  consumeComposer(entry);
  attachments = [];
  renderAttachments();
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
  // Writing remains available while delivery is in flight; Send is the turning ring until words are typed (plan AN.42, D74, D76).
  const stop = new AbortController();
  const delivery = { controller: stop, entry };
  activeDelivery = delivery;
  checkIdle();  // D65: NM working counts as activity from now
  paintSend();
  $('message').placeholder = COMPOSER_WAITING;
  entry.state = 'sending';
  entry.error = null;
  entry.refusal = null;
  entry.cancelled = false;
  repaint();
  $('thread').scrollTop = $('thread').scrollHeight;
  $('jump-latest').hidden = true;
  let watcher = null;
  try {
    if (!await saveProtectedDraft()) {
      throw new Error('The retry details could not be saved on this device. No request was sent.');
    }
    watcher = watchProgress(entry);
    // Plan AN.41 (D70): Continue sends the same turn by its own route, which reads its message and files as saved.
    let answer = await api(entry.endpoint || '/api/turn', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      signal: stop.signal, body: entry.envelope,
    });
    // Plan AN.48 (48f1, D167): a step still working when the server's wait ended goes on by itself; what it answers - this same
    // answer, or its refusal as the request would have said it - is read once it is done.
    if (answer && answer.working === true) answer = await stepOutcome(entry, answer, stop.signal);
    if (entry.attempt !== attempt) return;
    if (current()) snapshotIntent();
    entry.answer = answer;
    entry.state = answer.replayed ? 'replayed' : 'committed';
    entry.stopped = null;
    entry.endpoint = null;
    intent.pending = intent.pending.filter((item) => item !== entry);
    if (matchesIntake(entry, intent.intake)) intent.intake = null;
    // A reply belongs to the conversation that sent it. An unestablished
    // screen may ask for information, but prose must never navigate back to
    // the opening form or hide that question. Opening is an explicit user
    // action; correcting a saved cover uses the matter's own controls.
    intent.intakeOpen = false;
    // A saved opening acquires a file identity, but its original turn envelope
    // keeps matter_id:null for idempotent replay if this acknowledgement is lost.
    const previousKey = intent.key;
    if (answer.chat_id && !intent.chatId) {
      intentContexts.delete(intent.key);
      intent.chatId = answer.chat_id;
      intent.key = intentKey(intent.matterId, intent.chatId);
      intentContexts.set(intent.key, intent);
      // Saved, it is in the conversation history, which is read each time it opens.
    }
    if (answer.matter_id && !intent.matterId) {
      intentContexts.delete(intent.key);
      intent.matterId = answer.matter_id;
      intent.key = intentKey(intent.matterId, intent.chatId);
      intentContexts.set(intent.key, intent);
    }
    if (!current()) return;
    restoreIntent();
    await saveProtectedDraft({previousKey});
    // Plan AN.53 (53i, D224): A LATE REPLY ACTS ONLY ON ITS OWN CONVERSATION. Saving the draft is a wait; an advocate who opened
    // another conversation meanwhile stays in it - this answer is read from its own conversation when that is opened again.
    if (!current()) return;
    state.matterId = intent.matterId;
    if (Number.isInteger(answer.matter_version)) state.matterVersion = answer.matter_version;
    repaint();
    if (state.matterId) await showThreadBoard(state.matterId, {
      restore: false, closeNavigator: false, deferBoard: !entry.request.matter_id,
    });
    // The board is read again after every answer (owner, 16 Oct 2026).
    else if (intent.chatId) loadChatBoard();
    // Plan AN.43 (D84): the title, where NM had not named the conversation when this answer began.
    if (intent.chatId) refreshTitle(intent.chatId);
  } catch (e) {
    // clearPrivileged already freezes an abandoned attempt as unknown. Neither
    // that old response nor a later retry can rewrite one another's outcome.
    if (e.obsolete || entry.attempt !== attempt) return;
    entry.error = e.message;
    entry.refusal = (e.detail && typeof e.detail === 'object') ? e.detail : null;
    const said = entry.refusal && entry.refusal.committed;
    entry.state = said === 'not_committed' ? 'not_committed' : 'unknown';
    if (said === 'input_only') entry.state = 'input_only';
    if (said === 'previously_committed' && entry.refusal.release_state === 'replay_refused') {
      entry.state = 'replay_refused';
    }
    if (entry.cancelled) {
      entry.state = 'unknown';
      entry.error = 'You cancelled this turn’s request; whether it was saved is not confirmed.';
    }
    if (e.status === 409 && entry.refusal?.code === 'stale_version') entry.state = 'stale';
    // Plan AN.41 (D69): the answer stopped part-way and what NM finished is kept: the red message, read from the conversation.
    if (entry.refusal?.kept) {
      entry.state = 'stopped';
      entry.error = null;
      refreshStopped(entry, entry.chatId || intent.chatId || entry.request?.chat_id);
      // Plan AN.48 (48c): a new question heard while the matter waits goes as the next message, once the matter is done.
      if (entry.refusal.heard && entry.refusal.heard.taken === 'question' && entry.lastSent
          && !(intent.queued || []).some((item) => item.text === entry.lastSent)) {
        if (!Array.isArray(intent.queued)) intent.queued = [];
        intent.queued.push({ text: entry.lastSent, files: [] });
        renderQueued();
      }
    } else if (['/api/turn/go', '/api/turn/message', '/api/turn/answers'].includes(entry.endpoint)
        && [409, 422].includes(e.status)) {
      // Plan AN.48: a go-ahead the matter no longer waits for is said on its card, read again from the conversation.
      entry.goError = (entry.refusal && entry.refusal.why) || e.message;
      entry.state = 'stopped';
      entry.error = null;
      refreshStopped(entry, entry.chatId || intent.chatId || entry.request?.chat_id);
    }
    // D73: no reply at all - the server is being restarted. The page waits for it and follows the answer, which NM continues.
    if (!e.status && !entry.cancelled && !(e.name === 'AbortError')) {
      entry.state = 'reconnecting';
      entry.error = null;
      reconnect(entry);
    }
    if (!current()) return;
    if (entry.state === 'input_only' && entry.refusal?.matter_id) {
      const openedId = entry.refusal.matter_id;
      if (!intent.matterId && !entry.request.matter_id) {
        const previousKey = intent.key;
        intentContexts.delete(previousKey);
        intent.matterId = openedId;
        intent.key = intentKey(openedId);
        intentContexts.set(intent.key, intent);
        intent.pending = intent.pending.filter((item) => item !== entry);
        state.matterId = openedId;
        await saveProtectedDraft({previousKey});
        if (!current()) return;  // 53i: the advocate left during that wait
      }
      if (Number.isInteger(entry.refusal.matter_version)) {
        state.matterVersion = entry.refusal.matter_version;
      }
      await showThreadBoard(openedId, {
        restore: false, closeNavigator: false, deferBoard: !entry.request.matter_id,
      }).catch(() => {});
    }
    if (entry.state === 'stale' && state.matterId) {
      await showThreadBoard(state.matterId).catch(() => {});
    }
    if (ownsIntent(intent) && attempt.session === state.sessionGeneration) repaint();
  } finally {
    if (watcher) watcher.stop();
    entry.progress = null;
    if (activeDelivery === delivery) {
      activeDelivery = null;
      $('message').placeholder = COMPOSER_PROMPT;
      updateWorkspace();
      // An answer, made or not, may have used some of the allowance (P53).
      loadUsage();
      nmFinished();
    }
    if (!['reconnecting', 'stopped'].includes(entry.state)) releaseQueued(entry);
  }
}

// PLAN AN.48 (48f1, D167): A STEP THAT WENT ON BY ITSELF. The server answered that it is working; what it answers is read when it is
// done - exactly what the request would have answered, its refusal included. A moment without the network is waited out. Where the
// server no longer holds the step (it was restarted), the error carries no status, so that the page follows the conversation as it
// does after a restart (D73).
const STEP_EVERY_MS = 2000;
async function stepOutcome(entry, working, signal) {
  if (working.chat_id) entry.chatId = working.chat_id;
  for (let tries = 0; ; tries += 1) {
    await pauseFor(STEP_EVERY_MS, signal);
    let seen;
    try {
      seen = await api(`/api/turn/outcome?turn_id=${encodeURIComponent(entry.turnId)}`, { signal });
    } catch (error) {
      if (error?.status === 404 && error.detail?.code === 'no_step') throw new Error('NM no longer holds this step.');
      if (!error?.status && !error?.obsolete && error?.name !== 'AbortError' && tries < 400) continue;
      throw error;
    }
    if (!(seen && seen.working === true)) return seen;
    if (seen.chat_id) entry.chatId = seen.chat_id;
  }
}

function pauseFor(ms, signal) {
  return new Promise((resolve, reject) => {
    const aborted = () => reject(Object.assign(new Error('The request was cancelled.'), { name: 'AbortError' }));
    if (signal && signal.aborted) { aborted(); return; }
    const timer = setTimeout(resolve, ms);
    if (signal) signal.addEventListener('abort', () => { clearTimeout(timer); aborted(); }, { once: true });
  });
}

// PLAN AN.41 (D69, D70): WHY AN ANSWER STOPPED, AND WHAT IT FINISHED, as the conversation keeps it - never guessed by the page.
async function refreshStopped(entry, chatId) {
  if (!chatId) return;
  try {
    const chat = await api(`/api/chats/${encodeURIComponent(chatId)}`);
    const pending = chat.pending;
    if (!pending || pending.turn_id !== entry.turnId || entry.answer) return;
    entry.chatId = chatId;
    takePending(entry, pending);
    repaint();
    // Plan AN.48 (D139): a matter waiting for the advocate shows what it has so far on the board - its disputes once understood.
    if (pending.stopped && pending.stopped.code === 'waiting') loadChatBoard(chatId);
  } catch (error) { /* the red message says what the refusal said */ }
}

// What the conversation holds of a turn being worked on, taken into its entry (D66-D69, D79).
function takePending(entry, pending) {
  entry.shownElements = Array.isArray(pending.elements) ? pending.elements : [];
  if (pending.work) entry.work = pending.work;
  entry.steers = Array.isArray(pending.steers) ? pending.steers : [];
  if (pending.state === 'stopped' && pending.stopped) {
    entry.stopped = pending.stopped;
    if (!activeDelivery || activeDelivery.entry !== entry) entry.state = 'stopped';
  }
}

// D73: AFTER A RESTART NM CONTINUES BY ITSELF. The page asks every few seconds until the server is back, then follows the answer:
// still worked on, saved, or stopped - and where it stopped only because the server was restarted, presses Continue itself, once,
// with a line saying so. Where it cannot continue by itself the red message says why.
const RECONNECT_EVERY_MS = 3000;
async function reconnect(entry) {
  if (entry.reconnecting) return;
  entry.reconnecting = true;
  entry.following = true;
  followAs(entry);
  try {
    for (let tries = 0; tries < 400 && !entry.answer; tries += 1) {
      await new Promise((resolve) => setTimeout(resolve, RECONNECT_EVERY_MS));
      if (state.ended || !ownsIntent(entry.context)) return;
      const chatId = entry.chatId || entry.context.chatId || entry.request?.chat_id;
      let seen;
      try {
        seen = await api(`/api/turn-progress?turn_id=${encodeURIComponent(entry.turnId)}`
          + (chatId ? `&chat_id=${encodeURIComponent(chatId)}` : ''));
      } catch (error) {
        if (error?.status === 401) return;
        continue;  // not back yet
      }
      // 53i (D224): the server's word is a wait too; a conversation the advocate has left is not opened over the one they are in.
      if (state.ended || !ownsIntent(entry.context)) return;
      if (seen.chat_id) entry.chatId = seen.chat_id;
      if (seen.state === 'working') {
        entry.state = 'sending';
        entry.progress = seen;
        repaint();
        continue;
      }
      if (seen.state === 'finished' && entry.chatId) {
        entry.following = false;
        unfollow(entry);
        await restorePendingChat(entry.chatId);
        return;
      }
      if (seen.state === 'stopped' && seen.stopped) {
        entry.following = false;
        unfollow(entry);
        entry.stopped = seen.stopped;
        entry.state = 'stopped';
        repaint();
        if (seen.stopped.by_itself) continueTurn(entry, { byItself: true });
        else refreshStopped(entry, entry.chatId);
        return;
      }
      // Not known to the server at all: whether it was saved cannot be told; sending again is safe (BK-36).
      entry.following = false;
      entry.state = 'unknown';
      entry.error = 'NM was restarted before your message reached it.';
      repaint();
      return;
    }
  } finally {
    entry.reconnecting = false;
    entry.following = false;
    unfollow(entry);
    nmFinished();
  }
}

// CONTINUE (D70; D73 by itself after a restart): the same turn picks up where it stopped.
function continueTurn(entry, { byItself = false } = {}) {
  if (activeDelivery || !ownsIntent(entry.context)) return;
  const chatId = entry.chatId || entry.context.chatId || entry.request?.chat_id;
  if (!chatId) return;
  if (byItself) {
    if (entry.continuedByItself) return;  // once: should it stop again, the red message waits for the advocate
    entry.continuedByItself = true;
    entry.restartNote = 'NM was restarted while it worked on this message and continued by itself.';
  }
  entry.endpoint = '/api/turn/continue';
  entry.envelope = JSON.stringify({ chat_id: chatId, turn_id: entry.turnId });
  entry.stopped = null;
  deliver(entry);
}

// GO AHEAD, END TO END, DONE (plan AN.48, 48a3, 48b): the matter waiting for the advocate goes on - research or the analyses for the
// disputes named, every remaining step, or the finish - and stops again or is saved as one answer; Done before any analysis saves it
// as it stands.
function goTurn(entry, choice, disputes = null) {
  if (activeDelivery || !ownsIntent(entry.context)) return;
  const chatId = entry.chatId || entry.context.chatId || entry.request?.chat_id;
  if (!chatId) return;
  entry.goError = null;
  entry.endpoint = '/api/turn/go';
  entry.envelope = JSON.stringify({ chat_id: chatId, turn_id: entry.turnId, choice,
    ...(Array.isArray(disputes) && disputes.length ? { disputes } : {}) });
  entry.stopped = null;
  deliver(entry);
}

// A MESSAGE WHILE A MATTER WAITS (plan AN.48, 48c; D146, D158): it goes to the matter - NM reads whether it is a go-ahead, added
// information, a correction, a rethink or a new question, acts on it or asks, and says at the stop how it took it. Files attached go
// with it, as papers for the matter.
function messageTurn(entry, text) {
  if (activeDelivery || !ownsIntent(entry.context)) return;
  const chatId = entry.chatId || entry.context.chatId || entry.request?.chat_id;
  if (!chatId || !String(text || '').trim()) return;
  const refs = attachments.filter((item) => item.summary && item.summary.document_ref)
    .map((item) => item.summary.document_ref);
  attachments = [];
  renderAttachments();
  $('message').value = '';
  if (entry.context) entry.context.text = '';
  sizeComposer();
  entry.goError = null;
  entry.lastSent = text;
  entry.endpoint = '/api/turn/message';
  entry.envelope = JSON.stringify({ chat_id: chatId, turn_id: entry.turnId, message: text,
    ...(refs.length ? { document_refs: refs } : {}) });
  entry.stopped = null;
  deliver(entry);
}

// ANSWERS AT A STOP (plan AN.48, 48d; D154): kept with NM's questions; a step that stopped for them goes on once all are answered.
function answerTurn(entry, answers) {
  if (activeDelivery || !ownsIntent(entry.context)) return;
  const chatId = entry.chatId || entry.context.chatId || entry.request?.chat_id;
  if (!chatId) return;
  entry.goError = null;
  entry.endpoint = '/api/turn/answers';
  entry.envelope = JSON.stringify({ chat_id: chatId, turn_id: entry.turnId, answers });
  entry.stopped = null;
  deliver(entry);
}

// DISCARD (D71): the red message and its buttons go; the answer that stopped is saved as it stopped.
async function discardTurn(entry) {
  const chatId = entry.chatId || entry.context.chatId || entry.request?.chat_id;
  if (!chatId || entry.discarding) return;
  entry.discarding = true;
  repaint();
  try {
    const answer = await api('/api/turn/discard', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, turn_id: entry.turnId }) });
    entry.answer = answer;
    entry.state = 'committed';
    entry.stopped = null;
    const intent = entry.context;
    if (intent) intent.pending = (intent.pending || []).filter((item) => item !== entry);
    // 53i (D224): the version is its own conversation's, never given to another the advocate has opened since.
    if (Number.isInteger(answer.matter_version) && ownsIntent(entry.context)) state.matterVersion = answer.matter_version;
    releaseQueued(entry);
  } catch (error) {
    entry.discardError = error.message;
  } finally {
    entry.discarding = false;
    repaint();
  }
}

// ADD TO A QUESTION WHILE IT IS WORKED ON (owner decision, 15 Oct 2026), as in
// Cursor: what the advocate sends meanwhile is queued on the conversation the
// question belongs to and sent as the next message once the answer is saved. If the
// answer fails, it returns to the message box instead.
// PLAN AN.42 (D77, owner, 4 Nov 2026): each waits as a line just above the message box, with the files attached to it - their
// upload and reading go on - and Edit (back into the box, above what is typed there, with its files) and Discard. What waits goes
// once, together, when the answer is done (D80).
const COMPOSER_PROMPT = 'Tell NM what you need, ask a question, or add material.';
const COMPOSER_WAITING = 'Add to this question; it is sent as soon as the answer is ready (Enter).';
function queueAddition(text) {
  const intent = activeDelivery && activeDelivery.entry.context;
  if (!intent || !text.trim()) return;
  const blocked = attachmentsBlockSend({ reading: false });
  if (blocked) { $('attachments-status').textContent = blocked; return; }
  if (!Array.isArray(intent.queued)) intent.queued = [];
  const files = attachments.splice(0);
  files.forEach((item) => queuedFiles.add(item));
  intent.queued.push({ text, files });
  $('message').value = '';
  intent.text = '';
  sizeComposer();
  renderAttachments();
  saveQueued(intent);
}

// PLAN AN.42 (D77): what waits is kept with the conversation, so that a reload keeps it - its words and the files read so far.
async function saveQueued(intent) {
  const chatId = intent && (intent.chatId || (activeDelivery && activeDelivery.entry.context === intent
    && activeDelivery.entry.chatId));
  if (!chatId) return;
  const queued = (intent.queued || []).map((item) => ({ text: item.text,
    documents: item.files.filter((file) => file.summary && file.summary.document_ref)
      .map((file) => ({ document_ref: file.summary.document_ref, name: file.summary.name || file.name || '' })) }));
  try {
    await api(`/api/chats/${encodeURIComponent(chatId)}/queued`, { method: 'PUT',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify({ queued }) });
  } catch (error) { /* kept on this page; the next change saves it again */ }
}

// What waited when the conversation was opened (D77): its lines back above the box, each file as it was read. Where the answer
// it waited for is done, what waits goes now, once, together (D80); where it stopped, it waits for Continue or Discard.
async function restoreQueued(intent, queued, pending) {
  const items = [];
  for (const item of queued) {
    const files = [];
    for (const document_ of item.documents || []) {
      try {
        const summary = await api(`/api/documents/${encodeURIComponent(document_.document_ref)}`);
        files.push({ name: document_.name || summary.name, status: 'ready', summary, note: '' });
      } catch (error) {
        files.push({ name: document_.name, status: 'failed', summary: null, note: 'could not be opened again' });
      }
    }
    files.forEach((file) => queuedFiles.add(file));
    items.push({ text: item.text, files });
  }
  // The conversation's record is what waits: lines this page already held are taken back first.
  unqueue(intent.queued || []);
  intent.queued = items;
  renderQueued();
  if (!pending) releaseQueued({ state: 'committed', context: intent });
}

// STEER (D79): the line goes into the answer being worked on, with its files once they are read; NM decides what it changes. Where
// the answer has already finished, it stays to go as the next message, and the line under the files says so.
async function steerQueued(intent, item) {
  const delivery = activeDelivery;
  if (!delivery || delivery.entry.context !== intent || item.steering) return;
  if (item.files.some((file) => READING_STATES.includes(file.status))) return;
  item.steering = true;
  renderQueued();
  try {
    await api('/api/turn/steer', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ turn_id: delivery.entry.turnId, message: item.text,
        document_refs: item.files.filter((file) => file.summary && file.summary.document_ref)
          .map((file) => file.summary.document_ref) }) });
    intent.queued = intent.queued.filter((other) => other !== item);
    unqueue([item]);
    delivery.entry.steers = [...(delivery.entry.steers || []), item.text];
    $('attachments-status').textContent = 'Added to the answer NM is working on.';
    saveQueued(intent);
  } catch (error) {
    // Plan AN.48 (48f2): a step still waiting for a free place is not yet at work, so the line goes as the next message too.
    $('attachments-status').textContent = error?.status === 409
      ? (error.detail?.code === 'not_begun' ? 'NM has not begun on this message yet, so this one goes as the next message.'
        : 'NM had already finished this answer, so this message goes as the next one.')
      : `Not added: ${error.message}`;
  } finally {
    item.steering = false;
    repaint();
    paintSend();
  }
}

// The messages that waited, as one: their words, and their files back with the message box's.
function unqueue(items) {
  items.forEach((item) => item.files.forEach((file) => queuedFiles.delete(file)));
  return { words: items.map((item) => item.text).join('\n\n'), files: items.flatMap((item) => item.files) };
}

function releaseQueued(entry) {
  const intent = entry.context;
  if (!intent || !Array.isArray(intent.queued) || !intent.queued.length) return;
  // Another conversation is open: what waits stays on its own, with Edit and Discard, until the advocate comes back to it.
  if (!ownsIntent(intent)) return;
  const { words, files } = unqueue(intent.queued.splice(0));
  saveQueued(intent);
  const alone = !attachments.length;
  attachments.push(...files);
  // Plan AN.40 (D64): files still being read hold the words, which go by themselves once they are read.
  if (['committed', 'replayed'].includes(entry.state) && alone && !activeDelivery && !heldSend
      && !attachmentsBlockSend({ reading: false })) {
    renderAttachments();
    send(words);
    return;
  }
  const box = $('message');
  box.value = [words, box.value].filter((text) => text.trim()).join('\n\n');
  intent.text = box.value;
  sizeComposer();
  renderAttachments();
}

function editQueued(intent, item) {
  intent.queued = intent.queued.filter((other) => other !== item);
  const { words, files } = unqueue([item]);
  const box = $('message');
  box.value = [words, box.value].filter((text) => text.trim()).join('\n\n');
  intent.text = box.value;
  attachments.push(...files);
  sizeComposer();
  renderAttachments();
  box.focus();
  saveQueued(intent);
}

function discardQueued(intent, item) {
  intent.queued = intent.queued.filter((other) => other !== item);
  unqueue([item]);
  paintSend();
  saveQueued(intent);
}

function queuedFilesSaid(files) {
  if (!files.length) return '';
  const reading = files.filter((item) => READING_STATES.includes(item.status)).length;
  const unusable = files.filter((item) => ['held', 'failed'].includes(item.status)).length;
  const count = (n, what) => `${n} ${what}${n === 1 ? '' : 's'}`;
  if (unusable) return `${count(unusable, 'file')} could not be used`;
  if (reading) return `reading ${count(reading, 'file')}…`;
  return count(files.length, 'file');
}

// What waits, a line each above the message box (D77): the conversation shown's own.
function renderQueued() {
  const host = $('queued');
  const intent = activeIntent;
  const items = intent && Array.isArray(intent.queued) ? intent.queued : [];
  host.hidden = !items.length;
  host.replaceChildren(...items.map((item) => {
    const line = document.createElement('li');
    const words = document.createElement('span');
    words.className = 'queued-words';
    words.textContent = item.text;
    words.title = item.text;
    line.appendChild(words);
    const said = queuedFilesSaid(item.files);
    if (said) {
      const files = document.createElement('span');
      files.className = 'queued-files';
      files.textContent = said;
      line.appendChild(files);
    }
    // D79: Steer, while the answer it waits for is worked on and its files are read.
    if (activeDelivery && activeDelivery.entry.context === intent) {
      const steer = document.createElement('button');
      steer.type = 'button';
      steer.className = 'ghost';
      steer.textContent = item.steering ? 'Steering…' : 'Steer';
      steer.disabled = Boolean(item.steering) || item.files.some((file) => READING_STATES.includes(file.status));
      steer.setAttribute('aria-label', 'Send this into the answer NM is working on now');
      steer.addEventListener('click', () => steerQueued(intent, item));
      line.appendChild(steer);
    }
    const edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'ghost';
    edit.textContent = 'Edit';
    edit.setAttribute('aria-label', 'Put this message back in the box to edit it');
    edit.addEventListener('click', () => editQueued(intent, item));
    const discard = document.createElement('button');
    discard.type = 'button';
    discard.className = 'ghost';
    discard.textContent = 'Discard';
    discard.setAttribute('aria-label', 'Discard this message');
    discard.addEventListener('click', () => discardQueued(intent, item));
    line.append(edit, discard);
    return line;
  }));
}

// WHAT A TURN IN PROGRESS IS DOING (owner decision, 14 Oct 2026). Only stage
// names, counts and times come back. While sending, polling runs until the
// answer or a refusal arrives; after a reload (with onFinished) it stops when
// the server no longer knows the turn and fetches the saved answer when done.
const PROGRESS_EVERY_MS = 2000;
function watchProgress(entry, onFinished, onStopped = null) {
  let stopped = false;
  let timer = null;
  let stream = null;
  // The browser's timers are called directly: invoked as an object's method they
  // throw "Illegal invocation" and every send failed (found 15 Oct 2026).
  const stop = () => {
    stopped = true;
    if (timer !== null) clearTimeout(timer);
    if (stream) { stream.close(); stream = null; }
  };
  const where = () => {
    const chatId = entry.chatId || (entry.context && entry.context.chatId) || null;
    return `turn_id=${encodeURIComponent(entry.turnId)}` + (chatId ? `&chat_id=${encodeURIComponent(chatId)}` : '');
  };
  // What the turn is doing, taken in - asked for, or told by the server (plan AN.48, 48f5). True once the watch has ended.
  function heard(seen) {
    entry.progress = seen;
    if (seen.chat_id) entry.chatId = seen.chat_id;
    // Plan AN.41 (D68): the work finished has been saved again: read it from the conversation (D77: and what waits goes with it).
    if (Number.isInteger(seen.saved) && seen.saved > (entry.savedCount ?? -1) && seen.chat_id) {
      entry.savedCount = seen.saved;
      showSoFar(entry, seen.chat_id);
      if (entry.context && Array.isArray(entry.context.queued) && entry.context.queued.length) saveQueued(entry.context);
    }
    // Plan AN.37: a window of questions has opened; it is shown once by itself, and from the progress after - and by itself
    // again when a question is added to it while the turn works (D87).
    if (seen.asking === true && !entry.questionsOpen
        && (!entry.questionsSeen || (seen.asked || 0) > (entry.questionsSeenCount || 0))) openTurnQuestions(entry);
    if (Number.isInteger(seen.shown) && seen.shown > (entry.shownCount || 0) && seen.chat_id) {
      entry.shownCount = seen.shown;
      showSoFar(entry, seen.chat_id);
    }
    repaint();
    if (onFinished && seen.state === 'finished') { stop(); onFinished(); return true; }
    if (onFinished && seen.state !== 'working') { stop(); if (onStopped) onStopped(); return true; }
    return false;
  }
  async function poll() {
    if (stopped) return;
    try {
      const seen = await api(`/api/turn-progress?${where()}`);
      if (stopped) return;
      if (heard(seen)) return;
    } catch (error) {
      // Progress is auxiliary: the send or the saved conversation still decides.
      if (onFinished || error?.status === 401) { stop(); return; }
    }
    if (!stopped) timer = setTimeout(poll, PROGRESS_EVERY_MS);
  }
  // Plan AN.48 (48f5, D167): the server tells the page as the turn changes. Where the stream cannot be had - a browser without it,
  // a network or proxy that blocks it, a sign-in that has ended - the page asks every 2 seconds, as before.
  if (typeof EventSource === 'function') {
    try {
      stream = new EventSource(`/api/turn-events?${where()}`);
      stream.onmessage = (event) => {
        if (stopped) return;
        let seen = null;
        try { seen = JSON.parse(event.data); } catch (error) { return; }
        if (!seen || typeof seen !== 'object') return;
        // The stream has said its last word: it is closed here, not opened again by the browser.
        if (['finished', 'stopped'].includes(seen.state) && stream) { stream.close(); stream = null; }
        heard(seen);
      };
      stream.onerror = () => {
        if (!stream) return;
        stream.close();
        stream = null;
        if (!stopped) timer = setTimeout(poll, 0);
      };
      return { stop };
    } catch (error) {
      stream = null;
    }
  }
  timer = setTimeout(poll, onFinished ? 0 : PROGRESS_EVERY_MS);
  return { stop };
}

// WHAT AN ANSWER HAS SHOWN SO FAR (owner decisions P26-P27, 19 Oct 2026): saved with the
// conversation as each part passes, and read from there - never from the progress, which
// only says that there is more. The board is read again too, dispute by dispute.
async function showSoFar(entry, chatId) {
  try {
    const chat = await api(`/api/chats/${encodeURIComponent(chatId)}`);
    // 53i (D224): the page keeps one title, the open conversation's; a turn still worked on in another does not take it.
    if (ownsIntent(entry.context)) takeTitle(chatId, chat.title);
    if (entry.answer || !chat.pending || chat.pending.turn_id !== entry.turnId) return;
    entry.shownElements = chat.pending.elements;
    if (chat.pending.work) entry.work = chat.pending.work;
    entry.steers = Array.isArray(chat.pending.steers) ? chat.pending.steers : [];
    repaint();
    if (activeIntent && entry.context === activeIntent) loadChatBoard(activeIntent.chatId || chatId);
  } catch (error) {
    // Auxiliary while the answer is worked on: the answer, once saved, still decides.
  }
}

/* ------------------------------------------------------------------ wire --- */

$('composer').addEventListener('submit', (ev) => {
  ev.preventDefault();
  const box = $('message');
  const text = box.value;
  if (!text.trim()) return;
  // While a question is worked on, what is sent waits its turn (15 Oct 2026).
  if (activeDelivery) { queueAddition(text); return; }
  // Once nothing is left sending pauses, and the words stay in the box (AN.17).
  if (usageUsedUp()) { loadUsage(); return; }
  // deliver clears the typing field after minting the retry receipt, and
  // refuses network dispatch unless that receipt has been protected locally.
  send(text, { fromBox: true });
});

$('message').addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing && ev.keyCode !== 229) {
    ev.preventDefault();
    $('composer').requestSubmit();
  }
});

// SELECT AND REPLY (owner decision, 15 Oct 2026): select words in the conversation
// and reply to them. The quoted words go into the message box, where the advocate
// sees and edits exactly what is sent; nothing is sent by itself.
const REPLY_QUOTE_LIMIT = 600;
function selectedThreadText(selection, thread) {
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!thread.contains(range.commonAncestorContainer)) return null;
  const text = selection.toString().replace(/\s+/g, ' ').trim();
  if (text.length < 2 || text.length > REPLY_QUOTE_LIMIT) return null;
  return { text, rect: range.getBoundingClientRect() };
}
function quoteIntoMessage(box, quote) {
  const line = `Regarding “${quote}”:\n`;
  box.value = box.value.trim() ? `${line}${box.value}` : line;
  return box.value;
}
let replySync = null;
function syncReplyButton() {
  const button = $('reply-to-selection');
  const found = $('composer').hidden ? null : selectedThreadText(window.getSelection(), $('thread'));
  if (!found) { button.hidden = true; return; }
  button.dataset.quote = found.text;
  button.style.top = `${Math.max(8, found.rect.bottom + 6)}px`;
  button.style.left = `${Math.max(8, Math.min(window.innerWidth - 150, found.rect.left))}px`;
  button.hidden = false;
}
document.addEventListener('selectionchange', () => {
  if (replySync !== null) clearTimeout(replySync);
  replySync = setTimeout(syncReplyButton, 120);
});
window.addEventListener('scroll', () => { $('reply-to-selection').hidden = true; }, true);
// Keep the selection while the button is pressed; act on the click.
$('reply-to-selection').addEventListener('mousedown', (ev) => ev.preventDefault());
$('reply-to-selection').addEventListener('click', () => {
  const button = $('reply-to-selection');
  const box = $('message');
  quoteIntoMessage(box, button.dataset.quote || '');
  box.dispatchEvent(new Event('input', { bubbles: true }));
  sizeComposer();
  button.hidden = true;
  window.getSelection()?.removeAllRanges();
  box.focus();
  box.setSelectionRange(box.value.length, box.value.length);
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

// DOCUMENTS WITH A MESSAGE (owner decisions, 15 Oct 2026). Each file is sent to the
// server, checked for malware and read there; scanned pages are then read, and a
// recording transcribed, by the AI under the advocate's AI data-sharing agreement. A
// message carries only documents that finished; one that was held or failed must be
// removed before sending. The server owns every state shown here; this only reports it.
const DOCUMENT_MAX_BYTES = 16 * 1024 * 1024;
// A message carries at most this many documents. The server refuses more with HTTP 422 before anything is saved
// (TURN_DOCUMENT_LIMIT in nm/app/api.py; a test holds the two equal), so the page keeps the first ones and says so.
const DOCUMENTS_PER_MESSAGE = 10;
let attachments = [];
// Files that went into the queue with a message (plan AN.42, D77) are still wanted: their upload and reading go on.
const queuedFiles = new Set();
function wanted(item) {
  return attachments.includes(item) || queuedFiles.has(item);
}

// The documents a message would carry: all but those held or failed, which cannot be sent.
function documentsCarried() {
  return attachments.filter((item) => !['held', 'failed'].includes(item.status)).length;
}

// Whether the message already carries all it can. If it does, the advocate is told, and what came after the first ones is not
// kept: no request is made for it and no chip is left to block sending (owner decision, 26 Oct 2026, plan AN.26).
function messageIsFull() {
  if (documentsCarried() < DOCUMENTS_PER_MESSAGE) return false;
  $('attachments-status').textContent = `You can't upload more than ${DOCUMENTS_PER_MESSAGE} documents at a time, `
    + `so only the first ${DOCUMENTS_PER_MESSAGE} were kept.`;
  return true;
}

// VOICE NOTES (owner decisions, 15 Oct 2026). Recordings the transcription service
// takes go as they are; any other recording this browser can play (WhatsApp .opus or
// .ogg, AAC, FLAC and the like) is converted here to plain WAV, in parts of at most ten
// minutes. Video is not read.
const AUDIO_MAX_BYTES = 25 * 1024 * 1024;
const NATIVE_AUDIO = ['mp3', 'm4a', 'wav', 'webm'];
const AUDIO_NAME = /\.(mp3|m4a|wav|webm|ogg|oga|opus|aac|flac|amr|3gp|mpga|wma)$/i;
const VIDEO_NAME = /\.(mp4|mov|m4v|avi|mkv|wmv)$/i;
const PART_SECONDS = 600;
const VOICE_NOTE_LIMIT_MS = 10 * 60 * 1000;

function extensionOf(name) {
  const found = /\.([^.]+)$/.exec(name || '');
  return found ? found[1].toLowerCase() : '';
}

function isRecording(file) {
  return (file.type || '').startsWith('audio/') || AUDIO_NAME.test(file.name);
}

function wavBlob(samples, rate) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const write = (offset, text) => { for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i)); };
  write(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); write(8, 'WAVE'); write(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); write(36, 'data'); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const value = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return new Blob([view.buffer], { type: 'audio/wav' });
}

// The recording as 16 kHz mono WAV parts, decoded by this browser; nothing leaves it here.
async function wavParts(file) {
  const Playing = window.AudioContext || window.webkitAudioContext;
  const player = new Playing();
  let decoded;
  try {
    decoded = await player.decodeAudioData(await file.arrayBuffer());
  } finally {
    player.close();
  }
  const rate = 16000;
  const mixer = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * rate)), rate);
  const source = mixer.createBufferSource();
  source.buffer = decoded;
  source.connect(mixer.destination);
  source.start();
  const samples = (await mixer.startRendering()).getChannelData(0);
  const parts = [];
  for (let start = 0; start < samples.length; start += PART_SECONDS * rate) {
    parts.push(wavBlob(samples.subarray(start, start + PART_SECONDS * rate), rate));
  }
  return parts;
}

// How often the page asks after a reading of scanned pages (plan AN.25, P4).
const READING_POLL_MS = 1000;

function documentStatus(item) {
  if (item.status === 'recording') {
    const seconds = Math.floor((Date.now() - item.started) / 1000);
    return `Recording ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} — press Stop when done`;
  }
  if (item.status === 'converting') return 'Converting the recording in this browser…';
  if (item.status === 'uploading') return 'Checking for malware and reading…';
  if (item.status === 'reading_scans') {
    if (item.summary && item.summary.recording) return 'Transcribing the recording with AI…';
    const progress = item.progress;
    return progress && progress.total
      ? `Reading scanned pages with AI… ${progress.done} of ${progress.total} page${progress.total === 1 ? '' : 's'} read`
      : 'Reading scanned pages with AI…';
  }
  if (item.status === 'failed') return `Not attached: ${item.note}`;
  const summary = item.summary;
  if (item.status === 'held') return `Held, not read: ${summary.check.reason}`;
  if (summary.recording) {
    const text = summary.pages_read ? 'Transcribed by AI'
      : `Not transcribed: ${(summary.unread[0] && summary.unread[0].reason) || 'unknown reason'}`;
    return item.note ? `${text}. ${item.note}` : text;
  }
  const pages = (count) => `${count} page${count === 1 ? '' : 's'}`;
  let text = summary.state === 'not_read' ? 'No page could be read'
    : summary.state === 'partly_read' && summary.pages_total
      ? `${summary.pages_read} of ${pages(summary.pages_total)} read`
      : `Read · ${pages(summary.pages_read)}`;
  if (summary.pages_read_by_ai) text += ` (${summary.pages_read_by_ai} by AI)`;
  if (summary.pages_partly_legible) text += ` · ${pages(summary.pages_partly_legible)} partly legible`;
  if (item.note) return `${text}. ${item.note}`;
  // Why pages were not read, each reason once (17 Oct 2026).
  const reasons = [...new Set((summary.unread || []).map((page) => page.reason).filter(Boolean))];
  return reasons.length ? `${text}: ${reasons.join('; ')}` : text;
}

function renderAttachments() {
  const host = $('attachments');
  host.hidden = !attachments.length;
  host.replaceChildren(...attachments.map((item) => {
    const chip = document.createElement('li');
    chip.className = `attachment ${item.status}`;
    const name = document.createElement('span');
    name.className = 'attachment-name';
    name.textContent = item.name;
    const status = document.createElement('span');
    status.className = 'attachment-status';
    status.textContent = documentStatus(item);
    chip.append(name, status);
    if (item.status === 'recording') {
      const stop = document.createElement('button');
      stop.type = 'button';
      stop.className = 'ghost attachment-stop';
      stop.textContent = 'Stop';
      stop.setAttribute('aria-label', 'Stop recording the voice note and attach it');
      stop.addEventListener('click', () => stopVoiceNote());
      chip.appendChild(stop);
    }
    if (item.status === 'ready' && item.summary && item.summary.waiting_for_ai > 0) {
      const again = document.createElement('button');
      again.type = 'button';
      again.className = 'ghost attachment-again';
      again.textContent = item.summary.recording ? 'Transcribe again' : 'Read again';
      again.setAttribute('aria-label', item.summary.recording
        ? `Ask the AI to transcribe ${item.name} again` : `Ask the AI to read the unread pages of ${item.name} again`);
      again.addEventListener('click', () => readWaiting(item));
      chip.appendChild(again);
    }
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'ghost attachment-remove';
    remove.textContent = '×';
    remove.setAttribute('aria-label', item.status === 'recording'
      ? 'Discard this voice note recording' : `Remove ${item.name} from this message`);
    remove.addEventListener('click', () => {
      if (item.status === 'recording') stopVoiceNote({ discard: true });
      attachments = attachments.filter((other) => other !== item);
      renderAttachments();
      releaseHeld();
    });
    chip.appendChild(remove);
    return chip;
  }));
  if (!attachments.length) $('attachments-status').textContent = '';
  paintSend();
}

async function attachFile(file) {
  if ((file.type || '').startsWith('video/') || VIDEO_NAME.test(file.name)) {
    attachments.push({ name: file.name, status: 'failed', summary: null,
      note: 'video is not read; send the recording as audio (MP3, M4A, WAV, OGG or OPUS)' });
    renderAttachments();
    releaseHeld();
    return;
  }
  if (!isRecording(file) || (NATIVE_AUDIO.includes(extensionOf(file.name)) && file.size <= AUDIO_MAX_BYTES)) {
    await uploadAttachment(file);
    return;
  }
  if (messageIsFull()) return;
  const item = { name: file.name, status: 'converting', summary: null, note: '' };
  attachments.push(item);
  renderAttachments();
  let parts;
  try {
    parts = await wavParts(file);
  } catch {
    item.status = 'failed';
    item.note = 'this browser could not play this recording; save it as MP3 or M4A and attach it again';
    renderAttachments();
    releaseHeld();
    return;
  }
  if (!attachments.includes(item)) return;
  attachments = attachments.filter((other) => other !== item);
  renderAttachments();
  await Promise.all(parts.map((part, index) => uploadAttachment(new File([part],
    parts.length === 1 ? `${file.name}.wav` : `${file.name} (part ${index + 1} of ${parts.length}).wav`,
    { type: 'audio/wav' }))));
  releaseHeld();
}

async function uploadAttachment(file) {
  if (messageIsFull()) return;
  const item = { name: file.name, status: 'uploading', summary: null, note: '' };
  attachments.push(item);
  renderAttachments();
  const settle = (status, note = item.note) => {
    item.status = status;
    item.note = note;
    if (wanted(item)) renderAttachments();
    releaseHeld();
  };
  const limit = isRecording(file) ? AUDIO_MAX_BYTES : DOCUMENT_MAX_BYTES;
  if (file.size > limit) {
    return settle('failed', isRecording(file) ? 'a recording can be at most 25 MB' : 'a document can be at most 16 MB');
  }
  try {
    item.summary = await api('/api/documents', {
      method: 'POST', body: file,
      headers: { 'content-type': 'application/octet-stream',
        'X-NM-Document-Name': encodeURIComponent(file.name) },
    });
  } catch (error) {
    return settle('failed', error.message);
  }
  if (item.summary.state !== 'held' && item.summary.waiting_for_ai > 0 && wanted(item)) {
    await readWaiting(item);
    return;
  }
  settle(item.summary.state === 'held' ? 'held' : 'ready');
}

// The AI reads what waits for it: scanned pages, or a recording. While anything still
// waits (the AI could not read it just now, or AI data sharing was off), the chip
// offers to read it again (17 Oct 2026); what was already read stays.
// COPIES LOOKED AT AGAIN (plan AN.28, piece 4c): before a message goes with two documents or more, figures that copies of one page
// were read differently are looked at again on their images by the server; a document whose reading was corrected comes back as its
// new record. The message goes with the documents as they were read if this cannot be done.
async function relookAttachments() {
  const status = $('attachments-status');
  status.textContent = 'Checking copies of a page against their images…';
  try {
    const answer = await api('/api/documents/relook', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refs: attachments.map((item) => item.summary.document_ref) }) });
    if (answer && Array.isArray(answer.documents) && answer.documents.length === attachments.length) {
      answer.documents.forEach((summary, index) => { attachments[index].summary = summary; });
    }
  } catch { /* the documents go as they were read */ }
  status.textContent = '';
}

async function readWaiting(item) {
  const settle = (status) => {
    item.status = status;
    if (wanted(item)) renderAttachments();
  };
  item.note = '';
  item.progress = null;
  settle('reading_scans');
  const what = item.summary.recording ? 'The recording was not transcribed' : 'Scanned pages were not read';
  const address = `/api/documents/${encodeURIComponent(item.summary.document_ref)}/reading`;
  try {
    // A background job (plan AN.25, P4): started once, then asked after until it ends, so no request is held for the whole of a
    // long scan and the chip can say how many pages are read.
    let job = await api(address, { method: 'POST' });
    while (job.state === 'reading') {
      item.progress = { done: job.done, total: job.total };
      if (wanted(item)) renderAttachments();
      await new Promise((resolve) => setTimeout(resolve, READING_POLL_MS));
      if (!wanted(item)) return;
      job = await api(address);
    }
    if (job.state === 'failed') throw Object.assign(new Error(job.error.why), { status: job.error.status });
    item.summary = job.document;
  } catch (error) {
    item.note = error.status === 403
      ? `${what}: accept AI data sharing in your profile to allow it.`
      : error.status === 404 ? `${what}: the reading was interrupted; read it again.`
      : `${what}: ${error.message}`;
  }
  item.progress = null;
  settle(item.summary.state === 'held' ? 'held' : 'ready');
  loadUsage();
  releaseHeld();
}

// RECORD A VOICE NOTE: the microphone starts and stops only when the advocate presses.
const voiceNote = { recorder: null, stream: null, chunks: [], item: null, timer: null, ticker: null };

async function startVoiceNote() {
  if (voiceNote.recorder || (typeof dictation !== 'undefined' && dictation.recorder)) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    $('attachments-status').textContent = 'This browser cannot record audio. Attach a recording instead.';
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    $('attachments-status').textContent = 'The microphone is unavailable or permission was declined. Nothing was recorded.';
    return;
  }
  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((type) => MediaRecorder.isTypeSupported(type));
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
  const item = { name: 'Voice note', status: 'recording', summary: null, note: '', started: Date.now() };
  Object.assign(voiceNote, { recorder, stream, chunks: [], item });
  recorder.addEventListener('dataavailable', (event) => { if (event.data.size) voiceNote.chunks.push(event.data); });
  recorder.addEventListener('stop', () => {
    const type = (recorder.mimeType || 'audio/webm').split(';')[0];
    const blob = new Blob(voiceNote.chunks, { type });
    clearTimeout(voiceNote.timer);
    clearInterval(voiceNote.ticker);
    voiceNote.stream.getTracks().forEach((track) => track.stop());
    attachments = attachments.filter((other) => other !== item);
    Object.assign(voiceNote, { recorder: null, stream: null, chunks: [], item: null, timer: null, ticker: null });
    renderAttachments();
    if (recorder.discard || !blob.size) return;
    const when = new Date();
    const stamp = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}-`
      + `${String(when.getDate()).padStart(2, '0')} ${String(when.getHours()).padStart(2, '0')}`
      + `${String(when.getMinutes()).padStart(2, '0')}`;
    attachFile(new File([blob], `Voice note ${stamp}.${type === 'audio/mp4' ? 'm4a' : 'webm'}`, { type }));
  });
  attachments.push(item);
  recorder.start(1000);
  voiceNote.ticker = setInterval(() => renderAttachments(), 1000);
  voiceNote.timer = setTimeout(() => {
    $('attachments-status').textContent = 'Ten minutes is the limit for one voice note; it was stopped and attached.';
    stopVoiceNote();
  }, VOICE_NOTE_LIMIT_MS);
  renderAttachments();
}

function stopVoiceNote({ discard = false } = {}) {
  const recorder = voiceNote.recorder;
  if (!recorder) return;
  recorder.discard = discard;
  if (recorder.state !== 'inactive') recorder.stop();
}

// Why the message cannot carry its documents yet, or null when it can. reading: false leaves out the files still being read, for a
// message that waits for them (plan AN.40).
function attachmentsBlockSend({ reading = true } = {}) {
  if (attachments.some((item) => item.status === 'recording')) {
    return 'Stop the voice note recording before sending.';
  }
  if (reading && attachmentsReading()) {
    return 'Wait until the attached documents have been read.';
  }
  if (attachments.some((item) => ['held', 'failed'].includes(item.status))) {
    return 'Remove the documents that could not be used before sending.';
  }
  const carried = documentsCarried();
  if (carried > DOCUMENTS_PER_MESSAGE) {
    return `A message can carry at most ${DOCUMENTS_PER_MESSAGE} documents; remove ${carried - DOCUMENTS_PER_MESSAGE} before sending.`;
  }
  return null;
}

// SEND ONCE THE FILES ARE READ (plan AN.40, D61-D64; owner, 4 Nov 2026: "if SEND button is clicked, then greyout SEND button and once
// file scanning / reading is done send them automatically, instead of saying files are being read so wait kind of message"). A message
// sent while a file is still being uploaded, converted or read waits for it: Send is greyed and says so, Cancel beside it, and the
// message goes by itself through send() once nothing is being read. What goes is what the message box holds then (D62) - or, for words
// sent another way (added while NM was answering, or answers to NM's questions), those words. It does not go, and Send works again with
// the reason under the files, if a file read meanwhile could not be used or came back with pages not read (D63), or if anything else
// would stop a pressed Send; nor in another conversation than the one it was sent in, nor once the advocate has signed out (D64).
const READING_STATES = ['converting', 'uploading', 'reading_scans'];
const HOLD_SAID = 'Your message will go as soon as the files are read.';

function attachmentsReading() {
  return attachments.some((item) => READING_STATES.includes(item.status));
}

function holdSend(message, options) {
  heldSend = { intent: activeIntent, message: options.fromBox ? null : message, options,
    // The files already read when Send was pressed, as the advocate saw them then.
    seen: new Set(attachments.filter((item) => !READING_STATES.includes(item.status))) };
  $('attachments-status').textContent = HOLD_SAID;
  paintSend();
}

// Send as the page shows it (plan AN.42, D74-D76): a round up-arrow; a turning ring with a stop while an answer is worked on - until
// words are typed or a file attached, which bring the arrow back to queue them - and while a message waits for its files (D75);
// greyed while the file loads and once nothing is left of the allowance (AN.17: the words stay in the box). And what waits to be
// sent, above the box (D77).
const SEND_LOOKS = {
  send: 'Send',
  queue: 'Send: it waits until this answer is ready',
  working: 'Stop this answer',
  waiting: 'Do not send: keep the words and files',
  loading: 'Loading file…',
};
function paintSend() {
  const button = $('send');
  const writing = Boolean($('message').value.trim()) || attachments.length > 0;
  const look = heldSend ? 'waiting' : activeDelivery ? (writing ? 'queue' : 'working')
    : state.matterId && !state.matterReady ? 'loading' : 'send';
  button.dataset.state = look === 'queue' || look === 'loading' ? 'send' : look;
  button.setAttribute('aria-label', SEND_LOOKS[look]);
  button.title = SEND_LOOKS[look];
  button.disabled = look === 'loading' || (look === 'send' && usageUsedUp());
  renderQueued();
}

// The ring pressed (D74, D75): a message waiting for its files is let go; while an answer is worked on, it stops NM (D78) after the
// step in progress - every piece finished is kept and the red message follows, with Continue and Discard. If the stop cannot reach
// the server the ring keeps turning and the line under the files says so.
$('send').addEventListener('click', (event) => {
  const look = $('send').dataset.state;
  if (look === 'waiting' && heldSend) {
    event.preventDefault();
    cancelHold('Not sent. Your words and files are as they were.');
  } else if (look === 'working' && activeDelivery) {
    event.preventDefault();
    stopTurn(activeDelivery.entry);
  }
});

async function stopTurn(entry) {
  if (entry.stopping) return;
  entry.stopping = true;
  $('attachments-status').textContent = 'Stopping after the step in progress…';
  try {
    await api('/api/turn/stop', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ turn_id: entry.turnId }) });
  } catch (error) {
    entry.stopping = false;
    $('attachments-status').textContent = error?.status === 409
      ? 'NM had already finished this answer.' : 'The answer could not be stopped. NM is still working on it.';
  }
}

// The waiting message let go: words sent another way go back to its own conversation's message box; the box's own words never left it.
function cancelHold(said = '') {
  const hold = heldSend;
  if (!hold) return;
  heldSend = null;
  if (hold.message !== null && hold.message.trim()) {
    if (ownsIntent(hold.intent)) {
      const box = $('message');
      box.value = [hold.message, box.value].filter((text) => text.trim()).join('\n\n');
      hold.intent.text = box.value;
      sizeComposer();
    } else {
      hold.intent.text = [hold.message, hold.intent.text || ''].filter((text) => text.trim()).join('\n\n');
    }
  }
  $('attachments-status').textContent = said;
  paintSend();
}

// Asked whenever a file's upload or reading ends, or a file is added failed or removed: once nothing is being read, the waiting message
// goes - or, where it cannot, is let go with the reason.
function releaseHeld() {
  const hold = heldSend;
  if (!hold || attachmentsReading()) return;
  if (!ownsIntent(hold.intent)) { cancelHold(); return; }
  const unread = attachments.filter((item) => !hold.seen.has(item) && (['failed', 'held'].includes(item.status)
    || Boolean(item.note) || Boolean(item.summary && item.summary.waiting_for_ai > 0)));
  const message = hold.message === null ? $('message').value : hold.message;
  const them = unread.length === 1 ? 'it' : 'them';
  const refused = unread.length
    ? `Not sent: ${unread.map((item) => item.name).join(', ')} could not be fully read. Remove ${them} or read ${them} again, then `
      + 'press Send.'
    : attachmentsBlockSend() || (!message.trim() ? 'Not sent: the message box is empty.' : '')
      || (usageUsedUp() ? `Not sent: ${(usage && usage.limit) || 'Sending is paused until you upgrade.'}` : '');
  if (refused) { cancelHold(refused); return; }
  heldSend = null;
  paintSend();
  send(message, hold.options);
}

$('plus-attach').addEventListener('click', () => {
  setPlusMenu(false);
  $('attach-files').click();
});
$('plus-record').addEventListener('click', () => {
  setPlusMenu(false);
  startVoiceNote();
});
$('attach-files').addEventListener('change', () => {
  const files = [...$('attach-files').files];
  $('attach-files').value = '';
  for (const file of files) attachFile(file);
});

// F-C-02. THE MIC BESIDE THE PLUS: say the brief instead of typing it.
//
// Press to start, press again to stop. The recording is transcribed by the speech
// model through OpenAI under the advocate's AI agreement (`/api/dictation`; owner
// decisions, 15 Oct 2026, replacing the earlier on-this-machine model) and the words
// come back INTO THE BRIEF BOX, where the advocate reads and corrects them before
// sending. Nothing is sent by itself, and the recording is not kept: a voice note
// meant to be kept goes through the plus menu instead. Live words (F-C-03) come from
// GPT Live Transcribe, only for an advocate who turned them on in their Dictation
// setting (owner decision, 15 Oct 2026); their final words then replace the
// recording's transcription, which is used only if the live words do not finish.
const DICTATION_LIMIT_MS = 5 * 60 * 1000;
//: F-C-03. The rate the live speech model takes (24 kHz). The audio context is
//: opened at it, so nothing is resampled on the way to the model.
const LIVE_SAMPLE_RATE = 24000;
//: How long stopping waits for the last live words before transcribing the recording.
const LIVE_FINAL_WAIT_MS = 25000;
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

// The final live words, or null when there are none to use. `finish` asks the server
// for them; an abandoned dictation just closes, and the server keeps nothing either way.
function closeLiveWords({ finish = false } = {}) {
  const live = dictation.live;
  dictation.live = null;
  if (!live) return Promise.resolve(null);
  try {
    if (live.node) live.node.port.onmessage = null;
    if (live.node) live.node.disconnect();
    if (live.source) live.source.disconnect();
    if (live.silence) live.silence.disconnect();
    if (live.context.state !== 'closed') live.context.close();
  } catch { /* a graph already gone needs no closing */ }
  const shut = (words) => {
    try { live.socket.close(); } catch { /* already closed */ }
    return words;
  };
  if (!finish || live.socket.readyState !== WebSocket.OPEN) return Promise.resolve(shut(null));
  live.socket.send('done');
  const late = new Promise((resolve) => setTimeout(() => resolve(null), LIVE_FINAL_WAIT_MS));
  return Promise.race([live.final, late]).then(shut);
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
  let settle;
  const final = new Promise((resolve) => { settle = resolve; });
  dictation.live = { context, socket, node, source, silence, final };
  socket.addEventListener('message', (ev) => {
    let heard;
    try { heard = JSON.parse(ev.data); } catch { return; }
    if (heard.live === false) {
      sayDictation(`${heard.why} Listening; the words will appear when you stop.`);
      settle(null);
      return;
    }
    if (typeof heard.words === 'string') showLiveWords(heard.words);
    if ('final' in heard) settle(typeof heard.final === 'string' ? heard.final : null);
  });
  socket.addEventListener('close', () => settle(null));
  socket.addEventListener('error', () => {
    sayDictation('Listening. The words will appear when you stop.');
    settle(null);
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
  if (dictation.recorder || dictation.busy || !state.advocate || voiceNote.recorder) return;
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
  recorder.addEventListener('stop', async () => {
    const blob = new Blob(dictation.chunks, { type: recorder.mimeType || 'audio/webm' });
    dictation.chunks = [];
    dictation.recorder = null;
    const wasLive = Boolean(dictation.live);
    const heard = closeLiveWords({ finish: !recorder.discard });
    releaseMicrophone();
    $('dictate').setAttribute('aria-pressed', 'false');
    $('dictate').classList.remove('recording');
    if (recorder.discard || session !== state.sessionGeneration) return;
    if (wasLive) {
      // The live words' own final text, when they finished; otherwise the recording.
      dictation.busy = true;
      $('dictate').disabled = true;
      sayDictation('Finishing your words…');
      const words = await heard;
      dictation.busy = false;
      $('dictate').disabled = false;
      loadUsage();
      if (session !== state.sessionGeneration) return;
      if (typeof words === 'string') {
        addDictated(words);
        return;
      }
    }
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
  // Live words only for an advocate who turned them on (owner decision, 15 Oct 2026);
  // otherwise the words come back from GPT Transcribe when they stop.
  let live = false;
  try {
    live = (await api('/api/account/dictation')).live === true;
  } catch { /* the setting unread is the default: no live words */ }
  if (!live || session !== state.sessionGeneration || dictation.recorder !== recorder) return;
  beginProvisional();
  await openLiveWords(stream, session);
}

async function transcribeDictation(blob, session) {
  dictation.busy = true;
  $('dictate').disabled = true;
  sayDictation('Turning your words into text…');
  try {
    const type = blob.type.split(';')[0] || 'audio/webm';
    const heard = await api('/api/dictation', {
      method: 'POST',
      headers: { 'content-type': type, 'X-NM-Document-Name': `dictation.${type === 'audio/mp4' ? 'm4a' : 'webm'}` },
      body: blob,
    });
    if (session !== state.sessionGeneration) return;
    addDictated(heard.text);
  } catch (e) {
    if (e.obsolete || session !== state.sessionGeneration) return;
    sayDictation(`Your words were not added: ${e.message}`);
  } finally {
    dictation.busy = false;
    $('dictate').disabled = false;
    loadUsage();
  }
}

// THE FINAL TEXT REPLACES THE LIVE WORDS it was standing in for, and is inserted at
// the caret when those are no longer ours to replace.
function addDictated(text) {
  const words = (text || '').trim();
  if (!words) {
    sayDictation('No words were recognised. Nothing was added; try again closer to the microphone.');
    replaceProvisional('');
    return;
  }
  if (!replaceProvisional(words)) insertIntoBrief(words);
  dictation.ours = false;
  sayDictation('Added to your brief; check it before sending.');
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

// THE BOARD ON A PHONE (owner, 16 Oct 2026): behind the Matter board button.
//
// `aria-expanded` is kept in step because the button IS the disclosure at
// this width -- a screen reader that cannot tell open from closed has the
// same problem the sighted advocate had: no way to know the board is there.
function toggleMatterBoard(force) {
  const pane = $('pane-advise');
  const open = force === undefined ? !pane.classList.contains('show-board') : force;
  pane.classList.toggle('show-board', open);
  $('board-toggle').setAttribute('aria-expanded', String(open));
}

$('board-toggle').addEventListener('click', () => toggleMatterBoard());

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
  const others = Object.values(parties).some(role => role !== 'client');
  if (otherState === 'not_known' && others) {
    otherState = 'identified';
  }
  if (otherState === 'identified' && !others) {
    throw new Error('Other parties are marked as identified, but none is listed. '
      + 'Add their names, or change what is known about other parties.');
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

// F-B-02. EDIT THE OPENING DETAILS FROM THE BOARD (owner, 28 September 2026).
//
// The pencil on the matter board opens THE opening form -- borrowed into a
// dialog, not copied -- so a field added to the form is editable the day it is
// added. It starts from the details as they now stand, and saving records an
// attributed correction beside the original on the server. Deadline, position
// and last worked are not on the form: they are calculated, never typed.
const intakeHome = { parent: $('intake').parentElement, next: $('intake').nextElementSibling };
const INTAKE_WORDING = ['intake-eyebrow', 'intake-title', 'intake-lede', 'in-go'];
let intakeWording = null;

function fillOpeningForm(form) {
  const named = (side) => Object.entries(form.parties || {})
    .filter(([, role]) => role === side).map(([name]) => name).join('\n');
  const brief = form.brief || {};
  const values = {
    'in-title': form.title || '', 'in-client': named('client'),
    'in-adverse': named('adverse'), 'in-others': named('related'),
    'in-client-type': brief.client_type || 'not_known', 'in-scope': brief.objective || '',
    'in-instructing': brief.instructing || 'not_known', 'in-instructor': brief.instructor_name || '',
    'in-instructor-role': brief.instructor_role || '', 'in-authority': brief.authority_basis || '',
    'in-other-state': brief.other_party_state || 'not_known',
    'in-proceedings': brief.proceedings || 'not_known', 'in-forum': brief.forum || '',
    'in-reference': brief.case_reference || '', 'in-stage': brief.stage || '',
    'in-urgency': brief.urgency || 'not_known', 'in-urgency-note': brief.urgency_details || '',
    'in-date': brief.reported_date || '', 'in-date-source': brief.date_source || '',
  };
  INTAKE_INPUTS.forEach((id) => { $(id).value = values[id] ?? ''; });
  $('in-capacity').checked = brief.capacity?.state === 'not_in_doubt';
  openingSections();
  // Sections that hold an answer open, so nothing recorded is hidden.
  for (const section of $('intake').querySelectorAll('details.opening-details')) {
    section.open = [...section.querySelectorAll('input, textarea, select')].some((field) =>
      field.type === 'checkbox' ? field.checked : field.value && field.value !== 'not_known');
  }
}

async function openOpeningEdit() {
  const matterId = state.matterId;
  if (!matterId || !state.matterReady || activeDelivery || openingEdit) return;
  const trigger = $('files-toggle');
  if (trigger.disabled) return;
  trigger.disabled = true;
  let data;
  try {
    data = await api(`/api/matters/${encodeURIComponent(matterId)}`);
  } catch (e) {
    if (!e.obsolete && state.matterId === matterId) {
      showMatterStatus('loud',
        `The matter details could not be opened for editing: ${e.message}. Nothing was changed.`);
    }
    return;
  } finally {
    trigger.disabled = false;
    updateWorkspace();
  }
  if (state.matterId !== matterId || activeDelivery || openingEdit) return;
  if (!data?.opening_form || !Number.isInteger(data.version)) {
    showMatterStatus('loud',
      'The recorded details could not be established, so they cannot be edited. Reopen the matter.');
    return;
  }
  snapshotIntent();
  openingEdit = { matterId, version: data.version, capacity: data.opening_form.brief?.capacity || null,
    offer: null, key: null, saving: false, trigger };
  intakeWording = INTAKE_WORDING.map((id) => [id, $(id).textContent]);
  $('intake-eyebrow').textContent = 'MATTER DETAILS';
  $('intake-title').textContent = 'Edit or add what you know.';
  $('intake-lede').textContent = 'Saving records a correction beside the original details, with '
    + 'who made it and when. It does not clear conflicts, verify authority or establish a deadline.';
  $('in-go').textContent = 'Save changes';
  $('in-cancel').hidden = false;
  fillOpeningForm(data.opening_form);
  $('intake-state').textContent = '';
  $('opening-edit-host').appendChild($('intake'));
  $('intake').hidden = false;
  $('opening-edit').showModal();
  $('in-title').focus();
}

function closeOpeningEdit({ restore = true } = {}) {
  const edit = openingEdit;
  if (!edit) return;
  openingEdit = null;
  const form = $('intake');
  form.hidden = true;
  intakeHome.parent.insertBefore(form, intakeHome.next);
  (intakeWording || []).forEach(([id, text]) => { $(id).textContent = text; });
  intakeWording = null;
  $('in-cancel').hidden = true;
  $('intake-state').textContent = '';
  [...INTAKE_INPUTS, 'in-capacity', 'in-go', 'in-cancel'].forEach((id) => { $(id).disabled = false; });
  // The matter's details never stay behind in the hidden form.
  INTAKE_INPUTS.forEach((id) => { $(id).value = $(id).tagName === 'SELECT' ? 'not_known' : ''; });
  $('in-capacity').checked = false;
  if ($('opening-edit').open) $('opening-edit').close();
  if (restore) {
    restoreIntent();
    if (edit.trigger.isConnected && state.matterId === edit.matterId) edit.trigger.focus();
  }
}

async function saveOpeningEdit() {
  const edit = openingEdit;
  if (!edit || edit.saving) return;
  let fields;
  try { fields = intakeFields(); }
  catch (error) {
    $('intake-state').replaceChildren(stateBlock('loud', error.message));
    return;
  }
  const brief = { ...fields.brief };
  // AN UNTOUCHED BOX KEEPS THE RECORDED ASSESSMENT EXACTLY, including one the
  // checkbox cannot express; only a deliberate change records a new one.
  if (edit.capacity && $('in-capacity').checked === (edit.capacity.state === 'not_in_doubt')) {
    brief.capacity = edit.capacity;
  }
  const offer = { title: fields.title, parties: fields.parties, brief };
  // ONE REQUEST KEY PER SET OF DETAILS, as at opening: a retry after a lost
  // response is recognised as the same correction rather than a second one.
  const wire = JSON.stringify(offer);
  if (edit.offer !== wire) { edit.offer = wire; edit.key = `opening_${newTurnId().slice(5)}`; }
  const controls = [...INTAKE_INPUTS, 'in-capacity', 'in-go', 'in-cancel'];
  edit.saving = true;
  controls.forEach((id) => { $(id).disabled = true; });
  $('intake-state').replaceChildren(stateBlock('building', 'Saving the corrected details…'));
  let out;
  try {
    out = await api(`/api/matters/${encodeURIComponent(edit.matterId)}/opening`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ request_key: edit.key, expected_version: edit.version, ...offer }),
    });
  } catch (e) {
    if (openingEdit !== edit) return;
    edit.saving = false;
    controls.forEach((id) => { $(id).disabled = false; });
    if (e.obsolete) return;
    if (e.status === 409) {
      // THE FILE MOVED UNDER THE FORM. Reload what is recorded now rather
      // than write over details the advocate has not seen.
      try {
        const fresh = await api(`/api/matters/${encodeURIComponent(edit.matterId)}`);
        if (openingEdit !== edit || !fresh?.opening_form || !Number.isInteger(fresh.version)) return;
        edit.version = fresh.version;
        edit.capacity = fresh.opening_form.brief?.capacity || null;
        edit.offer = null;
        fillOpeningForm(fresh.opening_form);
        $('intake-state').replaceChildren(stateBlock('loud',
          'Not saved: this matter changed while the form was open. The form now shows the '
          + 'current details; make your change again and save.'));
      } catch (again) {
        if (openingEdit === edit && !again.obsolete) {
          $('intake-state').replaceChildren(stateBlock('loud',
            `Not saved: this matter changed while the form was open, and the current details could `
            + `not be read (${again.message}). Close this form and open it again.`));
        }
      }
      return;
    }
    $('intake-state').replaceChildren(stateBlock('loud',
      `The correction was not confirmed: ${e.message}. Your changes are still here. Saving again `
      + 'is safe: it carries the same request, so a correction that did land is not recorded twice.'));
    return;
  }
  if (openingEdit !== edit) return;
  edit.saving = false;
  controls.forEach((id) => { $(id).disabled = false; });
  if (!out || out.matter_id !== edit.matterId
      || !['opening_corrected', 'opening_unchanged'].includes(out.state)) {
    $('intake-state').replaceChildren(stateBlock('loud',
      'The server did not confirm the correction. Reopen the matter before relying on the board.'));
    return;
  }
  closeOpeningEdit();
  if (state.matterId !== edit.matterId) return;
  if (out.state === 'opening_corrected' && Array.isArray(out.changes) && out.changes.length) {
    state.turns.push({ note: { at: new Date().toISOString(), changes: out.changes.map(String) } });
    repaint();
  }
  // THE NEW VERSION IS READ BACK before the next brief can be sent on it.
  await showThreadBoard(edit.matterId, { restore: false, closeNavigator: false }).catch(() => {});
}

$('in-cancel').addEventListener('click', () => closeOpeningEdit());
// Escape closes the dialog; the form goes home with it, unsaved changes discarded.
$('opening-edit').addEventListener('cancel', (ev) => {
  ev.preventDefault();
  if (!openingEdit?.saving) closeOpeningEdit();
});

$('intake').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  if (openingEdit) { await saveOpeningEdit(); return; }
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
    // THE OPENING'S IDENTITY IS SPENT ONCE THE SERVER CONFIRMS IT. It exists so
    // a retry after a LOST reply reopens the same file; kept after success, the
    // next new-matter form with the same answers -- two blank forms, most often
    // -- reused it, and the server rightly handed back the earlier matter
    // (owner, 28 September 2026: "a blank form is going back to a latest
    // previous matter chat"). Every Record and continue is a new matter.
    intent.opening = null;
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
    if (intent.opening && [400, 403, 413, 422].includes(e.status)) {
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

// A new matter begins with only the chat. Its first turn opens the saved file;
// the board appears after its details have been read back.
function startMatter(chatId = null) {
  if (typeof chatId !== 'string') chatId = null;
  resetTurnChoice();
  state.workTab = 'home';
  showTab('advise');
  setWorkView('opening');
  selectIntent(null, { opening: true, chatId });
  activeIntent.intakeOpen = false;
  activeIntent.intake = null;
  state.intake = null;
  showIntake(false);
  closeOpenMatter();
  state.turns = [...activeIntent.pending];
  repaint();
  // The board beside the conversation: a saved conversation's; a new one shows none yet.
  loadChatBoard();
  $('mode-line').hidden = true;
  $('matter-heading').textContent = 'New matter';
  $('matter-heading').removeAttribute('title');
  window.dispatchEvent(new Event('nm:matter-changed'));
  $('message').focus();
}

// THE MODEL AND THE EFFORT FOR A MESSAGE (plan AN.33, D23; owner, 1 Nov 2026: "6 Luna being the default model. And whenever the
// user selects another model, that selected model will be used throughout", "Reset for new conversations"): the server's own
// lists, beside the send box; 6 Luna and Medium each time a conversation opens; Terra and Sol said as a cost beside Luna's. What
// differs from the defaults the server gave is kept in state.turnChoice, which the message carries.
let turnCosts = {};

function rememberTurnChoice() {
  const chosen = {};
  for (const [name, id] of [['model', 'turn-model'], ['effort', 'turn-effort']]) {
    const node = $(id);
    if (node && node.value && node.value !== (node.dataset || {}).default) chosen[name] = node.value;
  }
  state.turnChoice = chosen;
  const note = $('turn-cost');
  if (!note) return;
  const cost = turnCosts[($('turn-model') || {}).value] || '';
  note.textContent = cost;
  note.hidden = !cost;
}

function resetTurnChoice() {
  for (const id of ['turn-model', 'turn-effort']) {
    const node = $(id);
    if (node && node.dataset && node.dataset.default) node.value = node.dataset.default;
  }
  rememberTurnChoice();
}

async function loadTurnChoices() {
  let offered;
  try {
    offered = await api('/api/turn-choices');
  } catch {
    return; // the send box keeps 6 Luna and Medium, which the server takes without being told
  }
  const model = $('turn-model');
  const effort = $('turn-effort');
  if (!model || !effort) return;
  const fill = (select, items, chosen) => {
    select.replaceChildren(...items.map((item) => {
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.cost ? `${item.label} · ${item.cost}` : item.label;
      return option;
    }));
    if (chosen) select.dataset.default = chosen;
    select.onchange = rememberTurnChoice;
  };
  fill(model, offered.models || [], offered.default && offered.default.model);
  fill(effort, offered.efforts || [], offered.default && offered.default.effort);
  turnCosts = Object.fromEntries((offered.models || []).map((item) => [item.id, item.cost || '']));
  resetTurnChoice();
}

// F-A-18, F-B-01. The top bar's New matter starts one; Conversation history lists
// every conversation (owner, 16 Oct 2026).
$('home-start').addEventListener('click', startMatter);
$('top-new').addEventListener('click', () => startMatter());
$('top-history').addEventListener('click', () => openTab('advise'));

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
      ? 'OpenAI processing is enabled for your account.'
      : 'OpenAI processing is not enabled. Your matters remain accessible.';
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
      ? 'Permission recorded for OpenAI processing.'
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

// DICTATION (owner decision, 15 Oct 2026): which speech model the microphone uses.
// GPT Transcribe by default, words when you stop; live words while speaking (GPT Live
// Transcribe) only for an advocate who turns them on here.
let dictationSetting = null;
let dictationSettingRequest = 0;
function syncDictationSetting() {
  $('dictation-setting-save').disabled = !dictationSetting
    || $('dictation-live').checked === dictationSetting.live;
}
function showDictationSetting(setting) {
  dictationSetting = setting;
  $('dictation-standard').checked = !setting.live;
  $('dictation-live').checked = setting.live === true;
  // No price: usage is shown only as the percentage left (owner decisions O21, O22).
}
async function openDictationSetting() {
  setAccountMenu(false);
  const request = ++dictationSettingRequest;
  dictationSetting = null;
  $('dictation-setting-status').textContent = 'Checking your setting…';
  syncDictationSetting();
  if (!$('dictation-setting-dialog').open) $('dictation-setting-dialog').showModal();
  try {
    const setting = await api('/api/account/dictation');
    if (request !== dictationSettingRequest) return;
    showDictationSetting(setting);
    $('dictation-setting-status').textContent = '';
  } catch (err) {
    if (!err.obsolete && request === dictationSettingRequest) $('dictation-setting-status').textContent = err.message;
  }
  if (request === dictationSettingRequest) syncDictationSetting();
}
async function saveDictationSetting() {
  if (!dictationSetting) return;
  const request = ++dictationSettingRequest;
  const body = JSON.stringify({ live: $('dictation-live').checked, expected_version: dictationSetting.version });
  dictationSetting = null;
  syncDictationSetting();
  $('dictation-setting-status').textContent = 'Saving…';
  try {
    const setting = await api('/api/account/dictation', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body });
    if (request !== dictationSettingRequest) return;
    showDictationSetting(setting);
    $('dictation-setting-status').textContent = setting.live
      ? 'Saved. Your words will appear as you speak.' : 'Saved. Your words will appear when you stop.';
  } catch (err) {
    if (!err.obsolete && request === dictationSettingRequest) {
      $('dictation-setting-status').textContent = `Not saved. ${err.message}`;
    }
  }
  if (request === dictationSettingRequest) syncDictationSetting();
}
$('dictation-setting').addEventListener('click', openDictationSetting);
for (const id of ['dictation-standard', 'dictation-live']) $(id).addEventListener('change', syncDictationSetting);
$('dictation-setting-save').addEventListener('click', saveDictationSetting);
$('dictation-setting-close').addEventListener('click', () => $('dictation-setting-dialog').close());
$('dictation-setting-dialog').addEventListener('close', () => { ++dictationSettingRequest; dictationSetting = null; });
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
  document.body.dataset.pane = name;
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

/* F-B-04. THE OPEN MATTER'S FILES, from the one file icon in its header.
 *
 * Owner, 28 September 2026: "just keep file icon and show all the files under
 * it ... list all the files there include AV media files". Read from the
 * matter's saved upload receipts -- the same record the plus menu writes -- so
 * the list cannot name a file the matter does not hold. Listing is not
 * opening: originals stay held exactly as before. A list that could not be
 * read says so; it never renders as "no files".
 *
 * The generation lives on `state`, not in a module `let`: `closeFilesMenu` is
 * called from paths that run before this part of the script is reached.
 */
function closeFilesMenu() {
  state.filesGeneration = (state.filesGeneration || 0) + 1;
  const menu = $('files-menu');
  if (!menu) return;
  menu.hidden = true;
  menu.replaceChildren();
  $('files-toggle').setAttribute('aria-expanded', 'false');
}

function fileKind(row) {
  const type = String(row.receipt?.declared_type || '').toLowerCase();
  const name = String(row.filename || '');
  const extension = name.includes('.') ? name.split('.').pop().toLowerCase() : '';
  if (type.startsWith('audio/') || ['mp3', 'm4a', 'wav', 'ogg', 'oga', 'aac', 'flac', 'opus', 'amr'].includes(extension)
      || (type === 'video/webm' && name.startsWith('Voice note '))) {
    return name.startsWith('Voice note ') ? 'Voice note' : 'Audio';
  }
  if (type.startsWith('video/') || ['mp4', 'mov', 'webm', 'mkv', 'avi', '3gp'].includes(extension)) return 'Video';
  if (type.startsWith('image/') || ['jpg', 'jpeg', 'png', 'gif', 'heic', 'webp', 'tif', 'tiff', 'bmp'].includes(extension)) return 'Image';
  return 'Document';
}

function fileState(receipt) {
  return {
    received: 'Received',
    receiving: 'Incomplete upload',
    cancelled: 'Upload cancelled',
    not_started: 'Not yet sent',
  }[receipt?.state] || 'Integrity not established';
}

function fileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return '';
  if (bytes < 1024) return `${bytes} bytes`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[unit]}`;
}

/* F-B-04, later the same day. THE MATTER'S RECORDS, under the same icon.
 *
 * Owner: "if any of these are important and must be kept, keep those files
 * under the same files icon folder". The six records remain -- each serves something
 * nothing else does: recording a danger (Protective handoff), the capacity
 * correction a blocked turn points to and the recorded instructions (Matter
 * cover), the inspectable record of the file and where each statement came
 * from (Case file, Attributed file), the review record of what was served
 * (History), and an unsent message brought back (Recover a draft). Only the
 * last applies before a new matter is saved. Editing matter details is an
 * action beside those records.
 */
const MATTER_RECORDS = [
  { id: 'records-cover', label: 'Matter cover & instructions', matter: true,
    open: () => window.NMMatterRecords?.open('cover') },
  { id: 'records-edit', label: 'Edit matter details', matter: true,
    open: () => openOpeningEdit() },
  { id: 'records-casefile', label: 'Case file', matter: true,
    open: () => { $('casefile-matter').value = ''; showTab('casefile'); } },
  { id: 'records-attributed', label: 'Attributed file', matter: true,
    open: () => window.NMMatterRecords?.open('casefile') },
  { id: 'records-history', label: 'History', matter: true, open: () => showTab('history') },
  { id: 'records-handoff', label: 'Protective handoff', matter: true,
    open: () => window.NMMatterRecords?.open('emergency') },
  { id: 'draft-open', label: 'Recover a draft', matter: false, open: () => openDraftRecovery() },
];

function matterRecords() {
  const part = document.createElement('div');
  part.className = 'files-records';
  const head = document.createElement('p');
  head.className = 'files-head';
  head.textContent = 'Matter details and records';
  part.appendChild(head);
  for (const record of MATTER_RECORDS) {
    if (record.matter && !state.matterId) continue;
    const button = document.createElement('button');
    button.type = 'button'; button.id = record.id; button.className = 'files-record';
    button.textContent = record.label;
    button.disabled = (record.matter && !state.matterReady)
      || (record.id === 'records-edit' && Boolean(activeDelivery));
    button.addEventListener('click', () => { closeFilesMenu(); record.open(); });
    part.appendChild(button);
  }
  return part;
}

async function openFilesMenu() {
  const matterId = state.matterId;
  if (!state.advocate || state.ended) return;
  state.filesGeneration = (state.filesGeneration || 0) + 1;
  const generation = state.filesGeneration;
  const menu = $('files-menu');
  const note = (text) => { const p = document.createElement('p'); p.className = 'files-note'; p.textContent = text; return p; };
  const files = document.createElement('div');
  files.className = 'files-list';
  menu.replaceChildren(files, matterRecords());
  menu.hidden = false;
  $('files-toggle').setAttribute('aria-expanded', 'true');
  if (!matterId) {
    files.replaceChildren(note('Files appear here once this matter is saved.'));
    return;
  }
  files.replaceChildren(note('Reading the files on this matter…'));
  let reply;
  try {
    reply = await api(`/api/matters/${encodeURIComponent(matterId)}/uploads`);
  } catch (error) {
    if (generation !== state.filesGeneration || error.obsolete) return;
    files.replaceChildren(note('The file list could not be read. This does not mean no files are held; try again.'));
    return;
  }
  if (generation !== state.filesGeneration || matterId !== state.matterId) return;
  if (!reply || reply.matter_id !== matterId || !Array.isArray(reply.uploads)) {
    files.replaceChildren(note('The file list could not be verified. This does not mean no files are held.'));
    return;
  }
  const rows = reply.uploads.filter((row) => row && typeof row.filename === 'string' && row.receipt);
  if (!rows.length) {
    files.replaceChildren(note('No files on this matter yet. Add documents, media or a voice note with the + under the message box.'));
    return;
  }
  const head = document.createElement('p');
  head.className = 'files-head';
  head.textContent = `${rows.length} file${rows.length === 1 ? '' : 's'} on this matter`;
  const list = document.createElement('ul');
  for (const row of rows) {
    const item = document.createElement('li');
    const kind = document.createElement('span');
    kind.className = 'file-kind'; kind.textContent = fileKind(row);
    const name = document.createElement('span');
    name.className = 'file-name'; name.textContent = row.filename;
    const meta = document.createElement('span');
    meta.className = 'file-meta';
    const size = fileSize(row.receipt.observed_size ?? row.receipt.declared_size);
    meta.textContent = [size, fileState(row.receipt)].filter(Boolean).join(' · ');
    item.append(kind, name, meta);
    list.appendChild(item);
  }
  files.replaceChildren(head, list);
}

$('files-toggle').addEventListener('click', () => {
  if ($('files-menu').hidden) openFilesMenu();
  else closeFilesMenu();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !$('files-menu').hidden) {
    closeFilesMenu();
    $('files-toggle').focus();
  }
});
document.addEventListener('click', (event) => {
  if (!$('files-menu').hidden && !event.target.closest('#matter-files')) closeFilesMenu();
  // LB-83. A reply's rating pop-up closes on a click anywhere outside it.
  const rating = event.target.closest?.('.rate');
  closeRatePops(rating ? rating.querySelector('.rate-pop') : null);
});
window.addEventListener('nm:matter-changed', closeFilesMenu);
window.addEventListener('nm:session-ended', closeFilesMenu);

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

// List position is observable; the FTS score is not a calibrated measure of
// relevance and cannot tell whether a hit is first among these results.
// A sole hit has no meaningful relative position to display.
function searchPosition(index, total) {
  if (!Number.isInteger(index) || !Number.isInteger(total)
      || index < 0 || total <= 1 || index >= total) return '';
  return `result ${index + 1} of ${total} shown`;
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

  d.hits.forEach((h, index) => {
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
    // Preserve searched-vs-resolved provenance. Do not turn the uncalibrated
    // index score into a quality band; even tied hits have a definite display
    // position, while a sole result has nothing to compare against.
    const position = searchPosition(index, d.hits.length);
    prov.textContent = position ? `${h.origin} · ${position}` : h.origin;
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
    prov.textContent = c.band ? `${c.origin} · ${c.band}` : c.origin;
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
  renderOpeningBrief(null);
  if (!matterId) {
    st.textContent = '';
    entries.replaceChildren();
    delete entries.dataset.matterId;
    renderCurrency(null);
    return;
  }

  let file; let deps; let matter;
  try {
    [file, deps, matter] = await Promise.all([
      api(`/api/matters/${matterId}/casefile`),
      api(`/api/matters/${matterId}/dependencies`),
      api(`/api/matters/${matterId}`),
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
  renderOpeningBrief(matter.opening_brief);

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
    // THE LABEL, not the key; and WHO, from the record's own field -- the
    // reason is a sentence and attributes nobody.
    row.textContent =
      `${h.at || ''} — ${h.shown || h.name}: was ${h.was || '—'}` +
      (h.now ? `, now ${h.now}` : ', not yet recomputed') +
      ` — ${h.reason || ''}` + (h.by ? ` (by ${h.by})` : '');
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
  // No panel of other saved working stages here (owner, 28 September 2026;
  // LB-139): the stages are kept for review, not shown.

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
  $('pane-history').scrollTop = 0;
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

// THE ADMIN ENTRY (plan AN.46, piece 46p; D117 and D124). The person menu offers Admin only to an account the server's settings name: the
// server answers /api/admin/me for them and with the 404 of an address it does not have for everyone else, so this learns nothing from a
// refusal and shows nothing. It asks again at each sign-in, and `clearPrivileged` hides it when the session ends.
async function showAdminEntry() {
  const entry = $('admin-entry');
  const generation = state.sessionGeneration;
  entry.hidden = true;
  try {
    const res = await fetch('/api/admin/me', { credentials: 'same-origin' });
    if (generation === state.sessionGeneration && state.advocate) {
      entry.hidden = !res.ok;
      // A sign-in that began at /admin (the server sent the visitor here) goes on to it once the account is known to be an admin.
      if (res.ok && window.location.hash === '#admin') window.location.replace('/admin');
    }
  } catch {
    entry.hidden = true;
  }
}

$('admin-entry').addEventListener('click', () => { window.location.assign('/admin'); });

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
  loadTurnChoices();
  paintSend();
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
  // The initials on the person button come from the one shared rule (person.js; plans AN.20, AN.22).
  $('account-initials').textContent = window.NmPerson.initialsOf(shownName);
  $('profile-name').textContent = shownName;
  $('profile-email').textContent = advocate.email || 'Not recorded';
  $('who-detail').textContent = [advocate.enrolment, advocate.practice]
    .filter(Boolean).join(' · ') || 'Not recorded yet';
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
  // Owner decisions, 15 and 16 Oct 2026: no Home page and no tabs. A sign-in opens a
  // new matter, its board beside it, unless a brief was interrupted.
  showTab('advise');
  if (!draftWaiting) startMatter();
  loadHealth();
  loadUsage();
  showAdminEntry();
  // The landing page is Home. Loading every matter's checked register here
  // started a second, overlapping list request when the advocate chose My
  // work, and did work even when they resumed an already-open file. The list
  // is read at its actual entry point; it must never reuse an old result.

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

// HOW MUCH USAGE IS LEFT (owner decisions O21-O24; plans P53, AN.17). The server works out the
// percentage left and which notice is due, and the page shows them: the chip in the top bar; a
// notice above the message box at 50% and at 25% once, each closing itself after the time the
// server gives, and from 10% down at every 1%, staying until the advocate closes it; at nothing left
// the owner's words in its place, and sending pauses. The server refuses new paid work once nothing
// is left whatever this page last heard, so a page that is behind can never spend.
function usageUsedUp() {
  return Boolean(usage && usage.left <= 0);
}

function usageLevel(left) {
  return left <= 0 ? 'out' : left <= 10 ? 'crit' : left <= 25 ? 'low' : '';
}

function hideUsageNotice() {
  clearTimeout(usageNoticeTimer);
  usageNoticeTimer = null;
  $('usage-notice').hidden = true;
}

function sayUsage(kind, title, line, { closable = true, urgent = false } = {}) {
  const box = $('usage-notice');
  clearTimeout(usageNoticeTimer);
  usageNoticeTimer = null;
  box.className = `usage-notice ${kind}`;
  box.setAttribute('role', urgent ? 'alert' : 'status');
  $('usage-notice-title').textContent = title;
  $('usage-notice-text').textContent = line;
  $('usage-notice-close').hidden = !closable;
  box.hidden = false;
}

function showUsage(seen) {
  usage = seen;
  const chip = $('usage-chip');
  const level = usageLevel(seen.left);
  chip.className = level ? `usage ${level}` : 'usage';
  chip.querySelector('.usage-plan').textContent = seen.plan;
  chip.querySelector('.usage-left').textContent = seen.left > 0 ? `${seen.left}% left` : 'No usage left';
  chip.querySelector('.usage-meter i').style.width = `${Math.max(0, Math.min(100, seen.left))}%`;
  chip.setAttribute('aria-label', seen.left > 0
    ? `${seen.plan} allowance, ${seen.left}% left. See plans.` : `${seen.plan} allowance used up. See plans.`);
  chip.hidden = false;
  if (seen.limit) {
    sayUsage('limit', seen.limit, 'Sending is paused until you upgrade. Your message stays here, and your '
      + 'saved matters stay open to read.', { closable: false, urgent: true });
  } else if (seen.notice) {
    const { step } = seen.notice;
    const allowance = seen.plan === 'Trial' ? 'trial allowance' : `${seen.plan} allowance`;
    sayUsage(step > 25 ? 'info' : 'warn', `${seen.left}% of your ${allowance} is left.`,
      step === 25 ? 'See plans to keep going.'
        : step <= 10 ? 'When it runs out, NM cannot research or answer until you upgrade.' : '',
      { urgent: step <= 10 });
    if (seen.notice.closes_after_seconds) {
      usageNoticeTimer = setTimeout(hideUsageNotice, seen.notice.closes_after_seconds * 1000);
    }
    // Seen: it is not shown again, wherever the advocate signs in next.
    api('/api/usage/notice', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ step }) }).catch(() => {});
  } else if ($('usage-notice').classList.contains('limit')) {
    // The allowance grew again (an operator added to it): sending resumes.
    hideUsageNotice();
  }
  showUsagePlan(seen);
  updateWorkspace();
}

async function loadUsage() {
  if (!state.advocate) return;
  const request = ++usageRequest;
  try {
    const seen = await api('/api/usage');
    if (request === usageRequest && state.advocate) showUsage(seen);
  } catch {
    // The chip only informs; the server still refuses new work once nothing is left.
  }
}

function forgetUsage() {
  usage = null;
  usageRequest += 1;
  hideUsageNotice();
  $('usage-chip').hidden = true;
  resetUsagePlan();
}

$('usage-notice-close').addEventListener('click', hideUsageNotice);
// Back on the tab after a while: the allowance may have moved (another tab's answer, an operator).
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') loadUsage();
});

// USAGE AND PLAN (owner decisions O21-O24, O26; plans P53, AN.17, AN.19): a window over the workspace,
// opened from the chip, from a notice's See plans, or from the person menu. It shows only what the
// server says - the allowance's name and the percentage left, and at nothing left the owner's words;
// the plans themselves are on the page, in the public Plans page's words. Pro and Elite cannot be
// chosen yet (payment comes later, by UPI), so nothing here buys anything.
function showUsagePlan(seen) {
  $('usage-plan-allowance').textContent = `${seen.plan} allowance`;
  $('usage-plan-left').textContent = `${seen.left}%`;
  $('usage-plan-fill').style.width = `${Math.max(0, Math.min(100, seen.left))}%`;
  $('usage-plan-fill').parentElement.dataset.level = usageLevel(seen.left);
  $('usage-plan-name').textContent = seen.plan;
  $('usage-plan-note').textContent = seen.limit || (seen.plan === 'Trial' ? TRIAL_NOTE : '');
}

function resetUsagePlan() {
  usagePlanRequest += 1;
  $('usage-plan-allowance').textContent = 'Trial allowance';
  $('usage-plan-left').textContent = '—';
  $('usage-plan-fill').style.width = '0';
  $('usage-plan-fill').parentElement.dataset.level = '';
  $('usage-plan-name').textContent = 'Trial';
  $('usage-plan-note').textContent = TRIAL_NOTE;
  $('usage-plan-status').textContent = '';
}

async function openUsagePlan() {
  setAccountMenu(false);
  const request = ++usagePlanRequest;
  // What is known is shown at once; the server's current word replaces it.
  if (usage) showUsagePlan(usage);
  $('usage-plan-status').textContent = usage ? '' : 'Checking your usage…';
  if (!$('usage-plan-dialog').open) $('usage-plan-dialog').showModal();
  try {
    const seen = await api('/api/usage');
    if (request !== usagePlanRequest || !state.advocate) return;
    $('usage-plan-status').textContent = '';
    showUsage(seen);
  } catch (err) {
    if (!err.obsolete && request === usagePlanRequest) {
      $('usage-plan-status').textContent = `Your usage could not be read just now. ${err.message}`;
    }
  }
}

// The chip and the notice are links to the public Plans page, which still work without this script; a
// plain click opens the window instead, and a click with a modifier key keeps the link.
function plainClick(ev) {
  return !ev.defaultPrevented && ev.button === 0 && !(ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey);
}
$('usage-chip').addEventListener('click', (ev) => {
  if (!plainClick(ev)) return;
  ev.preventDefault();
  openUsagePlan();
});
$('usage-notice').addEventListener('click', (ev) => {
  const link = ev.target.closest ? ev.target.closest('.usage-notice-plans') : null;
  if (!link || !plainClick(ev)) return;
  ev.preventDefault();
  openUsagePlan();
});
$('usage-plan').addEventListener('click', openUsagePlan);
$('usage-plan-close').addEventListener('click', () => $('usage-plan-dialog').close());
$('usage-plan-dialog').addEventListener('close', () => { ++usagePlanRequest; });

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

// THE HOMEPAGE'S "CREATE YOUR ACCOUNT" OPENS THIS PAGE with `#register` (plan AN.16, now that the
// app is at /app and nyaymalaw.in opens the public homepage): the register card instead of the
// sign-in card, for someone not signed in. Read once and removed from the address, as the reset
// link is; someone already signed in simply opens their workspace.
function takeRegisterLink() {
  if (window.location.hash !== '#register') return false;
  history.replaceState(null, '', window.location.pathname + window.location.search);
  return true;
}

window.addEventListener('hashchange', () => {
  if (takeResetToken()) openReset();
  else if (takeRegisterLink() && !state.advocate) showForm('register');
});

async function boot() {
  checkBuild();
  if (takeResetToken()) {
    openReset();
    return;
  }
  const wantsRegister = takeRegisterLink();
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
    if (err.status === 401 && wantsRegister) showForm('register');
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
// Words typed while NM works bring the arrow back (plan AN.42, D76).
$('message').addEventListener('input', paintSend);
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
  if (which === 'register') {
    // The card opens on its first step; whatever was typed stays where it was.
    showRegisterStep(1);
    loadAccountCapabilities();
  }
}

// REGISTRATION IN STEPS (owner decision O24; plan AN.15): the account, then privacy and AI
// permission, then the emailed code on the confirmation card. ONE FORM STILL, posted once from its
// last step, so moving between steps sends nothing. The account step checks only what cannot be
// read two ways - a password typed, at least 8 characters, the same twice - and leaves the kinds of
// character to the server, which names what is missing when the form is posted.
function markSteps(card, current) {
  card.querySelectorAll('.reg-steps li').forEach((mark) => {
    const step = Number(mark.dataset.step);
    if (step === current) mark.setAttribute('aria-current', 'step');
    else mark.removeAttribute('aria-current');
    mark.classList.toggle('done', step < current);
  });
}

function showRegisterStep(step) {
  document.querySelectorAll('#register .reg-step').forEach((section) => {
    section.hidden = Number(section.dataset.step) !== step;
  });
  markSteps($('register'), step);
  $('reg-account-state').textContent = '';
}

function accountStepProblem(password, again) {
  if (password.length < 8) {
    return 'The password must be at least 8 characters and contain an upper-case letter, a '
      + 'lower-case letter, a numeral and a special character.';
  }
  if (password !== again) return 'The two passwords do not match.';
  return null;
}

$('reg-continue').addEventListener('click', () => {
  if (!$('reg-email').reportValidity()) return;
  const problem = accountStepProblem($('reg-password').value, $('reg-password2').value);
  if (problem) {
    // A slip puts both passwords away, as a refused registration always has.
    clearRegistrationPasswords();
    $('reg-account-state').replaceChildren(stateBlock('loud', `${problem} Type it twice again.`));
    $('reg-password').focus();
    return;
  }
  showRegisterStep(2);
  $('reg-privacy-title').tabIndex = -1;
  $('reg-privacy-title').focus();
});

$('reg-back').addEventListener('click', () => {
  showRegisterStep(1);
  $('reg-email').focus();
});

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
  markSteps($('confirm-email'), 3);
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
    // THE LAST STEP, READY (plan AN.15): the account is active, its trial is waiting (plan AN.17),
    // and - when this page made the registration - whether research and answers can start yet.
    const madeHere = registeredHere && registeredHere.email === result.advocate_id ? registeredHere : null;
    showOutcome('good', 'Your account is ready', [result.detail,
      'Your trial allowance is ready: 100% of it is left.',
      madeHere ? (madeHere.ai ? 'AI data sharing is on, so research and answers can start.'
        : 'AI data sharing is off: research and answers need your permission, which you can give '
          + 'in Profile, under AI data sharing.') : ''].filter(Boolean).join(' '), 'login');
    registeredHere = null;
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
    // Whether they allowed AI sharing, for the last step to say (AN.15); nothing else is kept.
    registeredHere = { email: r.email, ai: $('reg-external-ai').checked };
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
