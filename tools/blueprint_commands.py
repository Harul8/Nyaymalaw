"""Validate proposed wire contracts, never their runtime/legal conformance.

No network schema resolution is permitted. The catalogue, schema definitions,
examples and current acceptance registry are separate reconciled populations.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

CATALOG_FIELDS = frozenset({
    "$schema", "$id", "title", "$comment", "x-contract-version",
    "x-implementation-state", "x-scope", "x-example-policy", "x-common-rules",
    "x-error-catalog", "$defs", "x-commands",
})
COMMAND_FIELDS = frozenset({
    "id", "method", "path", "owner_ac", "request_schema", "response_schema",
    "error_schema", "success_status", "errors", "current_route", "authorization",
    "transitions", "authoritative_records", "retry", "semantic_refusal", "examples",
})
BINARY_FIELDS = frozenset({"response_representation", "binary_contract"})
EXAMPLE_FIELDS = frozenset({
    "valid_request", "invalid_request", "invalid_request_reason", "valid_response",
    "invalid_response", "invalid_response_reason",
})
COMMON_FIELDS = frozenset({
    "identity", "secret_handling", "transport", "header_matching", "idempotency",
    "optimistic_concurrency", "read_consistency", "mutation_commit", "time",
    "exceptions", "async_completion", "bounds", "auth_boundary", "catalogue_change",
})


def _formats() -> FormatChecker:
    """Do not let an absent optional RFC3339 package silently disable dates."""
    checker = FormatChecker()

    @checker.checks("date-time", raises=ValueError)
    def valid_instant(value):
        if not isinstance(value, str):
            return True  # The schema's type restriction owns this refusal.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None

    @checker.checks("date", raises=ValueError)
    def valid_date(value):
        if not isinstance(value, str):
            return True
        return date.fromisoformat(value).isoformat() == value

    @checker.checks("uri", raises=ValueError)
    def valid_https_uri(value):
        if not isinstance(value, str):
            return True
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not any(character.isspace() or ord(character) < 32 for character in value)
                and (parsed.port is None or 1 <= parsed.port <= 65535))

    return checker


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(value: object) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(_text(v) for v in value) and len(value) == len(set(value)))


def _walk(value: object, path: str):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _walk(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}/{index}")


def check_commands(catalog: dict, criteria: set[str]) -> list[str]:
    """Return named structural defects; even perfect output means design only."""
    errors: list[str] = []
    if not isinstance(catalog, dict):
        return ["commands: catalogue must be an object"]
    if set(catalog) != CATALOG_FIELDS:
        errors.append("commands: unsupported or missing catalogue fields")
    if (catalog.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or catalog.get("x-contract-version") != 1
            or catalog.get("x-implementation-state") != "design_only"):
        errors.append("commands: unsupported schema/version or non-design claim")
    for field in ("$id", "title", "$comment", "x-scope", "x-example-policy"):
        if not _text(catalog.get(field)):
            errors.append(f"commands: missing {field}")
    common = catalog.get("x-common-rules")
    if not isinstance(common, dict) or set(common) != COMMON_FIELDS:
        errors.append("commands: shared rule population changed or malformed")
    elif not all(_text(value) for value in common.values()):
        errors.append("commands: empty shared rule")
    definitions = catalog.get("$defs")
    rows = catalog.get("x-commands")
    if not isinstance(definitions, dict) or not definitions:
        return errors + ["commands: empty or malformed definition population"]
    if any(not isinstance(value, dict) or not value for value in definitions.values()):
        return errors + ["commands: definitions must be nonempty constrained schemas"]
    if not isinstance(rows, list) or not rows:
        return errors + ["commands: empty or malformed command population"]
    if not criteria or not all(_text(value) for value in criteria):
        errors.append("commands: empty or malformed acceptance population")

    # Refuse external resolution BEFORE asking jsonschema to evaluate anything.
    unsafe_refs = False
    for path, node in _walk(catalog, "catalogue"):
        if path != "catalogue" and "$id" in node:
            errors.append(f"commands: {path} nested schema identity/rebasing is not permitted")
            unsafe_refs = True
        if "$ref" in node:
            ref = node["$ref"]
            if (not isinstance(ref, str) or not re.fullmatch(r"#/[\$]defs/[^/]+", ref)
                    or ref[8:] not in definitions):
                errors.append(f"commands: {path} unresolved/nonlocal $ref {ref!r}")
                unsafe_refs = True
        if "$dynamicRef" in node or "$recursiveRef" in node:
            errors.append(f"commands: {path} dynamic/recursive resolution is not permitted")
            unsafe_refs = True
    if unsafe_refs:
        return errors
    for path, node in _walk(definitions, "$defs"):
        if isinstance(node.get("properties"), dict):
            for name, schema in node["properties"].items():
                if (not isinstance(schema, dict) or not schema
                        or not set(schema).intersection(Draft202012Validator.VALIDATORS)):
                    errors.append(f"commands: {path}/{name} unconstrained field schema")
        if node.get("type") == "object":
            if node.get("additionalProperties") is not False:
                errors.append(f"commands: {path} object must be closed")
            properties = node.get("properties")
            required = node.get("required")
            if (not isinstance(properties, dict) or not isinstance(required, list)
                    or any(not isinstance(v, str) for v in required)
                    or len(required) != len(set(required))
                    or set(required) - set(properties or {})):
                errors.append(f"commands: {path} malformed object required/properties")
        if node.get("additionalProperties") is True:
            errors.append(f"commands: {path} accept-all object is forbidden")
    try:
        Draft202012Validator.check_schema(catalog)
    except SchemaError as exc:
        return errors + [f"commands: invalid JSON Schema: {exc.message}"]

    error_rows = catalog.get("x-error-catalog")
    error_codes: set[str] = set()
    if not isinstance(error_rows, list) or not error_rows:
        errors.append("commands: empty or malformed error catalogue")
    else:
        for row in error_rows:
            if (not isinstance(row, dict)
                    or set(row) != {"code", "http_status", "outcome", "retry"}
                    or not all(_text(row.get(v)) for v in ("code", "outcome", "retry"))
                    or type(row.get("http_status")) is not int
                    or not 400 <= row["http_status"] <= 599):
                errors.append("commands: malformed error-catalogue row")
                continue
            if row["code"] in error_codes:
                errors.append(f"commands: duplicate error code {row['code']}")
            error_codes.add(row["code"])
        variants = definitions.get("Error", {}).get("oneOf", [])
        combinations = []
        for variant in variants:
            fields = variant.get("properties", {}).get("error", {}).get("properties", {})
            combinations.append({key: fields.get(key, {}).get("const")
                                 for key in ("code", "http_status", "outcome", "retry")})
        if combinations != error_rows:
            errors.append("commands: Error schema and error-catalogue combinations differ")

    ids: list[str] = []
    routes: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("id")):
            errors.append("commands: malformed command row/id")
            continue
        cid = row["id"]
        ids.append(cid)
        binary = row.get("response_representation") == "binary_headers"
        if set(row) != COMMAND_FIELDS | (BINARY_FIELDS if binary else set()):
            errors.append(f"{cid}: unsupported or missing command fields")
        if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", cid):
            errors.append(f"{cid}: malformed command id")
        method, path = row.get("method"), row.get("path")
        if (not isinstance(method, str) or method not in {"GET", "POST"} or not isinstance(path, str)
                or not re.fullmatch(r"/v1/(?:[a-z0-9/-]|\{[a-z_]+\})+", path)):
            errors.append(f"{cid}: invalid target method/path")
        else:
            routes.append((method, path))
        if type(row.get("success_status")) is not int or row["success_status"] not in {200, 201, 202}:
            errors.append(f"{cid}: invalid success status")
        if method == "GET" and row.get("success_status") != 200:
            errors.append(f"{cid}: read status must be 200")
        current = row.get("current_route")
        if current is not None and (not _text(current) or not re.match(r"^(GET|POST) /api/", current)):
            errors.append(f"{cid}: malformed compatibility route")
        for field in ("authorization", "retry", "semantic_refusal"):
            if not _text(row.get(field)):
                errors.append(f"{cid}: missing {field}")
        for field in ("owner_ac", "transitions", "authoritative_records", "errors"):
            if not _strings(row.get(field)):
                errors.append(f"{cid}: empty/duplicate/malformed {field}")
        if isinstance(row.get("owner_ac"), list):
            for criterion in row["owner_ac"]:
                if not isinstance(criterion, str) or criterion not in criteria:
                    errors.append(f"{cid}: unregistered acceptance {criterion!r}")
        if isinstance(row.get("errors"), list):
            for code in row["errors"]:
                if not isinstance(code, str) or code not in error_codes:
                    errors.append(f"{cid}: unknown error code {code!r}")
        expected_error_schema = {"allOf": [
            {"$ref": "#/$defs/Error"},
            {"properties": {"error": {"properties": {
                "code": {"enum": row.get("errors")}
            }}}},
        ]}
        if row.get("error_schema") != expected_error_schema:
            errors.append(f"{cid}: errors must constrain the shared Error schema to declared codes")
        examples = row.get("examples")
        if not isinstance(examples, dict) or set(examples) != EXAMPLE_FIELDS:
            errors.append(f"{cid}: missing/unknown example fields")
            continue
        for side in ("request", "response"):
            expected = {"$ref": f"#/$defs/{cid}_{side}"}
            if row.get(side + "_schema") != expected:
                errors.append(f"{cid}: {side} schema must own its named definition")
                continue
            if not _text(examples.get("invalid_" + side + "_reason")):
                errors.append(f"{cid}: missing negative {side} explanation")
            if examples.get("valid_" + side) == examples.get("invalid_" + side):
                errors.append(f"{cid}: {side} mutation changed nothing")
            validator = Draft202012Validator(
                {"$defs": definitions, **expected}, format_checker=_formats())
            try:
                valid_errors = list(validator.iter_errors(examples.get("valid_" + side)))
                invalid_errors = list(validator.iter_errors(examples.get("invalid_" + side)))
            except (RecursionError, ValueError, TypeError) as exc:
                errors.append(f"{cid}: {side} schema cannot evaluate: {type(exc).__name__}")
                continue
            if valid_errors:
                errors.append(f"{cid}: positive {side} witness rejected: {valid_errors[0].message}")
            if not invalid_errors:
                errors.append(f"{cid}: negative {side} witness was not rejected")
        request = definitions.get(cid + "_request", {})
        if (request.get("type") != "object"
                or set(request.get("properties", {})) != {"path", "query", "headers", "body"}
                or set(request.get("required", [])) != {"path", "query", "headers", "body"}):
            errors.append(f"{cid}: request must use the four-part closed envelope")
        else:
            path_schema = request["properties"]["path"]
            route_params = set(re.findall(r"\{([a-z_]+)\}", path if isinstance(path, str) else ""))
            if (set(path_schema.get("properties", {})) != route_params
                    or set(path_schema.get("required", [])) != route_params):
                errors.append(f"{cid}: route and required path parameters differ")
            if method == "POST":
                required = request["properties"]["headers"].get("required", [])
                if not {"Idempotency-Key", "X-CSRF-Token"} <= set(required):
                    errors.append(f"{cid}: mutation missing idempotency/CSRF headers")
        if binary:
            contract = row.get("binary_contract")
            if (not isinstance(contract, dict)
                    or set(contract) != {"body", "range_support", "verification", "headers_case"}
                    or not all(_text(v) for v in contract.values())):
                errors.append(f"{cid}: incomplete binary byte-verification contract")
    for cid, count in Counter(ids).items():
        if count > 1:
            errors.append(f"commands: duplicate command {cid}")
    for route, count in Counter(routes).items():
        if count > 1:
            errors.append(f"commands: duplicate route {route}")
    for suffix in ("_request", "_response"):
        owners = {name[:-len(suffix)] for name in definitions if name.endswith(suffix)}
        if owners != set(ids):
            errors.append(f"commands: {suffix} definitions and command population differ")
    return errors
