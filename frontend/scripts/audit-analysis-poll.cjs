// Exercise the production polling module with a fake API and accelerated clock.
// No browser, database writes or model calls.
const assert = require('assert/strict');
const path = require('path');
const {pathToFileURL} = require('url');

(async () => {
  const {pollAnalysis} = await import(pathToFileURL(path.join(__dirname, '../src/lib/pollAnalysis.mjs')));
  const {getAnalysisView} = await import(pathToFileURL(path.join(__dirname, '../src/lib/analysisProgress.mjs')));
  async function simulate(responses, {advanceMs = 0, target = 'full', cancelAfterResponse = false} = {}) {
    let clock = Date.UTC(2026, 9, 8), polls = 0, cancelled = false;
    const seen = [], connection = [];
    const api = {get: async () => {
      clock += advanceMs;
      const response = responses[Math.min(polls++, responses.length - 1)];
      if (response instanceof Error) throw response;
      if (cancelAfterResponse) cancelled = true;
      return {data: typeof response === 'function' ? response(clock) : response};
    }};
    try {
      const result = await pollAnalysis(api, 'selected', {
        target, now: () => clock, wait: async ms => {clock += ms;},
        isCancelled: () => cancelled,
        onStatus: data => seen.push(data), onConnectionError: error => connection.push(error),
      });
      return {result, polls, seen, connection};
    } catch (error) {return {error: error.message, kind: error.kind, polls, seen, connection};}
  }
  const ready = {is_paid: true, status: 'ready', full_report_status: 'ready', has_full_report: true};
  const failed = await simulate([{full_report_status: 'failed', full_report_error: 'backend failure'}]);
  assert.equal(failed.error, 'backend failure'); assert.equal(failed.polls, 1);
  const forbidden = await simulate([Object.assign(new Error('expired session'), {response: {status: 401}})]);
  assert.equal(forbidden.kind, 'access'); assert.equal(forbidden.polls, 1);
  const transient = await simulate([new Error('network blip'), ready]);
  assert.equal(transient.result, ready); assert.equal(transient.polls, 2);
  assert.match(transient.connection[0], /Connection interrupted/); assert.equal(transient.connection.at(-1), null);
  const active = await simulate([
    ...Array(6).fill(t => ({full_report_status: 'generating', last_progress_at: new Date(t).toISOString()})), ready,
  ], {advanceMs: 9 * 60 * 1000});
  assert.equal(active.result, ready); assert.equal(active.polls, 7);
  const stale = await simulate([{full_report_status: 'generating', last_progress_at: '2000-01-01T00:00:00Z'}], {advanceMs: 21 * 60 * 1000});
  assert.match(stale.error, /not reported progress/);
  const disconnected = await simulate([new Error('offline')], {advanceMs: 21 * 60 * 1000});
  assert.equal(disconnected.kind, 'stalled'); assert.equal(disconnected.polls, 1);
  const initial = {is_paid: true, status: 'ready', preview: {brief_summary: 'Initial'}, full_report_status: 'generating'};
  const previewThenFull = await simulate([initial, {...initial, has_full_report: true, full_report_status: 'finalizing'}, ready]);
  assert.equal(previewThenFull.polls, 3);
  assert.equal(getAnalysisView(previewThenFull.seen[0]).complete, false);
  assert.equal(getAnalysisView(previewThenFull.seen[1]).complete, false);
  const missingBody = await simulate([{...ready, has_full_report: false}, ready]);
  assert.equal(missingBody.polls, 2);
  const free = await simulate([{...initial, is_paid: false}], {target: 'preview'});
  assert.equal(free.polls, 1);
  const cancelled = await simulate([initial], {cancelAfterResponse: true});
  assert.equal(cancelled.result, null); assert.equal(cancelled.seen.length, 0);
  const rateLimit = await simulate([Object.assign(new Error('slow down'), {response: {status: 429}}), ready]);
  assert.equal(rateLimit.result, ready); assert.equal(rateLimit.polls, 2);
  const previewFailed = await simulate([{status: 'failed', error: 'Invalid video'}], {target: 'preview'});
  assert.equal(previewFailed.error, 'Invalid video'); assert.equal(previewFailed.polls, 1);
  const future = await simulate([{full_report_status: 'generating', last_progress_at: '2099-01-01T00:00:00Z'}], {advanceMs: 21 * 60 * 1000});
  assert.equal(future.kind, 'stalled');
  console.log('PASS: 13 polling scenarios, including paid preview → finalization → full readiness, 54+ minutes of real heartbeats, offline, access, cancellation and retry.');
})().catch(error => {console.error(error); process.exitCode = 1;});
