"""THE SERVED PRODUCT ON A TEMPORARY STORE. One owner, three callers.

WHY THIS MODULE EXISTS
-----------------------
`tests/conftest.py`'s `client` fixture composed the real ASGI app against a
temporary encrypted store, a scripted provider, an enrolled advocate and a
signed-in session. It was the only place that knew how, and BK-30 needs the
same thing from two more places: a real HTTP server for the browser suite, and
a command an advocate-facing journey can be run from.

Three compositions of one product is the arrangement CLAUDE.md §4 asks about.
The answer is not "be careful" — it is that there is one function here, and
the fixture calls it.

WHAT IT DELIBERATELY DOES NOT DO
----------------------------------
It does not read the environment for a provider, a key or a corpus. Every
value is passed in or defaulted to something that cannot reach a real system:
a key that says it is not a secret, a scripted model, and an evidence double.
A harness that could silently pick up `NM_MODEL_API_KEY` would bill a real
provider from a test run, and a harness that could pick up the production
`NM_MATTER_KEY` would write test matters into a real store.
"""
from __future__ import annotations

import contextlib
import os
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

#: The store key for a temporary journey store. It is not a secret and says
#: so: a fixture key that looked like a real one would eventually be pasted
#: somewhere real.
KEY = "test-key-not-a-secret"

#: Satisfies every clause `advocate.enrol` enforces — length, an upper case
#: letter, a lower case letter, a numeral and a special character. It is
#: written once here for the reason `conftest` records against its own copy:
#: a shared password that stops satisfying the rule fails every test that
#: signs in, at the fixture rather than at the assertion, which is the
#: hardest place to read a failure from.
PASSWORD = "Journey-password-not-a-secret-1"


@dataclass
class Served:
    """A wired product, and the pieces a caller needs to drive it."""

    app: object
    application: object
    directory: object
    root: Path

    def enrol(self, advocate_id: str = "adv_journey",
              password: str = PASSWORD) -> str:
        """Put an advocate in the directory. Returns the id.

        THROUGH THE DIRECTORY AND NOT THE ROUTE, because a harness that
        registers over HTTP is testing registration on every phase that only
        needs an advocate to exist — and when registration breaks, every
        later phase fails for a reason that is not its own.
        `test_an_advocate_can_register.py` owns that route.
        """
        from nm.domain.advocate import AdvocateIdentity, Enrolment, enrol

        if not (self.root / "advocates" / f"{advocate_id}.nm").exists():
            self.directory.enrol(Enrolment(
                identity=AdvocateIdentity(
                    id=advocate_id, name="A. Journey",
                    enrolment="AP/1234/2010", practice="Hyderabad",
                    firm_id="firm_journey"),
                credential=enrol(password)))
        return advocate_id


def served(root: Path, *, responses: dict | None = None,
           evidence=None, model=None, search=None) -> Served:
    """The real composition root, wired to a temporary encrypted store."""
    from nm.adapters.model.config import ModelConfig, TierConfig
    from nm.adapters.model.scripted import ScriptedModelAdapter
    from nm.adapters.store.directory import FileDirectory
    from nm.adapters.store.file_store import FileMatterStore
    from nm.bootstrap.composition import Application
    from nm.bootstrap.main import create_app
    from nm.ports.model import Tier

    # THE SYNTHETIC PROFILE, DEFAULTED HERE AND NOT READ FROM A `.env`.
    #
    # `Application.__init__` loads the model configuration whether or not a
    # model is passed in, and refuses to start without a provider. In the
    # main checkout a developer `.env` supplied one -- which is exactly the
    # borrowing this module's docstring says it does not do, and it went
    # unnoticed until the suite ran in a worktree with no `.env`, where every
    # phase errored on `NM_MODEL_PROVIDER is not set`. `setdefault`, so a
    # value the caller set deliberately still wins; the defaults name the
    # scripted provider and the fixture key, neither of which reaches a real
    # system. Same values as `tests/conftest.py::scripted_application_environment`.
    os.environ.setdefault("NM_MODEL_PROVIDER", "scripted")
    os.environ.setdefault("NM_MODEL_ROUTINE", "scripted-1")
    os.environ.setdefault("NM_EMBED_MODEL", "text-embedding-3-large")
    os.environ.setdefault("NM_MATTER_KEY", KEY)

    config = ModelConfig(tiers={
        Tier.ROUTINE: TierConfig(Tier.ROUTINE, "scripted", "scripted-1",
                                 None, None),
        Tier.EMBED: TierConfig(Tier.EMBED, "scripted",
                               "text-embedding-3-large", None, None),
    })
    if evidence is None:
        from tests.test_turn_contract import _Evidence
        evidence = _Evidence()

    directory = FileDirectory(root, key=KEY)
    application = Application(
        store=FileMatterStore(root, key=KEY),
        evidence=evidence,
        directory=directory,
        model=model or ScriptedModelAdapter(config, responses=responses or {
            "__default__": "Issue the statutory notice and diarise the window."}),
        # P21. A SEARCH PORT THE CALLER SUPPLIES -- the synthetic indexes in the
        # research suites. Absent, the composition root's default applies and
        # says `unavailable_index` on a machine with no `.nm/authority.db`.
        search=search,
    )
    return Served(app=create_app(application), application=application,
                  directory=directory, root=root)


def _free_port() -> int:
    with contextlib.closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextlib.contextmanager
def running(root: Path, **kwargs):
    """The product on a real HTTP port, for a real browser to talk to.

    A THREAD AND NOT A SUBPROCESS, so the harness holds the same `Served` the
    browser is driving and can reach into the store to check what was
    actually written. A subprocess would leave the suite asserting on
    responses alone, which is how a product that serves a correct answer and
    persists nothing passes its own journey.
    """
    import uvicorn

    box = served(root, **kwargs)
    port = _free_port()
    config = uvicorn.Config(box.app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # WAIT FOR THE PORT, not for a fixed sleep. A sleep that is long enough
    # on this machine is the flake that fails on a slower one.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("the journey server did not start within 30s")

    try:
        yield box, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
