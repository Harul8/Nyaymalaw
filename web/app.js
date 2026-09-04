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
    entry.error = e.message;
    entry.refusal = (e.detail && typeof e.detail === 'object') ? e.detail : null;
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

/* ============================== THE TABS ==============================
 *
 * Three surfaces that deliberately do NOT share state. A hit found in the
 * corpus is not a fact on a matter until the advocate puts it there, and the
 * quickest way to break that is a shared object both panes write to.
 */

const PANES = ['advise', 'search', 'record'];

function showTab(name) {
  PANES.forEach((p) => { $(`pane-${p}`).hidden = (p !== name); });
  document.querySelectorAll('#tabs .tab').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.tab === name);
  });
  if (name === 'search') $('q').focus();
  if (name === 'record') loadRecordMatters();
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
  const what = document.createElement('span');
  what.textContent = `Searched: ${d.index} · for “${d.query}”`;
  el.appendChild(what);

  if (d.identity) {
    const frac = d.identity.fraction_of_source;
    const held = d.identity.held.toLocaleString();
    const of = d.identity.of_source ? d.identity.of_source.toLocaleString() : null;
    const detail = document.createElement('span');
    detail.className = 'index-detail';
    // BOTH NUMBERS, because the RATIO is the disclosure. "451,548 paragraphs"
    // reads as the corpus; "451,548 of 1,015,780" does not.
    const size = of
      ? `${held} of ${of} source paragraphs (${(frac * 100).toFixed(1)}%)`
      : `${held} paragraphs · source size not recorded`;
    // SCOPE FIRST. It is the disclosure that changes whether the whole result
    // means anything: an empty answer to a Kerala question is not an answer
    // about Kerala law, and only this line says so.
    detail.textContent = ` · ${d.identity.scope} · ${size} · built ${d.identity.built_at}`;
    el.appendChild(detail);
  }
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
    prov.textContent = `${h.origin} · ${(h.confidence * 100).toFixed(0)}%`;
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
    advocate_id: state.advocate,
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

async function loadRecordMatters() {
  const sel = $('record-matter');
  try {
    const d = await api(`/api/matters?advocate_id=${encodeURIComponent(state.advocate)}`);
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
      $('record-state').appendChild(stateBlock('loud', d.unreadable_reason
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
    $('record-state').textContent = '';
    $('record-state').appendChild(stateBlock('loud',
      `The matter list could not be read: ${err.message}`));
  }
}

async function showRecord(matterId) {
  const st = $('record-state');
  const body = $('record-body');
  st.textContent = ''; body.textContent = '';
  if (!matterId) return;

  let d;
  try {
    d = await api(`/api/matters/${matterId}/transcript?advocate_id=${encodeURIComponent(state.advocate)}`);
  } catch (err) {
    st.appendChild(stateBlock('loud', `The record could not be read: ${err.message}`));
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

  d.turns.forEach((t, i) => {
    const card = document.createElement('article');
    card.className = 'recorded-turn';

    const h = document.createElement('header');
    h.textContent = `Turn ${i + 1} · ${t.turn_id || ''}`;
    card.appendChild(h);

    const asked = document.createElement('p');
    asked.className = 'recorded-asked';
    asked.textContent = t.message || t.asked
      || '(what the advocate wrote was not recorded on this turn)';
    card.appendChild(asked);

    const pre = document.createElement('pre');
    pre.className = 'recorded-raw';
    pre.textContent = JSON.stringify(t, null, 2);
    const wrap = document.createElement('details');
    const sum = document.createElement('summary');
    sum.textContent = 'The turn as it was served';
    wrap.append(sum, pre);
    card.appendChild(wrap);

    body.appendChild(card);
  });
}

$('record-matter').addEventListener('change', (ev) => showRecord(ev.target.value));
