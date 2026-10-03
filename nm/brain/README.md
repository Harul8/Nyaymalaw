# Served legal brain

`/api/turn` runs `BrainService`. New matter opens an empty central chat with
no form, matter code or board. A successful first message is stored under a
stable chat identity. A concrete, source-checked opening reveals the board;
greetings and general questions can remain recoverable pending chats.

The complete attributed transcript is retained and supplied to each reader.
Every stable prompt separates Message, Purpose, Look for and Outcome. Matter
data and retrieved documents are input, never instructions. Source IDs resolve
to exact saved words; interpretations remain proposals, not proved facts or
permission for an external action. Missing context or an oversized transcript
is refused explicitly instead of silently trimmed.

## Turn ownership

1. `conversation.interpret` owns requests, scope, urgency and whether the turn
   contributes legal material. It preserves mixed requests and diversions.
2. `disputes` identifies independently contestable issues; `material` captures
   other significant propositions and their relationship to saved material.
   Explicit saved-record links carry their original source automatically, plus
   selected context. Independent checks decide whether proposals are faithful.
   A dispute title is concise, not necessarily verbatim; identification does
   not establish merits.
3. `legal_requirements` decomposes due disputes into complementary queries.
   The corpus adapter searches Act and judgment passages using hybrid retrieval
   and reranking. A reader proposes requirements; an independent check examines
   each complete item, short label, citations and material links. Only checked
   items appear under disputes. Applicability and incomplete search remain
   explicit; reported documents are not verified documents.
4. `continuation` uses those records, passages and the whole conversation to
   answer the immediate request, explain supported uncertainty, select useful
   unanswered questions and assess scoped-task sufficiency. It does not repeat
   classification or extraction. A separate review checks each complete request
   unit, including question premises, recommendations and completion claims.
   Unsupported units are withheld while valid peers survive.
5. One atomic commit saves the user message, released response, material,
   research and coverage. An exact replay returns the saved result without
   re-admitting input or calling a model. Authentication is checked before save.

The continuation asks sensitive questions with a supported purpose, acknowledges
expressed concern proportionately, tests competing explanations without
accusing anyone, and challenges its own interpretation. Earlier answers and
unavailable material must be considered before asking again. Scoped completion
does not close a matter or authorise action.

## Model calls

Normal calls vary with the work actually due:

| Activity | Calls | Input and output |
| --- | ---: | --- |
| Interpret | 1 | Full transcript and latest words → requests, scope and reading need |
| Dispute extraction | 1 when material is read | Full context and active disputes → attributed proposals |
| Dispute check | 1 when proposals exist | Proposals and sources → independent verdicts |
| Detail extraction | 1 when material is read | Full context and disputes → attributed material |
| Detail/opening check | 1 when either exists | Proposals and sources → independent verdicts |
| Search decomposition | 1 per context-fitting due batch | Disputes/material → up to four distinct queries per dispute |
| Corpus search/rerank | 0 generative calls | Queries → candidates and coverage |
| Passage reading | 1 per context-fitting batch | Candidates and context → gathering proposals |
| Source support check | 1 per context-fitting nonempty batch | Complete proposals and passages → retain/withhold/unread |
| Continuation | 1 when substantive work remains | Full context, records and checked sources → response units |
| Continuation check | 1 when units exist | Complete units and sources → independent release verdicts |

A plain greeting or nonlegal diversion normally costs one call; a checked
substantive continuation with unchanged material/research normally costs three.
Material and research calls are conditional, not a fixed per-message intake
pipeline. Context-fitting batches and per-dispute isolation can add calls.
Readers allow one feedback correction. Verifiers retain valid peer verdicts and
retry only unresolved units once; provider outages do not trigger item-by-item
retry cascades. A rejected continuation gets at most one replacement generation
and another independent check. Independent review uses the configured judge
model; a downgraded routine result is not an independent verdict.

`metrics.llm_calls` and content-free `model_calls` receipts report actual service
calls, operations, tiers, timing and token usage. `provider_retries` separately
counts transport attempts. Replays report zero. There is no additional tone,
empathy or personality classifier.

## Source readback and failure boundaries

Each released block keeps authoritative source references. The authenticated
brain-source reader reopens the exact saved snapshot, with reported/checked
qualifications, independently of later corpus availability. It verifies source
identity, ownership, digest and the released block before returning text. Source
links are grouped beneath each response block; the reading pane has a fixed
heading and Close control with a scrolling body.

Failures are isolated at the smallest independent unit. Valid research and
response units survive rejected peers, with explicit missing coverage. A failed
core read cannot be replaced with an empty result and presented as complete.
Untrustworthy history, identity, attribution, source ownership or commit
integrity stops the whole save. User-facing recovery explains whether the brief
was saved; internal validation diagnostics are not shown as user instructions.
