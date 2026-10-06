const { execFileSync } = require('node:child_process');
const assert = require('node:assert/strict');

const output = execFileSync('pnpm', ['exec', 'expo', 'config', '--type', 'introspect', '--json'], {
  encoding: 'utf8',
  stdio: ['ignore', 'pipe', 'inherit'],
});
const config = JSON.parse(output);
const applications = config._internal.modResults.android.manifest.manifest.application;
const main = applications.flatMap((app) => app.activity || [])
  .find((activity) => activity.$['android:name'] === '.MainActivity');
assert.equal(main?.$['android:launchMode'], 'singleTop',
  'Android purchases must survive external bank verification');
console.log('Android purchase activity configuration verified.');
