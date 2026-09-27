"""M2 follows real source bindings, never unused imports or decorator spelling."""
from __future__ import annotations

from textwrap import dedent

import pytest

from tests.test_no_declared_owner_is_dead import _referenced

pytestmark = pytest.mark.class_a


def _references(tmp_path, consumer):
    source = tmp_path / "nm" / "phase"
    source.mkdir(parents=True)
    owner = source / "owner.py"
    owner.write_text("def canonical_owner():\n    return 1\n", encoding="utf8")
    caller = source / "consumer.py"
    caller.write_text(dedent(consumer), encoding="utf8")
    return _referenced((owner, caller), root=tmp_path)


@pytest.mark.parametrize("alias", ["first_name", "renamed", "another_call_name"])
@pytest.mark.parametrize("local", [False, True])
def test_an_actual_aliased_call_reaches_the_same_exact_owner(tmp_path, alias, local):
    body = f"from nm.phase.owner import canonical_owner as {alias}\n{alias}()\n"
    if local:
        body = "def factory():\n" + "".join("    " + line + "\n" for line in body.splitlines())
    assert _references(tmp_path, body)["canonical_owner"] == 1


@pytest.mark.parametrize("body", [
    "from nm.phase.owner import canonical_owner",
    "from nm.phase.owner import canonical_owner as unused",
    "from nm.phase.owner import canonical_owner as alias\nalias = lambda: 2\nalias()",
    "from nm.phase.owner import canonical_owner as alias\ndef caller(alias):\n    alias()",
    "from nm.phase.owner import canonical_owner as alias\n(lambda alias: alias())(None)",
    "from nm.phase.absent import canonical_owner as alias\nalias()",
    "from nm.phase.owner import canonical_owner as alias\n"
    "def caller():\n    alias = lambda: 2\n    alias()",
])
def test_an_unused_unknown_or_shadowed_import_is_not_an_owner_call(tmp_path, body):
    assert _references(tmp_path, body)["canonical_owner"] == 0


@pytest.mark.parametrize("constructor", [
    "from fastapi import APIRouter\nrouter = APIRouter()",
    "from fastapi import APIRouter as Router\nrouter = Router()",
    "import fastapi as framework\nrouter = framework.APIRouter()",
])
@pytest.mark.parametrize("escape", ["return router", "app.include_router(router)"])
@pytest.mark.parametrize("verb", ["get", "delete", "websocket"])
def test_actual_local_router_registration_reaches_its_handler(
    tmp_path, constructor, escape, verb
):
    body = "def install(app):\n" + "".join(
        "    " + line + "\n" for line in constructor.splitlines()
    ) + f"    @router.{verb}('/owned')\n    def route_entry():\n        return 1\n    {escape}\n"
    assert _references(tmp_path, body)["route_entry"] == 1


@pytest.mark.parametrize("constructor,decorator,escape", [
    ("from not_fastapi import APIRouter\nrouter = APIRouter()",
     "@router.get('/owned')", "return router"),
    ("from fastapi import APIRouter\nrouter = object()",
     "@router.get('/owned')", "return router"),
    ("from fastapi import APIRouter\nAPIRouter = object\nrouter = APIRouter()",
     "@router.get('/owned')", "return router"),
    ("from fastapi import APIRouter\nrouter = APIRouter()\nrouter = object()",
     "@router.get('/owned')", "return router"),
    ("from fastapi import APIRouter\nrouter = APIRouter()",
     "@router.unregistered('/owned')", "return router"),
    ("from fastapi import APIRouter\nrouter = APIRouter()",
     "@router.get('/owned')", "return None"),
    ("from fastapi import APIRouter\nrouter = APIRouter()",
     "@unknown.get('/owned')", "return router"),
    ("from fastapi import APIRouter\nrouter = APIRouter()",
     "@router.get(123)", "return router"),
])
def test_unknown_invalid_or_unexposed_decorators_do_not_create_callers(
    tmp_path, constructor, decorator, escape
):
    body = "def install(app):\n" + "".join(
        "    " + line + "\n" for line in constructor.splitlines()
    ) + f"    {decorator}\n    def route_entry():\n        return 1\n    {escape}\n"
    assert _references(tmp_path, body)["route_entry"] == 0
