// Check the actual projection; partial observations must not look like totals.
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../src/components/report-v2/derive.js'), 'utf8');
const start = source.indexOf('  const ms = full.match_stats || null;');
const end = source.indexOf('  // ---- Video highlight', start);
assert(start >= 0 && end > start, 'Review match stats projection boundaries');
const project = new Function('full', source.slice(start, end) + '\nreturn {matchStats, matchStatsCoverage};');
const partial = project({match_stats: {coverage_status: 'PARTIAL', coverage_note: 'Evidence incomplete',
  observed_goals: 1, observed_assists: 0}});
assert.equal(partial.matchStats.find(r => r.label === 'Verified Goals').value, 1);
assert.equal(partial.matchStatsCoverage, 'Evidence incomplete');
assert.equal(partial.matchStats.some(r => r.label === 'Goals'), false);
const complete = project({match_stats: {coverage_status: 'COMPLETE', goals: 0, assists: 0}});
assert.equal(complete.matchStats.find(r => r.label === 'Goals').value, 0);
assert.equal(complete.matchStatsCoverage, null);
const missing = project({});
assert.equal(missing.matchStats, null);
const outlookStart = source.indexOf('  const so = full.scout_outlook || {};');
const outlookEnd = source.indexOf('  // ---- Match stats ----', outlookStart);
assert(outlookStart >= 0 && outlookEnd > outlookStart);
const outlook = new Function('full', 'NEXT_TIER', 'obTier', 'ob', 'TIER_LABELS', 'TIER_DOTS', 'pa', 'firstSentences',
  source.slice(outlookStart, outlookEnd) + '\nreturn scoutOutlook;');
const unassessed = outlook({report_fact_authority: {status: 'REVIEW_REQUIRED'}, scores: {overall_development: null}},
  {}, null, {}, {}, {}, {}, () => '');
assert.equal(unassessed.potentialLabel, 'Not assessed');
assert.equal(unassessed.currentDots, 0);
assert.equal(unassessed.potentialDots, 0);
assert.equal(unassessed.longTerm, 'Not assessed');
const component = fs.readFileSync(path.join(__dirname, '../src/components/report-v2/PremiumReportV2.jsx'), 'utf8');
assert(component.includes('coverageNote={d.matchStatsCoverage}'), 'Report must display partial coverage note');
console.log('Report coverage and withheld assessment: 5 cases passed');
