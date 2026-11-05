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
function stanceDisplayPoint(rows, i) {
  const a = rows[i-1], s = rows[i], b = rows[i+1];
  if (!a || !b || s.media_ms-a.media_ms > 75 || b.media_ms-s.media_ms > 75) return s.ground;
  // A kicking boot briefly changes the silhouette's stance centre. Suppress
  // isolated lateral spikes, without shifting its measured ground height.
  const median = [a.ground[0], s.ground[0], b.ground[0]].sort((x,y) => x-y)[1];
  const cap = Math.min(a.player_width, s.player_width, b.player_width)*.25;
  return [s.ground[0]+Math.max(-cap, Math.min(cap, median-s.ground[0])), s.ground[1]];
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
  const tracks = bound && tracking?.version === 1 && tracking.event_id === raw.event_id && tracking.source_video_sha256 === raw.source_video_sha256 && ["TAP_OPTICAL_GROUND_PROXY", "TAP_BIDIRECTIONAL_INSTANCE_CONTOUR", "TAP_REACQUIRED_INSTANCE_CONTOUR", "TAP_OBSERVATION_BOUND_CONTOUR", "SOURCE_OBSERVATION_INSTANCE_CONTOUR"].includes(tracking.method) && Array.isArray(tracking.segments)
    ? tracking.segments.slice(0, 96).flatMap(segment => {
      if (!Array.isArray(segment.samples) || segment.samples.some(s => !s) || typeof segment.reference_frame !== "string") return [];
      const contour = tracking.method !== "TAP_OPTICAL_GROUND_PROXY";
      const reacquired = tracking.method === "TAP_REACQUIRED_INSTANCE_CONTOUR";
      const localized = tracking.method === "SOURCE_OBSERVATION_INSTANCE_CONTOUR";
      const sourceFrameContour = localized || tracking.method === "TAP_OBSERVATION_BOUND_CONTOUR";
      const bridge = localized && segment.ground_method === 'CAMERA_SPACE_DISPLAY_BRIDGE';
      if (bridge && (!['BIDIRECTIONAL_INSTANCE_AGREEMENT','SOURCE_CONFIRMED_ENDPOINT_BRIDGE'].includes(segment.identity_method) || segment.camera_method !== 'BACKGROUND_AFFINE' || segment.samples.length < 5 || segment.samples.at(-1).media_ms-segment.samples[0].media_ms > 800 || ![segment.samples[0], segment.samples.at(-1)].every(s => point(s.ground) || (s.display_origin === 'BOUND_SOURCE_OBSERVATION' && point(s.display_ground) && raw.samples.some(o => o.media_ms === s.media_ms && o.identity_status === 'CONFIRMED' && point(o.ground) && Math.hypot(...o.ground.map((v,i) => v-s.display_ground[i])) < .002))))) return [];
      if (segment.samples.some(s => !s || (s.display_ground !== undefined && (!bridge || s.ground != null || !point(s.display_ground) || s.display_estimated !== true || s.source_ground_observation !== false)))) return [];
      if (segment.samples.some(s => s.display_origin === 'BOUND_SOURCE_OBSERVATION' && (!point(s.display_ground) || !raw.samples.some(o => o.media_ms === s.media_ms && o.identity_status === 'CONFIRMED' && point(o.ground) && Math.hypot(...o.ground.map((v,i) => v-s.display_ground[i])) < .002)))) return [];
      if (contour && ((!bridge && segment.ground_method !== "LOWER_VISIBLE_CONTOUR") || !samples.some(s => s.frame_id === segment.reference_frame) || !finite(segment.overlap_frames) || segment.overlap_frames < 5)) return [];
      if (localized) {
        const refs = segment.observation_reference_frames;
        if (segment.source_frame_coverage !== 'COMPLETE_SEGMENT' || !Array.isArray(refs) || refs.length < 2 || refs.length > 160 || new Set(refs).size !== refs.length || !refs.includes(segment.reference_frame) || segment.samples.length < 5 || segment.samples.some(s => !s || !foregroundFor(s))) return [];
        const first = segment.samples[0].media_ms, last = segment.samples[segment.samples.length-1].media_ms;
        if (!refs.every(id => raw.samples.some(s => s.frame_id === id && s.identity_status === 'CONFIRMED' && point(s.ground) && segment.samples.some(row => row.media_ms === s.media_ms))) || raw.samples.some(s => s.media_ms >= first && s.media_ms <= last && (s.identity_status !== 'CONFIRMED' || (!bridge && !point(s.ground) && segment.identity_method !== 'BIDIRECTIONAL_INSTANCE_AGREEMENT')))) return [];
      } else if (sourceFrameContour) {
        const refs = segment.observation_reference_frames;
        if (segment.source_frame_coverage !== 'COMPLETE' || !Array.isArray(segment.seed_ms) || segment.seed_ms.length !== 1 || !finite(segment.seed_ms[0]) || segment.seed_ms[0] < start-750 || segment.seed_ms[0] >= start || end-segment.seed_ms[0] > 2500 || end-start > 2000 || !Array.isArray(refs) || refs.length < 2 || refs.length > 12 || new Set(refs).size !== refs.length || !refs.includes(segment.reference_frame)) return [];
        const supported = refs.map(id => samples.find(s => s.frame_id === id && s.ground));
        if (supported.some(s => !s || !segment.samples.some(row => row && Math.abs(row.media_ms-s.media_ms) <= 2)) || Math.max(...supported.map(s => s.media_ms))-Math.min(...supported.map(s => s.media_ms)) < 200) return [];
        if (segment.samples.length < 5 || segment.samples.some(s => !s || !foregroundFor(s)) || segment.samples[0].media_ms > start+35 || segment.samples[segment.samples.length-1].media_ms < end-35) return [];
      } else if (contour && (!Array.isArray(segment.seed_ms) || segment.seed_ms.length !== 2 || !segment.seed_ms.every(t => finite(t) && t >= start && t <= end) || segment.seed_ms[1]-segment.seed_ms[0] < 150 || segment.seed_ms[1]-segment.seed_ms[0] > 2500)) return [];
      if (reacquired && (!Array.isArray(segment.identity_reference_frames) || segment.identity_reference_frames.length !== 2 || new Set(segment.identity_reference_frames).size !== 2 || !segment.identity_reference_frames.every((id,i) => samples.some(s => s.frame_id === id && s.ground && Math.abs(s.media_ms-segment.seed_ms[i]) <= 40)))) return [];
      const rows = segment.samples.slice(0, 100).map(s => s.display_estimated === true && bridge ? {...s, ground: s.display_ground} : s).filter(s => finite(s.media_ms) && s.media_ms >= start && s.media_ms <= end && point(s.ground) && finite(s.player_width) && s.player_width >= .005 && s.player_width <= .4 && finite(s.confidence) && s.confidence >= .55);
      if (rows.length !== segment.samples.length || rows.length < 3 || rows.some((s, i) => i > 0 && (s.media_ms <= rows[i-1].media_ms || s.media_ms - rows[i-1].media_ms > (contour ? (!sourceFrameContour && segment.presentation_gap_ms === 200 ? 200 : 75) : 120)))) return [];
      return [rows.map((s, i) => ({...s, player_width: rows.slice(Math.max(0, i-2), i+3).map(r => r.player_width).sort((a,b) => a-b)[Math.floor(rows.slice(Math.max(0, i-2), i+3).length/2)], groundProxy: !contour, contourTrack: contour, sourceFrameContour, foreground: sourceFrameContour ? foregroundFor(s) : null, ballTrail: null, groundTrail: i > 0 && s.motion_from_ms === rows[i-1].media_ms && Array.isArray(s.groundTrail) && s.groundTrail.length === 2 && s.groundTrail.every(point) && s.groundTrail[1][0] === s.ground[0] && s.groundTrail[1][1] === s.ground[1] ? s.groundTrail : null}))];
    }) : [];
  // Only complete, event-bound sequences with a fresh mask on every source frame.
  const movingBall = bound && tracking?.version === 1 && tracking.event_id === raw.event_id && tracking.source_video_sha256 === raw.source_video_sha256 && Array.isArray(tracking.ball_playback)
    ? tracking.ball_playback.slice(0, 16).flatMap(segment => {
      if (!segment || !Array.isArray(segment.reference_frames) || segment.reference_frames.length !== 2) return [];
      const [first, last] = segment.reference_frames;
      const release = samples.find(s => s.frame_id === first && s.media_ms === segment.start_ms && s.ball);
      const arrival = samples.find(s => s.frame_id === last && s.media_ms === segment.arrival_ms && s.ballTrail);
      const rawArrival = raw.samples.find(s => s.frame_id === last && s.media_ms === segment.arrival_ms);
      const rows = segment.samples;
      const arrowPoint = p => Array.isArray(p) && p.length === 2 && p.every(x => finite(x) && x >= -1 && x <= 2);
      if (segment.method !== 'SOURCE_FRAME_BALL_DIRECTION' || !release || !arrival || rawArrival?.ball_motion_start_ms !== segment.start_ms || !finite(segment.end_ms) || segment.end_ms < segment.arrival_ms || segment.end_ms > Math.min(end, segment.arrival_ms+250) || !Array.isArray(rows) || rows.length < 2 || rows.length > 150) return [];
      if (rows.some(s => !s || typeof s !== 'object') || Math.abs(rows[0].media_ms-segment.start_ms) > 2 || rows[rows.length-1].media_ms !== segment.end_ms || !rows.some(s => Math.abs(s.media_ms-segment.arrival_ms) <= 2)) return [];
      if (rows.some((s, i) => !finite(s.media_ms) || s.media_ms < start || s.media_ms > end || typeof s.frame_id !== 'string' || !foregroundFor(s) || !Array.isArray(s.ballTrail) || s.ballTrail.length !== 2 || !s.ballTrail.every(arrowPoint) || (i > 0 && (s.media_ms <= rows[i-1].media_ms || s.media_ms-rows[i-1].media_ms > 75)))) return [];
      if (Math.hypot(...rows[0].ballTrail[0].map((v, i) => v-release.ball[i])) > .002) return [];
      const endpoint = rows.find(s => Math.abs(s.media_ms-segment.arrival_ms) <= 2);
      if (Math.hypot(...endpoint.ballTrail[1].map((v, i) => v-arrival.ball[i])) > .002) return [];
      if (segment.kick_reference_frames) {
        const refs = segment.kick_reference_frames;
        if (!Array.isArray(refs) || refs.length < 2 || refs.length > 17 || new Set(refs).size !== refs.length ||
            refs.at(-2) !== first || refs.at(-1) !== last || !finite(raw.contact_ms) ||
            !['SHOT', 'PASS'].includes(raw.action_type)) return [];
        const chain = refs.map(id => raw.samples.find(s => s.frame_id === id && point(s.ball)));
        if (chain.some(s => !s || !samples.some(x => x.frame_id === s.frame_id && x.ball)) || Math.abs(chain[0].media_ms-raw.contact_ms) > 80 ||
            chain.at(-1).media_ms-chain[0].media_ms > 2000 ||
            chain.some((s,i) => i > 0 && (s.ball_motion_start_ms !== chain[i-1].media_ms ||
              s.media_ms <= chain[i-1].media_ms ||
              (refs.length > 2 && raw.samples.some(x => x.media_ms > chain[i-1].media_ms && x.media_ms < s.media_ms))))) return [];
        if (rows.some(s => !Array.isArray(s.kickTrail) || s.kickTrail.length !== 2 || !s.kickTrail.every(arrowPoint)) ||
            Math.hypot(...endpoint.kickTrail[1].map((v,i)=>v-arrival.ball[i])) > .002 ||
            Math.hypot(...rows[0].kickTrail[1].map((v,i)=>v-release.ball[i])) > .002) return [];
      } else if (rows.some(s => s.kickTrail)) return [];
      return [{...segment, samples: rows}];
    }) : [];
  return {
    sourcePositionsOnly: bound && Array.isArray(raw.samples) && raw.samples.some(s => typeof s?.identity_status === 'string'),
    movingBall,
    tracks,
    start,
    end,
    stops: ordered,
    samples
  };
}
// Display coordinates only: retain measured samples and never join separate tracks.
function stanceAt(rows, mediaMs) {
  // Dense contours carry a mask for this exact source picture. Rounded JSON
  // milliseconds must not make a fractional decoder PTS select the prior mask.
  if (rows[0]?.sourceFrameContour) {
    const i = rows.findIndex(s => Math.abs(s.media_ms-mediaMs) <= 2);
    return i < 0 ? null : {...rows[i], ground: stanceDisplayPoint(rows, i), displayFiltered: true};
  }
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
  const ballTrail = room.sourcePositionsOnly ? null : sample?.ballTrail || (staticPair && moves(previous.ball,sample.ball) ? [previous.ball,sample.ball] : null);
  const withBall = mark => mark ? {...mark, ballTrail, foreground: mark.sourceFrameContour ? mark.foreground : sample?.foreground} : ballTrail ? {...sample, ground:null, groundTrail:null, ballTrail} : null;
  // A source-observed endpoint takes precedence over an optical box proxy.
  const observed = nearest(room.samples.filter(s => s.groundTrail && Math.abs(s.media_ms-mediaMs) <= 60));
  const candidates = (room.tracks || []).map(rows => stanceAt(rows, mediaMs)).filter(s => s && Math.abs(s.media_ms-mediaMs) <= (s.contourTrack ? 40 : 60));
  if (candidates.length) {
    // A coarse presentation estimate fills a missing measurement; it must not
    // erase a fresh measured contour when both cover the same source picture.
    const measured = candidates.filter(s => s.display_estimated !== true);
    const bound = candidates.filter(s => s.display_origin === 'BOUND_SOURCE_OBSERVATION');
    const supported = measured.length ? measured : bound.length ? bound : candidates;
    const chosen = supported.sort((a,b) => b.confidence-a.confidence)[0];
    // Competing evidence at the same level must still agree.
    if (supported.every(s => Math.hypot(s.ground[0]-chosen.ground[0], s.ground[1]-chosen.ground[1]) <= Math.min(s.player_width, chosen.player_width)*.5)) return withBall(chosen);
    return withBall(null);
  }
  if (room.sourcePositionsOnly) return null;
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


// Call with presented frame PTS, never an advancing wall clock. Seeking, pausing
// and changing playback speed reproduce the same geometry and opacity.
function continuesBallDirection(a, b) {
  if (!a || !b || a === b || a.end_ms !== a.arrival_ms || a.arrival_ms !== b.start_ms ||
      !Array.isArray(a.reference_frames) || !Array.isArray(b.reference_frames) ||
      a.reference_frames.length !== 2 || b.reference_frames.length !== 2 ||
      a.reference_frames[1] !== b.reference_frames[0]) return false;
  const tip = a.samples?.at(-1)?.ballTrail?.[1], tail = b.samples?.[0]?.ballTrail?.[0];
  return point(tip) && point(tail) && Math.hypot(...tip.map((v,i) => v-tail[i])) <= .002;
}

export function ballAt(room, mediaMs) {
  if (!finite(mediaMs)) return null;
  const candidates = (room.movingBall || []).filter(s => mediaMs >= s.start_ms-2 && mediaMs <= s.end_ms+2);
  let segment;
  if (candidates.length === 1) segment = candidates[0];
  else if (candidates.length === 2) {
    const [a,b] = candidates.slice().sort((a,b) => a.start_ms-b.start_ms);
    if (!continuesBallDirection(a,b)) return null;
    segment = b;
  } else return null;
  const sample = segment.samples.find(s => Math.abs(s.media_ms-mediaMs) <= 2);
  if (!sample) return null;
  const smooth = t => { const x = Math.max(0, Math.min(1, t)); return x*x*(3-2*x); };
  const fade = segment.end_ms > segment.arrival_ms ? 1-smooth((mediaMs-segment.arrival_ms)/(segment.end_ms-segment.arrival_ms)) : 1;
  const fadeInMs = Math.min(120, (segment.arrival_ms-segment.start_ms)/3);
  // Adjacent observations of the same ball are one presentation. Do not
  // flash the arrow off and restart its fade at each measured endpoint.
  const incoming = (room.movingBall || []).filter(s => continuesBallDirection(s, segment));
  const fadeIn = incoming.length === 1 ? 1 : smooth((mediaMs-segment.start_ms)/fadeInMs);
  return {...sample, ballTrail: sample.kickTrail || sample.ballTrail, opacity: fadeIn*fade};
}

// Clip a direction line to the visible picture, preserving its orientation.
// An edge arrow points towards an offscreen endpoint; it does not relocate it.
export function clipArrowToFrame(trail) {
  const [a, b] = trail;
  const d = b.map((v, i) => v-a[i]);
  let lo = 0, hi = 1;
  for (let axis = 0; axis < 2; axis++) {
    if (Math.abs(d[axis]) < 1e-10) {
      if (a[axis] < .015 || a[axis] > .985) return null;
    } else {
      const u = (.015-a[axis])/d[axis], v = (.985-a[axis])/d[axis];
      lo = Math.max(lo, Math.min(u, v));
      hi = Math.min(hi, Math.max(u, v));
    }
  }
  return lo < hi ? [lo, hi].map(t => a.map((v, i) => v+t*d[i])) : null;
}
