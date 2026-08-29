const fs = require('fs');
const path = require('path');
const H = require('./helpers');
const d = H.d;
const { Document, Packer, Paragraph, TextRun, Header, Footer, PageNumber,
        AlignmentType, BorderStyle, TableOfContents, PageBreak } = d;

const partA = require('./part_a');
const partB = require('./part_b');
const partC = require('./part_c');

const toc = [
  new Paragraph({
    spacing: { before: 200, after: 240 },
    children: [new TextRun({ text: 'Contents', bold: true, size: 32, color: H.ACCENT, font: 'Georgia' })],
  }),
  new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-3' }),
  new Paragraph({ children: [new PageBreak()] }),
];

const doc = new Document({
  creator: 'Nyaymalaw',
  title: 'Nyaymalaw — Product Requirements',
  description: 'End-to-end PRD: journey, features, retrieval, grounding, evaluation.',
  numbering: H.numbering,
  styles: {
    default: {
      document: { run: { font: 'Calibri', size: 20, color: H.INK } },
    },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Georgia', size: 34, bold: true, color: H.ACCENT } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Georgia', size: 26, bold: true, color: H.INK } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Calibri', size: 22, bold: true, color: H.ACCENT } },
      { id: 'Heading4', name: 'Heading 4', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Calibri', size: 20, bold: true, color: H.INK } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1080, bottom: 1080, left: 1260, right: 1260 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: H.RULE, space: 6 } },
          children: [new TextRun({ text: 'Nyaymalaw — Product Requirements', size: 15, color: '8A939B' })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ children: [PageNumber.CURRENT], size: 15, color: '8A939B' })],
        })],
      }),
    },
    children: [...partA.slice(0, 6), ...toc, ...partA.slice(6), ...partB, ...partC],
  }],
});

const outPath = process.argv[2] || path.join(process.cwd(), 'Nyaymalaw_PRD.docx');
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(outPath, buf);
  console.log('WROTE', outPath, (buf.length / 1024).toFixed(0) + ' KB');
}).catch((e) => { console.error('FAILED', e); process.exit(1); });
