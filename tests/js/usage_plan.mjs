// USAGE AND PLAN (owner decisions O21-O24, O26; plans P53, AN.17, AN.19): the window over the workspace -
// what it shows of the server's word, how it opens (the chip, a notice's See plans, the person menu),
// that a click with a modifier key keeps the link, that a slow or failed read says so, and that
// sign-out puts the account's usage away. Offline substitutes for the DOM and the network; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('function showUsagePlan(seen) {');
const end = app.indexOf("$('usage-plan-dialog').addEventListener('close'", start);
assert.ok(start >= 0 && end > start, 'the Usage and plan window must be shipped');
const after = app.indexOf('\n', end) + 1;

const TRIAL = 'You are on the trial. Choose a plan below when you want more.';
const LIMIT = 'You have run out of your usage limits. Please upgrade to continue accessing NM.';

function page({ usage = null, reply, advocate = 'advocate@chambers.in' } = {}) {
  const nodes = new Map();
  const listeners = {};
  const node = (id) => {
    if (!nodes.has(id)) {
      const element = {
        textContent: '', style: {}, dataset: {}, open: false, shown: 0,
        addEventListener(name, fn) { listeners[`${id}:${name}`] = fn; },
        showModal() { this.open = true; this.shown += 1; },
        close() { this.open = false; },
      };
      element.parentElement = { dataset: {} };
      nodes.set(id, element);
    }
    return nodes.get(id);
  };
  const log = { menu: [], shown: [], requests: 0 };
  const context = vm.createContext({
    $: node, Math, Error, usage, usagePlanRequest: 0, TRIAL_NOTE: TRIAL,
    state: { advocate },
    usageLevel: (left) => (left <= 0 ? 'out' : left <= 10 ? 'crit' : left <= 25 ? 'low' : ''),
    setAccountMenu: (open) => log.menu.push(open),
    showUsage(seen) { log.shown.push(seen); context.usage = seen; context.showUsagePlan(seen); },
    api: async (path) => {
      log.requests += 1;
      assert.equal(path, '/api/usage');
      const answer = typeof reply === 'function' ? await reply() : reply;
      if (answer instanceof Error) throw answer;
      return answer;
    },
  });
  vm.runInContext(app.slice(start, after), context);
  return { context, node, listeners, log };
}

const trial = (left, extra = {}) => ({ plan: 'Trial', left, notice: null, limit: left <= 0 ? LIMIT : null, ...extra });

{
  // What the server says is what the window shows: the name, the percentage, the meter, the sentence.
  const { context, node } = page();
  context.showUsagePlan(trial(57));
  assert.equal(node('usage-plan-allowance').textContent, 'Trial allowance');
  assert.equal(node('usage-plan-left').textContent, '57%');
  assert.equal(node('usage-plan-fill').style.width, '57%');
  assert.equal(node('usage-plan-fill').parentElement.dataset.level, '');
  assert.equal(node('usage-plan-name').textContent, 'Trial');
  assert.equal(node('usage-plan-note').textContent, TRIAL);

  context.showUsagePlan(trial(25));
  assert.equal(node('usage-plan-fill').parentElement.dataset.level, 'low');
  context.showUsagePlan(trial(9));
  assert.equal(node('usage-plan-fill').parentElement.dataset.level, 'crit');
  assert.equal(node('usage-plan-note').textContent, TRIAL);

  // Nothing left: the owner's words from the server in place of the trial sentence.
  context.showUsagePlan(trial(0));
  assert.equal(node('usage-plan-left').textContent, '0%');
  assert.equal(node('usage-plan-fill').style.width, '0%');
  assert.equal(node('usage-plan-fill').parentElement.dataset.level, 'out');
  assert.equal(node('usage-plan-note').textContent, LIMIT);

  // A figure outside 0-100 never draws outside the meter.
  context.showUsagePlan(trial(140));
  assert.equal(node('usage-plan-fill').style.width, '100%');
}

{
  // Opening shows what is known at once, then the server's current word.
  const { context, node, log } = page({ usage: trial(57), reply: trial(49) });
  await context.openUsagePlan();
  assert.deepEqual(log.menu, [false]);
  assert.equal(node('usage-plan-dialog').open, true);
  assert.equal(node('usage-plan-dialog').shown, 1);
  assert.equal(log.requests, 1);
  assert.equal(node('usage-plan-left').textContent, '49%');
  assert.equal(node('usage-plan-status').textContent, '');
  assert.equal(log.shown.length, 1, 'the chip, the notice and Send are told too');
}

