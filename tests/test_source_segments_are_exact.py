"""An indexed source reader must not change any scanner's actual evidence."""
from __future__ import annotations

import ast

import pytest

from tools._source import SourceSegments

pytestmark = pytest.mark.class_a


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("source", [
    "name = 'न्याय'; π = '☂'\ndef test_हक():\n    return name + π\n",
    "@dec('x')\nasync def probe():\n    return (\n        'first'\n        + 'second'\n    )\n",
    "def outer():\n    def inner():\n        return {'x': [1, 2]}\n    return inner()\n",
    "def form_feed():\n\f    return 'not\\f a source line'\n",
    "value = 'paragraph\u2029line\u2028vertical\vform\fspace'\nother = value",
])
def test_indexed_segments_match_ast_for_every_node(source, newline):
    source = source.replace("\n", newline)
    tree = ast.parse(source)
    segments = SourceSegments(source)
    nodes = list(ast.walk(tree))
    located = [node for node in nodes if getattr(node, "lineno", None) is not None]
    assert len(located) >= 3, "the comparison must examine real parsed nodes"
    for node in nodes:
        assert segments.get(node) == ast.get_source_segment(source, node)


def test_segment_observations_are_independent_and_do_not_invent_missing_locations():
    before, after = "answer = 'first'", "answer = 'changed'"
    first, second = SourceSegments(before), SourceSegments(after)
    assert first.get(ast.parse(before).body[0]) == before
    assert second.get(ast.parse(after).body[0]) == after
    assert first.get(ast.parse(before).body[0]) == before
    assert first.get(ast.Module(body=[], type_ignores=[])) is None
