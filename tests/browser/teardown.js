// After a run: keep what was seen (CI uploads it), and rewrite the record
// when UPDATE_RECORD=1. A partial run (a filtered or failed one) never
// rewrites: a record built from part of the screens would drop the rest.
const fs = require('fs');
const path = require('path');
const R = require('./record');

module.exports = async () => {
  for (const kind of ['a11y', 'panels']) {
    const seen = R.merge(kind);
    fs.mkdirSync(R.RUN, { recursive: true });
    fs.writeFileSync(path.join(R.RUN, `observed-${kind}.json`), JSON.stringify(seen, null, 2) + '\n');
    if (!R.UPDATE) continue;
    const expected = Number(process.env.BROWSER_EXPECTED_STATES || 0);
    if (expected && Object.keys(seen).length !== expected) {
      console.log(`record/${kind}.json NOT rewritten: the run saw ${Object.keys(seen).length} of ${expected} states`);
      continue;
    }
    R.write(kind, seen);
    console.log(`record/${kind}.json rewritten from ${Object.keys(seen).length} states`);
  }
};
