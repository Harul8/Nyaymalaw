const d = require('docx');
const {
  Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, AlignmentType, BorderStyle, LevelFormat,
} = d;

const INK = '1A1A1A';
const ACCENT = '0F4C5C';
const MUTED = '5C6670';
const SIGNAL = '96382F';
const WASH = 'EDF1F2';
const WASH2 = 'F5F7F8';
const RULE = 'C9D2D6';

const CONTENT_W = 9360; // 6.5in in DXA

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 480, after: 200 },
    children: [new TextRun({ text, bold: true, size: 34, color: ACCENT, font: 'Georgia' })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 340, after: 140 },
    children: [new TextRun({ text, bold: true, size: 26, color: INK, font: 'Georgia' })],
  });
}

function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 260, after: 100 },
    children: [new TextRun({ text, bold: true, size: 22, color: ACCENT })],
  });
}

function h4(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_4,
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text, bold: true, size: 20, color: INK })],
  });
}

// Rich text: **bold**, *italic*, `code`
function runs(text, opts = {}) {
  const base = { size: opts.size || 20, color: opts.color || INK, font: opts.font };
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ ...base, text: text.slice(last, m.index) }));
    const tok = m[0];
    if (tok.startsWith('**')) out.push(new TextRun({ ...base, text: tok.slice(2, -2), bold: true }));
    else if (tok.startsWith('`')) out.push(new TextRun({ ...base, text: tok.slice(1, -1), font: 'Consolas', size: base.size - 2, color: ACCENT }));
    else out.push(new TextRun({ ...base, text: tok.slice(1, -1), italics: true }));
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(new TextRun({ ...base, text: text.slice(last) }));
  return out;
}

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after === undefined ? 140 : opts.after, line: 276 },
    alignment: opts.align,
    indent: opts.indent,
    children: runs(text, opts),
  });
}

function callout(text, color) {
  return new Paragraph({
    spacing: { before: 140, after: 160 },
    indent: { left: 240 },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: color || ACCENT, space: 10 } },
    children: runs(text, { size: 20 }),
  });
}

function bullet(text, level = 0) {
  return new Paragraph({
    numbering: { reference: 'nm-bullets', level },
    spacing: { after: 70, line: 276 },
    children: runs(text),
  });
}

function num(text, level = 0) {
  return new Paragraph({
    numbering: { reference: 'nm-numbers', level },
    spacing: { after: 70, line: 276 },
    children: runs(text),
  });
}

function cell(text, o = {}) {
  return new TableCell({
    width: { size: o.w, type: WidthType.DXA },
    shading: o.fill ? { type: ShadingType.CLEAR, fill: o.fill, color: 'auto' } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    verticalAlign: d.VerticalAlign.TOP,
    columnSpan: o.span,
    children: (Array.isArray(text) ? text : [text]).map((t) =>
      new Paragraph({
        spacing: { after: 0, line: 264 },
        children: runs(String(t), { size: o.size || 18, color: o.color }),
      })),
  });
}

function table(headers, rows, widths) {
  const w = widths || headers.map(() => Math.floor(CONTENT_W / headers.length));
  const head = new TableRow({
    tableHeader: true,
    children: headers.map((hh, i) =>
      new TableCell({
        width: { size: w[i], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: ACCENT, color: 'auto' },
        margins: { top: 80, bottom: 80, left: 110, right: 110 },
        children: [new Paragraph({
          spacing: { after: 0 },
          children: [new TextRun({ text: hh, bold: true, size: 17, color: 'FFFFFF' })],
        })],
      })),
  });
  const body = rows.map((r, ri) => new TableRow({
    children: r.map((c, i) => cell(c, { w: w[i], fill: ri % 2 ? WASH2 : undefined })),
  }));
  return new Table({
    columnWidths: w,
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      left: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      right: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: RULE },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: RULE },
    },
    rows: [head, ...body],
  });
}

function spacer(h = 120) {
  return new Paragraph({ spacing: { after: h }, children: [] });
}

/**
 * Every feature() call is recorded here as it renders, so the same source that
 * produces the Word document also produces spec/features.yaml. One source, two
 * outputs — the PRD cannot drift from what the tests are held to.
 */
const REGISTRY = [];

