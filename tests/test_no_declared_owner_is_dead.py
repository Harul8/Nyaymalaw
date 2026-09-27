"""EVERY FUNCTION IN `nm/` IS REACHED, or it is not an enforcement.

WHY
---
`Thread.decisive_identifier_matches` was named by C4's docstring as the
enforcement of thread identity — *"enforced by the constructor and by
`decisive_identifier_matches`"* — and had NO CALLERS. The binder did the work
inline. That is B-050, and it is the shape `assurance/gate/trace.py` T8 catches for
gates: something declared as the enforcement that no code path consults.

Gates have a checker. Functions did not. Sweeping all 214 in `nm/` found three
more of exactly it:

    TreatmentState.usable_alone  "may this carry a proposition alone" — while
                                 `Finding.blocking_reason` enumerated NEGATIVE
                                 and NOT_CHECKED itself. Two owners, and the
                                 unconsulted one held the rule.
    CoveragePosition.discloses   "anything but MET is said out loud" — while
                                 `turn.py` asked `state is MET` inline.
    Answer.render_text           "The bytes that leave the process. Nothing
                                 else is emitted." Nothing called it; the real
                                 byte boundary composes a structured payload.

TWO OWNERS FOR ONE RULE is the shape that produced the O.S. 442/2023 defect,
where one copy was hardened and the other was not. Here it is worse: the second
copy is the one nobody consults, so hardening it would change nothing at all.

WHY AN ALLOWLIST AND NOT A CLEVERER SCAN
-----------------------------------------
Some functions are legitimately called by something this scan cannot see — a
web framework's router, a decorator that only registers, a Protocol method
implemented elsewhere. Each is named below with the reason. An exemption
someone typed is a decision; a scan that silently skips a category is how the
rule stops applying.
"""
from __future__ import annotations

import ast
import collections
from pathlib import Path

import pytest

from assurance.common.homes import TOOLING

pytestmark = pytest.mark.class_a

ROOT = Path(__file__).resolve().parents[1]

#: Called by something no AST scan of this repo can see. Each with its reason.
REACHED_ELSEWHERE = {
    # FastAPI routes -- the router calls them by registration, not by name.
    #
    # RE-MEASURED 23 September 2026: eleven routes added since the last entry,
    # each checked to be `@app.*`-registered and each named here with its
    # caller. Ten have a BROWSER caller in `nm/app/app.js` (or
    # `source-reader.js`) as a string literal this scan cannot see:
    # registration and password recovery, sessions and activity, the AI
    # data-sharing permission, draft protection, and the saved source reader.
    "account_capabilities", "cancel_registration", "confirm_email",
    "resend_confirmation", "forgot_password", "revoke_selected_session",
    "session_activity", "set_model_permission", "draft_key", "source_excerpt",
    # AND ONE WITH NO PAGE CALLER, which is recorded rather than smoothed
    # over: `update_capacity` is reached over HTTP by
    # `tests/test_capacity_admission_uses_a_record_not_prose.py`, and the page
    # records capacity through intake instead. A route only a test calls is
    # an API, not yet a feature.
    "update_capacity",
    #
    # P33's two. Registered by decorator like every route here, and named
    # in `commands.json` as the current_route for `create-retention-request`
    # and `get-retention-request` -- so the mapping is recorded rather than
    # inferred from a docstring.
    "create_retention_request", "get_retention_request",
    "place_retention_hold", "release_retention_hold",
    "resolve_retention_copy", "advance_retention_request",
    "check_restore",
    # P27's four, same registration.
    "record_advice_decision", "list_advice_decisions",
    "record_comparison", "get_comparison",
    # P25's two.
    "bind_source_to_thread", "list_source_bindings",
    # P29's three, same registration.
    "prepare_drafting_package", "get_drafting_package",
    "export_drafting_package",
    # P32's six.
    "matter_re_entry", "offer_handover", "accept_handover",
    "decline_handover", "close_matter", "reopen_matter",
    "record_matter_event",
    # P30's five.
    "create_action_proposal", "confirm_action", "execute_action",
    "record_action_outcome", "reconcile_action",
    # P31's six.
    "create_hearing_pack", "get_hearing_pack", "add_witness_plan",
    "add_expert_instruction", "in_court_view", "check_concession",
    # P45's four.
    "set_service_authority", "cancel_service_authority",
    "schedule_service_job", "get_service",
    "health", "matters", "matter", "matter_summary", "turn", "index",
    # A1's three. `search` is absent from this list ONLY because the word
    # occurs elsewhere in the tree, which is worth noticing: this check finds
    # a route with a distinctive name and misses one with a common name.
    "login", "logout", "whoami",
    # BK-31's two. They are reached the same way every route above is -- by
    # registration -- and they now have a BROWSER caller too (`showSessions`
    # on the Sessions control), which is the half this sweep cannot see and
    # the half that matters: an API nobody calls is not a feature, and the
    # first version of this row had exactly that.
    "sessions", "revoke_sessions",
    # P13's four. Registered the same way, and with a BROWSER caller too --
    # the cover and commission panels in `nm/app/app.js`. The note above about
    # `search` applies here in reverse: these have distinctive names, so the
    # sweep sees them as dead and the declaration is what tells it otherwise.
    "matter_cover", "get_commission", "set_commission", "concede",
    # P14's three, registered the same way.
    "declare_emergency", "get_emergency", "conceded",
    # P17's projection, registered the same way.
    "get_casefile",
    # P16 quarantine receipt routes: FastAPI registrations exercised by the
    # route-table authentication sweep and served upload browser journey.
    # The held-content route deliberately refuses original-byte release.
    "open_upload_first_intake", "begin_upload", "list_uploads", "inspect_upload",
    "receive_upload_chunk", "complete_upload", "cancel_upload", "held_upload_content",
    # P18's two, registered the same way, and both with a BROWSER caller: the
    # Case file pane's Correct control posts the correction and the pane reads
    # the ledger. The sweep sees neither call because both are template
    # literals in `nm/app/app.js`, which is the same blindness as `sessions`.
    "correct_fact", "get_dependencies",
    # P21's five, registered the same way, each with a BROWSER caller on the
    # search pane (`runResearchRound`, `expandCase`, `attachParagraph`).
    "start_research", "list_research", "get_research", "inspect_case",
    "attach_source",
    # P22's route, registered the same way, with a browser caller on the case
    # file (the Confirm-premise control).
    "state_premise",
    # P23's route, with a browser caller on the case file (the State-relief
    # control on the Relief and enforceability panel).
    "state_relief",
    # P24's two, with browser callers on the case file's briefing controls
    # (mark a need unavailable; resume it). Same template-literal blindness.
    "mark_need_unavailable", "resume_need",
    # F-C-02's route, registered the same way, with a browser caller: the mic
    # under the brief posts the recording from `transcribeDictation`.
    "transcribe_dictation",
    # F-C-03's socket, registered the same way, with a browser caller:
    # `openLiveWords` connects to it while the advocate is speaking.
    "dictation_socket",
    # `@implements` markers: their whole purpose is to be SCANNED by
    # assurance/gate/trace.py rather than called.
    "_implements_c4",
    # dataclass and Protocol machinery.
    "__post_init__", "decorate",
}


