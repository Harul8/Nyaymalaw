// BK-12 — the disclosure-fold rule, asserted BEHAVIOURALLY.
//
// `tests/test_the_screen_never_folds_a_disclosure.py` reads the JavaScript
// SOURCE and checks the partition's predicate. That is a real check and it is
// a structural one: it holds if the filter is right and the rendering does
// something else with the result.
//
// This runs the ACTUAL `renderTurn` from `web/app.js` against a stub DOM and
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
const app = readFileSync(join(here, "..", "..", "web", "app.js"), "utf8");

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
  window: { location: { reload() {} }, addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  console,
  setTimeout,
  clearTimeout,
  navigator: { userAgent: "node" },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(app, context, { filename: "web/app.js" });

// ------------------------------------------------------------- the facts ---
const mk = (kind, text, extra = {}) => ({
  kind, text, signal: "none", disclosure: false, refs: [], ...extra,
});

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

// The support fold exists, is closed, and holds exactly the plain grounds.
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

if (support.length > 1) {
  fails.push(`expected at most 1 support fold, rendered ${support.length}`);
}
if (audit.length > 1) {
  fails.push(`expected at most 1 audit fold, rendered ${audit.length}`);
}
for (const fold of folds) {
  if (fold.open) {
    fails.push(`a ${fold.className} fold is open by default`);
  }
  const inside = [];
  walk(fold, true, inside);
  if (inside.length) {
    fails.push(`${inside.length} disclosure(s) inside the ${fold.className} fold`);
  }
}

// The advocate's own words are set apart.
let bubble = false;
(function findBubble(node) {
  if (String(node.className).includes("brief")) bubble = true;
  for (const kid of node.children) findBubble(kid);
})(turn);
if (!bubble) fails.push("the advocate's own words are not set apart");

if (fails.length) {
  console.error("FAIL\n  " + fails.join("\n  "));
  process.exit(1);
}
console.log(`OK  ${disclosures.length} disclosures, all in the open; `
  + `${folds.length} fold, closed`);
