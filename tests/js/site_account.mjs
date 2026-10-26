// THE WEBSITE'S ACCOUNT BAR (owner decision O28; plan AN.22): a visitor who is signed in sees their own person
// control where Sign in and Create account were, and "Open your workspace" where a page said "Create your
// account"; a visitor who is not signed in, who carries no sign-in marker or who meets any failure sees the page
// exactly as it was written. Offline substitutes for the DOM and the network; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const site = fs.readFileSync(new URL('../../nm/site/site.js', import.meta.url), 'utf8');
const shared = fs.readFileSync(new URL('../../nm/app/person.js', import.meta.url), 'utf8');

let focused = null;

// Just enough of a page: a tree of nodes that can be found, changed, clicked and asked what they hold.
class El {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.parent = null;
    this.attributes = {};
    this.listeners = {};
    this.hidden = false;
    this.disabled = false;
    this.className = '';
    this.id = '';
    this.type = '';
    this.own = '';
  }
  get childNodes() { return this.children.slice(); }
  get textContent() { return this.own + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) {
    for (const child of this.children) child.parent = null;
    this.children = [];
    this.own = String(value);
  }
  get href() { return this.attributes.href; }
  set href(value) { this.attributes.href = String(value); }
  set innerHTML(_) { throw new Error('innerHTML must not be used: a name is only ever text'); }
  set outerHTML(_) { throw new Error('outerHTML must not be used'); }
  insertAdjacentHTML() { throw new Error('insertAdjacentHTML must not be used'); }
  append(...nodes) { for (const node of nodes) this.appendChild(node); }
  appendChild(node) { node.parent = this; this.children.push(node); return node; }
  replaceChildren(...nodes) {
    for (const child of this.children) child.parent = null;
    this.children = [];
    this.append(...nodes);
  }
  contains(other) {
    for (let node = other; node; node = node.parent) if (node === this) return true;
    return false;
  }
  setAttribute(name, value) {
    if (name === 'class') this.className = String(value);
    else this.attributes[name] = String(value);
  }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  focus() { focused = this; }
}

const all = (root) => root.children.flatMap((child) => [child, ...all(child)]);
const find = (root, test) => all(root).find(test);
const has = (node, name) => node.className.split(' ').includes(name);
const within = (root, name) => find(root, (node) => has(node, name));

function link(text, href, className) {
  const node = new El('a');
  node.setAttribute('href', href);
  node.className = className;
  node.textContent = text;
  return node;
}

// A page laid out as the seven are: a top bar whose right-hand end is the account bar holding Sign in and
// Create account, and a body with its own Create-account, plan and Sign-in buttons and other links.
function build(withAccount) {
  const body = new El('body');
  const bar = body.appendChild(new El('div'));
  bar.className = 'topbar';
  const nav = bar.appendChild(new El('header'));
  const brand = nav.appendChild(link('Nyaymalaw', '/', 'brand'));
  const account = new El('div');
  account.className = 'right';
  account.id = 'account';
  const signIn = account.appendChild(link('Sign in', '/app', 'signin'));
  const create = account.appendChild(link('Create account', '/app#register', 'btn primary'));
  if (withAccount) nav.appendChild(account);
  const main = body.appendChild(new El('main'));
  const hero = main.appendChild(link('Create your account', '/app#register', 'btn primary large'));
  const plan = main.appendChild(link('Choose Pro', '/app#register', 'btn primary'));
  const bodySignIn = main.appendChild(link('\n   Sign in\n ', '/app', 'btn'));
  const tryIt = main.appendChild(link('Try the app', '/app', 'btn'));
  const signInHelp = main.appendChild(link('Sign in to see more', '/app', 'btn'));
  const other = main.appendChild(link('How it works', '/how-it-works', ''));
  const note = main.appendChild(link('About registering', '/app#register-note', ''));
  return { body, account, brand, signIn, create, hero, plan, bodySignIn, tryIt, signInHelp, other, note };
}

const everything = [];

