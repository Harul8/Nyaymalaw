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
`backend/nm/domain/egress.refuse` treats an unlisted processor as unapproved rather
than as one nobody wrote a rule for. That is deliberately inconvenient: the
first run after this lands refuses to call a model until somebody records what
was approved, which is the only moment anyone will.

THE INVENTORY RESTRICTS; IT CANNOT SIGN ITS OWN APPROVAL
------------------------------------------------------
`docs/blueprint/processors.yaml` owns permitted purposes and data classes. A
nonempty approval ID in that file is not authenticated authority. This build
supports the controlled-local profile only: the concrete recipients wired here
have no external service. External dispatch requires the future authenticated
scoped approval integration; neither an authored ID nor a foreign-region note
can switch it on. Direct Policy fixtures remain policy-unit tests, not runtime
configuration or evidence of any real approval.
"""
from __future__ import annotations

import pathlib

from nm.domain.egress import HOME_REGION, DataClass, Policy, Processor, Sink

INVENTORY = pathlib.Path("docs") / "blueprint" / "processors.yaml"

# One catalogue of concrete built local receivers. Composition imports these
# identities; this does not duplicate the inventory's purposes or permissions.
SCRIPTED_PROCESSOR = "scripted"
STORAGE_PROCESSOR = "local-disk"
INDEX_PROCESSOR = "local-index"
#: The sealed local outbox account mail is written to (F-A-03). In-process, like
#: the others: a message lands on this installation's disk and reaches no
#: mailbox. A real mail provider is an external recipient, and this build admits
#: none until the authenticated approval integration exists.
OUTBOX_PROCESSOR = "local-outbox"
#: The speech model dictation is transcribed by (F-C-02), running in this
#: process. An outside speech service is an external recipient of client material,
#: and this build admits none until the authenticated approval integration exists.
TRANSCRIPTION_PROCESSOR = "local-speech"
CONTROLLED_LOCAL_PROCESSORS = frozenset({
    SCRIPTED_PROCESSOR, STORAGE_PROCESSOR, INDEX_PROCESSOR, OUTBOX_PROCESSOR,
    TRANSCRIPTION_PROCESSOR,
})
LOCAL_BASIS = "IN-PROCESS-NO-EGRESS"


def _controlled_local(processor: Processor) -> bool:
    return (processor.processor_id in CONTROLLED_LOCAL_PROCESSORS
            and processor.region == HOME_REGION
            and processor.approval_id == LOCAL_BASIS)


def _strings(value: object) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(member, str) and bool(member.strip()) for member in value)
            and len(value) == len(set(value)))


def egress_policy(root: pathlib.Path) -> Policy:
    """The recorded inventory, or an empty policy that permits nothing.

    Unavailable, malformed and empty remain distinguishable. Strictly parse
    before admitting any row; duplicate identity is not a first-row-wins rule.
    """
    import yaml

    path = root / INVENTORY
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf8"))
    except FileNotFoundError:
        return Policy(problems=("processor inventory is absent",))
    except (OSError, UnicodeError):
        return Policy(problems=("processor inventory is unreadable",))
    except yaml.YAMLError:
        return Policy(problems=("processor inventory YAML is malformed",))
    if (not isinstance(doc, dict)
            or set(doc) != {"schema", "processors", "approved_foreign_regions"}
            or type(doc["schema"]) is not int or doc["schema"] != 1
            or not isinstance(doc["processors"], list)
            or not isinstance(doc["approved_foreign_regions"], dict)):
        return Policy(problems=("processor inventory shape is invalid",))
    regions = doc["approved_foreign_regions"]
    if any(not isinstance(key, str) or not key.strip()
           or not isinstance(value, str) or not value.strip()
           for key, value in regions.items()):
        return Policy(problems=("processor region review shape is invalid",))

    processors: list[Processor] = []
    seen: set[str] = set()
    for row in doc["processors"]:
        if (not isinstance(row, dict)
                or set(row) != {"processor_id", "region", "purposes", "data_classes",
                                "approval_id"}
                or any(not isinstance(row[key], str) or not row[key].strip()
                       for key in ("processor_id", "region", "approval_id"))
                or not _strings(row["purposes"]) or not _strings(row["data_classes"])):
            return Policy(problems=("processor inventory row shape is invalid",))
        if row["processor_id"] in seen:
            return Policy(problems=("processor inventory contains duplicate identities",))
        seen.add(row["processor_id"])
        try:
            processor = Processor(
                processor_id=row["processor_id"], region=row["region"],
                purposes=tuple(Sink(p) for p in row["purposes"]),
                data_classes=tuple(DataClass(c) for c in row["data_classes"]),
                approval_id=row["approval_id"])
        except ValueError:
            return Policy(problems=("processor inventory classification is invalid",))
        if _controlled_local(processor):
            processors.append(processor)

    # Foreign-region strings and external approval IDs are claims that this
    # runtime cannot yet authenticate. They confer no permission, even for a
    # recipient otherwise named like a built local adapter.
    return Policy(processors=tuple(processors))
