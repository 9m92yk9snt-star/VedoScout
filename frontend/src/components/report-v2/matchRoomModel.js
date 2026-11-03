// All times are original source milliseconds, never playback/rounded badge time.
const finite = x => typeof x === 'number' && Number.isFinite(x);
const point = p => Array.isArray(p) && p.length === 2 && p.every(x => finite(x) && x >= 0 && x <= 1);
function supportedPass(raw, sample) {
  if (raw.action_type !== 'PASS' || raw.action_outcome !== 'COMPLETED' || !finite(raw.contact_ms) || typeof raw.receiver_visual_id !== 'string' || !raw.receiver_visual_id || sample.ball_phase !== 'RECEIVED' || sample.receiver !== raw.receiver_visual_id) return false;
  const releases = raw.samples.filter(p => p.ball_phase === 'RELEASE' && point(p.ball) && typeof p.frame_id === 'string' && finite(p.media_ms) && p.media_ms >= raw.start_ms && Math.abs(p.media_ms-raw.contact_ms) <= 80);
  return releases.length === 1 && releases[0].media_ms === sample.ball_motion_start_ms;
}
function foregroundFor(s) {
  const f = s.foreground;
  return f?.method === 'SOURCE_PERSON_MASK' && f.frame_id === s.frame_id && finite(f.media_ms) && Math.abs(f.media_ms-s.media_ms) <= 2 && Array.isArray(f.polygons) && f.polygons.length > 0 && f.polygons.length <= 48 && f.polygons.every(p => Array.isArray(p) && p.length >= 3 && p.length <= 512 && p.every(point)) ? f : null;
}
export function depthAt(mark, mediaMs, paused) {
  return paused && mark?.foreground && Math.abs(mark.foreground.media_ms-mediaMs) <= 2 ? mark.foreground : null;
}
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
    foreground: foregroundFor(s),
    ground: point(s.ground) && finite(s.player_width) && s.player_width >= .005 && s.player_width <= .4 ? s.ground : null,
    player_width: s.player_width,
    ball: point(s.ball) ? s.ball : null,
    ballTrail: (s.ball_motion_method === 'BACKGROUND_AFFINE_BALL_ENDPOINTS' || (s.ball_motion_method === 'BACKGROUND_AFFINE_PASS_ENDPOINTS' && supportedPass(raw,s))) && finite(s.ball_motion_start_ms) && s.media_ms > s.ball_motion_start_ms && s.media_ms-s.ball_motion_start_ms <= (s.ball_motion_method === 'BACKGROUND_AFFINE_PASS_ENDPOINTS' ? 2000 : 300) && raw.samples.some(p => p.media_ms === s.ball_motion_start_ms && p.media_ms >= start && typeof p.frame_id === 'string' && point(p.ball)) && (s.ball_motion_method === 'BACKGROUND_AFFINE_PASS_ENDPOINTS' || !raw.samples.some(p => finite(p.media_ms) && p.media_ms > s.ball_motion_start_ms && p.media_ms < s.media_ms)) && Array.isArray(s.ballTrail) && s.ballTrail.length === 2 && s.ballTrail.every(point) && point(s.ball) && s.ballTrail[1][0] === s.ball[0] && s.ballTrail[1][1] === s.ball[1] ? s.ballTrail : null,
    groundTrail: s.motion_method === 'BACKGROUND_AFFINE_ENDPOINTS' && finite(s.motion_start_ms) && s.media_ms > s.motion_start_ms && s.media_ms-s.motion_start_ms <= 1000 && raw.samples.some(p => p.media_ms === s.motion_start_ms && point(p.ground)) && Array.isArray(s.groundTrail) && s.groundTrail.length === 2 && s.groundTrail.every(point) && point(s.ground) && s.groundTrail[1][0] === s.ground[0] && s.groundTrail[1][1] === s.ground[1] ? s.groundTrail : null,
    motion_start_ms: s.motion_start_ms,
    camera_static_from_previous: s.camera_static_from_previous === true
  })).sort((a, b) => a.media_ms - b.media_ms) : [];
  const tracking = raw?.tracking;
  const tracks = bound && tracking?.version === 1 && tracking.event_id === raw.event_id && tracking.source_video_sha256 === raw.source_video_sha256 && ["TAP_OPTICAL_GROUND_PROXY", "TAP_BIDIRECTIONAL_INSTANCE_CONTOUR", "TAP_REACQUIRED_INSTANCE_CONTOUR"].includes(tracking.method) && Array.isArray(tracking.segments)
    ? tracking.segments.slice(0, 32).flatMap(segment => {
      if (!Array.isArray(segment.samples) || typeof segment.reference_frame !== "string") return [];
      const contour = tracking.method !== "TAP_OPTICAL_GROUND_PROXY";
      const reacquired = tracking.method === "TAP_REACQUIRED_INSTANCE_CONTOUR";
      if (contour && (segment.ground_method !== "LOWER_VISIBLE_CONTOUR" || !samples.some(s => s.frame_id === segment.reference_frame) || !Array.isArray(segment.seed_ms) || segment.seed_ms.length !== 2 || !segment.seed_ms.every(t => finite(t) && t >= start && t <= end) || segment.seed_ms[1]-segment.seed_ms[0] < 150 || segment.seed_ms[1]-segment.seed_ms[0] > 2500 || !finite(segment.overlap_frames) || segment.overlap_frames < 5)) return [];
      if (reacquired && (!Array.isArray(segment.identity_reference_frames) || segment.identity_reference_frames.length !== 2 || new Set(segment.identity_reference_frames).size !== 2 || !segment.identity_reference_frames.every((id,i) => samples.some(s => s.frame_id === id && s.ground && Math.abs(s.media_ms-segment.seed_ms[i]) <= 40)))) return [];
      const rows = segment.samples.slice(0, 100).filter(s => finite(s.media_ms) && s.media_ms >= start && s.media_ms <= end && point(s.ground) && finite(s.player_width) && s.player_width >= .005 && s.player_width <= .4 && finite(s.confidence) && s.confidence >= .55);
      if (rows.length !== segment.samples.length || rows.length < 3 || rows.some((s, i) => i > 0 && (s.media_ms <= rows[i-1].media_ms || s.media_ms - rows[i-1].media_ms > (contour ? (segment.presentation_gap_ms === 200 ? 200 : 75) : 120)))) return [];
      return [rows.map((s, i) => ({...s, player_width: rows.slice(Math.max(0, i-2), i+3).map(r => r.player_width).sort((a,b) => a-b)[Math.floor(rows.slice(Math.max(0, i-2), i+3).length/2)], groundProxy: !contour, contourTrack: contour, ballTrail: null, groundTrail: i > 0 && s.motion_from_ms === rows[i-1].media_ms && Array.isArray(s.groundTrail) && s.groundTrail.length === 2 && s.groundTrail.every(point) && s.groundTrail[1][0] === s.ground[0] && s.groundTrail[1][1] === s.ground[1] ? s.groundTrail : null}))];
    }) : [];
  return {
    tracks,
    start,
    end,
    stops: ordered,
    samples
  };
}
// Display coordinates only: retain measured samples and never join separate tracks.
function stanceAt(rows, mediaMs) {
  if (!rows.length || mediaMs < rows[0].media_ms || mediaMs > rows[rows.length-1].media_ms) return null;
  const right = rows.findIndex(s => s.media_ms >= mediaMs);
  const b = rows[right];
  if (right === 0 || b.media_ms === mediaMs) return b;
  const a = rows[right-1];
  if (!a.contourTrack || !b.contourTrack) return mediaMs-a.media_ms <= b.media_ms-mediaMs ? a : b;
  const gap = b.media_ms-a.media_ms;
  if (gap <= 0 || gap > 200) return null;
  const u = (mediaMs-a.media_ms)/gap;
  return {...a, media_ms:mediaMs, displayInterpolated:true,
    ground:a.ground.map((v,i) => v+(b.ground[i]-v)*u),
    player_width:a.player_width+(b.player_width-a.player_width)*u,
    confidence:Math.min(a.confidence,b.confidence), groundTrail:null};
}
export function graphicsAt(room, mediaMs) {
  const nearest = rows => rows.reduce((best, s) => Math.abs(s.media_ms-mediaMs) < Math.abs((best?.media_ms ?? Infinity)-mediaMs) ? s : best, null);
  const sample = nearest(room.samples.filter(s => Math.abs(s.media_ms-mediaMs) <= 60));
  const previous = sample ? room.samples[room.samples.indexOf(sample)-1] : null;
  const moves = (a,b) => a && b && Math.hypot(b[0]-a[0],b[1]-a[1]) > .008;
  const staticPair = sample && previous && sample.camera_static_from_previous && sample.media_ms > previous.media_ms && sample.media_ms-previous.media_ms <= 300;
  const ballTrail = sample?.ballTrail || (staticPair && moves(previous.ball,sample.ball) ? [previous.ball,sample.ball] : null);
  const withBall = mark => mark ? {...mark, ballTrail, foreground: sample?.foreground} : ballTrail ? {...sample, ground:null, groundTrail:null, ballTrail} : null;
  // A source-observed endpoint takes precedence over an optical box proxy.
  const observed = nearest(room.samples.filter(s => s.groundTrail && Math.abs(s.media_ms-mediaMs) <= 60));
  const candidates = (room.tracks || []).map(rows => stanceAt(rows, mediaMs)).filter(s => s && Math.abs(s.media_ms-mediaMs) <= (s.contourTrack ? 40 : 60));
  if (candidates.length) {
    const chosen = candidates.sort((a,b) => b.confidence-a.confidence)[0];
    // Competing tap windows must agree; do not choose a nearby teammate by confidence.
    if (candidates.every(s => Math.hypot(s.ground[0]-chosen.ground[0], s.ground[1]-chosen.ground[1]) <= Math.min(s.player_width, chosen.player_width)*.5)) return withBall(chosen);
    return withBall(null);
  }
  if (observed) return withBall({...observed, endpointMotion: true});
  // Brief exact-frame marks; never interpolate across occlusion, camera motion or sparse samples.
  if (!sample) return null;
  const groundTrail = staticPair && moves(previous.ground,sample.ground) ? [previous.ground, sample.ground] : null;
  return {
    ...sample,
    ballTrail,
    groundTrail
  };
}

