"""Exact unpadded AST segments from one immutable source observation."""
from __future__ import annotations

import ast
import re


class SourceSegments:
    """Index line bytes once instead of splitting a module for every node.

    Python AST columns are UTF-8 byte offsets, not character offsets. Only
    CR, LF and CRLF terminate source lines: splitlines() would also split
    form feeds and Unicode separators, changing the parser's coordinates.
    Nothing here reads a file or caches a prior source across invocations.
    """

    def __init__(self, source: str):
        self._lines = tuple(re.split(rb"(?<=\n)|(?<=\r)(?!\n)", source.encode("utf-8")))

    def get(self, node: ast.AST) -> str | None:
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)
        first = getattr(node, "col_offset", None)
        last = getattr(node, "end_col_offset", None)
        if any(value is None for value in (start, end, first, last)):
            return None
        if start == end:
            return self._lines[start - 1][first:last].decode("utf-8")
        body = (self._lines[start - 1][first:],
                *self._lines[start:end - 1], self._lines[end - 1][:last])
        return b"".join(body).decode("utf-8")
