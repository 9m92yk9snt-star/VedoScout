const assert = require('assert/strict');
const { seekPresentedFrame } = require('../src/components/marker-studio/videoFrameAuthority.cjs');
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
  console.log('Presented video frame authority: 6 cases passed');
})().catch(e => { console.error(e); process.exitCode = 1; });
