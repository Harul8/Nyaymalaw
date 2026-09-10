"""THE SEMANTIC INDEX, MEASURED AGAINST THE GRAPH IT IS AN INDEX OF.

WHY THIS EXISTS, measured on 10 September 2026
-----------------------------------------------
`code-review-graph update` refreshes nodes, edges and the FTS index. It does
NOT refresh the vectors. Both hooks in this repository -- the PostToolUse hook
in `.claude/settings.json` and `tools/hooks/pre-commit` -- ran `update` and
nothing else, so the graph went structurally current and semantically stale on
every commit.

Measured that morning: 2,963 nodes, 2,572 embedding rows, **132 non-File nodes
with no vector** -- every function, class and test added since 9 September.
`_refuse_a_shared_seal`, `SharedSealRefused`, `_refuse_an_unauthorised_enrolment`,
`Screen.uncovered` and all eleven members of `nm/domain/media.py` were among
them.

The query *"the seal on client files must not be shared with any other
credential"* returned five plausible credential tests and NOT ONE of the three
nodes that answer it. FTS found `_refuse_a_shared_seal` in a single hit, so the
node was in the graph; only its vector was missing.

**That miss renders as zero results, and zero reads exactly like "not in the
codebase".** Defect shape S3, one level up from the legal corpus, and aimed
squarely at the newest code -- the code most likely to be the subject of the
next question.

WHAT IT DOES WHEN IT CANNOT EMBED
-----------------------------------
It says so, in the terminal, at the commit. It does not block: a developer
offline must still be able to commit, and a search index is not a release
criterion. But it does not fall silent either, because silent drift is the
defect this tool exists to end -- the lag is printed as a number, in a form
that cannot be read as success.

`--check` therefore always exits 0. It is a REPORT, not a gate, and it is
labelled as one. What makes it honest is that the number is measured against
`graph.db` on disk rather than asserted, and it has been observed non-zero
(132) and zero on the same machine within ten minutes.

`.code-review-graph/` is gitignored, so this is deliberately NOT a test: a
pytest that skipped whenever the database was absent would pass on every clean
checkout and prove nothing -- a check that cannot fail. It is measured where
the artefact actually lives.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import sqlite3
import subprocess
import sys

from tools._console import utf8_console

utf8_console()

REPO = pathlib.Path(__file__).resolve().parent.parent
DB = REPO / ".code-review-graph" / "graph.db"
ENV = REPO / ".env"

#: File nodes are excluded BY DESIGN, not missing. `embed_all_nodes` reaches
#: its population through `get_all_nodes(exclude_files=True)`, so a File node
#: will never carry a vector however often the index is rebuilt. Counting them
#: as a lag would make this report permanently non-zero, and a number that is
#: always red is a number nobody reads.
NEVER_EMBEDDED = ("File",)

DEFAULT_MODEL = "text-embedding-3-large"


class NoGraph(RuntimeError):
    """The database is not there. Distinct from a lag of zero."""


def lag(db: pathlib.Path | None = None) -> tuple[int, int, int]:
    """(nodes eligible for a vector, how many have one, how many do not).

    THREE NUMBERS AND NOT A BOOLEAN. "Is it stale" cannot distinguish a fresh
    index from an empty one, and both would print as fine.

    `db=None` RATHER THAN `db=DB`, and this was a live bug for about four
    minutes. A default argument binds at import, so `db=DB` captured the path
    once and a caller reassigning the module global still read the original --
    which meant the first attempt to exercise the missing-database path
    measured the real database instead and printed `semantic index current`
    over a database that was not there. An absent input reading as success,
    §9, inside the tool written to refuse exactly that.
    """
    db = DB if db is None else db
    if not db.exists():
        raise NoGraph(f"no graph database at {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        marks = ",".join("?" * len(NEVER_EMBEDDED))
        eligible = con.execute(
            f"select count(*) from nodes where kind not in ({marks})",
            NEVER_EMBEDDED).fetchone()[0]
        embedded = con.execute(
            f"""select count(*) from nodes n
                join embeddings e on e.qualified_name = n.qualified_name
                where n.kind not in ({marks})""", NEVER_EMBEDDED).fetchone()[0]
    finally:
        con.close()
    return eligible, embedded, eligible - embedded


def examples(limit: int = 5, db: pathlib.Path | None = None) -> list[str]:
    """WHICH nodes are unreachable, not just how many.

    Same rule as `Screen.uncovered`: "some of it may be missing" is a worry,
    and "`_refuse_a_shared_seal` cannot be found" is a next step.

    `db=None` for the reason `lag` records -- swept here rather than fixed
    only where it was found, because one early-bound default in this module
    is one place the path can silently be the wrong one.
    """
    db = DB if db is None else db
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        marks = ",".join("?" * len(NEVER_EMBEDDED))
        rows = con.execute(
            f"""select n.qualified_name from nodes n
                left join embeddings e on e.qualified_name = n.qualified_name
                where e.qualified_name is null and n.kind not in ({marks})
                order by n.qualified_name limit ?""",
            (*NEVER_EMBEDDED, limit)).fetchall()
    finally:
        con.close()
    root = str(REPO).replace("\\", "/") + "/"
    return [r[0].replace(root, "") for r in rows]


def _credentials() -> dict[str, str]:
    """The same three facts `tools/crg_serve.ps1` sets, read the same way.

    ONE SOURCE FOR THE KEY. `.env` is gitignored; `.mcp.json` is tracked and
    must never carry it. Duplicating the value into a second file is the
    second copy §4 asks what refuses -- so nothing here writes it anywhere.
    """
    env = dict(os.environ)
    if ENV.exists():
        for line in ENV.read_text(encoding="utf8").splitlines():
            got = re.match(r"^\s*NM_MODEL_API_KEY\s*=\s*(.+?)\s*$", line)
            if got:
                env["CRG_OPENAI_API_KEY"] = got.group(1).strip('"')
            got = re.match(r"^\s*NM_EMBED_MODEL\s*=\s*(.+?)\s*$", line)
            if got:
                env["CRG_OPENAI_MODEL"] = got.group(1).strip('"')
    env.setdefault("CRG_OPENAI_BASE_URL", "https://api.openai.com/v1")
    env["CRG_ACCEPT_CLOUD_EMBEDDINGS"] = "1"
    # Norton injects a device path here and OpenSSL aborts the process on the
    # first TLS call of any kind. CPython tests it for truthiness, so empty
    # reads as unset. See CLAUDE.md -- this cost eight days once already.
    env["SSLKEYLOGFILE"] = ""
    return env


def embed(model: str = DEFAULT_MODEL) -> int:
    """Bring the vectors up to the graph. INCREMENTAL: the embedder keys on a
    text hash, so an unchanged node is skipped and only new or edited ones cost
    an API call."""
    env = _credentials()
    if not env.get("CRG_OPENAI_API_KEY", "").strip():
        print("SEMANTIC INDEX: no NM_MODEL_API_KEY in .env, so the vectors "
              "were not refreshed.", file=sys.stderr)
        return 1
    done = subprocess.run(
        ["code-review-graph", "embed", "--provider", "openai",
         "--model", env.get("CRG_OPENAI_MODEL", model),
         "--repo", str(REPO)],
        env=env, capture_output=True, text=True, shell=(os.name == "nt"))
    out = (done.stdout or "").strip() or (done.stderr or "").strip()
    if done.returncode != 0:
        print(f"SEMANTIC INDEX: the embed did not run -- {out}", file=sys.stderr)
    return done.returncode


def report() -> None:
    """Print the lag. NEVER SILENT ON A NON-ZERO NUMBER, never noisy on zero.

    A line printed above a successful commit every single time is a line
    nobody reads by the third day, which is the same failure as printing
    nothing. So zero is one short line and a lag is four.
    """
    try:
        eligible, embedded, behind = lag()
    except NoGraph as exc:
        print(f"SEMANTIC INDEX: {exc} -- semantic search cannot answer at all; "
              f"run `code-review-graph update` then `python "
              f"tools/graph_vectors.py --embed`")
        return
    if behind == 0:
        print(f"semantic index current: {embedded}/{eligible} nodes carry a vector")
        return
    print(f"SEMANTIC INDEX STALE BY {behind} NODE(S): "
          f"{embedded}/{eligible} carry a vector.")
    print("  Those nodes CANNOT be returned by a semantic query, and the miss "
          "renders as zero results -- which reads exactly like 'not in the "
          "codebase'. Use FTS (`code-review-graph search`) or Grep meanwhile.")
    for name in examples():
        print(f"    unreachable: {name}")
    print("  Fix: python tools/graph_vectors.py --embed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="report the lag and exit 0. A REPORT, not a gate.")
    ap.add_argument("--embed", action="store_true",
                    help="refresh the vectors, then report")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args()
    if args.embed:
        embed(args.model)
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
