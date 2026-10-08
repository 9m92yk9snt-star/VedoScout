// The built manifest must not expose executable tap policies as downloadable
// media assets. Jest/Node alone cannot catch CRA's .cjs asset-loader fallback.
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '../build/asset-manifest.json'),'utf8'));
const escapedModules = Object.keys(manifest.files).filter(name=>/\.cjs$/i.test(name));
assert.deepEqual(escapedModules, [], 'CommonJS modules were emitted as media URLs instead of executable code');
console.log('PASS: production tap policies and selection helpers are bundled as code, not asset links');
