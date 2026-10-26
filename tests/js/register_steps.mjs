// REGISTRATION IN STEPS (owner decision O24; plan AN.15): the account, then privacy and AI permission,
// then the emailed code - one form still, posted once from its last step, and moving between steps
// sends nothing. Offline substitutes for the DOM; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('function markSteps(card, current) {');
const end = app.indexOf("$('reg-back').addEventListener('click'", start);
const after = app.indexOf('});', end) + 3;
assert.ok(start >= 0 && end > start && after > end, 'the registration steps must be shipped');

function el(extra = {}) {
  const classes = new Set();
  const attributes = {};
  return {
    hidden: false, value: '', dataset: {}, tabIndex: 0, focused: 0, children: [], textContent: '',
    classList: { toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)), has: (name) => classes.has(name) },
    setAttribute(name, value) { attributes[name] = value; }, removeAttribute(name) { delete attributes[name]; },
    getAttribute: (name) => attributes[name] ?? null,
    focus() { this.focused += 1; }, replaceChildren(...kids) { this.children = kids; },
    ...extra,
  };
}

function page() {
  const marks = (current) => [1, 2, 3].map((step) => {
    const mark = el();
    mark.dataset.step = String(step);
    if (step === current) mark.setAttribute('aria-current', 'step');
    return mark;
  });
  const registerMarks = marks(1);
  const confirmMarks = marks(3);
  const sections = [1, 2].map((step) => { const section = el({ hidden: step === 2 }); section.dataset.step = String(step); return section; });
  const nodes = {
    register: el({ querySelectorAll: () => registerMarks }),
    'confirm-email': el({ querySelectorAll: () => confirmMarks }),
    'reg-email': el({ reportValidity: () => true, value: 'new@chambers.in' }),
    'reg-password': el(), 'reg-password2': el(), 'reg-account-state': el(), 'reg-privacy-title': el(),
  };
  const handlers = {};
  for (const id of ['reg-continue', 'reg-back']) nodes[id] = el({ addEventListener: (name, fn) => { handlers[id] = fn; } });
  let cleared = 0;
  const context = vm.createContext({
    $: (id) => nodes[id], Number, String,
    document: { querySelectorAll: (selector) => (selector === '#register .reg-step' ? sections : []) },
    stateBlock: (kind, text) => ({ kind, text }),
    clearRegistrationPasswords: () => { cleared += 1; nodes['reg-password'].value = ''; nodes['reg-password2'].value = ''; },
  });
  vm.runInContext(app.slice(start, after), context);
  return { context, nodes, sections, registerMarks, confirmMarks, handlers, cleared: () => cleared };
}

const current = (marks) => marks.findIndex((mark) => mark.getAttribute('aria-current') === 'step') + 1;
const done = (marks) => marks.filter((mark) => mark.classList.has('done')).map((mark) => Number(mark.dataset.step));

{
  const { context, sections, registerMarks, confirmMarks } = page();
  context.showRegisterStep(2);
  assert.deepEqual(sections.map((section) => section.hidden), [true, false]);
  assert.equal(current(registerMarks), 2);
  assert.deepEqual(done(registerMarks), [1]);
  context.showRegisterStep(1);
  assert.deepEqual(sections.map((section) => section.hidden), [false, true]);
  assert.deepEqual(done(registerMarks), []);
  context.markSteps({ querySelectorAll: () => confirmMarks }, 3);
  assert.equal(current(confirmMarks), 3);
  assert.deepEqual(done(confirmMarks), [1, 2]);
}

{
  const { context } = page();
  assert.match(context.accountStepProblem('Short1!', 'Short1!'), /at least 8 characters/);
  assert.equal(context.accountStepProblem('Court-order-18', 'Court-order-19'), 'The two passwords do not match.');
  // The kinds of character are the server's to name, so a password the page cannot judge passes on.
  assert.equal(context.accountStepProblem('lowercaseonly', 'lowercaseonly'), null);
  assert.equal(context.accountStepProblem('Court-order-18', 'Court-order-18'), null);
}

{
  // A slip stays on the account step, puts both passwords away and says what to do.
  const { nodes, sections, handlers, cleared } = page();
  nodes['reg-password'].value = 'Court-order-18';
  nodes['reg-password2'].value = 'Court-order-81';
  handlers['reg-continue']();
  assert.deepEqual(sections.map((section) => section.hidden), [false, true]);
  assert.equal(cleared(), 1);
  assert.equal(nodes['reg-password'].value, '');
  assert.equal(nodes['reg-account-state'].children[0].text,
    'The two passwords do not match. Type it twice again.');
  assert.equal(nodes['reg-password'].focused, 1);
}

{
  // Good details move to the privacy step, which takes the focus; Back returns, keeping what was typed.
  const { nodes, sections, registerMarks, handlers, cleared } = page();
  nodes['reg-password'].value = nodes['reg-password2'].value = 'Court-order-18';
  handlers['reg-continue']();
  assert.deepEqual(sections.map((section) => section.hidden), [true, false]);
  assert.equal(current(registerMarks), 2);
  assert.equal(nodes['reg-privacy-title'].tabIndex, -1);
  assert.equal(nodes['reg-privacy-title'].focused, 1);
  assert.equal(cleared(), 0);
  handlers['reg-back']();
  assert.deepEqual(sections.map((section) => section.hidden), [false, true]);
  assert.equal(nodes['reg-password'].value, 'Court-order-18');
}

{
  // An email the browser refuses never leaves the account step.
  const { nodes, sections, handlers } = page();
  nodes['reg-email'].reportValidity = () => false;
  nodes['reg-password'].value = nodes['reg-password2'].value = 'Court-order-18';
  handlers['reg-continue']();
  assert.deepEqual(sections.map((section) => section.hidden), [false, true]);
}

// The card opens on its first step; the code is the third; the last step says the account is ready,
// with its trial, and whether research can start.
assert.ok(app.includes("    showRegisterStep(1);\n    loadAccountCapabilities();"));
assert.ok(app.includes("markSteps($('confirm-email'), 3);"));
assert.ok(app.includes("showOutcome('good', 'Your account is ready'"));
assert.ok(app.includes("'Your trial allowance is ready: 100% of it is left.'"));
console.log('register steps: ok');
