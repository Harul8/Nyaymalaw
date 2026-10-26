'use strict';

// THE WEBSITE'S ACCOUNT BAR (owner decision O28, 26 Oct 2026; plan AN.22).
//
// The public pages are plain files: they read no session and no matter. This is the ONE script they run, and it
// asks the server ONE thing - who is signed in? (GET /api/session, a read that does not extend the session) -
// so that a visitor who is already signed in sees their own person control where Sign in and Create account
// were, and "Open your workspace" where a page said "Create your account". Its only other call is the existing
// sign-out route, when the visitor presses Sign out. The initials come from the rule the app uses (person.js).
//
// A visitor who is not signed in, who has no script, or who meets any failure sees the buttons exactly as the
// page was written. Nothing here uses innerHTML: a name is only ever text.
(() => {
  const SESSION = '/api/session';
  const SIGN_OUT = '/api/logout';
  const WORKSPACE = '/app';
  const REGISTER = '/app#register';
  // A server that does not answer must never leave a signed-in visitor without the buttons: the look at who is
  // signed in gives up after this long and the page is as it was written.
  const LOOK_MS = 5000;
  const SIGN_OUT_MS = 10000;

  const account = document.getElementById('account');
  if (!account) return;
  const originals = Array.from(account.childNodes);
  let changed = [];
  let generation = 0;
  let ui = null;

  function cookie(name) {
    const match = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }

  // The readable half of a sign-in (nm_csrf) is the page's hint that someone may be signed in, so the bar can
  // draw the profile at once instead of showing buttons for a moment and swapping them. A sign-out the app
  // never confirmed (nm_retirement) is not a sign-in the page may show.
  function maybeSignedIn() {
    return cookie('nm_csrf') !== '' && cookie('nm_retirement') !== 'pending';
  }

  function request(url, options, milliseconds) {
    const stop = new AbortController();
    const timer = setTimeout(() => stop.abort(), milliseconds);
    return fetch(url, { ...options, signal: stop.signal }).finally(() => clearTimeout(timer));
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function arrow() {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'acct-arrow');
    svg.setAttribute('viewBox', '0 0 12 12');
    svg.setAttribute('width', '10');
    svg.setAttribute('height', '10');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M2.5 4.5 6 8l3.5-3.5');
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.6');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    return svg;
  }

  // THE PERSON CONTROL: the initials circle, the name and a menu, as in the app. Drawn empty first (the circle
  // takes room and shows nothing) and filled when the server has said who it is.
  function draw() {
    const wrap = make('div', 'acct');
    const toggle = make('button', 'acct-toggle');
    toggle.type = 'button';
    toggle.disabled = true;   // until the server has said who it is
    toggle.setAttribute('aria-haspopup', 'true');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', 'acct-panel');
    toggle.setAttribute('aria-label', 'Your account and sign out');
    const initials = make('span', 'acct-avatar');
    initials.setAttribute('aria-hidden', 'true');
    const name = make('span', 'acct-name');
    toggle.append(initials, name, arrow());

    const panel = make('div', 'acct-panel');
    panel.id = 'acct-panel';
    panel.hidden = true;
    const title = make('p', 'acct-title', 'Signed in');
    const who = make('p', 'acct-who');
    const mail = make('p', 'acct-mail');
    const open = make('a', 'btn primary', 'Open the app');
    open.href = WORKSPACE;
    const out = make('button', 'acct-signout', 'Sign out');
    out.type = 'button';
    const status = make('p', 'acct-status');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    panel.append(title, who, mail, open, out, status);
    wrap.append(toggle, panel);

    ui = { wrap, toggle, panel, initials, name, who, mail, out, status };
    toggle.addEventListener('click', () => setMenu(panel.hidden));
    out.addEventListener('click', () => signOut());
    account.replaceChildren(wrap);
    account.setAttribute('aria-busy', 'true');
  }

  function setMenu(open) {
    if (!ui) return;
    ui.panel.hidden = !open;
    ui.toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  document.addEventListener('click', (event) => {
    if (ui && !ui.panel.hidden && !ui.wrap.contains(event.target)) setMenu(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && ui && !ui.panel.hidden) {
      setMenu(false);
      ui.toggle.focus();
    }
  });

  // THE PAGE'S OWN BUTTONS FOR SOMEONE WHO IS SIGNED IN: every Create account and Choose-a-plan link opens the
  // workspace and says so, and the page's own Sign in button, which would then say the same, is not shown.
  function workspaceLinks() {
    for (const link of document.querySelectorAll('a')) {
      if (account.contains(link)) continue;
      const href = link.getAttribute('href');
      if (href === REGISTER) {
        changed.push({ link, href, text: link.textContent, hidden: link.hidden });
        link.setAttribute('href', WORKSPACE);
        link.textContent = 'Open your workspace';
      } else if (href === WORKSPACE && link.textContent.trim() === 'Sign in') {
        changed.push({ link, href, text: link.textContent, hidden: link.hidden });
        link.hidden = true;
      }
    }
  }

  function anonymous() {
    account.replaceChildren(...originals);
    account.removeAttribute('aria-busy');
    for (const { link, href, text, hidden } of changed) {
      link.setAttribute('href', href);
      link.textContent = text;
      link.hidden = hidden;
    }
    changed = [];
    ui = null;
  }

  // Only text is ever shown; anything else the server sent is treated as not sent.
  function text(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function show(advocate) {
    const email = text(advocate.email);
    const name = text(advocate.name) || email || text(advocate.id);
    if (!name) return anonymous();   // never a blank profile
    // The one shared rule; if its file did not load the circle stays empty and so is not drawn.
    ui.initials.textContent = window.NmPerson ? window.NmPerson.initialsOf(name) : '';
    ui.name.textContent = name;
    ui.who.textContent = name;
    ui.mail.textContent = email;
    ui.mail.hidden = !email || email === name;   // the email is not said twice
    ui.toggle.setAttribute('aria-label', `Your account: ${name}`);
    ui.toggle.disabled = false;
    account.removeAttribute('aria-busy');
    workspaceLinks();
  }

  async function check() {
    const mine = ++generation;
    if (ui || changed.length) anonymous();
    if (!maybeSignedIn()) return;
    draw();
    let advocate = null;
    try {
      const reply = await request(SESSION, {
        credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } }, LOOK_MS);
      if (reply.ok) {
        const body = await reply.json();
        advocate = body && typeof body === 'object' && body.advocate && typeof body.advocate === 'object'
          ? body.advocate : null;
      }
    } catch (_) {
      advocate = null;
    }
    if (mine !== generation) return;   // a newer look has begun; this answer is stale
    if (!advocate) {
      anonymous();
      return;
    }
    show(advocate);
  }

  // SIGN OUT ONLY AS THE SERVER CONFIRMS IT (BK-40): the visitor is shown signed out only after the server has
  // answered that it is so, by loading the page again; an answer that never came is said, and nothing is shown
  // that did not happen.
  async function signOut() {
    if (!ui) return;
    const { out, status } = ui;
    out.disabled = true;
    status.textContent = 'Signing out…';
    try {
      const reply = await request(SIGN_OUT, {
        method: 'POST', credentials: 'same-origin', headers: { 'X-NM-CSRF': cookie('nm_csrf') } }, SIGN_OUT_MS);
      if (reply.ok) {
        window.location.reload();
        return;
      }
    } catch (_) {
      // said below
    }
    out.disabled = false;
    status.textContent = 'Signing out could not be confirmed. Try again, or open the app.';
  }

  // Back to this page from the app (the browser may keep the page as it was left): look again.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) check();
  });

  check();
})();