{
  // Nothing known yet: it says it is checking, and the window is open meanwhile.
  let release;
  const { context, node } = page({ reply: () => new Promise((resolve) => { release = () => resolve(trial(80)); }) });
  const opening = context.openUsagePlan();
  assert.equal(node('usage-plan-status').textContent, 'Checking your usage…');
  assert.equal(node('usage-plan-dialog').open, true);
  release();
  await opening;
  assert.equal(node('usage-plan-status').textContent, '');
  assert.equal(node('usage-plan-left').textContent, '80%');
}

{
  // A read that fails says so and keeps what was last known; it never shows an invented figure.
  const { context, node } = page({ usage: trial(57), reply: Object.assign(new Error('The server did not answer.'), { status: 503 }) });
  await context.openUsagePlan();
  assert.equal(node('usage-plan-status').textContent, 'Your usage could not be read just now. The server did not answer.');
  assert.equal(node('usage-plan-left').textContent, '57%');
}

{
  // An answer that arrives after the window was closed (or reopened) is not shown.
  let release;
  const { context, node, log, listeners } = page({ reply: () => new Promise((resolve) => { release = () => resolve(trial(33)); }) });
  const opening = context.openUsagePlan();
  listeners['usage-plan-dialog:close']();
  release();
  await opening;
  assert.equal(log.shown.length, 0);
  assert.notEqual(node('usage-plan-left').textContent, '33%');
}

{
  // An answer that arrives after sign-out is not shown.
  let release;
  const { context, log } = page({ reply: () => new Promise((resolve) => { release = () => resolve(trial(33)); }) });
  const opening = context.openUsagePlan();
  context.state.advocate = null;
  release();
  await opening;
  assert.equal(log.shown.length, 0);
}

{
  // Sign-out puts the account's usage away: nothing of it stays in the window.
  const { context, node } = page();
  context.showUsagePlan(trial(9));
  context.resetUsagePlan();
  assert.equal(node('usage-plan-left').textContent, '—');
  assert.equal(node('usage-plan-fill').style.width, '0');
  assert.equal(node('usage-plan-fill').parentElement.dataset.level, '');
  assert.equal(node('usage-plan-note').textContent, TRIAL);
  assert.equal(node('usage-plan-status').textContent, '');
}

{
  // The chip, a notice's See plans and the person menu open it; a click with a modifier key, or not
  // with the main button, keeps the link to the public Plans page.
  const { listeners, log, node } = page({ reply: trial(50) });
  const click = (extra = {}) => ({ button: 0, defaultPrevented: false, prevented: false,
    preventDefault() { this.prevented = true; }, ...extra });
  const opened = async (handler, event) => { const before = log.requests; handler(event); await Promise.resolve(); return log.requests > before; };

  const plain = click();
  assert.equal(await opened(listeners['usage-chip:click'], plain), true);
  assert.equal(plain.prevented, true);
  for (const extra of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }, { defaultPrevented: true }]) {
    const event = click(extra);
    assert.equal(await opened(listeners['usage-chip:click'], event), false, JSON.stringify(extra));
    assert.equal(event.prevented, false, JSON.stringify(extra));
  }

  const see = click({ target: { closest: (selector) => (selector === '.usage-notice-plans' ? {} : null) } });
  assert.equal(await opened(listeners['usage-notice:click'], see), true);
  assert.equal(see.prevented, true);
  const elsewhere = click({ target: { closest: () => null } });
  assert.equal(await opened(listeners['usage-notice:click'], elsewhere), false);
  assert.equal(elsewhere.prevented, false);

  assert.equal(await opened(listeners['usage-plan:click'], click()), true);
  node('usage-plan-dialog').open = true;
  listeners['usage-plan-close:click']();
  assert.equal(node('usage-plan-dialog').open, false);
}

// Sign-out closes the window; the state it needs is declared where boot() cannot reach it first.
const privileged = app.slice(app.indexOf('function clearPrivileged() {'), app.indexOf('/* ------------------------------------------------------- idle sign-out --- */'));
assert.ok(privileged.includes("$('usage-plan-dialog').close();"), 'sign-out must close the window');
assert.ok(privileged.includes('forgetUsage();'));
const forgotten = app.slice(app.indexOf('function forgetUsage() {'), app.indexOf("$('usage-notice-close').addEventListener"));
assert.ok(forgotten.includes('resetUsagePlan();'), 'forgetting the usage puts the window away too');
assert.ok(app.indexOf('let usagePlanRequest = 0;') < app.indexOf('boot();'), 'its state is declared before boot()');
assert.ok(app.indexOf("const TRIAL_NOTE =") < app.indexOf('boot();'));
console.log('usage plan: ok');
