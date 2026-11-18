// THE BOARD AND THE READING PANE'S PLACE ON THE PAGE. The board beside the conversation has one host, and the reading pane and the
// source reader open as full-height panels on the right that scroll inside themselves. The earlier matters' board and its own
// dispute reader, which this checked as well, were deleted with the screens of a matter saved before conversations (plan AN.57,
// D292); what the conversation's board draws is pinned by board_and_pane_frozen.mjs.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(here, '..', '..', 'nm', 'app', 'app.js'), 'utf8');
const html = readFileSync(join(here, '..', '..', 'nm', 'app', 'index.html'), 'utf8');
const css = readFileSync(join(here, '..', '..', 'nm', 'app', 'app.css'), 'utf8');
assert.equal((html.match(/id="matter-board"/g) || []).length, 1);
assert.equal((html.match(/id="matter-board-body"/g) || []).length, 1);
const sourceMarkup = html.match(/<dialog id="brain-source-reader"[\s\S]*?<\/dialog>/)?.[0];
// The design's pane (18 Oct 2026): Back, its name and Close in a bar, then what is open.
assert.match(sourceMarkup, /<header[^>]*>[\s\S]*?id="brain-source-back"[\s\S]*?id="brain-source-close"[\s\S]*?<\/header>[\s\S]*?id="brain-source-kind"[\s\S]*?id="brain-source-title"[\s\S]*?<div id="brain-source-body"/);
const paneStyle = css.match(/#brain-source-reader\s*\{([^}]+)\}/)?.[1];
const paneBodyStyle = css.match(/\.dispute-reader-body\s*\{([^}]+)\}/)?.[1];
const sourceStyle = css.match(/#source-reader\s*\{([^}]+)\}/)?.[1];
assert.match(paneStyle, /overflow:\s*hidden/);
assert.match(paneBodyStyle, /overflow-y:\s*auto/);
assert.match(paneBodyStyle, /min-height:\s*0/);
for (const style of [paneStyle, sourceStyle]) {
  assert.match(style, /position:\s*fixed/);
  assert.match(style, /inset:\s*0\s+0\s+0\s+auto/);
  assert.match(style, /margin:\s*0/);
  assert.match(style, /height:\s*100dvh/);
  assert.match(style, /max-height:\s*100dvh/);
}
assert.match(css, /#brain-source-reader\[open\]\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column/);
assert.match(css, /\.source-reader-head\s*\{[^}]*flex:\s*none/);
assert.match(css, /\.source-reader-body\s*\{[^}]*overflow-y:\s*auto/);

// The earlier matters' board, its dispute reader and the screen that opened them are not on the page.
assert.ok(!html.includes('id="dispute-reader"'));
for (const gone of ['function renderMatterBoard(', 'function renderDisputeBoard(', 'function openDisputeReader(',
  'async function showThreadBoard(']) {
  assert.ok(!app.includes(gone), gone);
}
console.log('dispute_board: ok');
