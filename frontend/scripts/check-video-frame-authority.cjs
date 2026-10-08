const assert = require('assert/strict');
const { seekPresentedFrame, resetPresentedFrame } = require('../src/components/marker-studio/videoFrameAuthority.cjs');
class Video {
  currentTime = 0; readyState = 2; seeking = false; callbacks = new Map(); listeners = new Map(); next = 1;
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  removeEventListener(name, fn) { if (this.listeners.get(name) === fn) this.listeners.delete(name); }
  requestVideoFrameCallback(fn) { const id = this.next++; this.callbacks.set(id, fn); return id; }
  cancelVideoFrameCallback(id) { this.callbacks.delete(id); }
  paint(time) {
    const [id, fn] = this.callbacks.entries().next().value;
    this.callbacks.delete(id); fn(0, {mediaTime: time});
  }
}
(async () => {
  const v = new Video();
  let resolved = false;
  const frame = seekPresentedFrame(v, 30).then(r => { resolved = true; return r; });
  v.paint(23); // stale pixels after currentTime already moved to 30
  await Promise.resolve();
  assert.equal(resolved, false);
  v.paint(29.983);
  assert.equal((await frame).mediaTime, 29.983);
  assert.equal(v.callbacks.size, 0);
  assert.equal((await seekPresentedFrame(v, 30)).mediaTime, 29.983);
  const old = seekPresentedFrame(v, 40).catch(e => e.message);
  const latest = seekPresentedFrame(v, 50);
  assert.equal(await old, 'FRAME_SEEK_SUPERSEDED');
  v.paint(50);
  assert.equal((await latest).mediaTime, 50);
  await assert.rejects(seekPresentedFrame(v, 60, {timeoutMs: 5}), /FRAME_SEEK_TIMEOUT/);
  assert.equal(v.callbacks.size, 0);
  global.requestAnimationFrame = fn => queueMicrotask(fn);
  const fallback = new Video();
  fallback.requestVideoFrameCallback = undefined;
  const legacy = seekPresentedFrame(fallback, 10);
  fallback.listeners.get('seeked')();
  assert.equal((await legacy).source, 'SEEKED_PAINT_FALLBACK');
  const stillSeeking = new Video();
  stillSeeking.seeking = true;
  const pending = seekPresentedFrame(stillSeeking, 10, {timeoutMs: 5});
  stillSeeking.paint(10);
  await assert.rejects(pending, /FRAME_SEEK_TIMEOUT/);
  const controller = new AbortController();
  const abortable = new Video();
  const aborted = seekPresentedFrame(abortable, 10, {signal: controller.signal});
  controller.abort();
  await assert.rejects(aborted, /FRAME_SEEK_ABORTED/);
  assert.equal(abortable.callbacks.size, 0);
  assert.equal(abortable.listeners.size, 0);
  await assert.rejects(seekPresentedFrame(abortable, 10, {signal: controller.signal}), /FRAME_SEEK_ABORTED/);
  const resetting = new Video();
  const invalidated = seekPresentedFrame(resetting, 20);
  resetPresentedFrame(resetting);
  await assert.rejects(invalidated, /FRAME_SEEK_SUPERSEDED/);
  assert.equal(resetting.callbacks.size, 0);
  const early = new Video();
  early.readyState = 1; early.seeking = true;
  let earlyResolved = false;
  const earlyFrame = seekPresentedFrame(early, 10).then(frame => { earlyResolved = true; return frame; });
  early.paint(9.983);
  await Promise.resolve();
  assert.equal(earlyResolved, false);
  early.readyState = 4; early.seeking = false;
  early.listeners.get('seeked')();
  assert.equal((await earlyFrame).mediaTime, 9.983);
  assert.equal(early.callbacks.size, 0);
  assert.equal(early.listeners.size, 0);
  const wrongEarly = new Video();
  wrongEarly.readyState = 1; wrongEarly.seeking = true;
  const wrongFrame = seekPresentedFrame(wrongEarly, 30, {timeoutMs: 5});
  wrongEarly.paint(23);
  wrongEarly.readyState = 4; wrongEarly.seeking = false;
  wrongEarly.listeners.get('seeked')();
  await assert.rejects(wrongFrame, /FRAME_SEEK_TIMEOUT/);
  const notDecoded = new Video();
  notDecoded.readyState = 1; notDecoded.seeking = true;
  const delayed = seekPresentedFrame(notDecoded, 10);
  notDecoded.paint(9.983);
  notDecoded.seeking = false;
  notDecoded.listeners.get('seeked')();
  notDecoded.readyState = 2;
  notDecoded.listeners.get('loadeddata')();
  assert.equal((await delayed).mediaTime, 9.983);
  console.log('Presented video frame authority: 12 cases passed');
})().catch(e => { console.error(e); process.exitCode = 1; });
