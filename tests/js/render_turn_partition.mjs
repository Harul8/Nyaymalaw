// BK-12 — the disclosure-fold rule, asserted BEHAVIOURALLY.
//
// `tests/test_the_screen_never_folds_a_disclosure.py` reads the JavaScript
// SOURCE and checks the partition's predicate. That is a real check and it is
// a structural one: it holds if the filter is right and the rendering does
// something else with the result.
//
// This runs the ACTUAL `renderTurn` from `frontend/app.js` against a stub DOM and
// asks the question the advocate cares about — is a disclosure ever inside a
// collapsed <details>? — which no amount of reading the source can answer.
//
// NO DEPENDENCY, DELIBERATELY. jsdom would be an npm install to hold one
// rule, which is R-6 apparatus: a check that needs a toolchain nobody
// maintains is a check that stops running. The stub below is forty lines and
// implements exactly what `renderTurn` touches. If it ever needs more than
// that, the honest move is a real DOM, not a bigger stub.
//
// app.js binds listeners at load, so every id it reaches for must exist. They
// are created on demand rather than listed, because a list would need
// updating every time the page grows an element and would fail as "missing
// stub" rather than as anything meaningful.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(here, "..", "..", "frontend", "app.js"), "utf8");
// Renderer-only harness: real browser tests own application boot and sessions.
// Refuse a changed entry point rather than silently evaluating no population.
if ((app.match(/^boot\(\);$/gm) || []).length !== 1) {
  throw new Error("expected one application boot entry point");
}
const rendererSource = app.replace(/^boot\(\);$/m, "");

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
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(rendererSource, context, { filename: "frontend/app.js" });

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

if (fails.length) {
  console.error("FAIL\n  " + fails.join("\n  "));
  process.exit(1);
}
console.log(`OK  ${disclosures.length} disclosures, all in the open; `
  + `${signalCases.length} domain signals and ${uncertainSignals.length} uncertain signals visible; `
  + `${rendered.length} exact bodies; support open, audit closed`);
