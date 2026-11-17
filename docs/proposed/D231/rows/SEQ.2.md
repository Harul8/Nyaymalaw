# SEQ.2 - Citation and statute identity

Row 159 of the 'Advocate build plan' sheet, written out by plan_export.py. The sheet is the record (P7).

## ID

SEQ.2

## Item

Citation and statute identity

## Description

Integrate retained E1 behind the core. Resolve exact judgment and Act/provision identity; read back full relevant words and source version. Preserve ambiguity and separate lookup, name, quotation and legal-validity status. Cover statute references before legal answers display them. Check an NM-generated citation as strictly as an advocate-supplied one.

## Governs or depends on

SEQ.1; E1/S1; P3/P18; J2

## Status

Integrated in fresh review/render v2 and source pane; browser acceptance remains open.

## Notes

Selected sources receive separate saved case lookup, name, quotation and provision-readback checks. A positive source mismatch withholds before save; unknown lookup is distinct. Pane presents authenticated unit/source inspection without blessing retrieval as Found. 47 endpoint and 10 UI checks; no added model calls. Legal currency and actual browser acceptance remain open.

## Column 7

2026-10-16 OPEN ITEMS ROUND, ITEMS (d) AND (m): PROVISION IDENTITY DEFECTS IN THE HELD CORPUS (read-only measurement; nothing changed). Store inspected: the provision passage store chunks.db (doc_type bare_act, 416,571 passages, revision 794afef3979327ff) and the held NI Act text. (1) Repeated identities: 1,030 of 3,211 held Acts and Rules give one chunk identity to different passages (76,913 passages, 18%); e.g. the Income Tax Act has 17 passages identified as section 1, the Apprenticeship Rules 408. Search correctly refuses to guess a parent when an identity repeats ('Source chunk identity is missing or ambiguous within its Act'), so such a clause is ranked and shown without its main section, recorded as a coverage gap; this is the source of the 'Search stage degraded: provision context' log lines. (2) Mis-filed sections: in the NI Act the rows identified as sections 139 and 146 hold only the headings from the Act's table of contents, while the real text of sections 137-146 is filed as 'Schedule I' passages (the table of contents ends with 'SCHEDULE.-[Enactments repealed]' and the parser treated what follows as the schedule); 6,529 passages in 98 Acts carry schedule identities, some real schedules and some mis-filed sections. Answers therefore cite 'Schedule SCHEDULE I 139' for the presumption. Mechanism: the corpus build pipeline's section and identity assignment (not in this repository; only its outputs are held under legal_database/vector_store). Code cannot safely relabel these (legal identity is never resolved by approximation). Repair needs a corpus rebuild of provision identities and parents, which requires the owner's specific authority; proposed to the owner with effects and cost before any action. Not done: any corpus change.
