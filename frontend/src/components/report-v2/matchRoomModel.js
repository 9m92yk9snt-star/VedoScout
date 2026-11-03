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
    groundTrail: s.motion_method === 'BACKGROUND_AFFINE_ENDPOINTS' && finite(s.motion_start_ms) && s.media_ms > s.motion_start_ms && s.media_ms-s.motion_start_ms <= 1000 && raw.samples.some(p => p.media_ms === s.motion_start_ms && point(p.ground)) && Array.isArray(s.groundTrail) && s.groundTrail.length === 2 && s.groundTrail.every(point) && point(s.ground) && s.groundTrail[1][0] === s.ground[0] && s.groundTrail[1][1] === s.ground[1] ? s.groundTrail : null,
    motion_start_ms: s.motion_start_ms,
    camera_static_from_previous: s.camera_static_from_previous === true
  })).sort((a, b) => a.media_ms - b.media_ms) : [];
  const tracking = raw?.tracking;
  const tracks = bound && tracking?.version === 1 && tracking.event_id === raw.event_id && tracking.source_video_sha256 === raw.source_video_sha256 && ["TAP_OPTICAL_GROUND_PROXY", "TAP_BIDIRECTIONAL_INSTANCE_CONTOUR"].includes(tracking.method) && Array.isArray(tracking.segments)
    ? tracking.segments.slice(0, 32).flatMap(segment => {
      if (!Array.isArray(segment.samples) || typeof segment.reference_frame !== "string") return [];
      const contour = tracking.method === "TAP_BIDIRECTIONAL_INSTANCE_CONTOUR";
      if (contour && (segment.ground_method !== "LOWER_VISIBLE_CONTOUR" || !samples.some(s => s.frame_id === segment.reference_frame) || !Array.isArray(segment.seed_ms) || segment.seed_ms.length !== 2 || !segment.seed_ms.every(t => finite(t) && t >= start && t <= end) || segment.seed_ms[1]-segment.seed_ms[0] < 150 || segment.seed_ms[1]-segment.seed_ms[0] > 2500 || !finite(segment.overlap_frames) || segment.overlap_frames < 5)) return [];
      const rows = segment.samples.slice(0, 100).filter(s => finite(s.media_ms) && s.media_ms >= start && s.media_ms <= end && point(s.ground) && finite(s.player_width) && s.player_width >= .005 && s.player_width <= .4 && finite(s.confidence) && s.confidence >= .55);
      if (rows.length !== segment.samples.length || rows.length < 3 || rows.some((s, i) => i > 0 && (s.media_ms <= rows[i-1].media_ms || s.media_ms - rows[i-1].media_ms > (contour ? 75 : 120)))) return [];
      return [rows.map((s, i) => ({...s, groundProxy: !contour, contourTrack: contour, ballTrail: null, groundTrail: i > 0 && s.motion_from_ms === rows[i-1].media_ms && Array.isArray(s.groundTrail) && s.groundTrail.length === 2 && s.groundTrail.every(point) && s.groundTrail[1][0] === s.ground[0] && s.groundTrail[1][1] === s.ground[1] ? s.groundTrail : null}))];
    }) : [];
  return {
    tracks,
    start,
    end,
    stops: ordered,
    samples
  };
}
export function graphicsAt(room, mediaMs) {
  // A source-observed endpoint takes precedence over an optical box proxy.
  const observed = room.samples.find(s => s.groundTrail && Math.abs(s.media_ms-mediaMs) <= 60);
  if (observed) return {...observed, ballTrail: null, endpointMotion: true};
  const candidates = (room.tracks || []).filter(rows => mediaMs >= rows[0].media_ms && mediaMs <= rows[rows.length-1].media_ms).map(rows => rows.reduce((a, b) => Math.abs(a.media_ms-mediaMs) <= Math.abs(b.media_ms-mediaMs) ? a : b)).filter(s => Math.abs(s.media_ms-mediaMs) <= (s.contourTrack ? 40 : 60));
  if (candidates.length) {
    const chosen = candidates.sort((a,b) => b.confidence-a.confidence)[0];
    // Competing tap windows must agree; do not choose a nearby teammate by confidence.
    if (candidates.every(s => Math.hypot(s.ground[0]-chosen.ground[0], s.ground[1]-chosen.ground[1]) <= Math.min(s.player_width, chosen.player_width)*.5)) return chosen;
    return null;
  }
  // Brief exact-frame marks; never interpolate across occlusion, camera motion or sparse samples.
  const sample = room.samples.reduce((best, s) => Math.abs(s.media_ms - mediaMs) < Math.abs((best?.media_ms ?? Infinity) - mediaMs) ? s : best, null);
  if (!sample || Math.abs(sample.media_ms - mediaMs) > 60) return null;
  const i = room.samples.indexOf(sample),
    previous = room.samples[i - 1];
  const moves = (a,b) => a && b && Math.hypot(b[0]-a[0],b[1]-a[1]) > .008;
  const ballTrail = moves(previous?.ball,sample.ball) && sample.camera_static_from_previous && sample.media_ms - previous.media_ms <= 300 && sample.media_ms > previous.media_ms ? [previous.ball, sample.ball] : null;
  const groundTrail = moves(previous?.ground,sample.ground) && sample.camera_static_from_previous && sample.media_ms - previous.media_ms <= 300 && sample.media_ms > previous.media_ms ? [previous.ground, sample.ground] : null;
  return {
    ...sample,
    ballTrail,
    groundTrail
  };
}

