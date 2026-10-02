# New legal brain: served conversation boundary

`/api/turn` uses `BrainService`. It does not construct or dispatch the archived
turn engine. New matter opens an empty chat without creating a file. The first
successful message saves an attributed conversation under a stable chat ID.
The matter board remains hidden until the interpretation proposes concrete
opening details grounded in the attributed conversation. Those details are marked
provisional. A later message can supply the missing context.

`conversation.interpret` makes **one model call per new message** for requests,
their relation to existing work, an immediate reply or consequential
clarification, a proposed opening, and whether the latest message contributes
legal material. When it does, or when an opening is proposed, two focused
readers run **in parallel**: `disputes.extract_disputes` identifies independently
contestable disputes, while `material.extract_details` identifies other
materially significant events, circumstances, positions, objectives, evidence,
procedure, and risks. Thus a substantive turn uses three model calls in two
sequential stages. All readers receive the full attributed conversation and use
stable Message, Purpose, Look for, and Outcome prompts; matter-specific content
stays in the variable input. Pure greetings and diversions need only the first
call. An exact saved replay makes no call. Each reader receives the complete
conversation as ordered, addressed source spans. The model selects span IDs;
the service inserts exact saved words for latest and earlier citations. A
rejected structured response gets one feedback-guided correction and is
validated again before any write. This adds calls only on a failed read, up to
six in the worst substantive turn if all three reads need correction. Each
material proposal keeps exact user words, any earlier words needed for context,
matter scope, basis, importance, and relation to prior content. The service
saves proposals with their source turn and returns them as `material`. It does
not admit them as matter facts. A first message has an empty earlier
conversation, so it cannot
be classified as a continuation or aside. `history.from_turns` refuses
gaps, unreadable replies, and unestablished releases rather than silently
omitting them. Conversation words are context, not admitted matter facts.
If correction still fails, the turn is withheld without a server write, and
the browser keeps the brief for a same-turn retry with a plain status message.
`metrics.llm_calls` counts logical model invocations on this request;
`metrics.provider_retries` reports additional transport attempts separately.
An exact replay reports zero for both. A full-context overflow is identified
as nonretryable because resending unchanged words cannot make them fit.

Substantive legal research and document review are not yet executed by this
new brain. A request for them receives a specific interim response from the
conversation read and is marked blocked; an unchecked model-written legal
answer is not released as completed work. This does not add a model call. A
source-aware work path and chat-first document attachment
path are still needed before those requests can be fulfilled. Pending chats
appear in the authenticated chat list, can be recovered by chat ID, and cannot
enter matter-only upload or board paths.
