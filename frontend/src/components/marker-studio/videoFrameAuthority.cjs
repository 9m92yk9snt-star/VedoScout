// A tap belongs to the presented pixels, never to a pending seek's currentTime.
const pending = new WeakMap();
const presented = new WeakMap();

function resetPresentedFrame(video) {
  if (!video) return;
  pending.get(video)?.();
  presented.delete(video);
}

function seekPresentedFrame(video, target, { timeoutMs = 2500, tolerance = 0.08, signal } = {}) {
  if (!video || !Number.isFinite(target)) return Promise.reject(new Error('FRAME_SEEK_INVALID'));
  if (signal?.aborted) return Promise.reject(new Error('FRAME_SEEK_ABORTED'));
  pending.get(video)?.();
  const previous = presented.get(video);
  if (previous && !video.seeking && video.readyState >= 2 &&
      Math.abs(video.currentTime - previous.mediaTime) <= tolerance &&
      Math.abs(previous.mediaTime - target) <= tolerance) {
    return Promise.resolve(previous);
  }
  return new Promise((resolve, reject) => {
    let done = false, callbackId, timer, candidate = null;
    const cleanup = () => {
      clearTimeout(timer);
      video.removeEventListener('seeked', onSeeked);
      video.removeEventListener('loadeddata', checkCandidate);
      video.removeEventListener('canplay', checkCandidate);
      signal?.removeEventListener('abort', abort);
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
    const abort = () => finish(null, 'FRAME_SEEK_ABORTED');
    const checkCandidate = () => {
      if (!candidate || done || video.seeking || video.readyState < 2 ||
          Math.abs(video.currentTime - target) > tolerance) return;
      const observed = candidate;
      // Native Chromium can deliver the RIGHT presented PTS while its
      // seeking flag is still true and readyState is still 1. Keep that
      // positive evidence; wait for seek completion/readiness and two paints
      // instead of discarding the sole callback of a paused frame.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (!done && candidate === observed && !video.seeking && video.readyState >= 2 &&
            Math.abs(video.currentTime - target) <= tolerance) finish(observed);
      }));
    };
    const requestFrame = () => {
      callbackId = video.requestVideoFrameCallback((_now, metadata) => {
        callbackId = null;
        if (done) return;
        const mediaTime = metadata?.mediaTime;
        if (Number.isFinite(mediaTime) && Math.abs(mediaTime - target) <= tolerance) {
          candidate = { mediaTime, source: 'PRESENTED_FRAME_CALLBACK' };
          if (!video.seeking && video.readyState >= 2) finish(candidate);
          else requestFrame(); // completion may follow this callback, with no new paused frame
        } else {
          candidate = null; // a callback for the old decoded image is not evidence
          requestFrame();
        }
      });
    };
    const onSeeked = () => {
      if (typeof video.requestVideoFrameCallback === 'function') { checkCandidate(); return; }
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
    video.addEventListener('loadeddata', checkCandidate);
    video.addEventListener('canplay', checkCandidate);
    signal?.addEventListener('abort', abort, { once: true });
    try {
      if (typeof video.requestVideoFrameCallback === 'function') requestFrame();
      video.currentTime = target;
    } catch { finish(null, 'FRAME_SEEK_FAILED'); }
  });
}

module.exports = { seekPresentedFrame, resetPresentedFrame };
