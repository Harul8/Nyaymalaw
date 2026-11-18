"""What to get for a case is on the matter board, not repeated in the answer (plan AN.48, D303; the owner: "yes", 18 Nov 2026).

Under "What I need from you" an answer listed each thing to get for a dispute's case - what, from whom and why - word for word as
the board shows it (the case is saved once and drawn in both). A new answer says, for each dispute with things to get, how many
there are and that they are on the board, where 'Tell NM about these' takes the advocate's answers; the questions the answer
itself asks stay. An answer saved with each thing listed is shown as saved (P46: saved elements are never rendered again).
The rendering is run on the invented matter of the checklist tests; the page's drawing of the line is checked in the page tests.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nm.core_engine import response_rendering

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("count, said", [
    (1, "One thing to get for this case is on the matter board, under this dispute, where 'Tell NM about these' takes your "
        "answers."),
    (3, "3 things to get for this case are on the matter board, under this dispute, where 'Tell NM about these' takes your "
        "answers."),
])
def test_the_line_says_how_many_and_where(count, said):
    assert response_rendering._on_the_board(count) == said


def test_the_line_is_code_s_own_never_a_paragraph_of_the_draft():
    assert "NEED_BOARD" in response_rendering.NOT_PARAGRAPHS


def test_the_renderer_lists_no_thing_to_get_and_keeps_the_questions():
    # From the source of the one place that builds "What I need from you": the list of things to get is gone from new answers,
    # code's line takes its place, and the section's own questions are still gathered after it.
    import inspect
    source = inspect.getsource(response_rendering._render_presented)
    assert '_label("NEED_CASE"' not in source
    assert '_label("NEED_BOARD", _on_the_board(len(to_get))' in source
    assert source.index('"NEED_BOARD"') < source.index('kind="ASK"')


_PAGE = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('nm/app/app.js', 'utf8');
const start = source.indexOf('function needQuestions(');
const end = source.indexOf('\nfunction openNeedAnswers(', start);
const sandbox = {};
vm.runInNewContext(source.slice(start, end) + '\nthis.needQuestions = needQuestions;', sandbox);
process.stdout.write(JSON.stringify(sandbox.needQuestions(JSON.parse(process.argv[1]))));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to run the page's own function")
def test_the_answer_window_asks_nothing_of_the_line_and_still_asks_the_questions():
    items = [{"kind": "NEED_GROUP", "text": "Recovery of the cheque amount"},
             {"kind": "NEED_BOARD", "text": response_rendering._on_the_board(2), "count": 2,
              "dispute": {"id": "D1", "name": "Recovery of the cheque amount"}},
             {"kind": "ASK", "text": "When did the drawer receive the notice?"}]
    run = subprocess.run(["node", "-e", _PAGE, json.dumps(items)], cwd=ROOT, capture_output=True, text=True, check=True)
    assert json.loads(run.stdout) == [{"group": "Recovery of the cheque amount", "text": "When did the drawer receive the notice?"}]
