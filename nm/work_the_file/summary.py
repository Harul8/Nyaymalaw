"""Current sealed relevance proofs forwarded to the existing file summary owner."""
from nm.work_the_file.summary_contracts import MatterSummary, unbuildable
from nm.work_the_file.summary_contracts import build as domain_build

__all__ = ["MatterSummary", "build", "unbuildable"]


def build(matter, *args, source_current=None, checklist_projections=None, **kwargs):
    from nm.Archives.legal_brain.reason.requirements import checked_file_projections

    if "classifications" in kwargs:
        raise ValueError("Summary relevance proofs come only from this file's saved reviews")
    projections = checked_file_projections(matter, checklist_projections,
                                           source_current=source_current)
    result = domain_build(matter, *args, **kwargs)
    for thread in result.threads:
        thread["requirements"] = projections[thread["thread_id"]].summary()
    return result
