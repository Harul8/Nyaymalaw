"""A research note: one saved answer as a document the advocate keeps or sends (owner
decisions, 15 Oct 2026: Word by default, PDF as an option).

Built by code from the saved turn after its replay checks, with no model call:
nothing is added, summarised or reworded. The question is shown exactly as sent with
the documents that went with it, the answer in its order with its dispute headings,
each paragraph followed by the numbers of the sources it cites, and each source quoted
exactly as saved (a judgment's stray line breaks closed up); passages of one provision,
judgment paragraph or document page share its number. The Word file is written here directly (a .docx is zipped XML); the
PDF is the browser's print of the same note.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

from nm.shared.clock_contracts import IST

CONTRACT = "core_research_note_v1"
#: How a source is described; a judgment passage instead by what the court was doing in it.
KINDS = {"provision": "Statute", "judgment": "Judgment", "document": "Document you sent"}
PROVENANCE = ("Prepared by Nyaymalaw from the answer saved on {when}. Each source is quoted exactly as "
              "it is held, or as it was read from your document. Check that the law is current and "
              "applies before relying on it.")


class NoteUnavailable(ValueError):
    """This saved turn has no answer to keep as a note."""


def _when(response):
    moment = datetime.fromisoformat(response["at"]).astimezone(IST)
    return moment, f"{moment.day} {moment:%B %Y}, {moment:%I:%M %p}".replace(" 0", " ") + " IST"


def note(row, *, prepared_for):
    """The note of one checked saved turn."""
    response = row["response"]
    elements = response.get("elements") or []
    if not any(element.get("kind") != "HEADING" and element.get("text", "").strip() for element in elements):
        raise NoteUnavailable("This answer has nothing to keep as a research note.")
    documents = row.get("documents") or []
    pages = {f"{row['turn_id']}:d{index}p{page['number']}": (page, bool(document.get("recording")))
             for index, document in enumerate(documents, 1) for page in document["pages"]}
    numbers, sources, blocks, quoted = {}, [], [], set()
    for element in elements:
        if element.get("kind") == "HEADING":
            blocks.append({"kind": "heading", "text": element["text"]})
            continue
        refs = []
        for source in element.get("sources") or []:
            title = source.get("title") or source.get("label") or ""
            key = (source["kind"], title, source.get("locator") or "")
            if key not in numbers:
                numbers[key] = len(sources) + 1
                recording = pages.get(source["id"], (None, False))[1]
                described = ((source.get("qualification") or "").rstrip(".")
                             if source["kind"] == "judgment" else
                             "Voice note you sent" if recording else KINDS.get(source["kind"], source["kind"]))
                sources.append({"number": numbers[key], "kind": source["kind"], "title": title,
                                "locator": key[2], "described": described, "read_by_ai": False,
                                "recording": recording, "passages": []})
            entry = sources[numbers[key] - 1]
            if source["id"] not in quoted:
                quoted.add(source["id"])
                # A stored judgment breaks lines mid-sentence where its source page did;
                # its words are kept and closed up. Statute clauses and document pages
                # keep their own line breaks.
                text = source["text"]
                entry["passages"].append(" ".join(text.split()) if source["kind"] == "judgment" else text)
                page = pages.get(source["id"], (None, False))[0]
                entry["read_by_ai"] |= bool(page and page["read_by"] == "ai")
            if numbers[key] not in refs:
                refs.append(numbers[key])
        blocks.append({"kind": "paragraph", "text": element["text"], "refs": refs})
    for source in sources:
        source["heading"] = _source_heading(source)
    moment, shown = _when(response)
    words = re.sub(r"[^\w\s-]", "", row["message"], flags=re.UNICODE).split()
    stem = " ".join(words[:8])[:60].strip() or "answer"
    return {"contract": CONTRACT, "title": "Research note", "question": row["message"],
            "documents": [{"name": document["name"], "pages_read": len(document["pages"]),
                           "pages_unread": len(document["unread"]),
                           "recording": bool(document.get("recording"))} for document in documents],
            "prepared_for": prepared_for, "prepared_at": shown, "blocks": blocks, "sources": sources,
            "provenance": PROVENANCE.format(when=shown),
            "file_name": f"Research note {moment:%Y-%m-%d} - {stem}"}


# --- the Word file ----------------------------------------------------------------

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _runs(text, properties=""):
    """Text as Word runs, its line breaks kept."""
    parts = []
    for index, line in enumerate(_NOT_XML.sub("", text).split("\n")):
        if index:
            parts.append(f"<w:r>{properties}<w:br/></w:r>")
        if line:
            parts.append(f'<w:r>{properties}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>')
    return "".join(parts)


def _paragraph(style, text, extra=""):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{_runs(text)}{extra}</w:p>'


def _source_heading(source):
    locator = source["locator"]
    if source["kind"] == "judgment" and locator.isdecimal():
        locator = f"para {locator}"
    name = " · ".join(part for part in (source["title"], locator) if part)
    scan = ("" if not source["read_by_ai"] else
            " (transcribed by AI)" if source.get("recording") else " (read by AI from a scan)")
    return f"[{source['number']}] {name}" + (f" — {source['described']}" if source["described"] else "") + scan


def _document_xml(note):
    body = [_paragraph("Title", note["title"]),
            _paragraph("Meta", f"Prepared for {note['prepared_for']} · {note['prepared_at']}"),
            _paragraph("Heading1", "Question"), _paragraph("Quote", note["question"])]
    if note["documents"]:
        body.append(_paragraph("Heading2", "Documents sent with it"))
        for document in note["documents"]:
            unread = f", {document['pages_unread']} not read" if document["pages_unread"] else ""
            if document["recording"]:
                heard = "transcribed" if document["pages_read"] else "not transcribed"
                body.append(_paragraph("Normal", f"• {document['name']} — recording, {heard}"))
                continue
            body.append(_paragraph("Normal", f"• {document['name']} — {document['pages_read']} "
                                             f"page{'s' if document['pages_read'] != 1 else ''} read{unread}"))
    body.append(_paragraph("Heading1", "Answer"))
    for block in note["blocks"]:
        if block["kind"] == "heading":
            body.append(_paragraph("Heading2", block["text"]))
            continue
        refs = ("" if not block["refs"] else _runs(" [" + ", ".join(map(str, block["refs"])) + "]",
                                                   '<w:rPr><w:color w:val="555555"/><w:sz w:val="18"/></w:rPr>'))
        body.append(_paragraph("Normal", block["text"], refs))
    if note["sources"]:
        body.append(_paragraph("Heading1", "Sources"))
        for source in note["sources"]:
            body.append(_paragraph("SourceTitle", source["heading"]))
            body.extend(_paragraph("Quote", passage) for passage in source["passages"])
    body.append(_paragraph("Meta", note["provenance"]))
    section = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1304" '
               'w:bottom="1418" w:left="1304" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {_W}><w:body>'
            + "".join(body) + section + "</w:body></w:document>")


_STYLES = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {_W}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Nirmala UI"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-IN"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="80"/></w:pPr><w:rPr><w:rFonts w:ascii="Cambria" w:hAnsi="Cambria"/><w:color w:val="185748"/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="185748"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="SourceTitle"><w:name w:val="Source title"/><w:basedOn w:val="Normal"/><w:next w:val="Quote"/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/></w:pPr><w:rPr><w:b/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:pPr><w:pBdr><w:left w:val="single" w:sz="12" w:space="8" w:color="BBBBBB"/></w:pBdr><w:ind w:left="397"/></w:pPr><w:rPr><w:color w:val="333333"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Meta"><w:name w:val="Meta"/><w:basedOn w:val="Normal"/><w:rPr><w:color w:val="666666"/><w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr></w:style>
</w:styles>'''

_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'''

_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''

_DOCUMENT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''

_APP = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Nyaymalaw</Application></Properties>'''


def _core(note, created):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{escape(_NOT_XML.sub("", note["file_name"]))}</dc:title><dc:creator>Nyaymalaw</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created></cp:coreProperties>')


def docx(note, saved_at):
    """The note as a Word file; the same note always gives the same bytes."""
    created = datetime.fromisoformat(saved_at).astimezone(IST).strftime("%Y-%m-%dT%H:%M:%S+05:30")
    parts = [("[Content_Types].xml", _TYPES), ("_rels/.rels", _RELS),
             ("word/_rels/document.xml.rels", _DOCUMENT_RELS), ("word/document.xml", _document_xml(note)),
             ("word/styles.xml", _STYLES), ("docProps/core.xml", _core(note, created)), ("docProps/app.xml", _APP)]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))
    return out.getvalue()
