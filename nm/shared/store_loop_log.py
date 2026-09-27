"""One sealed transactional owner for loop records: the existing matter store."""
from __future__ import annotations

from dataclasses import replace

from nm.act.action_proposal_tool import PreparedActionMutation
from nm.legal_brain.orchestrate.loop_contracts import LoopEvent, LoopIdentity, LoopRecord
from nm.shared.store_port import StaleWrite, StorePort
from nm.work_the_file.deadline_proposals import DeadlineProposalMutation
from nm.work_the_file.private_file_tools import PrivateFileMutation


class MatterLoopLog:
    def __init__(self, store: StorePort, *, advocate_id: str):
        self._store = store
        self._actor = advocate_id

    def _load(self, identity: LoopIdentity):
        matter = self._store.load(identity.matter_id)
        if (matter is None or matter.advocate_id != self._actor
                or identity.advocate_id != self._actor):
            raise PermissionError("the loop record is not available to this actor")
        return matter

    @staticmethod
    def _read(matter, identity: LoopIdentity) -> LoopRecord | None:
        rows = [row for row in matter.loop_records
                if row.identity.turn_id == identity.turn_id]
        if len(rows) > 1:
            raise ValueError("duplicate turn identities in the loop journal")
        if rows and rows[0].identity != identity:
            raise StaleWrite("a saved loop turn has different original instructions or versions")
        if rows:
            return LoopRecord(rows[0].identity, rows[0].events)
        return None

    def read(self, identity: LoopIdentity) -> LoopRecord | None:
        return self._read(self._load(identity), identity)

    def append(self, identity: LoopIdentity, event: LoopEvent) -> LoopRecord:
        return self._append(identity, event)

    def append_mutation(self, identity, event, mutation) -> LoopRecord:
        from nm.legal_brain.orchestrate.loop_contracts import StepKind
        from nm.legal_brain.reason.grounded_file_tools import GroundedReadingMutation
        from nm.legal_brain.reason.source_writes import SourceRequirementMutation
        from nm.work_the_file.file_mutation_contracts import FileMutation

        approved = (FileMutation, SourceRequirementMutation, GroundedReadingMutation,
                    PrivateFileMutation, PreparedActionMutation, DeadlineProposalMutation)
        if (type(mutation) not in approved
                or event.kind is not StepKind.TOOL_RETURNED
                or event.payload.get("mutation_identity") != mutation.identity):
            raise ValueError("a file mutation needs its exact committed tool receipt")
        return self._append(identity, event, mutation)

    def _append(self, identity, event, mutation=None) -> LoopRecord:
        matter = self._load(identity)
        recorded = self._read(matter, identity)
        if recorded is None:
            if matter.version != identity.matter_version:
                raise StaleWrite("the checked matter moved before the loop started")
            recorded = LoopRecord(identity)
        if event.sequence <= len(recorded.events):
            if recorded.events[event.sequence - 1] == event:
                return recorded  # Exact retry, not a second event.
            raise StaleWrite("an event sequence already carries different work")
        if matter.version != identity.matter_version + len(recorded.events):
            raise StaleWrite("the checked file changed outside this loop; re-derive from the file")
        if mutation is not None and (mutation.before != matter
                                     or mutation.advocate_id != self._actor):
            raise StaleWrite("the prepared mutation does not match this complete checked file")
        updated = LoopRecord(identity, (*recorded.events, event))
        records = tuple(row for row in matter.loop_records
                        if row.identity.turn_id != identity.turn_id)
        candidate = mutation.after if mutation is not None else matter
        self._store.commit(replace(candidate, loop_records=(*records, updated),
                                   version=matter.version + 1),
                           expected_version=matter.version)
        return updated