def _defined() -> dict[str, tuple[str, int]]:
    """Every function and method defined under `nm/`, with where it lives."""
    out: dict[str, tuple[str, int]] = {}
    protocols: set[str] = set()
    for f in sorted((ROOT / "nm").rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                    getattr(b, "id", "") == "Protocol" for b in node.bases):
                # A port's methods are implemented by adapters and called
                # through the protocol, so the name resolves at the call site
                # rather than at the definition.
                protocols.update(n.name for n in node.body
                                 if isinstance(n, ast.FunctionDef))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("__"):
                    continue
                out[node.name] = (str(f.relative_to(ROOT)), node.lineno)
    return {k: v for k, v in out.items() if k not in protocols}


def _local_nodes(scope):
    """Scope declarations, without borrowing a nested function's bindings."""
    def descend(node):
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            for child in ast.iter_child_nodes(node):
                yield from descend(child)

    body = scope.body if not isinstance(scope, ast.Lambda) else [scope.body]
    for node in body:
        yield from descend(node)


def _qualified(node, bindings):
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = _qualified(node.value, bindings)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _scope_bindings(scope, inherited, module):
    """Only single, stable source bindings provide extra caller evidence."""
    nodes = tuple(_local_nodes(scope))
    declarations = collections.defaultdict(list)
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level:
                parents = module.split(".")[:-node.level]
                target = ".".join([*parents, *target.split(".")]) if parents else ""
            for item in node.names:
                if item.name != "*":
                    declarations[item.asname or item.name].append(
                        f"{target}.{item.name}" if target else None)
        elif isinstance(node, ast.Import):
            for item in node.names:
                declarations[item.asname or item.name.split(".")[0]].append(
                    item.name if item.asname else item.name.split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            declarations[node.id].append(None)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            declarations[node.name].append(None)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            declarations[node.name].append(None)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                declarations[name].extend((None, None))
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = scope.args
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg):
            if arg is not None:
                declarations[arg.arg].append(None)
    bindings = dict(inherited)
    bindings.update({name: values[0] if len(values) == 1 else None
                     for name, values in declarations.items()})
    routers = {}
    for node in nodes:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        else:
            continue
        if (isinstance(target, ast.Name) and len(declarations[target.id]) == 1
                and isinstance(value, ast.Call)
                and _qualified(value.func, bindings) == "fastapi.APIRouter"):
            routers[target.id] = node.lineno
    exposed = set()
    for node in nodes:
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
            if node.value.id in routers:
                exposed.add(node.value.id)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "include_router"):
            supplied = [*node.args, *(kw.value for kw in node.keywords if kw.arg == "router")]
            exposed.update(value.id for value in supplied
                           if isinstance(value, ast.Name) and value.id in routers)
    return bindings, {name: routers[name] for name in exposed}


