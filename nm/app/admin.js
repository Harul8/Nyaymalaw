'use strict';

/* THE ADMIN AREA'S PAGE (plan AN.46, piece 46p; owner decisions D116-D119, D124 and D128, 7 Nov 2026).

   WHAT IT SHOWS: usage, balance and consumption beside the account facts they belong to, diagnostics, and who has done what. NEVER
   a conversation, matter, file or record of an advocate's - the server does not send any, and nothing here asks for one.

   EVERY WORD FROM THE SERVER IS SET AS TEXT. Names, emails and device labels are typed by advocates, so nothing below builds markup from
   them: elements are made with `el()`, which only ever sets text. No markup is made from a word of the server's anywhere in this file.

   A PART THAT CANNOT BE READ SAYS SO AND LEAVES THE REST STANDING (D128): each page asks for what it needs, and a refusal shows as a
   plain message with Try again, never as a page of zeros. */
(() => {
  const $ = (id) => document.getElementById(id);
  const INDIA = 'Asia/Kolkata';
  let me = null;
  let generation = 0;

  // ------------------------------------------------------------------ small tools ---

  function el(tag, attrs, ...kids) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'text') node.textContent = value;
      else if (key === 'class') node.className = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const kid of kids.flat()) {
      if (kid === undefined || kid === null || kid === false) continue;
      node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return node;
  }

  const num = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString('en-IN'));
  // Money is whole millionths of a US dollar; small amounts keep their fractions, so a cheap day is not shown as nothing.
  function money(micro) {
    if (micro === null || micro === undefined) return '—';
    const dollars = micro / 1e6;
    return '$' + dollars.toLocaleString('en-US', {
      minimumFractionDigits: 2, maximumFractionDigits: dollars !== 0 && Math.abs(dollars) < 0.1 ? 4 : 2 });
  }
  function when(iso) {
    if (!iso) return '—';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString('en-IN', { timeZone: INDIA, day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  }
  function dateOnly(iso) {
    if (!iso) return '—';
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('en-IN', { timeZone: INDIA, day: 'numeric', month: 'short', year: 'numeric' });
  }
  function shortDay(isoDay) {
    const [y, m, d] = isoDay.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-IN', { timeZone: 'UTC', day: 'numeric', month: 'short' });
  }
  function seconds(n) {
    if (n === null || n === undefined) return '—';
    return n >= 90 ? `${Math.floor(n / 60)} min ${n % 60} s` : `${n} s`;
  }
  function bytes(n) {
    if (n === null || n === undefined) return '—';
    const gb = n / 1024 ** 3;
    return gb >= 1 ? `${gb.toFixed(gb >= 100 ? 0 : 1)} GB` : `${(n / 1024 ** 2).toFixed(0)} MB`;
  }
  const words = (text) => String(text || '').replace(/^core_/, '').replace(/[_-]+/g, ' ');
  const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many}`;

  // ------------------------------------------------------------------- the server ---

  class Refused extends Error {
    constructor(message, status) { super(message); this.status = status; }
  }

  async function ask(path) {
    let res;
    try {
      res = await fetch(path, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    } catch {
      throw new Refused('The server could not be reached. Nothing has been changed.', 0);
    }
    let body = null;
    try { body = await res.json(); } catch { /* not JSON */ }
    if (res.status === 401) throw new Refused('Your session has ended. Sign in again from the workspace.', 401);
    if (!res.ok) {
      const detail = body && typeof body.detail === 'string' ? body.detail : `The server answered ${res.status}.`;
      throw new Refused(detail, res.status);
    }
    return body;
  }

  function cookie(name) {
    const hit = document.cookie.split('; ').find((part) => part.startsWith(`${name}=`));
    return hit ? decodeURIComponent(hit.slice(name.length + 1)) : '';
  }

  // A change is sent as a POST with the cross-site header every write in this product carries. The server's refusals come back in
  // words (and, for the password step, with a code the page answers by asking for the password).
  async function send(path, body) {
    let res;
    try {
      res = await fetch(path, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-NM-CSRF': cookie('nm_csrf') },
        body: JSON.stringify(body) });
    } catch {
      throw new Refused('The server could not be reached. Nothing has been changed.', 0);
    }
    let data = null;
    try { data = await res.json(); } catch { /* not JSON */ }
    if (res.status === 401) throw new Refused('Your session has ended. Sign in again from the workspace.', 401);
    if (!res.ok) {
      const detail = data && data.detail;
      const message = typeof detail === 'string' ? detail : detail && typeof detail.message === 'string' ? detail.message
        : Array.isArray(detail) ? 'Check the amount and the reason, and try again.' : `The server answered ${res.status}.`;
      const refused = new Refused(message, res.status);
      refused.code = detail && detail.code;
      throw refused;
    }
    return data;
  }

  // ----------------------------------------------------------------- the pieces ---

  const tip = $('adm-tip');
  function withTip(node, text) {
    node.addEventListener('pointerenter', (ev) => { tip.textContent = text; tip.hidden = false; place(ev); });
    node.addEventListener('pointermove', place);
    node.addEventListener('pointerleave', () => { tip.hidden = true; });
  }
  function place(ev) {
    tip.style.left = `${Math.min(ev.clientX + 12, window.innerWidth - 260)}px`;
    tip.style.top = `${ev.clientY + 14}px`;
  }

  function tile(label, value, note) {
    return el('div', { class: 'adm-tile' }, el('div', { class: 'adm-tile-label', text: label }),
      el('div', { class: 'adm-tile-value', text: value }), note ? el('div', { class: 'adm-tile-note', text: note }) : null);
  }
  const section = (title, ...kids) => el('section', { class: 'adm-section' }, el('h2', { text: title }), ...kids);
  const note = (text) => el('p', { class: 'adm-note', text });
  const callout = (kind, ...kids) => el('div', { class: `adm-callout ${kind}`, role: kind === 'adm-bad' ? 'alert' : null }, ...kids);

  function levelChip(row) {
    return el('span', { class: `adm-chip ${row.level === 'advocate' ? '' : 'adm-admin'}`, text: row.level_label });
  }
  function statusChip(status) {
    const label = { active: 'Active', suspended: 'Suspended', unreadable: 'Record unreadable' }[status] || status;
    return el('span', { class: `adm-chip ${status === 'active' ? 'adm-ok' : 'adm-bad'}`, text: label });
  }
  function meter(allowance) {
    if (!allowance.started) return el('span', { class: 'adm-note', text: 'Not started' });
    const low = allowance.left_percent <= 10;
    return el('div', { class: 'adm-meter', title: `${money(allowance.granted)} granted, ${money(allowance.spent)} used` },
      el('span', { class: 'adm-meter-bar' }, el('span', { class: `adm-meter-fill ${low ? 'adm-low' : ''}`, style: `width:${Math.max(0, Math.min(100, allowance.left_percent))}%` })),
      el('span', { class: 'adm-meter-text', text: `${allowance.left_percent}% left${low ? ' · low' : ''}` }));
  }
  function who(row, link) {
    const inner = [el('span', { class: 'adm-who', text: row.name || row.id }), row.name ? el('span', { class: 'adm-who-mail', text: row.id }) : null];
    return link ? el('a', { class: 'adm-row-link', href: `#users/${encodeURIComponent(row.id)}` }, inner) : el('div', {}, inner);
  }

  function facts(pairs) {
    return el('dl', { class: 'adm-facts' }, pairs.map(([label, value]) => el('div', {}, el('dt', { text: label }),
      el('dd', {}, value instanceof Node ? value : String(value ?? '—')))));
  }

  function table({ head, rows, empty, numeric = [] }) {
    if (!rows.length) return note(empty || 'Nothing to show.');
    const heads = head.map((h, i) => el('th', { scope: 'col', class: numeric.includes(i) ? 'adm-num' : '' }, h));
    return el('div', { class: 'adm-scroll' }, el('table', { class: 'adm-table' },
      el('thead', {}, el('tr', {}, heads)),
      el('tbody', {}, rows.map((cells) => el('tr', {}, cells.map((c, i) => el('td', { class: numeric.includes(i) ? 'adm-num' : '' }, c)))))));
  }

  // A bar chart of one series by day (one measure, one hue; the table view is the same numbers in words).
  function barChart({ rows, value, label, valueText, caption, columns }) {
    const figure = el('figure', { class: 'adm-chart' });
    const total = rows.reduce((sum, row) => sum + value(row), 0);
    const toggle = el('button', { type: 'button', class: 'adm-link', text: 'Show as a table' });
    figure.append(el('figcaption', {}, el('strong', { text: caption }), toggle));
    const H = 210, left = 56, right = 8, top = 10, bottom = 26, plotH = H - top - bottom;
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${caption}: ${rows.length} days, ${valueText(total)} in all. A table of the same figures follows.`);
    const max = Math.max(...rows.map(value), 0);
    const ceiling = max > 0 ? max : 1;
    // DRAWN AT THE WIDTH IT IS SHOWN AT, so its words stay the size they were written at however wide the page is.
    function paint(W) {
      const plotW = W - left - right;
      svg.replaceChildren();
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      const add = (name, attrs, text) => {
        const node = document.createElementNS(NS, name);
        for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
        if (text !== undefined) node.textContent = text;
        svg.append(node);
        return node;
      };
      for (const share of [0, 0.5, 1]) {
        const y = top + plotH - plotH * share;
        add('line', { x1: left, x2: W - right, y1: y, y2: y, class: share === 0 ? 'adm-axis' : 'adm-grid' });
        add('text', { x: left - 6, y: y + 4, 'text-anchor': 'end' }, valueText(ceiling * share));
      }
      const slot = plotW / Math.max(rows.length, 1);
      const gap = slot > 6 ? 2 : 1;
      const barW = Math.max(2, slot - gap);
      const every = Math.ceil(rows.length / Math.max(2, Math.floor(plotW / 70)));
      rows.forEach((row, i) => {
        const v = value(row);
        const h = max > 0 ? Math.max(v > 0 ? 2 : 0, (v / ceiling) * plotH) : 0;
        const x = left + i * slot + (slot - barW) / 2;
        const hit = add('rect', { x: left + i * slot, y: top, width: slot, height: plotH, fill: 'transparent', class: 'adm-bar-hit' });
        const r = Math.min(3, barW / 2, h);
        const mark = add('path', { class: 'adm-bar-mark',
          d: h > 0 ? `M${x},${top + plotH} V${top + plotH - h + r} Q${x},${top + plotH - h} ${x + r},${top + plotH - h} H${x + barW - r} Q${x + barW},${top + plotH - h} ${x + barW},${top + plotH - h + r} V${top + plotH} Z` : '' });
        withTip(hit, `${label(row)}: ${valueText(v)}`);
        hit.addEventListener('pointerenter', () => mark.classList.add('adm-on'));
        hit.addEventListener('pointerleave', () => mark.classList.remove('adm-on'));
        if (i % every === 0 || i === rows.length - 1) add('text', { x: left + i * slot + slot / 2, y: H - 8, 'text-anchor': 'middle' }, label(row));
      });
    }
    let drawn = 0;
    const fit = () => {
      const W = Math.max(300, Math.floor(figure.clientWidth));
      if (Math.abs(W - drawn) > 6) { drawn = W; paint(W); }
    };
    paint(640);
    drawn = 640;
    figure.append(svg);
    if (typeof ResizeObserver === 'function') new ResizeObserver(fit).observe(figure);
    const tableView = table({ head: columns.map((c) => c.head), numeric: columns.map((c, i) => (c.numeric ? i : -1)).filter((i) => i >= 0),
      rows: rows.map((row) => columns.map((c) => c.cell(row))) });
    tableView.hidden = true;
    figure.append(tableView);
    toggle.addEventListener('click', () => {
      const showing = tableView.hidden;
      tableView.hidden = !showing;
      svg.style.display = showing ? 'none' : '';
      toggle.textContent = showing ? 'Show as a chart' : 'Show as a table';
    });
    if (total === 0) figure.append(note('Nothing was recorded in this period.'));
    return figure;
  }

  function costByDay(by_day, caption) {
    return barChart({ rows: by_day, value: (r) => r.micro_usd, label: (r) => shortDay(r.day), valueText: money, caption,
      columns: [{ head: 'Day', cell: (r) => shortDay(r.day) }, { head: 'Calls', numeric: true, cell: (r) => num(r.calls) },
        { head: 'Cost', numeric: true, cell: (r) => money(r.micro_usd) }] });
  }

  const ATTENTION = {
    allowance_low: (n) => `${plural(n, 'account has', 'accounts have')} 10% or less of the allowance left.`,
    records_unreadable: (n) => `${plural(n, 'account record', 'account records')} could not be read.`,
    sessions_unreadable: (n) => `${plural(n, 'session file', 'session files')} could not be read, so the sessions shown may be incomplete.`,
    registrations_unreadable: () => 'The registrations waiting to be confirmed could not be read.' };

  function answersBlock(answers, caption) {
    if (!answers.available) {
      return note(answers.unreadable ? 'The turn record could not be read, so answers a day are not shown. Nothing else here depends on it.'
        : 'Answers a day need the turn record, which has not begun.');
    }
    const t = answers.totals;
    const began = answers.began ? note(`The turn record began on ${dateOnly(answers.began)}; turns before then were not recorded, and the days before it show nothing for that reason.`) : note('No turn has ended since the turn record began.');
    return el('div', {}, barChart({ rows: answers.by_day, value: (r) => r.answered, label: (r) => shortDay(r.day), valueText: num, caption,
      columns: [{ head: 'Day', cell: (r) => shortDay(r.day) }, { head: 'Answered', numeric: true, cell: (r) => num(r.answered) },
        { head: 'Stopped', numeric: true, cell: (r) => num(r.stopped) }, { head: 'Refused', numeric: true, cell: (r) => num(r.refused) },
        { head: 'Failed', numeric: true, cell: (r) => num(r.failed) }] }),
      el('div', { class: 'adm-tiles', style: 'margin-top:.8rem' }, tile('Answered', num(t.answered)), tile('Stopped by the advocate', num(t.stopped)),
        tile('Refused', num(t.refused), 'sign-in ended, AI sharing off, allowance used up…'), tile('Failed', num(t.failed), 'NM’s side or the AI service’s'),
        tile('A typical answer took', seconds(answers.seconds_middle), `nine in ten took ${seconds(answers.seconds_slow)} or less`)), began);
  }

  // --------------------------------------------------------------------- the pages ---

  async function overviewPage() {
    const o = await ask('/api/admin/overview');
    const a = o.accounts, w = o.week.tiles;
    const root = el('div');
    root.append(el('div', { class: 'adm-tiles' },
      tile('Accounts', num(a.accounts), `${num(a.advocates)} advocates · ${num(a.admins)} admins${a.suspended ? ` · ${num(a.suspended)} suspended` : ''}`),
      tile('Waiting to confirm', num(a.waiting), 'registered, email not yet confirmed'),
      tile('Signed in, last 7 days', num(o.signed_in_last_7_days), `${num(o.live_sessions)} live sessions now`),
      tile('Calls, last 7 days', num(w.calls), `${num(w.active_accounts)} accounts used the service`),
      tile('Cost, last 7 days', money(w.micro_usd), w.cost_not_established ? `${num(w.cost_not_established)} calls had no cost established` : null),
      tile('AI sharing on', num(a.ai_sharing_on), `of ${num(a.accounts)} accounts`)));
    root.append(section('Needs attention', o.needs_attention.length
      ? el('div', {}, o.needs_attention.map((item) => callout('adm-warn', (ATTENTION[item.kind] || (() => item.kind))(item.count), ' ',
        item.kind === 'allowance_low' ? el('a', { href: '#users', text: 'See the users.' }) : null)))
      : callout('adm-fine', 'Nothing needs attention in the accounts.')));
    root.append(section('This week', el('div', { class: 'adm-two' }, costByDay(o.week.by_day, 'Cost by day, last 7 days'),
      el('div', {}, answersBlock(o.answers, 'Answers by day, last 7 days')))));
    return root;
  }

  // THE USER TYPE (owner, 7 Nov 2026): every account is an Advocate until an Admin makes it an Admin, from this list. Those the server's
  // settings name are shown as they are set there and cannot be changed here; your own type is yours to keep (another admin changes it);
  // Admin (view only) sees the type and cannot change it.
  function typeCell(r) {
    if (r.type_locked) return el('div', {}, levelChip(r), el('span', { class: 'adm-who-mail', text: 'set in the server’s settings' }));
    if (!me.can_change || r.status === 'unreadable' || r.id === me.id) return levelChip(r);
    const label = r.name || r.id;
    const select = el('select', { class: 'adm-field adm-select', 'aria-label': `User type of ${label}` },
      el('option', { value: 'advocate', text: 'Advocate' }), el('option', { value: 'admin', text: 'Admin' }));
    select.value = r.user_type;
    select.addEventListener('change', async () => {
      const wanted = select.value;
      await confirmChange({
        title: wanted === 'admin' ? `Make ${label} an Admin` : `Make ${label} an Advocate`, submit: wanted === 'admin' ? 'Make an Admin' : 'Make an Advocate', fields: [],
        summary: wanted === 'admin'
          ? `${label} will see the Admin area as soon as they next open the workspace: every account’s usage, balance and account facts - never anyone’s conversations, files or records - and they can make changes.`
          : `${label} will no longer see or reach the Admin area. Nothing of theirs is deleted.`,
        run: async (v) => {
          await send(`/api/admin/users/${encodeURIComponent(r.id)}/user-type`, { user_type: wanted, reason: v.reason });
          return `${label} is now ${wanted === 'admin' ? 'an Admin' : 'an Advocate'}.`;
        } });
      if (select.isConnected) select.value = r.user_type;
    });
    return select;
  }

  let userSort = { key: 'name', dir: 1 };
  let userFilter = '';
  const USER_COLUMNS = [
    ['name', 'Name', (r) => (r.name || r.id).toLowerCase()], ['level', 'User type', (r) => r.level_label], ['status', 'Status', (r) => r.status],
    ['allowance', 'Allowance', (r) => (r.allowance.started ? r.allowance.left_percent : 1e9)],
    ['sharing', 'AI sharing', (r) => (r.ai_sharing === null ? -1 : Number(r.ai_sharing))], ['signin', 'Last sign-in', (r) => r.last_sign_in || ''],
    ['sessions', 'Sessions', (r) => r.live_sessions]];

  async function usersPage() {
    const page = await ask('/api/admin/users');
    const holder = el('div');
    const draw = () => {
      const needle = userFilter.trim().toLowerCase();
      const column = USER_COLUMNS.find((c) => c[0] === userSort.key) || USER_COLUMNS[0];
      const rows = page.accounts.filter((r) => !needle || `${r.name} ${r.id}`.toLowerCase().includes(needle))
        .sort((x, y) => (column[2](x) > column[2](y) ? 1 : column[2](x) < column[2](y) ? -1 : 0) * userSort.dir);
      const heads = USER_COLUMNS.map(([key, text]) => el('th', { scope: 'col' }, el('button', { type: 'button', class: 'adm-sort', text,
        'aria-sort': userSort.key === key ? (userSort.dir === 1 ? 'ascending' : 'descending') : null,
        onclick: () => { userSort = { key, dir: userSort.key === key ? -userSort.dir : 1 }; draw(); } })));
      holder.replaceChildren(rows.length ? el('div', { class: 'adm-scroll' }, el('table', { class: 'adm-table' },
        el('thead', {}, el('tr', {}, heads)),
        el('tbody', {}, rows.map((r) => el('tr', {},
          el('td', {}, who(r, true)), el('td', {}, typeCell(r)), el('td', {}, statusChip(r.status)),
          el('td', {}, meter(r.allowance)),
          el('td', { text: r.ai_sharing === null ? 'Could not be read' : r.ai_sharing ? 'On' : 'Off' }),
          el('td', { class: 'adm-nowrap', text: when(r.last_sign_in) }), el('td', { class: 'adm-num', text: num(r.live_sessions) })))))) : note('No account matches.'));
    };
    const root = el('div');
    const t = page.totals;
    root.append(el('p', { class: 'adm-sub', text: `${plural(t.accounts, 'account', 'accounts')}: ${num(t.advocates)} advocates and ${num(t.admins)} admins. ` +
      'Admins see usage, balance and account facts only - never conversations, files or records.' }));
    if (t.unreadable) root.append(callout('adm-bad', `${plural(t.unreadable, 'account record', 'account records')} could not be read and ${t.unreadable === 1 ? 'is' : 'are'} listed as unreadable.`));
    root.append(el('div', { class: 'adm-filter' }, el('input', { type: 'search', placeholder: 'Find by name or email', 'aria-label': 'Find a user', value: userFilter,
      oninput: (ev) => { userFilter = ev.target.value; draw(); } })));
    root.append(holder);
    draw();
    root.append(section('Waiting to confirm their email', page.waiting_readable
      ? table({ head: ['Email', 'Name', 'Asked', 'Expires'], empty: 'No one is waiting.',
        rows: page.waiting.map((w) => [w.email, w.name || '—', when(w.requested_at), when(w.expires_at)]) })
      : callout('adm-bad', 'The registrations waiting to be confirmed could not be read.')));
    return root;
  }

  async function userPage(id) {
    const u = await ask(`/api/admin/users/${encodeURIComponent(id)}`);
    const root = el('div');
    root.append(el('p', {}, el('a', { href: '#users', text: '← All users' })));
    root.append(el('div', { class: 'adm-person' }, el('strong', { text: u.name || u.id }), levelChip(u), statusChip(u.status),
      u.name ? el('span', { class: 'adm-person-mail', text: u.id }) : null));
    root.append(facts([
      ['User type', u.level_label], ['Enrolment', u.enrolment || '—'], ['Firm', u.firm_id || '—'], ['Account made', dateOnly(u.created_at)],
      ['Last sign-in', when(u.last_sign_in)], ['Last active', when(u.last_active)],
      ['AI data sharing', u.ai_sharing === null ? 'Could not be read' : u.ai_sharing ? `On${u.ai_notice_version ? ` (notice ${u.ai_notice_version})` : ''}` : 'Off'],
      ['Allowance', meter(u.allowance)],
      ['Granted and used', u.allowance.started ? `${money(u.allowance.granted)} granted · ${money(u.allowance.spent)} used` : 'Not started']]));
    if (u.unreadable_sessions) root.append(callout('adm-warn', 'Some session files could not be read, so the sessions below may be incomplete.'));
    root.append(section('Signed-in devices', table({ head: ['Device', 'Signed in', 'Last active', 'Ends', 'Now'], empty: 'No sessions are recorded.',
      rows: u.sessions.map((s) => [s.client_label || '—', when(s.issued_at), when(s.last_active_at), when(s.expires_at),
        el('span', { class: `adm-chip ${s.live ? 'adm-ok' : ''}`, text: s.live ? 'Live' : 'Ended' })]) })));
    root.append(changesPanel(u));
    const t = u.usage.totals;
    root.append(section(`Use in the last ${u.usage.period.days} days`, el('div', { class: 'adm-tiles' },
      tile('Calls', num(t.calls)), tile('Cost', money(t.micro_usd), t.cost_not_established ? `${num(t.cost_not_established)} calls had no cost established` : null),
      tile('Tokens in', num(t.tokens_in), `${num(t.cached_tokens)} read from the cache`), tile('Tokens out', num(t.tokens_out))),
      costByDay(u.usage.by_day, `Cost by day, last ${u.usage.period.days} days`)));
    return root;
  }

  let usageDays = 30;
  async function usagePage() {
    const root = el('div');
    const holder = el('div');
    const show = async () => {
      holder.replaceChildren(note('Reading the usage…'));
      const mine = generation;
      let u;
      try { u = await ask(`/api/admin/usage?days=${usageDays}`); } catch (error) { if (mine === generation) holder.replaceChildren(failure(error, show)); return; }
      if (mine !== generation) return;
      const t = u.tiles;
      const cachedShare = t.tokens_in ? Math.round((t.cached_tokens / t.tokens_in) * 100) : null;
      holder.replaceChildren(
        el('div', { class: 'adm-tiles' }, tile('Calls', num(t.calls), `${num(t.active_accounts)} accounts used the service`),
          tile('Cost', money(t.micro_usd), t.cost_not_established ? `${num(t.cost_not_established)} calls had no cost established` : null),
          tile('Allowance given', money(t.granted), 'trials and top-ups in this period'), tile('Tokens in', num(t.tokens_in), cachedShare === null ? null : `${cachedShare}% read from the cache`),
          tile('Tokens out', num(t.tokens_out))),
        section('Cost', costByDay(u.by_day, `Cost by day, last ${u.period.days} days`)),
        section('Answers', answersBlock(u.answers, `Answers by day, last ${u.period.days} days`)),
        el('div', { class: 'adm-two' },
          section('Where the cost went, by task', table({ head: ['Task', 'Calls', 'Cost'], numeric: [1, 2], empty: 'No calls in this period.',
            rows: [...u.by_operation].sort((x, y) => y.micro_usd - x.micro_usd).map((r) => [words(r.operation), num(r.calls), money(r.micro_usd)]) })),
          section('How the calls ended', table({ head: ['Outcome', 'Calls'], numeric: [1], empty: 'No calls in this period.',
            rows: u.by_outcome.map((r) => [words(r.outcome), num(r.calls)]) }))),
        section('Who used it most', table({ head: ['Account', 'Calls', 'Cost'], numeric: [1, 2], empty: 'No one used the service in this period.',
          rows: u.top_accounts.map((r) => [r.id ? el('a', { class: 'adm-row-link', href: `#users/${encodeURIComponent(r.id)}` }, el('span', { class: 'adm-who', text: r.name || r.id }),
            r.name ? el('span', { class: 'adm-who-mail', text: r.id }) : null) : 'An account no longer in the directory', num(r.calls), money(r.micro_usd)]) })),
        section('From registration to use', table({ head: ['Step', 'Accounts'], numeric: [1], rows: [
          ['Waiting to confirm their email', num(u.funnel.waiting)], ['Have an account', num(u.funnel.accounts)], ['AI data sharing on', num(u.funnel.ai_sharing_on)],
          ['Started their allowance', num(u.funnel.started_allowance)], ['Used the service in this period', num(u.funnel.used_in_period)]] })));
    };
    const buttons = [7, 30, 90].map((d) => el('button', { type: 'button', text: `${d} days`, 'aria-pressed': String(d === usageDays),
      onclick: () => { usageDays = d; buttons.forEach((b, i) => b.setAttribute('aria-pressed', String([7, 30, 90][i] === d))); show(); } }));
    root.append(el('div', { class: 'adm-filter' }, el('span', { class: 'adm-periods', role: 'group', 'aria-label': 'Period' }, buttons),
      el('span', { class: 'adm-note', text: 'Days are Indian days. Money is in US dollars, as the AI service charges it.' })), holder);
    await show();
    return root;
  }

  const STATE = { ok: ['adm-ok', '✓ Well'], attention: ['adm-warn', '! Needs attention'], note: ['', 'ℹ Note'], unavailable: ['adm-bad', '? Could not be checked'] };
  function factValue(key, value) {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'number') return /(^|_)(free|total)$/.test(key) ? bytes(value) : key.includes('seconds') ? seconds(value) : key.endsWith('_days') ? `${value} days` : num(value);
    if (typeof value === 'string') return /^\d{4}-\d{2}-\d{2}T/.test(value) ? when(value) : value || '—';
    return Object.entries(value).map(([k, v]) => `${words(k)}: ${factValue(k, v)}`).join(' · ');
  }
  async function diagnosticsPage() {
    const d = await ask('/api/admin/diagnostics');
    const root = el('div');
    root.append(el('p', { class: 'adm-sub', text: 'Counts, sizes and short names only. A problem is a kind and a count, never a message, and nothing here names an advocate.' }));
    const s = d.summary;
    root.append(el('div', { class: 'adm-tiles' }, tile('Well', num(s.ok)), tile('Need attention', num(s.attention)), tile('Notes', num(s.note)), tile('Could not be checked', num(s.unavailable))));
    root.append(section('Checks', d.checks.map((c) => {
      const [kind, text] = STATE[c.state] || ['', c.state];
      const entries = Object.entries(c.facts);
      return el('article', { class: 'adm-check' }, el('header', {}, el('h3', { text: c.label }), el('span', { class: `adm-chip ${kind}`, text })),
        entries.length ? facts(entries.map(([k, v]) => [words(k), factValue(k, v)])) : note('This could not be read just now. The other checks stand.'));
    })));
    root.append(note(`Read ${when(d.as_of)}.`));
    return root;
  }

  const COLLECTION = { acts: 'Acts', judgments: 'Judgments' };

  async function libraryPage() {
    const l = await ask('/api/admin/library');
    const root = el('div');
    root.append(el('p', { class: 'adm-sub', text: 'What the held law holds, as its own records describe it. This page shows it and does not change it: documents are added from a terminal ' +
      'with the server stopped (see below), so that the index being replaced is not in use.' }));
    root.append(section('What is held', l.stores.map((s) => {
      const name = COLLECTION[s.collection] || s.collection;
      if (!s.readable) return el('article', { class: 'adm-check' }, el('header', {}, el('h3', { text: name }), el('span', { class: 'adm-chip adm-bad', text: '? Could not be read' })),
        note('This store’s record could not be read just now. The other store stands.'));
      const catalogue = s.catalogue;
      return el('article', { class: 'adm-check' }, el('header', {}, el('h3', { text: name }),
        el('span', { class: `adm-chip ${s.files_present && s.sizes_as_recorded && s.bm25_present ? 'adm-ok' : 'adm-warn'}`,
          text: s.files_present && s.sizes_as_recorded && s.bm25_present ? '✓ In place' : '! A file is missing or a size differs' })),
        facts([['Passages', num(s.passages)], ['Vectors', num(s.vectors)], ['Built with', s.model], ['Recorded', when(s.recorded_at)],
          ['Checked at recording', `${num(s.same_vector)} of ${num(s.sampled)} sampled vectors matched their passages`],
          ['Vector index', bytes(s.index_bytes)], ['Passage store', bytes(s.passage_store_bytes)],
          ...(catalogue ? [['Acts', num(catalogue.acts)]] : [])]),
        catalogue ? el('div', { class: 'adm-two', style: 'margin-top:.8rem' },
          table({ head: ['Jurisdiction', 'Acts'], numeric: [1], rows: catalogue.by_jurisdiction.map((r) => [r.name, num(r.acts)]) }),
          table({ head: ['Standing, as India Code gives it', 'Acts'], numeric: [1], rows: catalogue.by_standing.map((r) => [r.name, num(r.acts)]) })) : null);
    })));
    root.append(section('Built beside, not yet searched', table({ head: ['Store', 'Built', 'Judgments', 'Passages', 'Index'], numeric: [2, 3],
      empty: 'No other store is waiting.', rows: l.candidates.map((c) => [c.name, c.readable ? when(c.built_at) : 'Could not be read', num(c.judgments), num(c.passages),
        c.has_index ? 'Built' : 'Not built yet']) })));
    root.append(section('Set aside when a store was last replaced', table({ head: ['Name', 'Size'], numeric: [1], empty: 'Nothing is kept from an earlier replacement.',
      rows: l.earlier_copies.map((c) => [c.name + (c.folder ? ' (folder)' : ''), bytes(c.bytes)]) })));
    if (l.disk) {
      root.append(section('Room to add', facts(Object.entries(l.disk).map(([k, v]) => [k === 'law' ? 'The disk the law is on' : 'The disk the records are on',
        `${bytes(v.free)} free of ${bytes(v.total)}`]))));
    }
    root.append(section('How a document is added', el('ol', { class: 'adm-steps' },
      el('li', { text: 'Acts: put the Act’s text file in the library’s own form, then run the append job for Acts with --dry-run first and read what it prints. It encodes only the new Acts, adds their vectors after the existing ones, rebuilds the word index, and keeps the earlier files beside the new ones.' }),
      el('li', { text: 'Judgments: the read stage cuts them into passages (the store above, “built beside”); the index stage encodes them and a swap makes the new store the one searched. Each stage is run by the owner.' }),
      el('li', { text: 'Both change the library, so the owner runs them with the server stopped. Start the server again and this page shows the new counts; the earlier files stay beside the new ones for a roll-back.' }))));
    root.append(note(`Read ${when(l.as_of)}.`));
    return root;
  }

  async function accessPage() {
    const a = await ask('/api/admin/access');
    const root = el('div');
    root.append(el('p', { class: 'adm-sub', text: 'The first admins are named in the server’s own settings and can only be changed there. Any other account is an Admin when an Admin sets its user type on the Users page.' }));
    root.append(section('Who is an admin', table({ head: ['Admin', 'Level', 'Set by', 'Account'], empty: 'No account is an admin yet.',
      rows: a.admins.map((m) => [el('div', {}, el('span', { class: 'adm-who', text: m.name || m.id }), m.name ? el('span', { class: 'adm-who-mail', text: m.id }) : null),
        el('span', { class: 'adm-chip adm-admin', text: m.label }), m.source, m.has_account ? statusChip(m.status) : el('span', { class: 'adm-chip adm-warn', text: 'No account yet' })]) }),
      a.rejected_entries ? callout('adm-warn', `${plural(a.rejected_entries, 'entry', 'entries')} in the setting could not be used and ${a.rejected_entries === 1 ? 'was' : 'were'} ignored. An ignored entry never raises anyone; it can only leave someone out.`) : null));
    const log = a.audit;
    if (!log.available) {
      root.append(section('What admins have done', callout('adm-bad', 'The audit log could not be read. Nothing has been changed.')));
      return root;
    }
    const chain = log.chain;
    root.append(section('What admins have done',
      chain.ok ? callout('adm-fine', chain.entries ? `The log’s chain holds: each of its ${plural(chain.entries, 'entry', 'entries')} follows from the one before.` : 'The log is empty, so its chain holds.')
        : callout('adm-bad', `The log’s chain is broken at entry ${chain.first_bad_id}: that entry or one before it was changed after it was written.`),
      chain.newest ? el('p', { class: 'adm-note' }, 'Newest fingerprint: ', el('span', { class: 'adm-mono', text: chain.newest }),
        '. Write it down somewhere else now and then: the chain shows an entry that was changed, but only a fingerprint kept elsewhere shows entries cut off the end. The log is tamper-evident, not tamper-proof.') : null,
      table({ head: ['When', 'Admin', 'Did', 'To', 'Why', 'Result'], empty: 'No admin has changed anything yet.',
        rows: log.entries.map((e) => [when(e.at), e.actor, words(e.action), e.target, e.reason || '—', e.outcome]) })));
    return root;
  }

  // ---------------------------------------------------------------- changes (D116) ---

  let flash = null;

  // One dialog for every change: what will happen, the fields it needs, the reason, and - only when the server has not had it from this
  // session in the last ten minutes - the admin's password. Nothing is sent until the admin presses the button, and the password is
  // sent to the server's own password check and nowhere else; it is cleared from the field as soon as it is sent.
  async function confirmChange({ title, summary, fields, submit, run }) {
    let status;
    try { status = await ask('/api/admin/me'); } catch (error) { flash = { kind: 'adm-bad', text: error.message }; return render(); }
    const dialog = $('adm-dialog');
    let needPassword = !status.password_confirmed;
    const inputs = {};
    const message = el('p', { class: 'adm-dialog-message', role: 'alert' });
    const rows = fields.map((f) => {
      inputs[f.name] = el('input', { class: 'adm-field', id: `adm-f-${f.name}`, type: f.type || 'text', required: true, maxlength: f.maxlength,
        min: f.min, max: f.max, step: f.step, autocomplete: 'off', inputmode: f.inputmode });
      return el('div', { class: 'adm-dialog-row' }, el('label', { for: `adm-f-${f.name}`, text: f.label }), inputs[f.name],
        f.help ? el('span', { class: 'adm-note', text: f.help }) : null);
    });
    inputs.reason = el('input', { class: 'adm-field', id: 'adm-f-reason', type: 'text', required: true, maxlength: 200, autocomplete: 'off' });
    const password = el('input', { class: 'adm-field', id: 'adm-f-password', type: 'password', autocomplete: 'current-password', maxlength: 1024 });
    const passwordRow = el('div', { class: 'adm-dialog-row' }, el('label', { for: 'adm-f-password', text: 'Your password' }), password,
      el('span', { class: 'adm-note', text: 'Asked once in ten minutes, in each browser you sign in with.' }));
    passwordRow.hidden = !needPassword;
    const go = el('button', { type: 'submit', class: 'adm-button', text: submit });
    const cancel = el('button', { type: 'button', class: 'adm-button adm-plain', text: 'Cancel', onclick: () => dialog.close() });
    const form = el('form', { method: 'dialog', class: 'adm-dialog-form' }, el('h2', { id: 'adm-dialog-title', text: title }), el('p', { text: summary }),
      rows, el('div', { class: 'adm-dialog-row' }, el('label', { for: 'adm-f-reason', text: 'Why (one line, kept in the audit log)' }), inputs.reason,
        el('span', { class: 'adm-note', text: 'At most 200 characters. Do not put an advocate’s case in it.' })),
      passwordRow, message, el('div', { class: 'adm-dialog-buttons' }, cancel, go));
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      go.disabled = true;
      message.textContent = '';
      try {
        if (needPassword) {
          if (!password.value) { message.textContent = 'Type your password to continue.'; return; }
          try { await send('/api/admin/password', { password: password.value }); } finally { password.value = ''; }
          needPassword = false;
        }
        const values = Object.fromEntries(Object.entries(inputs).map(([name, input]) => [name, input.value]));
        const result = await run(values);
        dialog.close();
        flash = { kind: 'adm-fine', text: result };
        render();
      } catch (error) {
        if (error.code === 'password_needed') { needPassword = true; passwordRow.hidden = false; password.focus(); }
        message.textContent = error.message;
        if (error.status === 401) { dialog.close(); render(); }
      } finally {
        go.disabled = false;
      }
    });
    dialog.replaceChildren(form);
    const closed = new Promise((resolve) => dialog.addEventListener('close', resolve, { once: true }));
    dialog.showModal();
    (inputs[fields[0] ? fields[0].name : 'reason']).focus();
    return closed;
  }

  function changesPanel(u) {
    if (!me.can_change) {
      return section('Changes', note('Admin (view only) can look but cannot change anything. Changes are made by an Admin.'));
    }
    const who = u.name || u.id;
    const buttons = [
      el('button', { type: 'button', class: 'adm-button adm-plain', text: 'Add to the allowance…', onclick: () => confirmChange({
        title: `Add to ${who}’s allowance`, submit: 'Add to the allowance',
        summary: `${who} has had ${u.allowance.started ? money(u.allowance.granted) : 'nothing yet'} granted and has used ${u.allowance.started ? money(u.allowance.spent) : money(0)}. ` +
          'What you add is in US dollars, at most $1,000 at a time.',
        fields: [{ name: 'usd', label: 'Amount to add (US dollars)', type: 'number', min: '0.01', max: '1000', step: '0.01', inputmode: 'decimal' }],
        run: async (v) => {
          const done = await send(`/api/admin/users/${encodeURIComponent(u.id)}/allowance`, { usd: v.usd, reason: v.reason });
          return `Added $${Number(v.usd).toLocaleString('en-US')} to ${who}’s allowance. They now have ${money(done.allowance.granted)} granted.` +
            (done.audited ? '' : ' The audit log could not take its second entry; the first stands.');
        } }) }),
      el('button', { type: 'button', class: 'adm-button adm-plain', text: 'Send a password-reset email…', onclick: () => confirmChange({
        title: `Send ${who} a password-reset email`, submit: 'Send the email', fields: [],
        summary: `A one-time link to choose a new password goes to ${u.id}. Using it ends every session of the account. Nothing else changes.`,
        run: async (v) => (await send(`/api/admin/users/${encodeURIComponent(u.id)}/reset-email`, { reason: v.reason })).message }) }),
      el('button', { type: 'button', class: 'adm-button adm-plain', text: 'End all sessions…', onclick: () => confirmChange({
        title: `End ${who}’s sessions`, submit: 'End the sessions', fields: [],
        summary: `This signs ${who} out of every device. Their conversations and matters are not touched, and they can sign in again.`,
        run: async (v) => {
          const done = await send(`/api/admin/users/${encodeURIComponent(u.id)}/end-sessions`, { reason: v.reason });
          return `Ended ${plural(done.sessions_ended, 'session', 'sessions')} of ${who}.`;
        } }) })];
    if (u.level !== 'advocate') {
      buttons.push(el('span', { class: 'adm-note', text: 'This account is an admin, named in the server’s settings. It is not suspended from here.' }));
    } else if (u.status === 'suspended') {
      buttons.push(el('button', { type: 'button', class: 'adm-button', text: 'Reinstate the account…', onclick: () => confirmChange({
        title: `Reinstate ${who}`, submit: 'Reinstate', fields: [], summary: `${who} will be shown as active again.`,
        run: async (v) => { await send(`/api/admin/users/${encodeURIComponent(u.id)}/reinstate`, { reason: v.reason }); return `${who} is active again.`; } }) }));
    } else {
      buttons.push(el('button', { type: 'button', class: 'adm-button adm-plain', text: 'Suspend the account…', onclick: () => confirmChange({
        title: `Suspend ${who}`, submit: 'Suspend', fields: [],
        summary: `${who} is signed out everywhere and shown as suspended. The next time they sign in with their password the suspension ends by itself and they are in, with no message; you can also reinstate them sooner. Nothing is deleted: their matters and conversations stay as they are.`,
        run: async (v) => {
          const done = await send(`/api/admin/users/${encodeURIComponent(u.id)}/suspend`, { reason: v.reason });
          return `${who} is suspended; ${plural(done.sessions_ended, 'session was', 'sessions were')} ended.`;
        } }) }));
    }
    return section('Changes', note('Each change asks for a reason and, once in ten minutes, your password, and is written to the audit log (Access and audit).'),
      el('div', { class: 'adm-actions' }, buttons));
  }

  // ---------------------------------------------------------------------- routing ---

  const PAGES = {
    overview: ['Overview', overviewPage], users: ['Users', usersPage], usage: ['Usage and analytics', usagePage],
    diagnostics: ['Diagnostics', diagnosticsPage], library: ['Library', libraryPage], access: ['Access and audit', accessPage] };

  function failure(error, retry) {
    if (error.status === 401) {
      return el('div', { class: 'adm-error', role: 'alert' }, el('p', { text: error.message }), el('p', {}, el('a', { href: '/app', text: 'Open the workspace' })));
    }
    return el('div', { class: 'adm-error', role: 'alert' }, el('p', { text: error.message || 'This part could not be read.' }),
      retry ? el('button', { type: 'button', class: 'adm-button adm-plain', text: 'Try again', onclick: retry }) : null);
  }

  async function render() {
    const mine = ++generation;
    const parts = location.hash.replace(/^#/, '').split('/');
    const key = PAGES[parts[0]] ? parts[0] : parts[0] === '' ? 'overview' : null;
    const body = $('adm-body');
    document.querySelectorAll('#adm-nav a').forEach((a) => {
      if (a.dataset.page === (key || '')) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (!key) { $('adm-title').textContent = 'Not here'; body.replaceChildren(note('There is no such page.')); return; }
    const [title, page] = PAGES[key];
    $('adm-title').textContent = title;
    document.title = `${title} · Nyaymalaw Admin`;
    body.replaceChildren(note('Reading…'));
    try {
      const node = key === 'users' && parts[1] ? await userPage(decodeURIComponent(parts.slice(1).join('/'))) : await page();
      if (mine === generation) {
        body.replaceChildren(...(flash ? [callout(flash.kind, flash.text)] : []), node);
        flash = null;
      }
    } catch (error) {
      if (mine === generation) body.replaceChildren(failure(error, render));
    }
  }

  function gate(...kids) {
    const box = $('adm-gate');
    box.hidden = false;
    $('adm-shell').hidden = true;
    box.replaceChildren(...kids);
  }

  async function boot() {
    let res;
    try { res = await fetch('/api/admin/me', { credentials: 'same-origin', headers: { Accept: 'application/json' } }); } catch {
      gate('The server could not be reached.'); return; }
    if (res.status === 401) { gate(el('p', { text: 'Sign in to the workspace first, then open Admin from the person menu.' }), el('a', { href: '/app', text: 'Open the workspace' })); return; }
    if (!res.ok) { gate(el('p', { text: 'This page is not available.' }), el('a', { href: '/app', text: 'Back to the workspace' })); return; }
    me = await res.json();
    $('adm-level').textContent = me.label;
    $('adm-level').hidden = false;
    $('adm-gate').hidden = true;
    $('adm-shell').hidden = false;
    window.addEventListener('hashchange', render);
    render();
  }

  boot();
})();
