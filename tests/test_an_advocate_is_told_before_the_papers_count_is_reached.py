"""An advocate is told before the count of their papers is reached (plan AN.53, 53h5b; D241: 2,000 papers, told before it is
reached).

53h5a refuses the 2,001st paper. Before that, from nine in ten (1,800), the answer to each paper sent says how many are kept and
what frees room, and the page shows it on that paper's line beside the message box - so that the refusal is never the first an
advocate hears of the count. Below it, nothing is said. Two files, said so: nm/app/api.py, which answers the upload, and
nm/app/app.js, which shows it.

Offline: the served application with a stand-in malware checker, and the shipped script's own functions run in Node; no browser.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from nm.app import documents as desk_rules
from tests.test_core_document_routes import upload
from tests.test_core_documents import Checker

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


def _holding(served, monkeypatch, count):
    texts = served.app.documents.texts
    real = texts.names
    monkeypatch.setattr(texts, "names", lambda where: tuple(
        f"doc_{number:024x}-{'c' * 64}" for number in range(count)) + real(where))


def test_it_is_told_from_nine_in_ten():
    assert desk_rules.PAPERS_KEPT_TOLD == 1800 and desk_rules.PAPERS_KEPT_MOST == 2000


def test_from_nine_in_ten_the_answer_says_how_many_are_kept_and_what_frees_room(served, monkeypatch):
    served.app.documents.checker = Checker()
    _holding(served, monkeypatch, 1_849)
    answer = upload(served.client)
    assert answer.status_code == 201, answer.text
    kept = answer.json()["kept"]
    assert (kept["papers"], kept["most"]) == (1_850, 2_000)
    assert "1,850" in kept["said"] and "2,000" in kept["said"] and "deletes its papers with it" in kept["said"]


def test_below_it_nothing_is_said(served, monkeypatch):
    served.app.documents.checker = Checker()
    _holding(served, monkeypatch, 1_798)
    answer = upload(served.client)
    assert answer.status_code == 201 and "kept" not in answer.json(), "1,799 kept: below nine in ten"


def test_the_page_keeps_what_was_said_and_shows_it_on_the_papers_line():
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required to run the shipped script"
    check = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
// The script as its lines, whichever line endings this checkout gives it (a Windows checkout has CRLF; written on Linux).
const source = fs.readFileSync('nm/app/app.js', 'utf8').replace(/\r\n/g, '\n');
function slice(from, to) {
  const start = source.indexOf(from); const end = source.indexOf(to, start);
  assert.ok(start >= 0 && end > start, from); return source.slice(start, end);
}
const shipped = slice('async function uploadAttachment(file) {', '// The AI reads what waits for it')
  + slice('function chipStatus(item) {', '\n}\n') + '\n}\n';
const said = 'NM keeps 1,850 of your papers; it keeps at most 2,000 for one advocate.';
const sandbox = { attachments: [], DOCUMENT_MAX_BYTES: 16, AUDIO_MAX_BYTES: 25, encodeURIComponent,
  messageIsFull: () => false, renderAttachments: () => {}, isRecording: () => false, releaseHeld: () => {},
  wanted: () => true, readWaiting: async () => {},
  api: async () => ({ state: 'read', waiting_for_ai: 0, kept: { papers: 1850, most: 2000, said } }),
  documentStatus: (item) => 'Read · 1 page' };
vm.runInNewContext(shipped + '\nthis.uploadAttachment = uploadAttachment; this.chipStatus = chipStatus;', sandbox);
(async () => {
  await sandbox.uploadAttachment({ name: 'note.txt', size: 3 });
  const item = sandbox.attachments[0];
  assert.equal(item.kept, said);
  assert.equal(sandbox.chipStatus(item), `Read · 1 page. ${said}`);
  assert.equal(sandbox.chipStatus({ status: 'ready', kept: '' }), 'Read · 1 page', 'nothing said, nothing added');
  assert.equal(sandbox.chipStatus({ status: 'failed', kept: said }), 'Read · 1 page', 'not on a paper that was not attached');
})().catch((error) => { console.error(error); process.exit(1); });
"""
    result = subprocess.run([node, "-e", check], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
                            check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    script = (ROOT / "nm/app/app.js").read_text(encoding="utf-8")
    assert "status.textContent = chipStatus(item);" in script, "each paper's line beside the message box is drawn by it"
