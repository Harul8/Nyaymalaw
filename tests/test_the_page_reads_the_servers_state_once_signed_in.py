"""The page reads the server's state once signed in, and asks a visitor's address for none of it (plan AN.52, 52a4; D207).

52a3 made the public health answer one word and put what the page shows - whether the library can be read, whether the model
is a stand-in, whether the running code is the code on disk - behind sign-in. The page asked the public address in two places:
once signed in, for the library's line, and at its start, before anyone had signed in, for the build. It now asks the signed-in
address once, after sign-in, and draws both from that one answer; at its start it asks nothing about the code, and the banner
about the code is taken down with the workspace when the sign-in screen is shown.

The shipped script's own functions run in Node, with the server and the screen stood in for. Not a browser check.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "nm/app/app.js").read_text(encoding="utf-8")

_HARNESS = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('nm/app/app.js', 'utf8');
function slice(from, to) {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start >= 0 && end > start, `the shipped script must hold: ${from}`);
  return source.slice(start, end);
}
const shipped = [
  slice('async function loadHealth() {', '/* ------------------------------------------------- the two board surfaces'),
  slice('function showBuild(', '// THE RESET LINK OPENS THIS PAGE'),
].join('\n');

// What the page is told (or the failure of the asking), and what it then shows.
async function shown(said) {
  const asked = [];
  const classes = (el) => ({ toggle(name, on) { on ? el.classes.add(name) : el.classes.delete(name); },
    add(name) { el.classes.add(name); } });
  const element = () => { const el = { textContent: '', title: '', hidden: true, className: '', classes: new Set() };
    el.classList = classes(el); return el; };
  const elements = {};
  const sandbox = {
    $: (id) => (elements[id] = elements[id] || element()),
    api: async (address) => { asked.push(address); if (said instanceof Error) throw said; return said; },
  };
  vm.runInNewContext(`${shipped}\nthis.loadHealth = loadHealth;`, sandbox);
  await sandbox.loadHealth();
  return { asked, line: elements.health, rehearsal: sandbox.$('rehearsal-warning'), build: sandbox.$('build-warning') };
}
const well = { runtime: 'ready', corpus: 'readable', rehearsal: false, code_state: 'current', steps: {}, readiness: {} };
"""

_CASES = {
    "the_signed_in_address_is_asked_once_and_the_public_one_never": r"""
(async () => {
  const page = await shown(well);
  assert.deepEqual(page.asked, ['/api/health/detail']);
  assert.match(page.line.textContent, /^Legal library available/);
  assert.equal(page.line.classes.has('bad'), false);
  assert.equal(page.rehearsal.hidden, true);
  assert.equal(page.build.hidden, true, 'code that is the code on disk shows no banner');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "the_librarys_line_is_what_readiness_measured": r"""
(async () => {
  for (const corpus of ['NOT READABLE', 'configured_unverified']) {
    const page = await shown({ ...well, corpus });
    assert.match(page.line.textContent, /^Legal library unavailable/, corpus);
    assert.equal(page.line.classes.has('bad'), true);
  }
  const chat = await shown({ ...well, corpus: 'not_connected' });
  assert.match(chat.line.textContent, /^Chat available/);
  assert.equal(chat.line.classes.has('bad'), false);
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "a_stand_in_model_is_said_from_the_servers_word_for_it": r"""
(async () => {
  assert.equal((await shown({ ...well, rehearsal: true })).rehearsal.hidden, false);
  // The provider's name is no longer told to the page; a page still reading it would hide the warning for ever.
  assert.equal((await shown({ ...well, rehearsal: false, provider: 'scripted' })).rehearsal.hidden, true);
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "older_code_is_said_in_the_servers_sentence": r"""
(async () => {
  const why = 'This server is running code that is no longer on disk. Everything it serves is the older code. Restart it.';
  const page = await shown({ ...well, code_state: 'stale', why });
  assert.equal(page.build.hidden, false);
  assert.equal(page.build.textContent, why);
  assert.equal(page.build.className, 'build-warning');
  assert.doesNotMatch(page.build.textContent, /undefined|[0-9a-f]{12}/, 'no fingerprint, and no field the server no longer sends');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "code_that_could_not_be_identified_is_not_an_all_clear": r"""
(async () => {
  const page = await shown({ ...well, code_state: 'not_assessed', why: 'the working tree could not be fingerprinted' });
  assert.equal(page.build.hidden, false);
  assert.equal(page.build.className, 'build-warning unknown');
  assert.equal(page.build.textContent, 'The build could not be identified: the working tree could not be fingerprinted.');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "an_asking_that_fails_is_not_an_all_clear_either": r"""
(async () => {
  const page = await shown(Object.assign(new Error('HTTP 503'), { status: 503 }));
  assert.match(page.line.textContent, /^Not ready/);
  assert.equal(page.line.classes.has('bad'), true);
  assert.equal(page.build.hidden, false);
  assert.equal(page.build.className, 'build-warning unknown');
  assert.match(page.build.textContent, /^The build could not be identified: HTTP 503/);
  // An asking this page abandoned (the session ended meanwhile) draws nothing.
  const left = await shown(Object.assign(new Error('obsolete'), { obsolete: true }));
  assert.equal(left.line.textContent, '');
  assert.equal(left.build.hidden, true);
})().catch((error) => { console.error(error); process.exit(1); });
""",
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_what_the_page_shows_of_the_server(case):
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required to run the shipped script"
    result = subprocess.run([node, "-e", _HARNESS + _CASES[case]], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_page_asks_a_visitors_address_for_nothing_of_the_code():
    """The public answer is one word; a page that still read the build from it would show 'could not be identified' to everyone."""
    assert "api('/api/health'" not in SCRIPT and 'api("/api/health"' not in SCRIPT
    assert SCRIPT.count("/api/health/detail") == 1, "asked in one place, once signed in"
    boot = SCRIPT[SCRIPT.index("async function boot()"):]
    boot = boot[:boot.index("\n}")]
    assert "/api/health" not in boot and "showBuild" not in boot and "checkBuild" not in boot


def test_the_banner_about_the_code_comes_down_when_the_sign_in_screen_is_shown():
    """What a signed-in advocate was told of the code is not left on the screen for whoever is at the sign-in screen next."""
    gate = SCRIPT[SCRIPT.index("function showGate(message) {"):]
    gate = gate[:gate.index("\n}")]
    assert "$('build-warning').hidden = true;" in gate
