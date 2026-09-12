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
};

let pendingApplication = null;
let outcomeReturn = 'register';

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
  const composer = $('message');
  const text = composer ? composer.value : '';
  if (text && text.trim()) state.draft = { advocate: state.advocate, text };
}

// PRIVILEGED CONTENT COMES OFF THE GLASS IMMEDIATELY, in one place, so a
// surface added later cannot be the one that keeps painting a matter after
// the session behind it is gone.
function clearPrivileged() {
  state.railGeneration += 1;
  state.advocate = null;
  state.workspace = null;
  state.matterId = null;
  state.turns = [];
  ['thread', 'rail-body', 'rail-meta', 'search-results', 'history-body',
   'who-detail'].forEach((id) => { const el = $(id); if (el) el.textContent = ''; });
  const who = $('who-name');
  if (who) who.textContent = '—';
  const workspace = $('workspace-name');
  if (workspace) workspace.textContent = '—';
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

async function api(path, options) {
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
      ? 'Corpus ready'
      : 'Corpus not readable — answers will be short of authority';
    el.title = [
      `${h.provider}/${h.routine_model}`,
      `hard: ${h.hard_tier}`,
      `judge: ${h.judge_tier}`,
      `store: ${h.encryption}`,
      `corpus: ${h.corpus}`,
      `manifest: ${h.manifest_acts} acts`,
    ].join('  ·  ');
    el.classList.toggle('bad', !readable);
  } catch (e) {
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
  if (status === 'not_assessed') {
    return { pill: 'unknown', text: 'not assessed — no register on this file' };
  }
  if (status === 'none_on_this_matter') {
    return { pill: 'ok', text: 'none on this matter' };
  }
  if (status === 'passed') {
    return { pill: 'blocked', text: `${m.next_deadline} — PASSED` };
  }
  if (status === 'near') {
    return { pill: 'blocked', text: `${m.next_deadline} — soon` };
  }
  if (status === 'not_computed') {
    return { pill: 'unknown', text: 'a deadline with no date established' };
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
  return m.next_deadline || 'none recorded';
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

async function showMatterList() {
  const generation = ++state.railGeneration;
  state.matterId = null;
  $('pane-advise').dataset.matterId = '';
  $('rail-title').textContent = 'Matters';
  $('back').hidden = true;
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
    $('rail-meta').textContent = 'state: unbuildable';
    return;
  }
  if (generation !== state.railGeneration) return;

  $('rail-meta').textContent =
    `${data.row_count} row(s) · bounded by ${data.bounded_by}`;

  if (!data.matters.length) {
    body.replaceChildren(stateBlock('empty', 'No matters yet. Brief me and I will open one.'));
    return;
  }

  body.replaceChildren(...data.matters.map((m) => {
    const row = document.createElement('div');
    row.className = 'row' + (m.blocked ? ' loud' : '');
    row.dataset.matterId = m.matter_id;
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
    field(dl, 'blocked', m.blocked
      ? { pill: 'blocked', text: m.blocked }
      : { pill: 'ok', text: 'nothing blocking' });
    row.append(t, dl);
    row.onclick = () => showThreadBoard(m.matter_id);
    return row;
  }));
}

async function showThreadBoard(
  matterId, { restore = true, closeNavigator = true } = {}) {
  const generation = ++state.railGeneration;
  // OPENING A MATTER CLOSES THE LIST at narrow widths. Leaving it up would
  // put the advocate on the answer they asked for with the index still over
  // it, which is the same unreachability wearing the other face.
  if (closeNavigator) toggleMatters(false);
  state.matterId = matterId;
  $('pane-advise').dataset.matterId = matterId;
  $('rail-title').textContent = 'Threads';
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
    if (typeof data.version === 'number') state.matterVersion = data.version;
  } catch (e) {
    if (generation !== state.railGeneration) return;
    body.replaceChildren(stateBlock(
      'unbuildable', `The thread board could not be built: ${e.message}`));
    $('rail-meta').textContent = 'state: unbuildable';
    return;
  }

  $('rail-meta').textContent =
    `${data.row_count} row(s) · bounded by ${data.bounded_by} · v${data.version}`;

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
              + `${e.message}. What you were told is not lost — it could not `
              + `be decoded here, and the file itself is intact.`,
        }],
        metrics: null, restored: true,
      },
    }];
    repaint();
    return true;
  }

  if (generation !== state.railGeneration) return false;

  state.turns = (d.turns || []).map((t) => ({
    brief: t.message || '',
    answer: {
      elements: t.elements || [],
      blocked: t.blocked,
      blocked_reason: t.blocked_reason,
      // `metrics: null` IS THE FLAG. `renderTurn` shows the audit line only
      // when there is something measured to show.
      metrics: null,
      restored: true,
      at: t.at || '',
    },
  }));

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

    if (refusal && refusal.withheld_by) {
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
    };
    if (SAID[entry.state]) {
      const d = document.createElement('div');
      d.className = 'refusal-gap';
      d.textContent = SAID[entry.state];
      f.appendChild(d);
    }
    if (entry.turnId && entry.state !== 'committed') {
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

  // WHAT FOLDS AND WHAT MAY NEVER FOLD.
  //
  // A GROUND element carrying `disclosure` is what could not be established --
  // the screens that have not run, the corpus gap, the read that came back
  // empty. Folding those is B-128 in reverse: that defect WAS a disclosure the
  // advocate could not see. §9 wants the third state visible in the OUTPUT,
  // and behind a triangle is available rather than visible.
  //
  // Plain GROUND is the SUPPORT for a claim stated above it -- retrieved
  // statutory text, quoted paragraphs -- and it is what actually crowds the
  // screen. Nothing is lost by folding it and it can be opened in one click.
  // AND ONLY WHAT THE SERVER FILED AS AUTHORITY. `nm/domain/brief.py` puts a
  // ground with refs under `authority` and a ground carrying a loud signal
  // under `window` or `risk` -- the expired limitation is a ground with the
  // LIMITATION_BAR signal, filed under Time. This folded every plain ground
  // whatever its section, so "Limitation for our side runs to 2021-03-14 ...
  // That period has run" sat behind "4 supporting passages" and the one
  // date the advocate came for was available rather than visible. Measured
  // by journey phase 6b on the integrated tree, 12 September 2026, and it
  // predates P18: the fold was written before the sections were. An element
  // with no section (an older transcript) folds as before.
  const isSupport = (el) => el.kind === 'ground' && !el.disclosure
    && (!el.section || el.section === 'authority');
  let support = entry.answer.elements.filter(isSupport);
  let spoken = entry.answer.elements.filter((el) => !isSupport(el));

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

async function send(message) {
  const entry = { brief: message, turnId: newTurnId(), state: 'sending' };
  state.turns.push(entry);
  repaint();
  await deliver(entry);
}

// THE RETRY IS THE SAME TURN, and that is the whole point of the id. It is a
// separate function because the retry button calls it too -- a retry that
// re-entered `send` would mint a new id and duplicate the brief, which is the
// defect wearing the costume of a fix.
async function deliver(entry) {
  const btn = $('send');
  // BK-41. THE COMPOSER STAYS USABLE.
  //
  // It was globally disabled for the length of a turn, and a turn's measured
  // p90 is about 18 seconds -- 20 for one making eight or more model calls.
  // An advocate who thinks of the next thing to say while the last one is
  // running had nowhere to put it, so they held it in their head or lost it.
  // Only SEND is held, because two turns in flight on one thread is a
  // different problem (BK-36 owns it).
  btn.disabled = true;
  btn.textContent = 'Working…';
  // CANCEL, and it is honest about what it can promise: it abandons the
  // REQUEST, which is all a browser can do. Whether the server committed
  // before the abort is unknown to us -- so the entry lands in `unknown`,
  // the state BK-36 already built for exactly this, and its retry carries
  // the same turn id.
  const cancel = document.createElement('button');
  cancel.className = 'ghost cancel';
  cancel.textContent = 'Cancel';
  const stop = new AbortController();
  cancel.addEventListener('click', () => {
    entry.cancelled = true;
    stop.abort();
  });
  btn.parentElement.insertBefore(cancel, btn);
  entry.state = 'sending';
  entry.error = null;
  entry.refusal = null;
  repaint();
  try {
    const answer = await api('/api/turn', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      signal: stop.signal,
      body: JSON.stringify({
        message: entry.brief,
        matter_id: state.matterId,
        turn_id: entry.turnId,
        // B3-B5. Sent with the brief they were given for, and only until the
        // matter has recorded them: re-sending on every turn would re-answer
        // a screen the advocate answered once.
        parties: (state.intake && state.intake.parties) || {},
        release: (state.intake && state.intake.release) || {},
        // WHAT THIS TAB BELIEVES IT IS WRITING ON TOP OF. A second tab that
        // loaded the matter and sat for ten minutes was writing onto a file
        // it had never seen; now the server refuses with both numbers and
        // this tab re-derives.
        expected_version: state.matterVersion,
      }),
    });
    entry.answer = answer;
    // A SCREEN BLOCK RE-OPENS THE FORM. The block is the question, and an
    // advocate who is told the file cannot be worked until the scope is
    // recorded needs the place to record it, not just the sentence.
    if (answer.blocked && /screen|scope|capacity|part(y|ies)/i.test(
        answer.blocked_reason || '')) {
      showIntake(true);
    }
    entry.state = answer.replayed ? 'replayed' : 'committed';
    // THE INTAKE HAS LANDED ON THE FILE and does not travel again.
    state.intake = null;
    // THE BRIEF IS ON THE FILE, so the composer may let go of it. This is the
    // only place that clears it.
    if ($('message').value.trim() === entry.brief.trim()) $('message').value = '';
    if (answer.matter_id && answer.matter_id !== state.matterId) {
      state.matterId = answer.matter_id;
    }
    if (typeof answer.matter_version === 'number') {
      state.matterVersion = answer.matter_version;
    }
    repaint();
    // `restore: false` -- the turn on screen IS the live one, and reading it
    // back would replace it with a copy that has no metrics.
    if (state.matterId) {
      await showThreadBoard(state.matterId, {
        restore: false,
        closeNavigator: false,
      });
    }
  } catch (e) {
    entry.error = e.message;
    entry.refusal = (e.detail && typeof e.detail === 'object') ? e.detail : null;
    // WAS IT SAVED? The one question a failed send has to answer, and it used
    // to be unanswerable. The server now says so on every failure it can, and
    // where it says nothing at all -- a lost response, which is the case this
    // is really for -- `unknown` is the honest word and it is not `no`.
    const said = entry.refusal && entry.refusal.committed;
    entry.state = said === 'not_committed' ? 'not_committed' : 'unknown';
    if (entry.cancelled) {
      // CANCELLING ABANDONS THE REQUEST, NOT THE TURN. The server may have
      // committed before the abort reached it, and saying "cancelled --
      // nothing was saved" would be a claim we are in no position to make.
      // `unknown` is the honest state and its retry is already safe: it
      // carries the same turn id, so a turn that did land is recognised
      // rather than written twice.
      entry.state = 'unknown';
      entry.error = 'You cancelled this turn.';
    }
    if (e.status === 409) {
      // A STALE WRITE RE-DERIVES RATHER THAN ASKING. The advocate did not do
      // anything wrong and cannot fix it by reading a message about versions.
      entry.state = 'stale';
      if (state.matterId) {
        await showThreadBoard(state.matterId).catch(() => {});
      }
    }
    repaint();
  } finally {
    cancel.remove();
    btn.disabled = false;
    btn.textContent = 'Send';
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
      capacity: $('in-capacity').checked
        ? 'the advocate confirms the client can give instructions'
        : '',
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

$('new-matter').addEventListener('click', () => {
  state.matterVersion = null;
  state.intake = null;
  // STARTING A MATTER CLOSES THE LIST, for the same reason opening one does.
  //
  // `showThreadBoard` already says it: leaving the drawer up "would put the
  // advocate on the answer they asked for with the index still over it, which
  // is the same unreachability wearing the other face." That reasoning was
  // applied at one site and not the other, so below 820px an advocate tapped
  // "Brief a new matter", got the intake form BEHIND the drawer they had just
  // used, and had `focus()` called on a field they could not see.
  //
  // Found by the journey suite at 390px and 768px once phase 3 started
  // driving narrow widths for real -- which is the whole reason that phase
  // was repaired.
  toggleMatters(false);
  showIntake(true);
  state.matterId = null;
  $('pane-advise').dataset.matterId = '';
  state.turns = [];
  repaint();
  $('mode-line').hidden = true;
  $('message').focus();
  showMatterList();
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

const PANES = ['advise', 'search', 'casefile', 'history'];

function showTab(name) {
  PANES.forEach((p) => { $(`pane-${p}`).hidden = (p !== name); });
  document.querySelectorAll('#tabs .tab').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.tab === name);
  });
  if (name === 'search') $('q').focus();
  if (name === 'history') loadHistoryMatters();
  if (name === 'casefile') loadCasefileMatters();
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
  what.textContent = `Searched the case law · for “${d.query}”`;
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
    const held = d.identity.held ? d.identity.held.toLocaleString() : null;
    const of = d.identity.of_source ? d.identity.of_source.toLocaleString() : null;
    const detail = document.createElement('span');
    detail.className = 'index-detail';
    // BOTH NUMBERS, because the RATIO is the disclosure. "451,548 paragraphs"
    // reads as the corpus; "451,548 of 1,015,780" does not.
    const size = (held && of)
      ? `${held} of ${of} source paragraphs (${(frac * 100).toFixed(1)}%)`
      : `${held} paragraphs · source size not recorded`;
    // SCOPE FIRST. It is the disclosure that changes whether the whole result
    // means anything: an empty answer to a Kerala question is not an answer
    // about Kerala law, and only this line says so.
    // FRESHNESS AS A DATE, not a build timestamp. `built
    // 2026-08-30T07:51:38` is an engineering artefact; what an advocate
    // needs is how current the law they are being shown is.
    const day = String(d.identity.built_at || '').slice(0, 10);
    detail.textContent = ` · ${d.identity.scope} · ${size}`
      + (day ? ` · current to ${day}` : '');
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
    st.appendChild(stateBlock('loud', `NOT SEARCHED — ${d.why}`));
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
    renderSearch(await api(`/api/search?${params}`));
  } catch (err) {
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
  const st = $('casefile-state');
  const entries = $('casefile-entries');
  st.textContent = ''; entries.textContent = '';
  renderCurrency(null);
  if (!matterId) return;

  let file; let deps;
  try {
    file = await api(`/api/matters/${matterId}/casefile`);
    deps = await api(`/api/matters/${matterId}/dependencies`);
  } catch (err) {
    st.appendChild(stateBlock('loud', `The case file could not be read: ${err.message}`));
    return;
  }
  if (file.state !== 'ok') {
    st.appendChild(stateBlock('loud', `The case file is ${file.state}.`));
  }
  renderCurrency(deps);

  const live = new Set((file.live || []).map((e) => e.fact_id));
  (file.entries || []).forEach((e) => {
    entries.appendChild(renderEntry(matterId, e, live.has(e.fact_id), file.version));
  });
  if (!(file.entries || []).length) {
    entries.appendChild(stateBlock('empty', 'Nothing has been recorded on this file yet.'));
  }
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
  const sel = $('history-matter');
  try {
    const d = await api('/api/matters');
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
    $('history-state').textContent = '';
    $('history-state').appendChild(stateBlock('loud',
      `The matter list could not be read: ${err.message}`));
  }
}

async function showHistory(matterId) {
  const st = $('history-state');
  const body = $('history-body');
  st.textContent = ''; body.textContent = '';
  if (!matterId) return;

  let d;
  try {
    d = await api(`/api/matters/${matterId}/transcript`);
  } catch (err) {
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

    card.appendChild(renderTurn({
      brief: t.message || t.asked || '',
      answer: {
        elements: t.elements || [],
        blocked: t.blocked,
        blocked_reason: t.blocked_reason,
        metrics: null,
        restored: true,
        at: t.at || '',
        raw: t,
      },
    }));

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

function showApplication(advocate, workspace) {
  if (!workspace || !workspace.id || !workspace.label) {
    clearPrivileged();
    showGate('I could not establish the active workspace. Matter content '
      + 'remains closed; ask the installation administrator to check this account.');
    return;
  }
  state.advocate = advocate.id;
  state.workspace = workspace && workspace.id;
  $('who-name').textContent = advocate.name;
  // ENROLMENT AND FIRM, ON SCREEN. The firm is recorded on every file, so
  // an advocate signed in under the wrong one should see it before they
  // brief a matter rather than after. It does NOT scope the conflict
  // check -- that runs against the matters this advocate holds, and
  // BK-31 is explicit that no firm-wide claim may be made until a
  // verified membership and a working registry exist.
  $('who-detail').textContent = `${advocate.enrolment} · ${advocate.practice}`;
  $('workspace-name').textContent = workspace.label;
  $('gate').hidden = true;
  $('masthead').hidden = false;
  state.ended = false;
  showTab('advise');
  loadHealth();
  showMatterList();
  showIntake(false);

  // THE DRAFT COMES BACK, AND ONLY TO THE ADVOCATE WHO WROTE IT. BK-40 asks
  // for exactly that scoping: a brief names a client, and restoring one into
  // the next person's composer on a shared machine would be a disclosure, not
  // a convenience.
  if (state.draft && state.draft.advocate === advocate.id) {
    $('message').value = state.draft.text;
    $('message').focus();
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
    const h = await api('/api/health');
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
    showApplication(me.advocate, me.workspace);
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
      showApplication(r.advocate, r.workspace);
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
  return r && r.signed_out === true;
}

async function signOut() {
  const btn = $('signout');
  btn.disabled = true;
  state.signOut = 'signing_out';
  keepDraft();
  clearPrivileged();
  $('login-id').value = '';
  try {
    await revoke();
    state.signOut = 'none';
    state.ended = false;
    showGate(null);
  } catch (err) {
    // A 401 IS A CONFIRMATION HERE, not a failure: the token no longer
    // authenticates, which is the thing being asked for.
    if (err.status === 401) {
      state.signOut = 'none';
      state.ended = false;
      showGate(null);
      return;
    }
    state.signOut = 'unconfirmed';
    showGate(null);
    $('login-state').appendChild(stateBlock('loud',
      'I could not reach the server to end your session, so YOU MAY STILL BE '
      + 'SIGNED IN on it. This screen is not proof that you are signed out. '
      + 'I will keep trying; if you are on a shared machine, do not walk away '
      + 'until it says the session is closed.'));
    const again = document.createElement('button');
    again.className = 'ghost';
    again.textContent = 'Try to end the session again';
    again.addEventListener('click', retryRevoke);
    $('login-state').appendChild(again);
    // AND WHEN CONNECTIVITY COMES BACK, without being asked. An advocate who
    // has closed the laptop is the case this is for.
    window.addEventListener('online', retryRevoke, { once: true });
  } finally {
    btn.disabled = false;
  }
}

async function retryRevoke() {
  if (state.signOut !== 'unconfirmed') return;
  try {
    await revoke();
  } catch (err) {
    if (err.status !== 401) return;   // still unreachable; the notice stands
  }
  state.signOut = 'none';
  state.ended = false;
  showGate(null);
  $('login-state').appendChild(stateBlock('quiet',
    'The session is now closed on the server.'));
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
const NEWLINE = String.fromCharCode(10);

async function showSessions() {
  let d;
  try {
    d = await api('/api/sessions');
  } catch (e) {
    window.alert(`I could not read your sessions: ${e.message}`);
    return;
  }
  const lines = d.sessions.map((s) => {
    const when = String(s.issued_at).slice(0, 16).replace('T', ' ');
    const state = s.this_one ? 'this device'
      : (s.live ? 'signed in' : `ended — ${s.ended_because || 'no reason recorded'}`);
    return `· ${when} · device ${s.device} · ${state}`;
  });
  const live = d.sessions.filter((s) => s.live && !s.this_one).length;
  const body = [`You have ${d.count} session(s) on record:`, '', ...lines, ''];
  body.push(live
    ? `Sign out the ${live} other signed-in session(s)? This device stays signed in.`
    : 'Nothing else is signed in.');

  if (!live) { window.alert(body.join(NEWLINE)); return; }
  if (!window.confirm(body.join(NEWLINE))) return;
  try {
    const r = await api('/api/sessions/revoke', { method: 'POST' });
    window.alert(r.ended === 1
      ? 'Ended 1 other session.'
      : `Ended ${r.ended} other sessions.`);
  } catch (e) {
    window.alert(`I could not end them: ${e.message}. They may still be `
               + `signed in — this is not a confirmation.`);
  }
}

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
  // An invitation is a credential, not form state. It must not survive a
  // move to sign-in or the outcome card where another person could return to
  // a pre-authorised form.
  if (which !== 'register') {
    const invitation = $('reg-invitation');
    if (invitation) invitation.value = '';
  }
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
    showApplication(current.advocate, current.workspace);
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
  const go = $('register-go');
  const password = $('reg-password').value;
  const again = $('reg-password2').value;
  const invitation = $('reg-invitation').value.trim();
  // Read once and remove it from the DOM before any network wait. A rejected
  // request must not leave a live enrolment credential on the glass.
  $('reg-invitation').value = '';

  // CHECKED HERE AND ON THE SERVER. Not because the browser is trusted -- it
  // is not, and the route checks it again -- but because a typo that costs a
  // round trip and a stern sentence is a typo the advocate reads as a
  // rejection rather than as a slip.
  if (password !== again) {
    $('reg-password2').value = '';
    showOutcome('bad', 'Registration failed',
      'The two passwords do not match. Nothing was saved.');
    return;
  }

  go.disabled = true;
  try {
    const r = await api('/api/register', {
      method: 'POST',
      // BK-31. A HEADER, NOT A BODY FIELD. The invitation is proof the
      // advocate was invited onto the roster, not part of who they are, so it
      // does not belong in the identity the registration creates.
      //
      // THE NAME MUST MATCH `nm/edge/api.py::register`, and for a while it
      // did not: the route moved to `x-enrolment-invitation` and this kept
      // sending `x-enrolment-code`, so the browser form could enrol nobody
      // while every server-side test passed. Two files holding one name with
      // nothing refusing the drift -- CLAUDE.md §4. It is now asserted by
      // `test_the_page_and_the_script_agree.py`.
      headers: {
        'content-type': 'application/json',
        'x-enrolment-invitation': invitation,
      },
      body: JSON.stringify({
        password: password,
        password_again: again,
      }),
    });
    // THE PASSWORDS LEAVE THE PAGE. They stay in the DOM otherwise, readable
    // by anything running later on this document -- the same rule the sign-in
    // handler already follows.
    $('reg-password').value = '';
    $('reg-password2').value = '';

    // REGISTERED, NOT SIGNED IN. A form post that created a session would mean
    // creating an account also logs in whatever machine sent it, and the
    // device binding is minted at sign-in for exactly that reason.
    //
    // THE EMAIL IS FILLED FROM WHAT THE SERVER RETURNED. The advocate never
    // retypes it here: the sealed invitation owns the roster identity and the
    // canonical handle returned by the route is exactly what sign-in accepts.
    $('login-id').value = r.advocate_id;
    showOutcome('good', 'Registration successful',
      `Enrolled as ${r.name}. Sign in with ${r.advocate_id} and the password `
      + 'you just chose.', r.recovery_codes || [], 'register');
  } catch (err) {
    $('reg-password').value = '';
    $('reg-password2').value = '';
    showOutcome('bad', 'Registration failed', err.message, [], 'register');
  } finally {
    $('reg-invitation').value = '';
    go.disabled = false;
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
