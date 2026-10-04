// Execute the actual polling function against a synthetic failure and clock.
// No browser, network request, model call, or production write is performed.
const fs = require('fs');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../src/pages/ReportPage.jsx'), 'utf8');
const start = source.indexOf('  const pollFullReportReady = async () => {');
const end = source.indexOf('\n  const handleGenerateFull', start);
if (start < 0 || end < 0) throw new Error('Polling function boundaries changed; review the audit.');
const definition = source.slice(start, end).replace('const pollFullReportReady = ', 'return ');
const ticks = [0, 0, 1200000];
let polls = 0;
const poll = new Function('api', 'isFullReportReady', 'setDoubtInfo', 'id', 'Date', 'setTimeout', definition)(
  { get: async () => { polls++; return { data: {
    full_report_status: 'failed', full_report_error: 'synthetic backend failure'
  } }; } },
  () => false, () => {}, 'synthetic',
  { now: () => ticks.length ? ticks.shift() : 1200000 }, callback => callback()
);
poll().then(() => {
  console.error('Unexpected success; review the audit.');
  process.exitCode = 1;
}).catch(error => {
  console.log(JSON.stringify({
    method: 'actual frontend polling function with synthetic API and clock',
    backendFailure: 'synthetic backend failure', surfacedError: error.message, polls
  }, null, 2));
  if (error.message !== 'Full report is taking longer than usual. Please refresh the page in a minute.') {
    process.exitCode = 1;
  }
});