function page({ cookie = '', answer = () => new Promise(() => {}), person = true, account = true } = {}) {
  focused = null;
  const dom = build(account);
  const calls = [];
  const timers = [];
  const reloads = { count: 0 };
  const document = {
    cookie,
    listeners: {},
    getElementById: (id) => find(dom.body, (node) => node.id === id) || null,
    createElement: (tag) => new El(tag),
    createElementNS: (_namespace, tag) => new El(tag),
    querySelectorAll: (selector) => {
      assert.equal(selector, 'a', 'the script looks only at links');
      return all(dom.body).filter((node) => node.tag === 'a');
    },
    addEventListener: (type, handler) => { (document.listeners[type] ||= []).push(handler); },
  };
  const window = {
    listeners: {},
    location: { reload: () => { reloads.count += 1; } },
    addEventListener: (type, handler) => { (window.listeners[type] ||= []).push(handler); },
  };
  const context = vm.createContext({
    document, window, AbortController, Array, Object, String, RegExp, Promise, decodeURIComponent,
    fetch: (url, options) => {
      calls.push({ url, options });
      everything.push(url);
      return answer(url, options, calls.length);
    },
    setTimeout: (fn, ms) => { timers.push({ fn, ms, cleared: false }); return timers.length - 1; },
    clearTimeout: (id) => { timers[id].cleared = true; },
  });
  if (person) vm.runInContext(shared, context);
  vm.runInContext(site, context);
  return { dom, document, window, calls, timers, reloads };
}

function click(p, target) {
  if (target.disabled) return;   // a button that is switched off gives no click
  const event = { type: 'click', target };
  for (let node = target; node; node = node.parent) for (const handler of node.listeners.click || []) handler(event);
  for (const handler of p.document.listeners.click || []) handler(event);
}
function press(p, key) {
  for (const handler of p.document.listeners.keydown || []) handler({ key });
}
function pageshow(p, persisted) {
  for (const handler of p.window.listeners.pageshow || []) handler({ persisted });
}

const reply = (body, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const settle = () => new Promise((resolve) => setImmediate(resolve));
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}
function sameNodes(actual, expected, message) {
  assert.equal(actual.length, expected.length, message);
  expected.forEach((node, index) => assert.ok(actual[index] === node, `${message} (position ${index})`));
}

// The page exactly as it was written: the very same buttons, in the same places, saying the same things.
function asWritten(p, message) {
  const d = p.dom;
  sameNodes(d.account.children, [d.signIn, d.create], `${message}: the account bar's own buttons are back`);
  assert.equal(d.account.getAttribute('aria-busy'), null, `${message}: nothing is left marked busy`);
  assert.equal(d.signIn.textContent, 'Sign in', message);
  assert.equal(d.create.textContent, 'Create account', message);
  assert.equal(d.hero.textContent, 'Create your account', message);
  assert.equal(d.hero.getAttribute('href'), '/app#register', message);
  assert.equal(d.plan.textContent, 'Choose Pro', message);
  assert.equal(d.plan.getAttribute('href'), '/app#register', message);
  assert.equal(d.bodySignIn.hidden, false, `${message}: the page's own Sign in button is shown`);
  assert.equal(d.bodySignIn.getAttribute('href'), '/app', message);
}

const SIGNED_IN = { advocate: { id: 'adv_1', name: 'Adv. Meera Rao', email: 'meera@chambers.in' } };
const signedInAnswer = (url) => (url === '/api/session' ? Promise.resolve(reply(SIGNED_IN)) : new Promise(() => {}));

// A visitor with no sign-in marker is not asked about, and sees the page as written.
{
  const p = page({ cookie: 'nm_device=abc; theme=dark', answer: () => assert.fail('no one is asked') });
  await settle();
  assert.equal(p.calls.length, 0);
  assert.equal(p.timers.length, 0);
  asWritten(p, 'no marker');
}