_ROUTE_METHODS = frozenset({
    "get", "put", "post", "delete", "patch", "head", "options", "trace",
    "api_route", "websocket", "websocket_route",
})


class _CallerReferences(ast.NodeVisitor):
    """Resolve actual alias calls and bounded local APIRouter registrations.

    Registration is source evidence, not proof of deployed/authenticated use.
    Existing name/attribute counts and authored exemptions remain unchanged.
    """
    def __init__(self, tree, module, owned_callables):
        self.used = collections.Counter()
        self.module = module
        self.owned_callables = owned_callables
        self.bindings, self.routers = _scope_bindings(tree, {}, module)

    def visit_Name(self, node):
        self.used[node.id] += 1

    def visit_Attribute(self, node):
        self.used[node.attr] += 1
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            canonical = _qualified(node.func, self.bindings)
            if canonical in self.owned_callables:
                self.used[canonical.rsplit(".", 1)[-1]] += 1
        self.generic_visit(node)

    def _function(self, node):
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.attr in _ROUTE_METHODS
                    and self.routers.get(decorator.func.value.id, float("inf"))
                    < decorator.lineno):
                paths = (list(decorator.args[:1]) or
                         [kw.value for kw in decorator.keywords if kw.arg == "path"])
                if len(paths) == 1 and isinstance(paths[0], ast.Constant):
                    if type(paths[0].value) is str:
                        self.used[node.name] += 1
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        self._body(node)

    def visit_FunctionDef(self, node):
        self._function(node)

    def visit_AsyncFunctionDef(self, node):
        self._function(node)

    def _body(self, node):
        previous = self.bindings, self.routers
        self.bindings, self.routers = _scope_bindings(node, self.bindings, self.module)
        for child in node.body:
            self.visit(child)
        self.bindings, self.routers = previous

    def visit_ClassDef(self, node):
        for child in (*node.decorator_list, *node.bases, *node.keywords):
            self.visit(child)
        self._body(node)

    def visit_Lambda(self, node):
        self.visit(node.args)
        previous = self.bindings, self.routers
        self.bindings, self.routers = _scope_bindings(node, self.bindings, self.module)
        self.visit(node.body)
        self.bindings, self.routers = previous


def _referenced(sources=None, *, root=ROOT) -> collections.Counter:
    """Every original source population, plus actual import/registration paths."""
    paths = sources if sources is not None else (
        f for top in ("nm", "tests", *TOOLING)
        for f in (root / top).rglob("*.py") if "__pycache__" not in f.parts)
    trees = {}
    for path in paths:
        parts = path.relative_to(root).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        trees[".".join(parts)] = ast.parse(path.read_text(encoding="utf8"))
    owned_callables = frozenset(
        f"{module}.{node.name}" for module, tree in trees.items() if module.startswith("nm.")
        for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    used = collections.Counter()
    for module, tree in trees.items():
        reader = _CallerReferences(tree, module, owned_callables)
        reader.visit(tree)
        used.update(reader.used)
    return used


def test_the_scan_can_see_the_product():
    """A guard on the guard: an empty population passes the test below."""
    assert len(_defined()) >= 100, (
        "almost no functions were discovered — this file would then be "
        "asserting nothing over nothing")


def test_no_function_in_the_product_is_defined_and_never_reached():
    """THE POINT. A declared enforcement nothing calls is not an enforcement.

    It is worse than absent: the docstring says the rule is enforced there, so
    the next person hardens the copy that runs on nothing.
    """
    used = _referenced()
    dead = [f"{path}:{line}  {name}()"
            for name, (path, line) in sorted(_defined().items())
            if name not in REACHED_ELSEWHERE and used[name] == 0]

    assert not dead, (
        "these are defined in nm/ and referenced nowhere:\n  "
        + "\n  ".join(dead)
        + "\n\nEither give it a caller, delete it, or add it to "
          "REACHED_ELSEWHERE with the reason a scan cannot see the call. A "
          "function whose docstring claims to enforce a rule, with no callers, "
          "is the shape that let `decisive_identifier_matches` sit in C4's "
          "contract while the binder did the work inline (B-050).")
