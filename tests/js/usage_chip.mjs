// HOW MUCH USAGE IS LEFT (owner decisions O21-O24; plans P53, AN.17): the chip in the top bar and the
// notice above the message box, as the page shows what the server says - the percentage left, the
// notice due and the owner's words at nothing left - and sending paused once nothing is left.
// Offline substitutes for the DOM and the network; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('function usageUsedUp() {');
const end = app.indexOf("$('usage-notice-close').addEventListener", start);
assert.ok(start >= 0 && end > start, 'the usage chip and notice must be shipped');

function page() {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) {
      const parts = new Map();
      const classes = new Set();
      nodes.set(id, {
        hidden: id === 'usage-notice' || id === 'usage-chip', textContent: '', attributes: {},
        get className() { return [...classes].join(' '); },
        set className(value) { classes.clear(); String(value).split(' ').filter(Boolean).forEach((c) => classes.add(c)); },
        classList: { contains: (c) => classes.has(c) },
        setAttribute(name, value) { this.attributes[name] = value; },
        querySelector(selector) {
          if (!parts.has(selector)) parts.set(selector, { textContent: '', style: {} });
          return parts.get(selector);
        },
      });
    }
    return nodes.get(id);
  };
  const posted = [];
  const timers = [];
  const context = vm.createContext({
    $: node, state: { advocate: 'advocate@chambers.in' }, usage: null, usageRequest: 0, usageNoticeTimer: null,
    Math, JSON, updates: 0,
    updateWorkspace() { context.updates += 1; },
    setTimeout: (fn, ms) => { timers.push(ms); return timers.length; }, clearTimeout() {},
    api: async (path, options) => { posted.push([path, options && JSON.parse(options.body)]); return {}; },
  });
  vm.runInContext(app.slice(start, end), context);
  return { context, node, posted, timers };
}

const LIMIT = 'You have run out of your usage limits. Please upgrade to continue accessing NM.';

{
  const { context, node, posted } = page();
  context.showUsage({ plan: 'Trial', left: 100, notice: null, limit: null });
  const chip = node('usage-chip');
  assert.equal(chip.hidden, false);
  assert.equal(chip.className, 'usage');
  assert.equal(chip.querySelector('.usage-left').textContent, '100% left');
  assert.equal(chip.querySelector('.usage-plan').textContent, 'Trial');
  assert.equal(chip.querySelector('.usage-meter i').style.width, '100%');
  assert.equal(chip.attributes['aria-label'], 'Trial allowance, 100% left. See plans.');
  assert.equal(node('usage-notice').hidden, true, 'no notice above 50%');
  assert.equal(posted.length, 0);
  assert.equal(context.usageUsedUp(), false);
}

{
  // 50% once, closing itself after the time the server gives; recorded as seen.
  const { context, node, posted, timers } = page();
  context.showUsage({ plan: 'Trial', left: 47, notice: { step: 50, closes_after_seconds: 600 }, limit: null });
  const notice = node('usage-notice');
  assert.equal(notice.hidden, false);
  assert.equal(notice.className, 'usage-notice info');
  assert.equal(notice.attributes.role, 'status');
  assert.equal(node('usage-notice-title').textContent, '47% of your trial allowance is left.');
  assert.equal(node('usage-notice-text').textContent, '');
  assert.equal(node('usage-notice-close').hidden, false);
  assert.deepEqual(timers, [600000]);
  assert.deepEqual(posted, [['/api/usage/notice', { step: 50 }]]);
  assert.equal(node('usage-chip').className, 'usage');
}

{
  const { context, node } = page();
  context.showUsage({ plan: 'Trial', left: 25, notice: { step: 25, closes_after_seconds: 600 }, limit: null });
  assert.equal(node('usage-notice').className, 'usage-notice warn');
  assert.equal(node('usage-notice-text').textContent, 'See plans to keep going.');
  assert.equal(node('usage-chip').className, 'usage low', 'amber at 25% or less');
}

{
  // From 10% down: every 1%, staying until closed, announced.
  const { context, node, timers } = page();
  context.showUsage({ plan: 'Trial', left: 9, notice: { step: 9, closes_after_seconds: null }, limit: null });
  assert.equal(node('usage-notice').className, 'usage-notice warn');
  assert.equal(node('usage-notice').attributes.role, 'alert');
  assert.equal(node('usage-notice-text').textContent,
    'When it runs out, NM cannot research or answer until you upgrade.');
  assert.deepEqual(timers, [], 'it stays until the advocate closes it');
  assert.equal(node('usage-chip').className, 'usage crit', 'darker with the warning mark at 10% or less');
}

{
  // Nothing left: the owner's words from the server, no close button, sending paused; an allowance
  // that grows again lifts it.
  const { context, node } = page();
  context.showUsage({ plan: 'Trial', left: 0, notice: null, limit: LIMIT });
  assert.equal(node('usage-notice').className, 'usage-notice limit');
  assert.equal(node('usage-notice-title').textContent, LIMIT);
  assert.equal(node('usage-notice-close').hidden, true);
  assert.equal(node('usage-chip').className, 'usage out');
  assert.equal(node('usage-chip').querySelector('.usage-left').textContent, 'No usage left');
  assert.equal(context.usageUsedUp(), true);
  assert.ok(context.updates >= 1, 'the send button is recomputed');
  context.showUsage({ plan: 'Trial', left: 95, notice: null, limit: null });
  assert.equal(node('usage-notice').hidden, true);
  assert.equal(context.usageUsedUp(), false);
  context.forgetUsage();
  assert.equal(node('usage-chip').hidden, true);
  assert.equal(context.usage, null);
}

// The composer's Send: once nothing is left, nothing is sent and the words stay in the box.
{
  const wireStart = app.indexOf("$('composer').addEventListener('submit',");
  const wireEnd = app.indexOf("$('message').addEventListener('keydown',", wireStart);
  const handlers = new Map();
  const sent = [];
  let checked = 0;
  const box = { value: 'Please check the notice.' };
  const context = vm.createContext({
    $: (id) => (id === 'message' ? box : { addEventListener: (name, fn) => handlers.set(name, fn) }),
    activeDelivery: null, queueAddition() {}, send: (text) => sent.push(text),
    usageUsedUp: () => true, loadUsage: () => { checked += 1; },
  });
  vm.runInContext(app.slice(wireStart, wireEnd), context);
  handlers.get('submit')({ preventDefault() {} });
  assert.deepEqual(sent, []);
  assert.equal(box.value, 'Please check the notice.');
  assert.equal(checked, 1, 'the allowance is asked again, in case it grew');
}

// The send button pauses with it.
assert.ok(app.includes("$('send').disabled = Boolean(activeDelivery || (state.matterId && !state.matterReady) || usageUsedUp());"));
// No price is shown in Dictation (O21, O22).
assert.ok(!app.includes('a minute.`'), 'Dictation no longer shows a price');
console.log('usage chip: ok');