/**
 * ANCHORS: the ids the document defines that are NOT feature contracts --
 * the ten controls (H1-H10) and the architecture principles (P1-P6).
 *
 * Code declares `@implements("P1")` against these, and the gate matrix names
 * them as owners. Without a registry they are strings in a table, and
 * trace.py has to either reject them as orphans or stop checking ids at all.
 */
const ANCHORS = [];
function anchor(id, kind, title) {
  ANCHORS.push({ id, kind, title });
}

/**
 * The four-field feature contract. This is the unit the whole PRD is built from.
 *   DOES     - the behaviour
 *   NEVER    - the failure it must refuse
 *   PRODUCES - the state it leaves for the next slice
 *   EVAL     - the check, and the counterexample the check must reject
 */
function feature(id, title, f) {
  REGISTRY.push({
    id,
    title,
    does: f.does || [],
    never: f.never || [],
    produces: f.produces || [],
    evals: f.evals || [],
    counterexample: f.counter || null,
  });
  const W = [1500, 7860];
  const row = (label, items, labelColor) => new TableRow({
    children: [
      new TableCell({
        width: { size: W[0], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: WASH, color: 'auto' },
        margins: { top: 70, bottom: 70, left: 110, right: 110 },
        children: [new Paragraph({
          spacing: { after: 0 },
          children: [new TextRun({ text: label, bold: true, size: 16, color: labelColor || ACCENT })],
        })],
      }),
      new TableCell({
        width: { size: W[1], type: WidthType.DXA },
        margins: { top: 70, bottom: 70, left: 110, right: 110 },
        children: items.map((t) => new Paragraph({
          spacing: { after: items.length > 1 ? 50 : 0, line: 264 },
          bullet: items.length > 1 ? { level: 0 } : undefined,
          children: runs(t, { size: 18 }),
        })),
      }),
    ],
  });

  const rows = [
    new TableRow({
      children: [new TableCell({
        width: { size: CONTENT_W, type: WidthType.DXA },
        columnSpan: 2,
        shading: { type: ShadingType.CLEAR, fill: ACCENT, color: 'auto' },
        margins: { top: 80, bottom: 80, left: 110, right: 110 },
        children: [new Paragraph({
          spacing: { after: 0 },
          children: [
            new TextRun({ text: id + '  ', bold: true, size: 17, color: 'BFD9DE', font: 'Consolas' }),
            new TextRun({ text: title, bold: true, size: 19, color: 'FFFFFF' }),
          ],
        })],
      })],
    }),
    row('DOES', f.does),
    row('NEVER', f.never, SIGNAL),
    row('PRODUCES', f.produces),
    row('EVAL', f.evals),
  ];
  if (f.counter) rows.push(row('MUST FAIL', [f.counter], SIGNAL));

  return [
    new Table({
      columnWidths: W,
      width: { size: CONTENT_W, type: WidthType.DXA },
      borders: {
        top: { style: BorderStyle.SINGLE, size: 4, color: RULE },
        bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE },
        left: { style: BorderStyle.SINGLE, size: 4, color: RULE },
        right: { style: BorderStyle.SINGLE, size: 4, color: RULE },
        insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: RULE },
        insideVertical: { style: BorderStyle.SINGLE, size: 2, color: RULE },
      },
      rows,
    }),
    spacer(160),
  ];
}

const numbering = {
  config: [
    {
      reference: 'nm-bullets',
      levels: [0, 1, 2].map((l) => ({
        level: l,
        format: LevelFormat.BULLET,
        text: ['•', '◦', '–'][l],
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360 + l * 300, hanging: 240 } } },
      })),
    },
    {
      reference: 'nm-numbers',
      levels: [0, 1].map((l) => ({
        level: l,
        format: l === 0 ? LevelFormat.DECIMAL : LevelFormat.LOWER_LETTER,
        text: l === 0 ? '%1.' : '%2.',
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360 + l * 300, hanging: 240 } } },
      })),
    },
  ],
};

module.exports = {
  d, h1, h2, h3, h4, p, bullet, num, table, cell, callout, feature, spacer, runs,
  numbering, INK, ACCENT, MUTED, SIGNAL, WASH, WASH2, RULE, CONTENT_W,
  REGISTRY, ANCHORS, anchor,
};
