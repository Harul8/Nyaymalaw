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
  advocate: 'adv_demo',
  matterId: null,
  turns: [],
};

/* --------------------------------------------------------------- fetch --- */

async function api(path, options) {
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) {
    const detail = (body && (body.detail || body.message)) || `HTTP ${res.status}`;
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return body;
}

/* --------------------------------------------------------------- health --- */

async function loadHealth() {
  const el = $('health');
  try {
    const h = await api('/api/health');
    const bits = [
      `${h.provider}/${h.routine_model}`,
      `hard: ${h.hard_tier}`,
      `judge: ${h.judge_tier}`,
      `store: ${h.encryption}`,
      `corpus: ${h.corpus}`,
      `manifest: ${h.manifest_acts} acts`,
    ];
    el.textContent = bits.join('  ·  ');
    el.classList.toggle('bad', h.corpus !== 'readable');
  } catch (e) {
    el.textContent = `configuration refused: ${e.message}`;
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

async function showMatterList() {
  state.matterId = null;
  $('rail-title').textContent = 'Matters';
  $('back').hidden = true;
  const body = $('rail-body');
  body.replaceChildren(stateBlock('building', 'Loading matters…'));

  let data;
  try {
    data = await api(`/api/matters?advocate_id=${encodeURIComponent(state.advocate)}`);
  } catch (e) {
    // NEVER render an unreadable board as an empty one.
    body.replaceChildren(stateBlock(
      'unbuildable',
      `The matter list could not be built: ${e.message}. This is a failure to ` +
      `read, not a statement that you have no matters.`));
    $('rail-meta').textContent = 'state: unbuildable';
    return;
  }

  $('rail-meta').textContent =
    `${data.row_count} row(s) · bounded by ${data.bounded_by}`;

  if (!data.matters.length) {
    body.replaceChildren(stateBlock('empty', 'No matters yet. Brief me and I will open one.'));
    return;
  }

  body.replaceChildren(...data.matters.map((m) => {
    const row = document.createElement('div');
    row.className = 'row' + (m.blocked ? ' loud' : '');
    const t = document.createElement('div');
    t.className = 'r-title'; t.textContent = m.matter;
    const dl = document.createElement('dl'); dl.className = 'r-fields';
    field(dl, 'threads', String(m.threads));
    field(dl, 'deadline', m.next_deadline || 'none recorded');
    field(dl, 'blocked', m.blocked
      ? { pill: 'blocked', text: m.blocked }
      : { pill: 'ok', text: 'nothing blocking' });
    row.append(t, dl);
    row.onclick = () => showThreadBoard(m.matter_id);
    return row;
  }));
}

async function showThreadBoard(matterId) {
  state.matterId = matterId;
  $('rail-title').textContent = 'Threads';
  $('back').hidden = false;
  const body = $('rail-body');
  body.replaceChildren(stateBlock('building', 'Loading threads…'));

  let data;
  try {
    data = await api(`/api/matters/${matterId}?advocate_id=${encodeURIComponent(state.advocate)}`);
  } catch (e) {
    body.replaceChildren(stateBlock(
      'unbuildable', `The thread board could not be built: ${e.message}`));
    $('rail-meta').textContent = 'state: unbuildable';
    return;
  }

  $('rail-meta').textContent =
    `${data.row_count} row(s) · bounded by ${data.bounded_by} · v${data.version}`;

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
    field(dl, 'deadline', t.next_deadline || 'none recorded');
    row.append(title, dl);
    return row;
  }));
}

/* -------------------------------------------------------------- the answer --- */

const KIND_LABEL = {
  action: 'Action',
  finding: 'Finding',
  question: 'Blocking question',
  ground: 'Ground',
};

function renderTurn(entry) {
  const wrap = document.createElement('div');
  wrap.className = 'turn';

  if (entry.brief) {
    const b = document.createElement('div');
    b.className = 'brief';
    const w = document.createElement('span');
    w.className = 'who-said'; w.textContent = 'You briefed';
    b.append(w, document.createTextNode(entry.brief));
    wrap.appendChild(b);
  }

  if (entry.error) {
    const f = document.createElement('div');
    f.className = 'failure';
    f.textContent = entry.error;
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

  for (const el of entry.answer.elements) {
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
    wrap.appendChild(d);
  }

  // THE GATES THAT FIRED. A gate whose response is `disclose` and which the
  // advocate cannot see has disclosed nothing -- and G-UNSCREENED fires on
  // every turn, because the conflict, competence and engagement screens are
  // slice 10 and are not built.
  const fired = (entry.answer.metrics.gates_fired || []);
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
    wrap.appendChild(g);
  }

  const m = entry.answer.metrics;
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
  wrap.appendChild(met);
  return wrap;
}

function repaint() {
  const t = $('thread');
  t.replaceChildren(...state.turns.map(renderTurn));
  t.scrollTop = t.scrollHeight;
}

/* ------------------------------------------------------------------ send --- */

async function send(message) {
  const entry = { brief: message };
  state.turns.push(entry);
  repaint();

  const btn = $('send');
  btn.disabled = true;
  btn.textContent = 'Working…';
  try {
    const answer = await api('/api/turn', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        advocate_id: state.advocate,
        message,
        matter_id: state.matterId,
      }),
    });
    entry.answer = answer;
    if (answer.matter_id && answer.matter_id !== state.matterId) {
      state.matterId = answer.matter_id;
    }
    repaint();
    if (state.matterId) await showThreadBoard(state.matterId);
  } catch (e) {
    entry.error = `The turn was refused: ${e.message}`;
    repaint();
  } finally {
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
  box.value = '';
  send(text);
});

$('message').addEventListener('keydown', (ev) => {
  if (ev.key === 'Enter' && !ev.shiftKey) {
    ev.preventDefault();
    $('composer').requestSubmit();
  }
});

$('advocate').addEventListener('change', (ev) => {
  state.advocate = ev.target.value.trim() || 'adv_demo';
  state.turns = [];
  repaint();
  showMatterList();
});

$('back').addEventListener('click', showMatterList);

$('new-matter').addEventListener('click', () => {
  state.matterId = null;
  state.turns = [];
  repaint();
  $('mode-line').hidden = true;
  $('message').focus();
  showMatterList();
});

loadHealth();
showMatterList();
