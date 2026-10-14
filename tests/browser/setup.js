// Before a run: clear the observations an earlier run left (record.fresh).
const R = require('./record');

module.exports = async () => { R.fresh(); };
