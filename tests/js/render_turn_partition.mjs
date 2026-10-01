// BK-12 — the disclosure-fold rule, asserted BEHAVIOURALLY.
//
// `tests/test_the_screen_never_folds_a_disclosure.py` reads the JavaScript
// SOURCE and checks the partition's predicate. That is a real check and it is
// a structural one: it holds if the filter is right and the rendering does
// something else with the result.
//
// This runs the ACTUAL `renderTurn` from `nm/app/app.js` against a stub DOM and
// asks the question the advocate cares about — is a disclosure ever inside a
// collapsed <details>? — which no amount of reading the source can answer.
//
// NO DEPENDENCY, DELIBERATELY. jsdom would be an npm install to hold one
// rule, which is R-6 apparatus: a check that needs a toolchain nobody
// maintains is a check that stops running. The stub below is forty lines and
// implements exactly what `renderTurn` touches. If it ever needs more than
// that, the honest move is a real DOM, not a bigger stub.
//
// Evaluate the actual renderer and its text helpers, without booting the app's
// unrelated session, preferences and network controllers.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(here, "..", "..", "nm", "app", "app.js"), "utf8");
const between = (start, end) => {
  const a = app.indexOf(start);
  const b = app.indexOf(end, a + start.length);
  if (a < 0 || b < 0 || b <= a) throw new Error(`renderer boundary moved: ${start}`);
  return app.slice(a, b);
};
const rendererSource = between("function appendReplyBody(", "const REPLY_ICONS")
  + "\n" + between("async function restoreConversation(", "function restoredTurn(")
  + "\n" + between("function restoredTurn(turn) {", "function renderBriefing(")
  + "\n" + between("function renderTurn(entry) {", "function showConversationFromStart()")
  + "\n" + between("function showConversationFromStart()", "function repaint()");

// ---------------------------------------------------------- the stub DOM ---
function el(tag) {
  const node = {
    tagName: tag.toUpperCase(),
    className: "",
    children: [],
    _text: "",
    open: false,
    dataset: {},
    style: {},
    hidden: false,
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() {
      return this._text + this.children.map((c) => c.textContent).join("");
    },
    set innerHTML(v) { this._text = String(v); },
    get innerHTML() { return this._text; },
    append(...kids) { for (const k of kids) this.children.push(k); },
    appendChild(k) { this.children.push(k); return k; },
    replaceChildren(...kids) { this.children = kids; },
    addEventListener() {},
    // A THROWAWAY NODE FOR ANY SELECTOR. The metrics row sets `innerHTML`
    // and then reaches back into it with `querySelector('.v')`, which a stub
    // that does not parse HTML cannot answer. Returning a scratch node lets
    // that code run; it is safe here because every assertion below walks
    // `children` rather than querying, so nothing under test can be masked
    // by it. The day an assertion wants a selector, this stub is the wrong
    // tool and a real DOM is the right one.
    querySelector() { return el("span"); },
    querySelectorAll() { return []; },
    setAttribute() {},
    removeAttribute() {},
    closest() { return null; },
    focus() {},
  };
  return node;
}

const byId = new Map();
const document = {
  createElement: el,
  createTextNode: (t) => Object.assign(el("#text"), { _text: String(t) }),
  // Created on demand: app.js reaches for many ids at load and a missing one
  // would fail as "stub incomplete" rather than as anything about the rule.
  getElementById: (id) => {
    if (!byId.has(id)) byId.set(id, el("div"));
    return byId.get(id);
  },
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  body: el("body"),
};

