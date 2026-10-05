// A tap belongs to the presented pixels, never to a pending seek's currentTime.
const pending = new WeakMap();
const presented = new WeakMap();

function seekPresentedFrame(video, target, { timeoutMs = 2500, tolerance = 0.08 } = {}) {
  if (!video || !Number.isFinite(target)) return Promise.reject(new Error('FRAME_SEEK_INVALID'));
  pending.get(video)?.();
  const previous = presented.get(video);
  if (previous && !video.seeking && video.readyState >= 2 &&
      Math.abs(video.currentTime - previous.mediaTime) <= tolerance &&
      Math.abs(previous.mediaTime - target) <= tolerance) {
    return Promise.resolve(previous);
  }
  return new Promise((resolve, reject) => {
    let done = false, callbackId, timer;
    const cleanup = () => {
      clearTimeout(timer);
      video.removeEventListener('seeked', onSeeked);
      if (callbackId != null && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(callbackId);
      if (pending.get(video) === cancel) pending.delete(video);
    };
    const finish = (frame, error) => {
      if (done) return;
      done = true;
      cleanup();
      if (error) reject(new Error(error));
      else { presented.set(video, frame); resolve(frame); }
    };
    const cancel = () => finish(null, 'FRAME_SEEK_SUPERSEDED');
    const requestFrame = () => {
      callbackId = video.requestVideoFrameCallback((_now, metadata) => {
        callbackId = null;
        if (done) return;
        const mediaTime = metadata?.mediaTime;
        if (Number.isFinite(mediaTime) && Math.abs(mediaTime - target) <= tolerance &&
            !video.seeking && video.readyState >= 2) {
          finish({ mediaTime, source: 'PRESENTED_FRAME_CALLBACK' });
        } else requestFrame(); // discard a callback for the old decoded image
      });
    };
    const onSeeked = () => {
      if (typeof video.requestVideoFrameCallback === 'function') return;
      // Older browsers expose only seek completion. Wait for its painted frame;
      // never treat the timeout itself as successful decoding.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (!done && !video.seeking && video.readyState >= 2 &&
            Math.abs(video.currentTime - target) <= tolerance) {
          finish({ mediaTime: video.currentTime, source: 'SEEKED_PAINT_FALLBACK' });
        }
      }));
    };
    pending.set(video, cancel);
    timer = setTimeout(() => finish(null, 'FRAME_SEEK_TIMEOUT'), timeoutMs);
    video.addEventListener('seeked', onSeeked);
    try {
      if (typeof video.requestVideoFrameCallback === 'function') requestFrame();
      video.currentTime = target;
    } catch { finish(null, 'FRAME_SEEK_FAILED'); }
  });
}

module.exports = { seekPresentedFrame };
