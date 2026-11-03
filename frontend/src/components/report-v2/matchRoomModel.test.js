import { roomFor, graphicsAt } from './matchRoomModel';

test('stationary observations do not manufacture a direction', () => {
  const samples=raw.samples.map(s=>({...s,ground:[.4,.8],ball:[.5,.8]}));
  const graphic=graphicsAt(roomFor({...comment,match_room:{...raw,samples}},10),10250);
  expect(graphic.ballTrail).toBeNull();
  expect(graphic.groundTrail).toBeNull();
});
test('leftward movement keeps the observed leftward direction', () => {
  const samples=raw.samples.map((s,i)=>({...s,ball:i?[.3,.8]:[.5,.8]}));
  const graphic=graphicsAt(roomFor({...comment,match_room:{...raw,samples}},10),10250);
  expect(graphic.ballTrail[1][0]).toBeLessThan(graphic.ballTrail[0][0]);
});
const comment = {
  event_id: 'e1',
  source_video_sha256: 'source',
  evidence_time_ms: 10340
};
const raw = {
  version: 1,
  event_id: 'e1',
  source_video_sha256: 'source',
  coordinate_space: 'FULL_FRAME_NORMALIZED',
  start_ms: 9000,
  end_ms: 12000,
  stops: [{
    media_ms: 10340,
    label: 'Shot'
  }],
  samples: [{
    frame_id: 's1',
    media_ms: 10000,
    ground: [.4, .8],
    player_width: .06,
    ball: [.5, .8]
  }, {
    frame_id: 's2',
    media_ms: 10250,
    ground: [.45, .8],
    player_width: .06,
    ball: [.6, .7],
    camera_static_from_previous: true
  }]
};
test('keeps original subsecond timing; legacy reports have a real evidence stop', () => {
  expect(roomFor(comment, 10).stops[0].media_ms).toBe(10340);
  expect(roomFor({
    ...comment,
    match_room: raw
  }, 10).stops[0].media_ms).toBe(10340);
});
test('rejects geometry borrowed from another event or video', () => {
  for (const change of [{
    event_id: 'e2'
  }, {
    source_video_sha256: 'other'
  }, {
    coordinate_space: 'CROP'
  }]) expect(roomFor({
    ...comment,
    match_room: {
      ...raw,
      ...change
    }
  }, 10).samples).toEqual([]);
});
test('source time produces only short-lived exact-frame marks', () => {
  const room = roomFor({
    ...comment,
    match_room: raw
  }, 10);
  expect(graphicsAt(room, 10250).ground).toEqual([.45, .8]);
  expect(graphicsAt(room, 10250).groundTrail).toEqual([[.4, .8], [.45, .8]]);
  expect(graphicsAt(room, 10250).ballTrail).toEqual([[.5, .8], [.6, .7]]);
  expect(graphicsAt(room, 10125)).toBeNull();
  expect(graphicsAt(room, 12000)).toBeNull();
});
test('camera motion or sparse observations never produce a direction arrow', () => {
  const samples = raw.samples.map(s => ({
    ...s,
    camera_static_from_previous: false
  }));
  expect(graphicsAt(roomFor({
    ...comment,
    match_room: {
      ...raw,
      samples
    }
  }, 10), 10250).ballTrail).toBeNull();
});

const tracked = {
  version:1,event_id:'e1',source_video_sha256:'source',method:'TAP_OPTICAL_GROUND_PROXY',
  segments:[{reference_frame:'s1',samples:[10000,10080,10160].map(media_ms=>({media_ms,ground:[.4,.8],player_width:.06,confidence:.8}))}]
};
const trackedRoom = t => roomFor({...comment,match_room:{...raw,samples:[],tracking:t}},10);
test('optical segments fill only their own short intervals',()=>{
  const room=trackedRoom(tracked);
  expect(graphicsAt(room,10040).groundProxy).toBe(true);
  expect(graphicsAt(room,10200)).toBeNull();
});
test('optical geometry cannot cross event, source or missing frames',()=>{
  for (const patch of [{event_id:'other'},{source_video_sha256:'other'},{segments:[{reference_frame:'s1',samples:[10000,10080,10500].map(media_ms=>({media_ms,ground:[.4,.8],player_width:.06,confidence:.8}))}]}]) {
    expect(trackedRoom({...tracked,...patch}).tracks).toEqual([]);
  }
});
test('disagreeing optical windows hide graphics instead of choosing an identity',()=>{
  const other={...tracked.segments[0],samples:tracked.segments[0].samples.map(s=>({...s,ground:[.7,.8]}))};
  expect(graphicsAt(trackedRoom({...tracked,segments:[...tracked.segments,other]}),10080)).toBeNull();
});
test('camera compensated arrow must reference the immediately preceding sample',()=>{
  const samples=tracked.segments[0].samples.map((s,i)=>({...s,motion_from_ms:10000,groundTrail:[[.5,.8],[.4,.8]]}));
  const room=trackedRoom({...tracked,segments:[{reference_frame:'s1',samples}]});
  expect(graphicsAt(room,10080).groundTrail).toEqual([[.5,.8],[.4,.8]]);
  expect(graphicsAt(room,10160).groundTrail).toBeNull();
});
test('camera corrected source endpoints override a box proxy at the pause',()=>{
  const samples=raw.samples.map((s,i)=>i?{...s,motion_method:'BACKGROUND_AFFINE_ENDPOINTS',motion_start_ms:10000,groundTrail:[[.5,.8],s.ground]}:s);
  const room=roomFor({...comment,match_room:{...raw,samples,tracking:tracked}},10);
  const mark=graphicsAt(room,10250);
  expect(mark.endpointMotion).toBe(true);
  expect(mark.groundTrail).toEqual([[.5,.8],[.45,.8]]);
});
test('endpoint arrows need the cited earlier sample from this event',()=>{
  const samples=raw.samples.map((s,i)=>({...s,camera_static_from_previous:false,...(i?{motion_method:'BACKGROUND_AFFINE_ENDPOINTS',motion_start_ms:9900,groundTrail:[[.5,.8],s.ground]}:{})}));
  const room=roomFor({...comment,match_room:{...raw,samples}},10);
  expect(graphicsAt(room,10250).groundTrail).toBeNull();
});

const contourTracking = {
  ...tracked, method: 'TAP_BIDIRECTIONAL_INSTANCE_CONTOUR',
  segments: [{reference_frame:'s1', ground_method:'LOWER_VISIBLE_CONTOUR', seed_ms:[10000,10200], overlap_frames:6,
    samples:[10000,10033,10067,10100].map(media_ms=>({media_ms,ground:[.4,.8],player_width:.06,confidence:.8}))}]
};
const contourRoom = t => roomFor({...comment,match_room:{...raw,tracking:t}},10);
test('measured contours require two anchors and same-source support',()=>{
  expect(graphicsAt(contourRoom(contourTracking),10050).contourTrack).toBe(true);
  for (const changes of [{seed_ms:[10000,10000]},{overlap_frames:4},{reference_frame:'unknown'},{ground_method:'BOX_OFFSET'}]) {
    expect(contourRoom({...contourTracking,segments:[{...contourTracking.segments[0],...changes}]}).tracks).toEqual([]);
  }
});
test('contour samples cannot bridge a long gap or create ball arrows',()=>{
  const rows=contourTracking.segments[0].samples;
  expect(graphicsAt(contourRoom(contourTracking),10050).ballTrail).toBeNull();
  expect(contourRoom({...contourTracking,segments:[{...contourTracking.segments[0],samples:[...rows.slice(0,2),{...rows[2],media_ms:10200}]}]}).tracks).toEqual([]);
});
