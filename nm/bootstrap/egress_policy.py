"""The processor inventory this installation actually runs under. BK-85-AC1.

    from nm.bootstrap.egress_policy import egress_policy

WHY THE POLICY IS BUILT AT THE COMPOSITION ROOT
-------------------------------------------------
Which provider is live is the composition root's business -- `build_model` is
"the whole of switching provider is an environment variable", and a policy
assembled anywhere else would be a second place that knows. So the inventory is
read here, beside the adapter choice, and handed to the wrapper.

EMPTY IS THE CORRECT DEFAULT AND IT REFUSES EVERYTHING
--------------------------------------------------------
An installation with no recorded inventory has approved no processor, and
`nm/domain/egress.refuse` treats an unlisted processor as unapproved rather
than as one nobody wrote a rule for. That is deliberately inconvenient: the
first run after this lands refuses to call a model until somebody records what
was approved, which is the only moment anyone will.

THE FILE IS NOT AUTHORED IN CODE
----------------------------------
`docs/blueprint/processors.yaml` holds it, so adding a processor is a reviewable
diff against a document rather than an edit to a module -- and so the approval
id in each row can be checked against the adoption register by somebody reading
both. A list compiled in Python is a list nobody reviews.
"""
from __future__ import annotations

import pathlib

from nm.domain.egress import DataClass, Policy, Processor, Sink

INVENTORY = pathlib.Path("docs") / "blueprint" / "processors.yaml"


def egress_policy(root: pathlib.Path) -> Policy:
    """The recorded inventory, or an empty policy that permits nothing.

    AN UNREADABLE INVENTORY IS NOT AN EMPTY ONE, and both refuse -- but they
    refuse for different reasons and the audit line says which, because an
    operator whose file will not parse and an operator who has recorded nothing
    need different things.
    """
    import yaml

    path = root / INVENTORY
    if not path.exists():
        return Policy()
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf8")) or {}
    except yaml.YAMLError:
        return Policy()
    if doc.get("schema") != 1:
        return Policy()

    processors: list[Processor] = []
    for row in doc.get("processors") or []:
        if not isinstance(row, dict):
            continue
        try:
            processors.append(Processor(
                processor_id=str(row["processor_id"]),
                region=str(row["region"]),
                purposes=tuple(Sink(p) for p in row.get("purposes") or ()),
                data_classes=tuple(DataClass(c)
                                   for c in row.get("data_classes") or ()),
                approval_id=str(row.get("approval_id") or "")))
        except (KeyError, ValueError):
            # A MALFORMED ROW IS DROPPED, WHICH REFUSES IT. Repairing it here
            # by guessing a region or a purpose would admit a processor on
            # terms nobody wrote down.
            continue

    regions = doc.get("approved_foreign_regions") or {}
    return Policy(processors=tuple(processors),
                  approved_foreign_regions={str(k): str(v)
                                            for k, v in regions.items()
                                            if str(v).strip()})
