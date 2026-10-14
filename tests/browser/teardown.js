// After a run: keep what was seen (CI uploads it), and rewrite the record
// when UPDATE_RECORD=1, but only from a run that saw every screen at every
// size. A filtered or failed run never rewrites: a record built from part of
// the screens would drop the rest. The run started empty (setup.js), so
// nothing here is left over from an earlier one.
const fs = require('fs');
const path = require('path');
const R = require('./record');
const SCREENS = require('./screens');

module.exports = async (config) => {
  const projects = config.projects.map(p => p.name);
  for (const kind of ['a11y', 'panels']) {
    const seen = R.merge(kind);
    fs.mkdirSync(R.RUN, { recursive: true });
    fs.writeFileSync(path.join(R.RUN, `observed-${kind}.json`), JSON.stringify(seen, null, 2) + '\n');
    if (!R.UPDATE) continue;
    const { ok, missing } = R.complete(seen, SCREENS, projects);
    if (!ok) {
      console.log(`record/${kind}.json NOT rewritten: the run did not see ${missing.length} of ${SCREENS.length * projects.length} states (${missing.slice(0, 3).join(', ')}...)`);
      continue;
    }
    R.write(kind, seen);
    console.log(`record/${kind}.json rewritten from ${Object.keys(seen).length} states`);
  }
};
