const assert = require('assert/strict');
const policy = require('../src/components/marker-studio/scoutTapPolicy.cjs');
let cases = 0;
const check = (name, fn) => { fn(); cases++; console.log('PASS ' + name); };
const box = { x: 0.2, y: 0.2, w: 0.1, h: 0.2 };
const frames = Array.from({ length: 10 }, (_, i) => ({ t: i * 6 + 3, jpegDataUrl: 'jpeg-' + i }));
const marks = Object.fromEntries(frames.map((f, i) => [i, { t: f.t, box: { ...box } }]));
const checks = [12, 30, 48].map(t => ({ t, box: { ...box }, jpegDataUrl: 'check-' + t }));
check('ten guided taps plus exactly three explicit checks', () => {
  const result = policy.buildPayload(frames, marks, checks, [20, 40]);
  assert.equal(result.anchors.length, 13);
  assert.equal(result.anchors.filter(a => a.verify).length, 3);
  assert.equal(result.anchors[0].t, 3);
  assert.equal(result.markerImageDataUrl, 'jpeg-0');
  assert.equal(result.anchors[8].segment, 2);
  assert.equal(result.anchors[11].segment, 1);
  assert(!result.anchors.some(a => 'confidence' in a || 'frameIndex' in a));
});
check('hidden/skipped moment never becomes an anchor', () => {
  const result = policy.buildPayload(frames, { ...marks, 4: { skipped: true, t: frames[4].t } }, checks, []);
  assert.equal(result.anchors.length, 12);
  assert(!result.anchors.some(a => a.t === frames[4].t));
});
check('two visible taps plus a skip cannot reach minimum three', () => {
  const progress = policy.markingProgress([0, 1, 2], 2, { 0: marks[0], 1: marks[1], 2: { skipped: true } });
  assert.equal(progress.verify, false);
  assert.equal(progress.confirmed, 2);
  assert.equal(progress.needsVisible, true);
});
check('repeating/editing a tap cannot inflate count', () => {
  const progress = policy.markingProgress([0, 1, 2], 0, { 0: marks[0] });
  assert.equal(progress.confirmed, 1);
  assert.equal(progress.next, 1);
  assert.equal(progress.verify, false);
});
check('three visible moments plus skipped frames can proceed', () => {
  assert.equal(policy.markingProgress([0, 1, 2, 3], 3, { 0: marks[0], 1: marks[1], 2: marks[2], 3: { skipped: true } }).verify, true);
});
check('replacement image must carry its actual new timestamp', () => {
  const replaced = frames.map((f, i) => i === 0 ? { t: 3.497, jpegDataUrl: 'nearby' } : f);
  assert.throws(() => policy.buildPayload(replaced, marks, checks, []), /displayed frame/);
  const result = policy.buildPayload(replaced, { ...marks, 0: { t: 3.497, box } }, checks, []);
  assert.equal(result.anchors[0].t, 3.497);
  assert.equal(result.markerImageDataUrl, 'nearby');
});
check('a missing image cannot be submitted', () => {
  assert.throws(() => policy.buildPayload([null, ...frames.slice(1)], marks, checks, []), /displayed frame/);
});
check('zero-sized/outside/non-finite box is rejected', () => {
  for (const bad of [{ ...box, w: 0 }, { ...box, x: -1 }, { ...box, y: NaN }, { ...box, h: 2 }]) {
    assert.equal(policy.validBox(bad), false);
    assert.throws(() => policy.buildPayload(frames, { ...marks, 0: { t: 3, box: bad } }, checks, []), /invalid/);
  }
});
check('verification requires three genuinely different times', () => {
  assert.throws(() => policy.buildPayload(frames, marks, [checks[0], checks[0], checks[2]], []), /different/);
  assert.throws(() => policy.buildPayload(frames, marks, checks.slice(0, 2), []), /3 extra/);
});
check('checks are proposed throughout the clip, not all at the end', () => {
  assert.deepEqual([0, 1, 2].map(i => policy.verifyTime(60, i)), [12, 30, 48]);
});
check('occlusion navigation does not cross a scene cut', () => {
  assert.equal(policy.nearbyTime(19.9, 1, 60, [20, 40]), 19.96);
  assert.equal(policy.nearbyTime(20.1, -1, 60, [20, 40]), 20.04);
  assert.equal(policy.nearbyTime(19.96, 1, 60, [20]), null);
  assert.equal(policy.nearbyTime(19.99, 1, 60, [20]), null);
  assert.equal(policy.nearbyTime(0, -1, 60), null);
});
check('nearby buttons move half a second and clamp to video bounds', () => {
  assert.equal(policy.nearbyTime(5, 1, 60), 5.5);
  assert.equal(policy.nearbyTime(5, -1, 60), 4.5);
  assert.equal(policy.nearbyTime(0.1, -1, 60), 0.04);
  assert.equal(policy.nearbyTime(59.9, 1, 60), 59.96);
});
check('portrait letterbox margins are not selectable', () => {
  const rect = { left: 0, top: 0, width: 390, height: 500 };
  const video = { width: 1080, height: 1920 };
  assert.equal(policy.screenToVideo({ x: 10, y: 250 }, rect, video, 1, { x: 0, y: 0 }), null);
  assert.deepEqual(policy.screenToVideo({ x: 195, y: 250 }, rect, video, 1, { x: 0, y: 0 }), { x: 0.5, y: 0.5 });
});
check('landscape letterbox margins are not selectable', () => {
  const rect = { left: 0, top: 0, width: 390, height: 500 };
  assert.equal(policy.screenToVideo({ x: 195, y: 10 }, rect, { width: 1920, height: 1080 }, 1, { x: 0, y: 0 }), null);
});
check('pinch/pan inverse geometry keeps the intended player', () => {
  const rect = { left: 10, top: 20, width: 400, height: 600 };
  const v = { width: 1000, height: 1500 };
  const result = policy.screenToVideo({ x: 310, y: 270 }, rect, v, 2, { x: 100, y: -50 });
  assert.deepEqual(result, { x: 0.5, y: 0.5 });
});
check('tap boxes remain fully inside the frame at every corner', () => {
  for (const x of [0, 1]) for (const y of [0, 1]) assert(policy.validBox(policy.tapBox({ x, y })));
});
console.log('Guided tap policy: ' + cases + ' cases passed');