// A signed-in visitor: the person control is drawn at once, empty and not pressable, so the bar does not
// show the buttons for a moment and then swap them; the server's answer fills it in.
{
  const look = deferred();
  const p = page({ cookie: 'nm_device=abc; nm_csrf=tok123', answer: () => look.promise });
  const d = p.dom;
  assert.equal(d.account.children.length, 1, 'the control replaces both buttons while the server is asked');
  const control = d.account.children[0];
  assert.ok(has(control, 'acct'));
  const toggle = within(control, 'acct-toggle');
  const panel = within(control, 'acct-panel');
  assert.equal(toggle.disabled, true, 'nothing to open until the server has said who it is');
  assert.equal(toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(toggle.getAttribute('aria-controls'), panel.id);
  assert.equal(within(control, 'acct-avatar').textContent, '');
  assert.equal(d.account.getAttribute('aria-busy'), 'true');
  assert.equal(panel.hidden, true);
  assert.equal(p.calls.length, 1, 'one look, nothing else');
  const first = p.calls[0];
  assert.equal(first.url, '/api/session');
  assert.equal(first.options.method, undefined, 'asking who is signed in is a read');
  assert.equal(first.options.credentials, 'same-origin');
  assert.equal(first.options.cache, 'no-store');
  assert.equal(first.options.headers.Accept, 'application/json');
  assert.ok(first.options.signal, 'a look that is never answered can be given up');
  assert.deepEqual(p.timers.map((timer) => timer.ms), [5000]);
  assert.equal(d.hero.textContent, 'Create your account', 'the page is unchanged until the server has answered');
  assert.equal(d.bodySignIn.hidden, false);

  look.resolve(reply(SIGNED_IN));
  await settle();
  assert.equal(p.timers[0].cleared, true, 'an answered look leaves no timer behind');
  assert.equal(toggle.disabled, false);
  assert.equal(toggle.getAttribute('aria-label'), 'Your account: Adv. Meera Rao');
  assert.equal(within(control, 'acct-avatar').textContent, 'MR', 'the initials are the app\'s own rule');
  assert.equal(within(control, 'acct-name').textContent, 'Adv. Meera Rao');
  assert.equal(within(control, 'acct-who').textContent, 'Adv. Meera Rao');
  const mail = within(control, 'acct-mail');
  assert.equal(mail.textContent, 'meera@chambers.in');
  assert.equal(mail.hidden, false);
  assert.equal(within(control, 'acct-title').textContent, 'Signed in');
  assert.equal(d.account.getAttribute('aria-busy'), null);
  const open = find(control, (node) => node.tag === 'a');
  assert.equal(open.textContent, 'Open the app');
  assert.equal(open.getAttribute('href'), '/app');
  assert.equal(within(control, 'acct-signout').textContent, 'Sign out');
  assert.equal(within(control, 'acct-status').getAttribute('role'), 'status');
  assert.equal(panel.hidden, true, 'the menu opens only when pressed');

  // The page's own buttons: every Create-account and plan button opens the workspace and says so; the page's
  // own Sign in button is not shown; every other link is untouched.
  for (const node of [d.hero, d.plan]) {
    assert.equal(node.textContent, 'Open your workspace');
    assert.equal(node.getAttribute('href'), '/app');
    assert.equal(node.hidden, false);
  }
  assert.equal(d.bodySignIn.hidden, true);
  assert.equal(d.tryIt.hidden, false, 'a link to the app that is not the Sign in button stays');
  assert.equal(d.tryIt.textContent, 'Try the app');
  assert.equal(d.signInHelp.hidden, false, 'a link that only mentions signing in stays');
  assert.equal(d.signInHelp.textContent, 'Sign in to see more');
  assert.equal(d.brand.textContent, 'Nyaymalaw');
  assert.equal(d.other.getAttribute('href'), '/how-it-works');
  assert.equal(d.note.getAttribute('href'), '/app#register-note');
  assert.equal(d.note.textContent, 'About registering');

  // The menu: opens, stays open for a click inside it, closes for a click outside it and for Escape (which
  // gives the focus back), and the arrow key presses of others do nothing to it.
  click(p, toggle);
  assert.equal(panel.hidden, false);
  assert.equal(toggle.getAttribute('aria-expanded'), 'true');
  click(p, panel);
  assert.equal(panel.hidden, false, 'a click inside the menu does not close it');
  click(p, d.other);
  assert.equal(panel.hidden, true, 'a click elsewhere closes it');
  assert.equal(toggle.getAttribute('aria-expanded'), 'false');
  click(p, toggle);
  press(p, 'Enter');
  assert.equal(panel.hidden, false);
  press(p, 'Escape');
  assert.equal(panel.hidden, true);
  assert.equal(toggle.getAttribute('aria-expanded'), 'false');
  assert.ok(focused === toggle, 'Escape returns the focus to the control');
  click(p, toggle);
  click(p, toggle);
  assert.equal(panel.hidden, true, 'pressing the control again closes it');
  assert.equal(p.calls.length, 1, 'opening a menu asks the server nothing');
}

// Signing out: shown signed out only as the server confirms it - the page loads again; an answer that is not
// a yes, or none at all, is said and the control is usable again. The token sent is the one held now.
{
  const out = deferred();
  const p = page({ cookie: 'nm_csrf=tok123', answer: (url) => (url === '/api/session' ? Promise.resolve(reply(SIGNED_IN)) : out.promise) });
  await settle();
  const control = p.dom.account.children[0];
  const toggle = within(control, 'acct-toggle');
  const signOut = within(control, 'acct-signout');
  const status = within(control, 'acct-status');
  p.document.cookie = 'nm_device=abc; nm_csrf=tok456';   // renewed since this page loaded
  click(p, toggle);
  click(p, signOut);
  assert.equal(p.calls.length, 2);
  const post = p.calls[1];
  assert.equal(post.url, '/api/logout');
  assert.equal(post.options.method, 'POST');
  assert.equal(post.options.credentials, 'same-origin');
  assert.equal(post.options.headers['X-NM-CSRF'], 'tok456');
  assert.equal(signOut.disabled, true, 'pressed once while the server is asked');
  assert.equal(status.textContent, 'Signing out…');
  assert.deepEqual(p.timers.map((timer) => timer.ms), [5000, 10000]);
  click(p, signOut);
  assert.equal(p.calls.length, 2, 'a second press while waiting sends nothing');
  assert.equal(p.reloads.count, 0, 'not shown signed out before the server has said so');
  out.resolve(reply({}));
  await settle();
  assert.equal(p.reloads.count, 1, 'the page loads again once the server has confirmed');
}
for (const [label, answer] of [
  ['the server refuses', () => Promise.resolve(reply({}, 403))],
  ['the server cannot be reached', () => Promise.reject(new Error('network down'))],
]) {
  let signOutAnswer = answer;
  const p = page({ cookie: 'nm_csrf=tok123', answer: (url) => (url === '/api/session' ? Promise.resolve(reply(SIGNED_IN)) : signOutAnswer()) });
  await settle();
  const control = p.dom.account.children[0];
  const signOut = within(control, 'acct-signout');
  const status = within(control, 'acct-status');
  click(p, within(control, 'acct-toggle'));
  click(p, signOut);
  await settle();
  assert.equal(p.reloads.count, 0, `${label}: not shown signed out`);
  assert.equal(signOut.disabled, false, `${label}: the control can be used again`);
  assert.match(status.textContent, /could not be confirmed/, label);
  assert.equal(p.dom.account.children[0], control, `${label}: still shown as signed in`);
  signOutAnswer = () => Promise.resolve(reply({}));
  click(p, signOut);
  await settle();
  assert.equal(p.reloads.count, 1, `${label}: a second try that is confirmed loads the page again`);
}

// Every failure leaves the buttons exactly as the page was written.
for (const [label, answer] of [
  ['the server says nobody is signed in', () => Promise.resolve(reply({}, 401))],
  ['the server fails', () => Promise.resolve(reply({}, 500))],
  ['the server cannot be reached', () => Promise.reject(new Error('network down'))],
  ['the answer is not JSON', () => Promise.resolve({ ok: true, status: 200, json: async () => { throw new SyntaxError('bad'); } })],
  ['the answer names no advocate', () => Promise.resolve(reply({}))],
  ['the advocate is empty', () => Promise.resolve(reply({ advocate: null }))],
  ['the advocate is not an object', () => Promise.resolve(reply({ advocate: 'meera' }))],
  ['the advocate holds nothing to show', () => Promise.resolve(reply({ advocate: { id: '  ', name: '', email: null } }))],
  ['the advocate holds only values that are not text', () => Promise.resolve(reply({ advocate: { id: 7, name: { a: 1 }, email: ['x'] } }))],
]) {
  const p = page({ cookie: 'nm_csrf=tok', answer });
  await settle();
  asWritten(p, label);
  assert.equal(p.calls.length, 1, label);
}

// A server that never answers: after five seconds the look is given up and the page is as written.
{
  const p = page({
    cookie: 'nm_csrf=tok',
    answer: (_url, options) => new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted')))),
  });
  assert.equal(p.dom.account.children.length, 1, 'the skeleton is shown while waiting');
  p.timers[0].fn();
  await settle();
  asWritten(p, 'a look nobody answered');
}

// A sign-out the app never confirmed is not a sign-in the page may show.
{
  const p = page({ cookie: 'nm_csrf=tok; nm_retirement=pending', answer: () => assert.fail('no one is asked') });
  await settle();
  assert.equal(p.calls.length, 0);
  asWritten(p, 'a sign-out pending');
}

// An answer that arrives after a newer look has begun is ignored, in either order.
for (const order of ['older answers last', 'older answers first']) {
  const older = deferred();
  const newer = deferred();
  const queue = [older, newer];
  const p = page({ cookie: 'nm_csrf=tok', answer: () => queue.shift().promise });
  pageshow(p, true);
  assert.equal(p.calls.length, 2);
  const settleOlder = () => older.resolve(reply({ advocate: { name: 'Old Person', email: 'old@x.in' } }));
  const settleNewer = () => newer.resolve(reply({ advocate: { name: 'New Person', email: 'new@x.in' } }));
  if (order === 'older answers last') { settleNewer(); await settle(); settleOlder(); } else { settleOlder(); await settle(); settleNewer(); }
  await settle();
  assert.equal(p.dom.account.children.length, 1, order);
  assert.equal(within(p.dom.account.children[0], 'acct-name').textContent, 'New Person', order);
  assert.equal(p.dom.hero.textContent, 'Open your workspace', order);
}

// Coming back to a page the browser kept: looks again when the page was restored, never otherwise; a visitor who
// signed out meanwhile gets the buttons back, and the changes do not pile up on one another.
{
  let now = signedInAnswer;
  const p = page({ cookie: 'nm_csrf=tok', answer: (...given) => now(...given) });
  await settle();
  pageshow(p, false);
  await settle();
  assert.equal(p.calls.length, 1, 'a page shown for the first time is not looked at twice');
  pageshow(p, true);
  pageshow(p, true);
  await settle();
  assert.equal(p.calls.length, 3);
  assert.equal(p.dom.account.children.length, 1, 'one control, however often the page is restored');
  assert.equal(p.dom.hero.textContent, 'Open your workspace');

  now = () => Promise.resolve(reply({}, 401));   // the session ended while the page was kept
  pageshow(p, true);
  await settle();
  assert.equal(p.calls.length, 4);
  asWritten(p, 'the session ended meanwhile');

  now = signedInAnswer;
  pageshow(p, true);
  await settle();
  assert.equal(p.dom.hero.textContent, 'Open your workspace');
  p.document.cookie = 'nm_device=abc';   // signed out in another tab: the marker is gone
  pageshow(p, true);
  await settle();
  assert.equal(p.calls.length, 5, 'no marker, no question');
  asWritten(p, 'signed out meanwhile');
}

// What the server sent is shown as text and nothing else.
{
  const markup = '<img src=x onerror=alert(1)>';
  const p = page({ cookie: 'nm_csrf=tok', answer: () => Promise.resolve(reply({ advocate: { name: markup, email: '"><script>alert(1)</script>' } })) });
  await settle();
  const control = p.dom.account.children[0];
  const name = within(control, 'acct-name');
  assert.equal(name.textContent, markup);
  assert.equal(name.children.length, 0, 'no element was made from a name');
  assert.equal(within(control, 'acct-mail').children.length, 0);
  assert.equal(within(control, 'acct-toggle').getAttribute('aria-label'), `Your account: ${markup}`);
  assert.equal(all(p.dom.body).filter((node) => ['img', 'script'].includes(node.tag)).length, 0);
}

// An account that holds no name shows its email once, and its initial; one that holds only an id shows that.
{
  const p = page({ cookie: 'nm_csrf=tok', answer: () => Promise.resolve(reply({ advocate: { id: 'adv_9', name: '', email: 'p14lrahul@iima.ac.in' } })) });
  await settle();
  const control = p.dom.account.children[0];
  assert.equal(within(control, 'acct-name').textContent, 'p14lrahul@iima.ac.in');
  assert.equal(within(control, 'acct-avatar').textContent, 'P');
  assert.equal(within(control, 'acct-mail').hidden, true, 'the email is not said twice');
  const only = page({ cookie: 'nm_csrf=tok', answer: () => Promise.resolve(reply({ advocate: { id: 'adv_demo' } })) });
  await settle();
  const idControl = only.dom.account.children[0];
  assert.equal(within(idControl, 'acct-name').textContent, 'adv_demo');
  assert.equal(within(idControl, 'acct-avatar').textContent, 'A');
  assert.equal(within(idControl, 'acct-mail').hidden, true);
  const mixed = page({ cookie: 'nm_csrf=tok', answer: () => Promise.resolve(reply({ advocate: { name: { a: 1 }, email: 'x@y.in' } })) });
  await settle();
  assert.equal(within(mixed.dom.account.children[0], 'acct-name').textContent, 'x@y.in', 'a value that is not text is treated as not sent');
}

// If the shared initials rule did not load, the control still works and the circle stays empty.
{
  const p = page({ cookie: 'nm_csrf=tok', answer: signedInAnswer, person: false });
  await settle();
  const control = p.dom.account.children[0];
  assert.equal(within(control, 'acct-name').textContent, 'Adv. Meera Rao');
  assert.equal(within(control, 'acct-avatar').textContent, '');
  assert.equal(within(control, 'acct-toggle').disabled, false);
}

// A page with no account bar is left alone: nothing is asked and nothing is listened to.
{
  const p = page({ cookie: 'nm_csrf=tok', answer: () => assert.fail('no one is asked'), account: false });
  await settle();
  assert.equal(p.calls.length, 0);
  assert.deepEqual(Object.keys(p.document.listeners), []);
  assert.deepEqual(Object.keys(p.window.listeners), []);
}

// What the script is allowed to be. It asks two things of the server and sets no cookie and keeps nothing;
// it builds its markup as nodes, never from text.
const code = site.replace(/(^|\s)\/\/.*$/gm, '$1');   // the script without its comments, which may name what it avoids
assert.deepEqual([...new Set(everything)].sort(), ['/api/logout', '/api/session'], 'the script reaches only these two routes');
assert.deepEqual([...new Set(code.match(/'\/api\/[^']*'/g))].sort(), ["'/api/logout'", "'/api/session'"]);
assert.ok(!/document\.cookie\s*=[^=]/.test(code), 'the script reads cookies and never sets one');
assert.ok(!/localStorage|sessionStorage|indexedDB/.test(code), 'the script keeps nothing in the browser');
assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function/.test(code), 'a name is only ever text');
console.log('site account: ok');
