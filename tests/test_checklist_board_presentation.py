"""The shipped matter board distinguishes stale legal relevance from missing answers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]

_RENDERER_CHECK = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('nm/app/app.js', 'utf8');
const start = source.indexOf('const REQUIREMENT_MARK = ');
const end = source.indexOf('\nfunction renderOpeningBrief(', start);
assert.ok(start >= 0 && end > start, 'the shipped checklist renderer must be present');

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.text = ''; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(' '); }
  appendChild(child) { this.children.push(child); }
  setAttribute() {}
}
const sandbox = {document: {createElement: tag => new Element(tag)}};
vm.runInNewContext(source.slice(start, end), sandbox);

function board(overrides) {
  const parent = new Element('section');
  sandbox.renderRequirements(parent, {
    requirements_state: 'established',
    requirements: [{
      state: 'held',
      applicability_state: 'review_required',
      need: 'Check notice',
      source: 'Admitted statute',
      span: 'Passage words',
    }],
    applicability_review_required: 1,
    outstanding_requirements: 0,
    requirements_settled: true,
    nothing_to_ask: true,
    ...overrides,
  });
  return parent.textContent;
}

// A previous answer remains on file, but a changed dispute cannot inherit
// the passage's former relevance or display a settled checklist.
assert.match(board({}), /legal relevance needs re-review/);
assert.match(board({}), /1 checklist item needs legal relevance re-review/);
assert.match(board({}), /\? Check notice/);
assert.doesNotMatch(board({}), /\u2713 Check notice/);
assert.doesNotMatch(board({}), /follow-up complete|Nothing further to ask/);
assert.match(board({outstanding_requirements: 2}), /2 still to ask about/);
assert.match(board({
  requirements: [], applicability_review_required: 0,
}), /Checklist follow-up complete/);
"""


def test_shipped_board_does_not_call_changed_law_applicability_complete():
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required to run the shipped board renderer"
    result = subprocess.run(
        [node, "-e", _RENDERER_CHECK], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