const context = {
  document,
  window: { location: { hash: '', reload() {} }, addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  console,
  setTimeout,
  clearTimeout,
  navigator: { userAgent: "node" },
  // The responsive warning-height observer is armed at page load. This
  // tree-only harness deliberately does not simulate layout or invoke its
  // callback; the three real-browser widths measure that separate boundary.
  ResizeObserver: class { observe() {} },
  state: { matterId: null, ended: false, advocate: null },
  renderOpeningNote: () => el("div"),
  renderBoardNote: () => null,
  stateBlock: (_kind, message) => Object.assign(el("div"), { textContent: message }),
  replyFooter: (_entry, copyText) => Object.assign(el("div"), { copyText }),
  openSourceReader() {},
  $: id => document.getElementById(id),
  withOpeningNotes: turns => turns,
  reconcileIntent() {},
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(rendererSource, context, { filename: "nm/app/app.js" });

// ------------------------------------------------------------- the facts ---
// Python supplies EVERY actual Signal member via the domain enum. No copied
// JS list can quietly stop this population at today's six loud signals.
const signalCases = JSON.parse(process.argv[2] || "null");
if (!Array.isArray(signalCases) || !signalCases.length
    || new Set(signalCases.map(row => row.signal)).size !== signalCases.length
    || signalCases.some(row => !row.signal || row.signal === "none" || row.kind !== "ground")) {
  console.error("FAIL: a nonempty, distinct domain Signal population is required");
  process.exit(1);
}
const mk = (kind, text, extra = {}) => ({
  kind, text, signal: "none", disclosure: false, refs: [], ...extra,
});
const uncertainSignals = [
  mk("ground", "Renderer-only absent signal.", { signal: undefined, section: "risk" }),
  mk("ground", "Renderer-only null signal.", { signal: null, section: "risk" }),
  mk("ground", "Renderer-only unfamiliar signal.", { signal: "future_signal", section: "risk" }),
];

const entry = {
  brief: "We act for the plaintiff at Hyderabad.",
  answer: {
    metrics: {
      gates_fired: [], outcome: "ok", latency_ms: 1, llm_calls: 1,
      tokens: { in: 1, out: 1 }, cost_usd: 0, violations: [],
      tier_downgrades: [],
    },
    elements: [
      mk("action", "File the suit."),
      mk("finding", "Limitation: three years."),
      mk("ground", "A retrieved span, which is support and may fold."),
      mk("ground", "Another retrieved span."),
      mk("ground", "Screens on this matter, none of which has run.",
         { disclosure: true }),
      mk("ground", "I looked for adverse facts and found none.",
         { disclosure: true }),
      ...signalCases,
      ...uncertainSignals,
    ],
  },
};

const turn = context.renderTurn(entry);

// ------------------------------------------------------------ the checks ---
const fails = [];

function walk(node, inFold, out) {
  const nowInFold = inFold || node.tagName === "DETAILS";
  if (String(node.className).includes("disclosure")) {
    out.push({ text: node.textContent.slice(0, 60), folded: nowInFold });
  }
  for (const kid of node.children) walk(kid, nowInFold, out);
}

const disclosures = [];
walk(turn, false, disclosures);

if (disclosures.length !== 2) {
  fails.push(`expected 2 disclosure elements, rendered ${disclosures.length}`);
}
for (const d of disclosures) {
  if (d.folded) {
    fails.push(`A DISCLOSURE IS INSIDE A FOLD: ${d.text}`);
  }
}

// The support fold starts open and holds exactly the plain grounds.
const folds = [];
(function findFolds(node) {
  if (node.tagName === "DETAILS") folds.push(node);
  for (const kid of node.children) findFolds(kid);
})(turn);

// TWO FOLDS SINCE BK-37, and counting them was the wrong check the moment a
// second one was legitimate. The support fold holds plain grounds; the audit
// fold holds the gate rows and the trace (J-7). The rule that matters is not
// HOW MANY folds there are -- it is that no disclosure is inside ANY of them,
// which is what this now asserts.
//
// Counting would have failed on a correct change and passed on the defect it
// was written for, if that defect ever arrived alongside a fold being removed.
const support = folds.filter((f) => String(f.className).includes("support"));
const audit = folds.filter((f) => String(f.className).includes("audit"));

if (support.length !== 1) {
  fails.push(`expected exactly 1 support fold for the two plain grounds, rendered ${support.length}`);
}
if (audit.length > 1) {
  fails.push(`expected at most 1 audit fold, rendered ${audit.length}`);
}
for (const fold of folds) {
  if (Boolean(fold.open) !== support.includes(fold)) {
    fails.push(`wrong default visibility for the ${fold.className} fold`);
  }
  const inside = [];
  walk(fold, true, inside);
  if (inside.length) {
    fails.push(`${inside.length} disclosure(s) inside the ${fold.className} fold`);
  }
}

// Inspect original body bytes, not a CSS signal class the faulty branch could
// drop. Every source element is accounted for exactly once in the actual tree.
const rendered = [];
(function findElements(node, insideFold = false) {
  const folded = insideFold || node.tagName === "DETAILS";
  if (String(node.className).split(/\s+/).includes("el")) {
    const bodies = node.children.filter(child => child.className === "body");
    if (bodies.length !== 1) fails.push("an answer element lost its unique body");
    else rendered.push({text: bodies[0].textContent, folded});
  }
  for (const kid of node.children) findElements(kid, folded);
})(turn);
if (rendered.length !== entry.answer.elements.length) {
  fails.push(`expected ${entry.answer.elements.length} elements, rendered ${rendered.length}`);
}
for (const source of entry.answer.elements) {
  const matches = rendered.filter(row => row.text === source.text);
  if (matches.length !== 1) {
    fails.push(`expected one exact rendered body, got ${matches.length}: ${source.text}`);
    continue;
  }
  const ordinarySupport = source.kind === "ground" && source.disclosure === false
    && source.signal === "none";
  if (matches[0].folded !== ordinarySupport) {
    fails.push(`wrong visibility for signal=${String(source.signal)}: ${source.text}`);
  }
}
if (rendered.filter(row => row.folded).length !== 2) {
  fails.push("the fold must contain exactly the two plain unsignalled grounds");
}

// The advocate's own words are set apart.
let bubble = false;
(function findBubble(node) {
  if (String(node.className).includes("brief")) bubble = true;
  for (const kid of node.children) findBubble(kid);
})(turn);
if (!bubble) fails.push("the advocate's own words are not set apart");

const inputOnly = context.renderTurn({
  brief: 'Saved instructions', state: 'input_only', turnId: 'withheld-input',
  error: 'Answer withheld', refusal: {withheld_by: ['G-QUOTE'], why: 'Unsupported quotation'}
});
if (!inputOnly.textContent.includes('Your brief is saved.')
    || !inputOnly.textContent.includes('no new conclusions were saved')
    || inputOnly.textContent.includes('brief was NOT saved')) {
  fails.push('input-only persistence is presented as either a full save or a lost brief');
}

// A source label embedded in prose is linked in place and copied once. History
// uses the same restored-turn projection and renderer as the open conversation.
const label = 'Specific Relief Act s.6';
const locator = 'synthetic::sra::6::';
const prose = `**Eastern gate**: The passage is ${label}.`;
const start = prose.indexOf(label);
const source = { label, locator, text: 'Synthetic retrieved passage.' };
const citedElement = mk('ground', 'Synthetic retrieved passage.',
  { refs: [locator], source });
const composed = [{ text: prose, passage: null, carries: null,
  cites: [[start, start + label.length, 0]] }];
const saved = { committed: true, release_state: 'released', message: 'Open the eastern gate.',
  matter_id: 'matter_a', turn_id: 'turn_a', elements: [citedElement], composed,
  at: '2026-09-30T10:00:00Z' };
const flat = node => [node, ...node.children.flatMap(flat)];
for (const entry of [{ brief: saved.message, answer: saved }, context.restoredTurn(saved)]) {
  const rendered = context.renderTurn(entry);
  const body = flat(rendered).find(node => node.className === 'body');
  const links = flat(body).filter(node => node.className === 'citation-link');
  const copy = flat(rendered).find(node => typeof node.copyText === 'function')?.copyText();
  if (body?.textContent !== prose.replaceAll('**', '') || links.length !== 1
      || links[0]?.textContent !== label) {
    fails.push('the saved inline citation was not rendered in the reply as served');
  }
  if (!copy?.includes(label) || copy.includes(locator) || copy.includes('**')) {
    fails.push('the copied reply differs from its visible inline citation');
  }
}
const boldProse = `The passage is **${label}**.`;
const boldStart = boldProse.indexOf(label);
const boldEntry = { brief: saved.message, answer: { ...saved, composed: [{
  text: boldProse, passage: null, carries: null,
  cites: [[boldStart, boldStart + label.length, 0]],
}] } };
const boldReply = context.renderTurn(boldEntry);
const strong = flat(boldReply).find(node => node.tagName === 'STRONG');
if (strong?.textContent !== label || !flat(strong).some(node => node.className === 'citation-link')
    || boldReply.textContent.includes('**')) {
  fails.push('a citation inside bold prose broke the saved text or its link');
}
const damaged = { brief: saved.message, answer: { ...saved, composed: [{
  text: prose, passage: null, carries: null, cites: [[-1, 500, 0], null],
}] } };
const damagedReply = context.renderTurn(damaged);
const damagedBody = flat(damagedReply).find(node => node.className === 'body');
if (damagedBody?.textContent !== prose.replaceAll('**', '')
    || flat(damagedBody).some(node => node.className === 'citation-link')) {
  fails.push('bad saved citation metadata changed or hid the reply words');
}

// Reopening a saved matter restores the whole transcript in record order and
// starts at the first turn, even when the conversation is taller than its pane.
const thread = document.getElementById('thread');
thread.scrollHeight = 900; thread.clientHeight = 200; thread.scrollTop = 700;
context.state.railGeneration = 1;
context.repaint = () => thread.replaceChildren(...context.state.turns.map(context.renderTurn));
const second = { ...saved, message: 'The next instruction.', turn_id: 'turn_b',
  composed: [{ text: 'The second reply.', passage: null, carries: null, cites: [] }] };
context.api = async path => {
  if (path !== '/api/matters/matter_a/transcript') throw Error(`wrong transcript: ${path}`);
  return { turns: [saved, second], opening_changes: [] };
};
await context.restoreConversation('matter_a', 1);
const bubbles = flat(thread).filter(node => node.className === 'brief').map(node => node.textContent);
if (JSON.stringify(bubbles) !== JSON.stringify([saved.message, second.message])
    || thread.scrollTop !== 0 || document.getElementById('jump-latest').hidden) {
  fails.push('reopening the matter did not show its saved conversation from first to last');
}

if (fails.length) {
  console.error("FAIL\n  " + fails.join("\n  "));
  process.exit(1);
}
console.log(`OK  ${disclosures.length} disclosures, all in the open; `
  + `${signalCases.length} domain signals and ${uncertainSignals.length} uncertain signals visible; `
  + `${rendered.length} exact bodies; support open, audit closed`);
