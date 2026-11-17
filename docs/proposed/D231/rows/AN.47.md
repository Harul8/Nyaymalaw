# AN.47 - 8 Nov 2026: the Acts the owner has checked by their short names (the Evidence Act, the Contract Act, IPC and the rest of pipeline/act_aliases.json) are looked up by those names in the live research, instead of being said not to be held.

Row 282 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

AN.47

## Item

8 Nov 2026: the Acts the owner has checked by their short names (the Evidence Act, the Contract Act, IPC and the rest of pipeline/act_aliases.json) are looked up by those names in the live research, instead of being said not to be held.

## Description

THE OWNER'S WORDS, 8 Nov 2026: "check if there is anything pending for build and complete the build". WHAT WAS PENDING, read from the plan (AN.45 column 3, D108 b and 'STILL OPEN (a)'; AN.46 column 5): of everything open, one item needed building and waited on nothing but the owner's check of the alias list, which the owner made on 7-8 Nov (all 59 entries marked checked): THE CHECKED ALIASES ARE NOT USED BY THE LIVE RESEARCH, so a plan that names 'the Evidence Act' is told no held Act is that name (the held Act is 'Indian Evidence Act, 1872'). The rest is not for building without the owner: the corpus runs (the Act vectors and their swap, the paid naming) are the owner's, with specific authority; the pane is frozen (D60); the 'not built' items of AN.46 each wait on a reason or the owner's word.
DECISIONS (D129-D133 are Claude's, for the owner to correct).
D129. CANDIDATES ONLY. Search already treats a name as a way to propose candidate Acts and never to resolve identity (instrument_candidates). A checked alias now proposes the held Acts it names, in the same way; an alias that names several held Acts keeps every one, so the existing handling of an ambiguous name (the question which Act is meant) takes over. Nothing is resolved by approximate matching; the owner's checked list is the only new word.
D130. THE YEAR. A year written in the name must be the first year of an Act the alias names (else no candidate: the name says an Act we do not name); with no year, every held Act the alias names. No narrowing by the years an Act was in force: the live research has no judgment date, and what was in force on a matter's dates is for the answer.
D131. NAME FIRST. The exact key, then the same title apart from the year, are tried as before; the alias is tried only where both give nothing. So no name that finds an Act today finds a different one.
D132. WHERE IT IS READ. HybridSearcher.local reads pipeline/act_aliases.json beside pipeline/instrument_copies.json, checked entries only, once when the searcher is built. A list that cannot be read, or is not of its schema, means no aliases (a warning in the log) - names resolve as today, search never fails because of it. A changed list takes a restart.
D133. NO NEW CONTRACT. The search record keeps its shape (hybrid_retrieval_v11); a saved record is read as saved and never searched again (P46) - the same as 45f.

## Governs or depends on

AN.45 (D104 the alias list and ActResolver; D108 b; STILL OPEN (a)); AN.35 (35b, named sections read by their number; D30-D33); CLAUDE.md (named Acts resolve by exact identity or checked canonical aliases; approximate matching proposes, never resolves); P46 (saved as saved)

## Status

AGREED in the owner's words (column 3); decisions D129-D133 recorded 8 Nov 2026 before the code. BUILT and pushed 8 Nov 2026: 47a (98b01d5e), 47b (8d1b7eaa). The owner's server was stopped when nm/ was edited, so it takes effect when the owner next starts it. Open: one live turn that names a short form (the Evidence Act, IT Act) to see it searched and read in the answer; browser acceptance. Evidence in column 7.

## Notes

PIECES. Each: trigger / original inputs / admitted output / owner / state effect / failure scope / recovery / observable outcome.
47a nm/shared/citation_contracts.py::instrument_candidates(name, held_keys, aliases=None). Trigger: a name given to search. Inputs: the name, the held instrument keys, the checked-alias index (act_alias_index). Output: the candidate keys, as before, or - only where the name finds none - the held keys of the alias's Acts (D130). Owner: the function (one copy). State effect: none. Failure scope: none (pure). Recovery: aliases=None is today's behaviour. Outcome: 'Evidence Act' proposes indian evidence act 1872.
47b nm/core_engine/retrieval.py: HybridSearcher(collections, aliases=None); local() reads the list (D132); the two places a name meets the held instruments - the Acts a plan names, and the sections a plan names by number (_read_named) - pass it. Trigger: a search naming Acts or sections. State effect: none beyond the search record. Failure scope: an unreadable list affects only alias names. Recovery: no aliases, a warning. Outcome: a plan naming 'Evidence Act s.63' reads section 63 of the Indian Evidence Act instead of 'not held'.
No piece has a model call. Nothing is paid, nothing long is run.

## Column 7

EVIDENCE (8 Nov 2026; no model call, nothing paid, nothing long).
FREE MEASUREMENT against the real register (1,587 kept instruments) and the owner's list (59 entries, all checked, 115 ways of writing): before, 14 of the 115 ways of writing found a held Act by name; after, 111. 97 gained candidates: 86 exactly one Act (the Evidence Act, the Contract Act, IPC, the Constitution...), 11 several, which the existing handling of an ambiguous name turns into the question which Act is meant (IT Act: the Income-tax Act 1961 or the Information Technology Act 2000; LA Act: the Land Acquisition Act 1894 or the 2013 Act; PC Act: 1947 or 1988; JJ Act: 1986, 2000 or 2015; Succession Act: Hindu 1956 or Indian 1925). A name that already found an Act was changed in 0 cases (D131). 4 ways of writing still find nothing, correctly: the Representation of the People Act, 1951 (RP Act, R.P. Act), the Sea Customs Act, 1878 and the Foreign Awards Act, 1961 are not in the register, and are said not to be held. THE REAL SEARCHER: HybridSearcher.local built read-only on the real checkout carries the list (59 entries, 107 spellings once normalised); 'the Evidence Act' proposes indian evidence act 1872.
TESTS: tests/test_a_checked_short_name_proposes_the_act_it_names.py (10) and tests/test_a_checked_short_name_is_searched_and_read_by_its_number.py (10: a short name searched inside the Act it names, a section named under it read by its number and, without the list, 'not held'; checked entries only; an unreadable, malformed or self-contradicting list costs only the short names, with a warning; the owner's real list loads with its 59 entries); 151 related retrieval, research, alias and citation tests pass. NOT RUN: the full suite, a live turn, the browser.
FOR THE OWNER, NOT DECIDED HERE: (1) the list names the codes as judgments write them - the Evidence Act, IPC and the Criminal Procedure Code propose the 1872, 1860 and 1973 enactments only; a plan that means the 2023 replacements names them itself, and what applied on a matter's dates stays the answer's. (2) A changed list takes a restart. (3) The which-Act question for the 11 several-Act spellings is the existing one (AN.37, D87), unchanged.
