function validPoint(p) { return !!p && ['x', 'y'].every(k => Number.isFinite(p[k]) && p[k] >= 0 && p[k] <= 1); }
function validMask(m) {
  return !!m && m.width === 96 && m.height === 192 && Array.isArray(m.runs) && m.runs.length <= 8192 &&
    m.runs.length >= 2 && m.runs.every(n => Number.isInteger(n) && n >= 0) &&
    m.runs.reduce((a, b) => a + b, 0) === 96 * 192 && m.runs.filter((_, i) => i % 2).reduce((a, b) => a + b, 0) >= 20;
}
function hints(a) {
  const result = {};
  if (a.visibility === 'partial') result.visibility = 'partial';
  if (validPoint(a.target_point)) result.target_point = { ...a.target_point };
  if (Array.isArray(a.include_points)) result.include_points = a.include_points.filter(validPoint).slice(0, 4).map(p => ({ ...p }));
  if (Array.isArray(a.exclude_points)) result.exclude_points = a.exclude_points.filter(validPoint).slice(0, 4).map(p => ({ ...p }));
  if (validMask(a.visible_mask)) result.visible_mask = { ...a.visible_mask, runs: [...a.visible_mask.runs] };
  if (a.tracking_check?.status === 'user_confirmed' && Number.isFinite(a.tracking_check.start) && Number.isFinite(a.tracking_check.end)) result.tracking_check = { ...a.tracking_check };
  return result;
}
function maskImage(mask) {
  if (!validMask(mask)) return null;
  const canvas = document.createElement('canvas'); canvas.width = mask.width; canvas.height = mask.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const pixels = ctx.createImageData(mask.width, mask.height);
  let offset = 0;
  mask.runs.forEach((count, index) => {
    for (let n = 0; n < count; n++, offset++) if (index % 2) {
      pixels.data[offset * 4] = 255; pixels.data[offset * 4 + 1] = 255; pixels.data[offset * 4 + 2] = 255; pixels.data[offset * 4 + 3] = 255;
    }
  });
  ctx.putImageData(pixels, 0, 0); return canvas.toDataURL('image/png');
}
module.exports = { validPoint, validMask, hints, maskImage };
