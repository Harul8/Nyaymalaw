"""Entry point. The only module that both builds adapters and touches the edge.

    python -m nm.bootstrap.main            # serve on :8000
    python -m nm.bootstrap.main --check    # wire everything, print health, exit

`--check` exists because "does it start" and "does it work" are different
questions, and the second one is the one worth being able to answer without a
browser.
"""
from __future__ import annotations

import argparse
import json
import sys

from nm.bootstrap.composition import Application
from nm.edge import api


def create_app(application: Application | None = None):
    """Wire the composition root into the served path and return the ASGI app."""
    api.set_application(application or Application())
    return api.app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nyaymalaw")
    ap.add_argument("--check", action="store_true",
                    help="wire everything, print health, and exit")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)

    try:
        application = Application()
    except Exception as exc:
        # Configuration is refused at STARTUP rather than used: an unpinned
        # alias, an unlisted provider, a judge that grades its own homework, or
        # an unconfigured encryption key all land here.
        print(f"REFUSED TO START: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    health = application.health()
    if args.check:
        print(json.dumps(health, indent=2))
        return 0 if health["corpus"] == "readable" else 1

    create_app(application)
    import uvicorn

    print(json.dumps(health, indent=2))
    uvicorn.run(api.app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
