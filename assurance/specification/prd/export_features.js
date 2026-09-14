/**
 * Dump the feature contracts captured while rendering the PRD.
 *
 * The point of this file: the Word document and the machine-readable spec come
 * from ONE source. Requiring part_b.js renders the features (into objects we
 * throw away) and, as a side effect, fills helpers.REGISTRY. So the registry
 * cannot describe a feature the document does not contain, or omit one it does.
 *
 *   node export_features.js > ../features.raw.json
 */
const H = require('./helpers');

require('./part_a');
require('./part_b');
require('./part_c');

const { SCHEMAS } = require('./schemas');

process.stdout.write(JSON.stringify({
  features: H.REGISTRY,
  anchors: H.ANCHORS,
  schemas: SCHEMAS.map(([name, owner, purpose, fields]) => ({
    name,
    owner,
    purpose,
    fields: fields.map(([field, type, required, why]) => ({
      field, type, required, why,
    })),
  })),
}, null, 2));
