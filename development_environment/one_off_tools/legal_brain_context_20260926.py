"""Add the context-management rows, built on how Claude manages context.

OWNER DIRECTION, 26 September 2026: understand how context is managed for
Claude's best models and build those principles into Nyaymalaw's context
management.

WHAT WAS LEARNED, and where. From the Claude API documentation bundled with
this environment (shared/agent-design.md, shared/prompt-caching.md,
shared/model-migration.md): prompt caching is a byte-exact prefix match over
tools, then system, then messages; the history must be append-only, because
editing an earlier turn breaks the cache and, on the newest models, invalidates
the model's earlier thinking; per-turn state is appended, never edited in;
tool search and skills load detail on demand; context editing clears spent tool
results without counting as an edit; compaction summarises -- and the
recommended client-side shape restarts from one summary plus the new turn,
never mid tool round; memory persists across sessions; subagents get their own
context and a cheaper model without breaking the main loop's cache; task
budgets let the model pace itself. Observed in this very session's harness:
deferred tools loaded by search, skills listed by description and read on
demand, oversized tool output saved to a file with a preview, a notice when a
file changed on disk since it was read, and a compaction that left a pointer to
the full transcript.

THE CONFLICT IT EXPOSED, and the refinement. LB-145 said context is "built
fresh each turn". Rebuilding and rewriting history every turn would break the
cache and the model's thinking. So LB-147 refines it: assembled once, extended
by appending, and regenerated from the checked file only at a compaction
(LB-150).

Seven rows, LB-147..153, in L.5 after the rows already there, mirrored into
the Implementation Plan sheet. The mechanism and the proof are the
strengthen tool's, reused rather than copied.
"""
import importlib.util
from pathlib import Path

_here = Path(__file__).with_name("legal_brain_strengthen_20260926.py")
_spec = importlib.util.spec_from_file_location("strengthen", _here)
strengthen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(strengthen)

CLAUDE = "Claude API features the Anthropic adapter may use where the model supports them: "

