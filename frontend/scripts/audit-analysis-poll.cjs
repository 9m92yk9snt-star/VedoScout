// Regress the actual polling function without browser/network/model calls.
const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../src/pages/ReportPage.jsx'), 'utf8');
const start = source.indexOf('  const pollFullReportReady = async () => {');
const end = source.indexOf('\n  const handleGenerateFull', start);
assert(start >= 0 && end > start, 'Review polling function boundaries');
const definition = source.slice(start, end).replace('const pollFullReportReady = ', 'return ');

async function simulate(responses, advanceMs = 0) {
  let clock = Date.UTC(2026, 9, 4), polls = 0;
  const api = { get: async () => {
    clock += advanceMs;
    const response = responses[Math.min(polls++, responses.length - 1)];
    if (response instanceof Error) throw response;
    return {data: typeof response === 'function' ? response(clock) : response};
  }};
  const poll = new Function('api', 'isFullReportReady', 'setDoubtInfo', 'id', 'Date', 'setTimeout', definition)(
    api, d => d?.full_report_status === 'ready', () => {}, 'synthetic',
    {now: () => clock, parse: Date.parse}, callback => { clock += 4500; callback(); }
  );
  try { return {result: await poll(), polls}; }
  catch (error) { return {error: error.message, polls}; }
}

(async () => {
  const failed = await simulate([{full_report_status: 'failed', full_report_error: 'synthetic backend failure'}]);
  assert.equal(failed.error, 'synthetic backend failure');
  assert.equal(failed.polls, 1);
  const forbidden = await simulate([Object.assign(new Error('expired session'), {response: {status: 401}})]);
  assert.equal(forbidden.error, 'expired session');
  const transient = await simulate([new Error('network blip'), {full_report_status: 'ready'}]);
  assert.equal(transient.result.full_report_status, 'ready');
  const active = await simulate([
    ...Array(6).fill(t => ({full_report_status: 'generating', last_progress_at: new Date(t).toISOString()})),
    {full_report_status: 'ready'},
  ], 9 * 60 * 1000);
  assert.equal(active.result.full_report_status, 'ready');
  assert.equal(active.polls, 7);
  const stale = await simulate([{full_report_status: 'generating', last_progress_at: '2000-01-01T00:00:00Z'}], 21 * 60 * 1000);
  assert.match(stale.error, /not reported progress/);
  console.log(JSON.stringify({cases: 5, failed, forbidden, transient, active, stale}, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
