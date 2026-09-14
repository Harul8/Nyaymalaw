"""Fresh safe YAML decoding for control-plane documents; never an evidence cache."""
from __future__ import annotations

import yaml


def safe_load(stream):
    """Use the installed safe parser, with the same safe Python fallback.

    Both loaders use PyYAML's safe constructors and implicit scalar types.
    There is deliberately no path, mtime, parsed-object or verdict cache:
    every call consumes its supplied bytes, including successive mutations.
    """
    return yaml.load(stream, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
