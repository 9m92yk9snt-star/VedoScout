// All times are original source milliseconds, never playback/rounded badge time.
const finite = x => typeof x === 'number' && Number.isFinite(x);
const point = p => Array.isArray(p) && p.length === 2 && p.every(x => finite(x) && x >= 0 && x <= 1);
export function roomFor(comment, fallbackSeconds) {
  const raw = comment?.match_room;
  const bound = raw?.version === 1 && raw.event_id === comment?.event_id && !!raw.source_video_sha256 && raw.source_video_sha256 === comment?.source_video_sha256 && raw.coordinate_space === 'FULL_FRAME_NORMALIZED' && finite(raw.start_ms) && finite(raw.end_ms) && raw.end_ms >= raw.start_ms;
  const pivot = finite(comment?.evidence_time_ms) ? comment.evidence_time_ms : fallbackSeconds * 1000;
  const start = bound ? raw.start_ms : Math.max(0, pivot - 4000);
  const end = bound ? raw.end_ms : pivot + 2500;
  const stops = bound && Array.isArray(raw.stops) ? raw.stops.filter(s => finite(s.media_ms) && s.media_ms >= start && s.media_ms <= end && typeof s.label === 'string').map(s => ({
    media_ms: s.media_ms,
    phase: s.phase,
    label: s.label.slice(0, 80),
    caption: typeof s.caption === 'string' ? s.caption.slice(0, 240) : null
  })) : [];
  const seen = new Set();
  const ordered = (stops.length ? stops : [{
    media_ms: pivot,
    label: 'Key action',
    phase: 'action'
  }]).sort((a, b) => a.media_ms - b.media_ms).filter(s => !seen.has(s.media_ms) && seen.add(s.media_ms)).slice(0, 8);
  const samples = bound && Array.isArray(raw.samples) ? raw.samples.filter(s => finite(s.media_ms) && s.media_ms >= start && s.media_ms <= end && typeof s.frame_id === 'string').slice(0, 160).map(s => ({
    media_ms: s.media_ms,
    frame_id: s.frame_id,
    ground: point(s.ground) && finite(s.player_width) && s.player_width >= .005 && s.player_width <= .4 ? s.ground : null,
    player_width: s.player_width,
    ball: point(s.ball) ? s.ball : null,
    camera_static_from_previous: s.camera_static_from_previous === true
  })).sort((a, b) => a.media_ms - b.media_ms) : [];
  return {
    start,
    end,
    stops: ordered,
    samples
  };
}
export function graphicsAt(room, mediaMs) {
  // Brief exact-frame marks; never interpolate across occlusion, camera motion or sparse samples.
  const sample = room.samples.reduce((best, s) => Math.abs(s.media_ms - mediaMs) < Math.abs((best?.media_ms ?? Infinity) - mediaMs) ? s : best, null);
  if (!sample || Math.abs(sample.media_ms - mediaMs) > 60) return null;
  const i = room.samples.indexOf(sample),
    previous = room.samples[i - 1];
  const ballTrail = previous?.ball && sample.ball && sample.camera_static_from_previous && sample.media_ms - previous.media_ms <= 300 && sample.media_ms > previous.media_ms ? [previous.ball, sample.ball] : null;
  return {
    ...sample,
    ballTrail
  };
}
