// Pure editor policy. It never infers identity or fills in an occluded player.
const TARGET_TAPS = 10;
const MIN_TAPS = 3;
const VERIFY_TAPS = 3;
const VERIFY_SPACING = 0.5;
const clamp = (n, low, high) => Math.max(low, Math.min(high, n));
const selection = require('./selectionHints.cjs');

function validBox(box) {
  return !!box && ['x', 'y', 'w', 'h'].every(k => Number.isFinite(box[k])) &&
    box.x >= 0 && box.y >= 0 && box.w > 0 && box.h > 0 &&
    box.x + box.w <= 1.000001 && box.y + box.h <= 1.000001;
}

function screenToVideo(point, rect, video, zoom, pan) {
  if (!rect.width || !rect.height || !video.width || !video.height) return null;
  const scale = Math.min(rect.width / video.width, rect.height / video.height);
  const w = video.width * scale, h = video.height * scale;
  const x = (point.x - rect.left - rect.width / 2 - pan.x) / zoom + rect.width / 2;
  const y = (point.y - rect.top - rect.height / 2 - pan.y) / zoom + rect.height / 2;
  const fx = (x - (rect.width - w) / 2) / w, fy = (y - (rect.height - h) / 2) / h;
  return fx < 0 || fy < 0 || fx > 1 || fy > 1 ? null : { x: fx, y: fy };
}

function tapBox(point) {
  const w = 0.08, h = 0.18;
  return { x: clamp(point.x - w / 2, 0, 1 - w), y: clamp(point.y - h * 0.42, 0, 1 - h), w, h };
}

function prioritizeTapMoments(times, duration) {
  // Present a broad identity reference early; never create an automatic tap.
  const ordered = [...new Set(times.filter(t => Number.isFinite(t) && t >= 0 && t < duration))].sort((a, b) => a - b);
  if (ordered.length < 3) return ordered;
  const middle = ordered.reduce((best, t) => Math.abs(t - duration / 2) < Math.abs(best - duration / 2) ? t : best);
  return [...new Set([ordered[0], middle, ordered[ordered.length - 1], ...ordered])];
}

function markingProgress(queue, current, marks) {
  const confirmed = queue.filter(i => validBox(marks[i]?.box)).length;
  // An updated/repeated mark occupies one slot, not another confirmation.
  const pending = queue.filter(i => !marks[i]);
  if (pending.length) {
    const after = pending.find(i => queue.indexOf(i) > queue.indexOf(current));
    return { next: after ?? pending[0], confirmed, ready: false };
  }
  const full = queue.filter(i => validBox(marks[i]?.box) && marks[i]?.visibility !== 'partial').length;
  if (full >= MIN_TAPS) return { next: null, confirmed, ready: true };
  return { next: queue.find(i => marks[i]?.skipped) ?? current, confirmed, ready: false, needsVisible: true };
}

function nearbyTime(time, direction, duration, cuts = []) {
  if (!Number.isFinite(time) || !Number.isFinite(duration) || duration <= 0) return null;
  const bounds = [0, ...cuts.filter(t => Number.isFinite(t) && t > 0 && t < duration).sort((a, b) => a - b), duration];
  let segment = 0;
  for (let i = 1; i < bounds.length - 1; i++) if (time >= bounds[i]) segment = i;
  const low = bounds[segment] + 0.04, high = bounds[segment + 1] - 0.04;
  if (high <= low) return null;
  const next = clamp(time + (direction < 0 ? -0.5 : 0.5), low, high);
  if ((direction < 0 && next >= time) || (direction >= 0 && next <= time)) return null;
  return Math.abs(next - time) < 0.02 ? null : next;
}

function verifyTime(duration, index) { return duration * [0.2, 0.5, 0.8][index]; }
function distinctVerifyTime(time, marks) {
  return Number.isFinite(time) && time >= 0 && marks.every(m => Math.abs(m.t - time) >= VERIFY_SPACING);
}

function buildPayload(frames, marks, verifyMarks, cuts) {
  if (Object.values(marks).some(m => !m.skipped && !validBox(m.box))) {
    throw new Error('A player box is invalid. Please re-mark it.');
  }
  const entries = Object.entries(marks).filter(([, m]) => !m.skipped && validBox(m.box));
  // Older saved drafts may include the three explicit checks. New selections
  // need only the guided anchors; no verify flag is inferred from their order.
  if (entries.filter(([, m]) => m.visibility !== 'partial').length < MIN_TAPS || entries.length > TARGET_TAPS || ![0, VERIFY_TAPS].includes(verifyMarks.length)) {
    throw new Error('Complete at least 3 clear guided taps. Legacy extra checks must be a complete set of 3.');
  }
  const segment = time => cuts.filter(c => time >= c).length;
  const anchors = entries.map(([i, mark]) => {
    const frame = frames[Number(i)];
    if (!frame?.jpegDataUrl || !Number.isFinite(frame.t) || frame.t < 0 || frame.t !== mark.t) {
      throw new Error('A tap no longer matches its displayed frame. Please re-mark it.');
    }
    return { t: frame.t, box: { ...mark.box }, ...selection.hints(mark),
      ...(mark.continuity?.length ? { continuity: mark.continuity.map(c => ({ ...c, segment: segment(c.t) })) } : {}),
      segment: segment(frame.t), frameIndex: Number(i) };
  // Keep broad guided references at the front of the existing crop budgets.
  // Sorting back into time order would put all ten-tap profile crops near the
  // beginning again. Partial fragments still follow clear references.
  }).sort((a, b) => (a.visibility === 'partial') - (b.visibility === 'partial'));
  const checks = verifyMarks.map((m, i) => {
    if (m.visibility === 'partial' || !validBox(m.box) || !m.jpegDataUrl || !distinctVerifyTime(m.t, verifyMarks.slice(0, i))) {
      throw new Error('Choose three different, clearly visible moments for the extra checks.');
    }
    return { t: m.t, box: { ...m.box }, ...selection.hints(m), segment: segment(m.t), verify: true };
  });
  const markerImageDataUrl = frames[anchors[0].frameIndex].jpegDataUrl;
  return {
    anchors: [...anchors.map(({ frameIndex, ...a }) => a), ...checks],
    sceneCuts: cuts, markerImageDataUrl,
  };
}

module.exports = { TARGET_TAPS, MIN_TAPS, VERIFY_TAPS, VERIFY_SPACING, validBox, screenToVideo, tapBox, prioritizeTapMoments, markingProgress, nearbyTime, verifyTime, distinctVerifyTime, buildPayload };