strengthen.NEW_ROWS = {
    "LB-147": ("L.5", [
        "A stable prefix and an append-only conversation",
        "Within a conversation nothing already sent is rewritten: the principles "
        "and tools form a stable prefix, and every update -- a changed fact, a "
        "reminder, the budget -- is appended.",
        "Get fast, economical turns without the model losing its own earlier "
        "reasoning.",
        "Every model request in a loop.",
        "Order and freeze the prefix: tool definitions in a deterministic order, "
        "then the principles, the advocate memory (LB-151) and the matter brief "
        "as it stood when the conversation began. Nothing volatile goes in it -- "
        "no timestamps, request identifiers or unsorted structures. Within the "
        "conversation the history is append-only: a corrected fact, a change "
        "notice, a per-turn reminder of the remaining budget or the open "
        "questions is appended as a new message, never edited into an earlier "
        "one. On Claude models this keeps the prompt cache and keeps the model's "
        "earlier thinking valid, which editing earlier turns destroys on the "
        "newest models; on other providers the same discipline holds, so the "
        "product depends on no one provider's rules. The brief is regenerated "
        "from the file only at a compaction (LB-150). This refines LB-145: "
        "context is assembled when a conversation begins and extended by "
        "appending, not rewritten each turn.",
        "Consecutive requests in a loop share their whole earlier history byte "
        "for byte.",
        "A request whose earlier history changed is detected by comparing it "
        "with the previous request and logged as a defect, never silently "
        "accepted.",
        "Never put a timestamp, identifier or other volatile value in the "
        "prefix. Never edit or delete an earlier message to update state; "
        "append instead. Never reorder or remove tools mid-conversation.",
        "LB-147-AC1: across a ten-step loop, each request's history is a "
        "byte-identical prefix of the next.\n"
        "LB-147-AC2 (planted): a timestamp injected into the principles is "
        "caught by the prefix comparison.\n"
        "LB-147-AC3: a fact corrected mid-conversation reaches the model as an "
        "appended message, and the earlier message is unchanged.",
        "LB-128, LB-145; backend/nm/ports/model.py. " + CLAUDE +
        "prompt caching, mid-conversation system messages and turn-scoped "
        "reminders. OPEN: the cache hit-rate target, measured on golden runs.",
    ]),
    "LB-148": ("L.5", [
        "Detail loaded on demand: tools and practice-area playbooks",
        "The model starts with a small core and discovers the rest -- tools it "
        "rarely needs, and guidance for the kind of matter in front of it -- "
        "when the matter calls for it.",
        "Have NM bring the right expertise to my matter without burying every "
        "turn in all of it.",
        "The model needs a capability or guidance outside its core set.",
        "Two catalogues, each with a one-line description always in context and "
        "the full content loaded on request. Tools: the core -- read the file, "
        "retrieve, compute, ask, record, check -- is always loaded; the rest -- "
        "curated tables, specialist computations, rarely used lookups -- is found "
        "through a tool-search tool and appended when needed. Practice-area "
        "playbooks: short, owner-edited guidance for a kind of matter -- cheque "
        "dishonour, tenancy eviction, partition, money recovery, bail -- setting "
        "out what an experienced advocate checks first, which provisions and "
        "authorities usually matter, and the common traps; the model reads one "
        "when the matter fits. A playbook is guidance under the principles "
        "(LB-126), never a rule, and every legal statement in it is a pointer "
        "to text that must be retrieved. Loading appends rather than replaces, "
        "so the stable prefix survives (LB-147).",
        "The model has the tools and guidance the matter needs, and not the "
        "rest.",
        "A tool or playbook that cannot be found is reported to the model as "
        "not available; the model continues without it and the gap is logged.",
        "Never let a playbook assert law the loop did not retrieve. Never let a "
        "playbook override a principle or a harness check. Never remove a "
        "loaded tool mid-conversation.",
        "LB-148-AC1: a cheque-dishonour matter loads that playbook and the "
        "pre-institution tool; a tenancy matter loads neither.\n"
        "LB-148-AC2: the core context stays under its declared size with every "
        "catalogue listed.\n"
        "LB-148-AC3 (planted): a playbook line stating a period in days with no "
        "retrievable source is refused by a repository check.",
        "LB-126, LB-129, LB-147; LB-120-125. " + CLAUDE +
        "tool search with deferred loading, and the skills pattern. OPEN: the "
        "first playbooks, and counsel review of each (BK-85-AC3).",
    ]),
    "LB-149": ("L.5", [
        "Spent results cleared, large results paged, everything re-fetchable by locator",
        "Once a tool result has been used and its findings recorded, the raw "
        "result leaves the context and a stub with its locator stays; a large "
        "result arrives as a preview the model pages through.",
        "Keep a long investigation sharp rather than buried in material already "
        "dealt with.",
        "A tool returns a large result, or the context fills with results "
        "already used.",
        "Large results return a preview and a handle: a judgment returns its "
        "headnote, a paragraph index and the paragraphs that matched, and the "
        "model reads further paragraphs by locator. Filtering happens inside "
        "the tool, not in the context: 'authorities on this point binding in "
        "Telangana' returns the few that qualify, with a count of what was "
        "excluded and why. When results have been used and their findings "
        "recorded on the file (LB-142), older raw results are cleared and "
        "replaced by a stub naming the locator and the recorded finding; "
        "because retrieval can be repeated, clearing loses nothing. The "
        "advocate's own words, and the spans a pending claim cites, are never "
        "cleared.",
        "The context holds what is still being worked on; everything cleared "
        "is one locator away.",
        "A cleared result needed again is re-fetched by its locator; if the "
        "source has changed or gone, that is said, never covered with the "
        "stale copy.",
        "Never clear a span a pending claim cites. Never let a filter's "
        "exclusions vanish -- the count and the reason stay. Never clear "
        "without leaving the locator.",
        "LB-149-AC1: a 200-paragraph judgment enters the context as its index "
        "and matched paragraphs, and a further paragraph is read by locator.\n"
        "LB-149-AC2: after clearing, a finding is re-verified by re-fetching "
        "its span through the stub's locator.\n"
        "LB-149-AC3 (planted): clearing a span a pending claim cites is "
        "refused.",
        "LB-105, LB-106, LB-135, LB-142; the search port's expand and passage. "
        + CLAUDE + "context editing that clears tool results, which does not "
        "count as a history edit. OPEN: the clearing threshold.",
    ]),
    "LB-150": ("L.5", [
        "Compaction regenerates the brief from the checked file",
        "When a conversation grows too long it restarts from a brief generated "
        "from the matter file -- not from a model's summary of the chat -- and "
        "the full record stays reachable.",
        "Know that a long matter does not drift: after a long session NM works "
        "from what the file says.",
        "A conversation approaches its context budget; never in the middle of "
        "a tool round.",
        "At a compaction the loop starts a fresh conversation containing only: "
        "the stable prefix; a matter brief regenerated from the structured "
        "file, every line tagged with its source and status (LB-145); a short "
        "handover of the current task written by the model -- open questions, "
        "what it was doing, what it had found -- and checked against the file; "
        "and the new message. Nothing else is replayed. The full transcript and "
        "step log stay on the record and reachable by tool, so the model can "
        "look back rather than rely on its memory of them. The handover may "
        "not introduce a fact that is not on the file.",
        "The model continues the task from the file's current state, with a "
        "handover that names its sources.",
        "A handover that states something the file does not hold is rejected "
        "and regenerated; if it cannot be made faithful, the model continues "
        "from the brief alone and says so.",
        "Never compact mid tool round. Never let a summary of the chat replace "
        "the file as the thing worked from. Never discard the full record.",
        "LB-150-AC1: a matter run past its budget compacts, and a fact from the "
        "first turn is used correctly afterwards.\n"
        "LB-150-AC2 (planted): a handover that alters a date is rejected "
        "against the file.\n"
        "LB-150-AC3: after compaction the model retrieves an earlier turn "
        "verbatim by tool.",
        "LB-135, LB-142, LB-145, LB-147. " + CLAUDE + "server-side compaction "
        "with custom instructions -- but its summary is not harness-checked, so "
        "the harness-controlled form here is preferred for matter state, and a "
        "native summary, where used, is checked the same way. OPEN: the "
        "compaction threshold.",
    ]),
    "LB-151": ("L.5", [
        "The advocate's own memory, kept apart from every matter",
        "What NM learns about how the advocate works -- their courts, their "
        "preferences, how they like advice set out -- is remembered across "
        "matters, with consent, and never mixed with any client's facts.",
        "Not have to tell NM the same things about how I work on every matter.",
        "The advocate states a working preference, or approves one NM suggests.",
        "An advocate memory, separate from every matter file: the courts they "
        "appear in, the preferred form and length of advice, drafting "
        "conventions, standing instructions. Written only with the advocate's "
        "approval, shown to them, editable and deletable. Loaded into the "
        "stable prefix when a conversation begins (LB-147). It may shape how "
        "NM works and presents; it may never supply a fact or a legal "
        "proposition in an answer.",
        "The advocate's standing preferences apply across matters without being "
        "repeated.",
        "An unreadable memory is set aside with a notice, and the matter "
        "proceeds on defaults.",
        "Never store a client's facts, names or documents in the advocate "
        "memory. Never carry anything from one matter into another. Never write "
        "to it without the advocate's approval.",
        "LB-151-AC1: a stated preference for short advice with the authorities "
        "at the end applies on the next matter.\n"
        "LB-151-AC2 (planted): an attempt to record a client's name in the "
        "advocate memory is refused.\n"
        "LB-151-AC3: the advocate can view and delete every entry.",
        "LB-12, OM-P12, A.9; the professional directory. " + CLAUDE +
        "the memory tool pattern, a directory the harness implements. OPEN: "
        "retention and deletion rules for the memory.",
    ]),
    "LB-152": ("L.5", [
        "The file in context is never staler than the file",
        "Every read of the matter carries its version; a write based on an "
        "older read is refused; a change made elsewhere mid-conversation is "
        "announced to the model.",
        "Know that NM never acts on a version of my file I have already "
        "changed.",
        "The model reads or writes the matter file, or the file changes during "
        "a conversation.",
        "Each read returns the file version it reflects. A write carries the "
        "version it was based on and is refused if the file has moved since, "
        "returning what changed so the model can re-read and redo -- the "
        "G-STALE discipline, extended to the model's own writes. A change made "
        "in another tab, by the advocate, or by an earlier step is appended to "
        "the conversation as a change notice naming what moved (LB-147), so "
        "the model does not keep reasoning from a value that has been "
        "replaced.",
        "No write lands on a file the model has not seen in its current state.",
        "A refused write returns to the model with what changed; repeated "
        "refusals end the turn with the conflict disclosed.",
        "Never let a write overwrite a change the model has not seen. Never "
        "drop a change notice.",
        "LB-152-AC1 (planted): a fact corrected in another tab mid-turn causes "
        "the model's stale write to be refused and redone.\n"
        "LB-152-AC2: a change notice appears in the conversation before the "
        "model's next step.",
        "G-STALE, G-CASCADE; LB-63, LB-142, LB-147.",
    ]),
    "LB-153": ("L.5", [
        "One context policy on every provider; the budget visible; one model per loop",
        "The harness owns how context is managed and provider features only "
        "make it faster or cheaper; the model sees its remaining budget; the "
        "main loop keeps one model, and cheaper models work only in sub-loops.",
        "Get the same quality of reasoning whichever model serves me, at a "
        "known cost.",
        "Every loop, on every supported provider.",
        "Clearing, compaction, the brief, the stable prefix and the advocate "
        "memory are implemented in the harness, so they behave the same on "
        "Opus, Fable or an OpenAI model. Where a provider offers a native "
        "equivalent, the adapter may use it, provided the result passes the "
        "same checks. The model is told its remaining budget as the loop runs, "
        "so it paces itself and finishes rather than being cut off. The main "
        "loop stays on one model for a conversation, because switching loses "
        "its cache and its earlier thinking; cheaper models -- the verifier, "
        "research readers -- run in their own sub-loops (LB-136, LB-141).",
        "The same golden matter behaves the same on each provider within a "
        "measured tolerance, with its cost recorded.",
        "A provider without a native feature falls back to the harness's own "
        "implementation, never to no management at all.",
        "Never let a provider feature bypass a harness check. Never switch the "
        "main loop's model mid-conversation. Never hide a budget stop.",
        "LB-153-AC1: the replay suite (LB-146) passes through both the "
        "Anthropic and the OpenAI adapters.\n"
        "LB-153-AC2: a loop told its budget finishes with a disclosed partial "
        "result rather than being cut off.\n"
        "LB-153-AC3: a golden comparison records cache hit rate and cost per "
        "completed task for each provider.",
        "LB-127, LB-128, LB-136, LB-141, LB-146; ModelPort.context_budget. "
        + CLAUDE + "task budgets. OPEN: per-provider budgets.",
    ]),
}

strengthen.HEADER_ADDITIONS = {
    "L.5": (" Within a conversation the history is append-only behind a stable prefix; detail loads on demand; "
            "spent results are cleared and re-fetchable; compaction regenerates the brief from the checked file "
            "(LB-147–153)."),
}
strengthen.NEW_NOTE_RANGE = ("LB-126–146", "LB-126–153")

if __name__ == "__main__":
    raise SystemExit(strengthen.main())
