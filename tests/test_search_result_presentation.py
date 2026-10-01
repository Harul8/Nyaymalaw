"""Search display order is not a model or index confidence judgment."""
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
const start = source.indexOf('function searchPosition(');
const end = source.indexOf("\n$('search-form')", start);
assert.ok(start >= 0 && end > start, 'the shipped search renderer must be present');

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.text = ''; this.dataset = {}; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(child => child.textContent).join(' '); }
  appendChild(child) { this.children.push(child); }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  addEventListener() {}
  setAttribute() {}
}
const elements = {'search-state': new Element('div'), 'search-results': new Element('div')};
const sandbox = {
  document: {createElement: tag => new Element(tag)},
  $: id => elements[id],
  renderIndexLine: () => {},
  stateBlock: (_level, text) => {
    const node = new Element('p'); node.textContent = text; return node;
  },
};
vm.runInNewContext(source.slice(start, end), sandbox);
const casesStart = source.indexOf('function renderCases(');
const casesEnd = source.indexOf('\nasync function expandCase(', casesStart);
assert.ok(casesStart >= 0 && casesEnd > casesStart,
  'the shipped research renderer must be present');
vm.runInNewContext(source.slice(casesStart, casesEnd), sandbox);

function hit(confidence) {
  return {case_name: 'A v B', court: 'Court', year: 2020, para_type: 'reasoning',
    snippet: 'Retrieved text', origin: 'searched', confidence};
}
function labels(scores) {
  sandbox.renderSearch({coverage: 'answered', hits: scores.map(hit), hit_count: scores.length,
    why: 'No paragraph matched.'});
  return elements['search-results'].children.slice(1).map(card =>
    card.children[0].children[2].textContent);
}

// Counterexample: a sole low-scored hit cannot be "lower-ranked here".
assert.deepEqual(labels([0.01]), ['searched']);

// Tied scores have distinct display positions, but no fabricated relevance order.
assert.deepEqual(labels([0.2, 0.2, 0.2]), [
  'searched · result 1 of 3 shown',
  'searched · result 2 of 3 shown',
  'searched · result 3 of 3 shown',
]);

// Changing raw FTS scores cannot change what the renderer says about position.
assert.deepEqual(labels([0.99, 0.01, 0.65]), labels([0.01, 0.99, 0.01]));
assert.equal(sandbox.searchPosition(-1, 3), '');
assert.equal(sandbox.searchPosition(0, 1), '');
assert.equal(sandbox.searchPosition(3, 3), '');
assert.equal(sandbox.searchPosition(0.5, 3), '');

function researchLabels(bands) {
  elements['search-results'].textContent = '';
  sandbox.renderCases('rid', {cases: bands.map((band, index) => ({
    case_id: String(index), case_name: 'A v B', origin: 'searched', band,
    snippet: 'Retrieved text',
  }))});
  return elements['search-results'].children[0].children.map(card =>
    card.children[0].children[2].textContent);
}
assert.deepEqual(researchLabels(['']), ['searched']);
assert.deepEqual(researchLabels(['result 1 of 2 shown', 'result 2 of 2 shown']), [
  'searched · result 1 of 2 shown', 'searched · result 2 of 2 shown',
]);

sandbox.renderSearch({coverage: 'not_assessed', hits: [], hit_count: 0, why: 'Index unavailable'});
assert.equal(elements['search-results'].textContent, '');
assert.match(elements['search-state'].textContent, /NOT SEARCHED/);
"""


def test_shipped_search_renderer_does_not_turn_an_index_score_into_confidence():
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required to run the shipped search renderer"
    result = subprocess.run(
        [node, "-e", _RENDERER_CHECK], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_served_case_discovery_uses_actual_position_not_score_bands():
    from nm.app.api import _discovery_dict, _search_position
    from nm.Archives.legal_brain.retrieve.evidence_port import Coverage
    from nm.Archives.legal_brain.retrieve.search_port import CaseDiscovery, CaseHit, IndexIdentity

    identity = IndexIdentity("authority", "dated-build", "source", "generation-one", 3, 4,
                             "India")

    def discovery(*scores):
        cases = tuple(CaseHit(f"case-{i}", f"Case {i}", "Court", 2020, 1,
                              float(i), score, "Original words") for i, score in enumerate(scores))
        return _discovery_dict(CaseDiscovery("query", "authority", Coverage.ANSWERED,
                                             identity, cases=cases, paragraphs_ranked=len(cases)))

    assert [row["band"] for row in discovery(0.01)["cases"]] == [""]
    expected = ["result 1 of 3 shown", "result 2 of 3 shown", "result 3 of 3 shown"]
    assert [row["band"] for row in discovery(0.2, 0.2, 0.2)["cases"]] == expected
    assert [row["band"] for row in discovery(0.99, 0.01, 0.65)["cases"]] == expected
    assert _search_position(-1, 3) == ""
    assert _search_position(0, 1) == ""
    assert _search_position(True, 3) == ""
