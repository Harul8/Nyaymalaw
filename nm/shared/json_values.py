"""Exact typed JSON-value equality for evidence, never Python coercion."""
from __future__ import annotations


def same_json_value(actual, cited):
    """Compare complete decoded values without conflating booleans and numbers.

    Both inputs are decoded, bounded JSON owned by the calling boundary. Object
    order is immaterial; array order, scalar type and every member are material.
    Iteration also avoids a second recursion limit while checking nested data.
    """
    pending = [(actual, cited)]
    while pending:
        actual, cited = pending.pop()
        if type(actual) is not type(cited):
            return False
        if isinstance(actual, dict):
            if actual.keys() != cited.keys():
                return False
            pending.extend((value, cited[key]) for key, value in actual.items())
        elif isinstance(actual, list):
            if len(actual) != len(cited):
                return False
            pending.extend(zip(actual, cited, strict=True))
        elif actual != cited:
            return False
    return True
