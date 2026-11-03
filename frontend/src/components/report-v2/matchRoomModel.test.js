import { roomFor, graphicsAt, depthAt } from './matchRoomModel';

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

const ballSamples = raw.samples.map((s,i)=>({...s,camera_static_from_previous:false,...(i?{
  ball_motion_method:'BACKGROUND_AFFINE_BALL_ENDPOINTS',ball_motion_start_ms:10000,
  ballTrail:[[.65,.7],s.ball]
}:{})}));
const ballRoom = (samples=ballSamples, tracking=undefined) => roomFor({...comment,match_room:{...raw,samples,tracking}},10);
test('camera corrected ball arrow is independent of the player arrow and track',()=>{
  const samples=ballSamples.map((s,i)=>i?{...s,motion_method:'BACKGROUND_AFFINE_ENDPOINTS',motion_start_ms:10000,groundTrail:[[.4,.8],s.ground]}:s);
  const mark=graphicsAt(ballRoom(samples),10250);
  expect(mark.groundTrail).toEqual([[.4,.8],[.45,.8]]);
  expect(mark.ballTrail).toEqual([[.65,.7],[.6,.7]]);
  const t={...tracked,segments:[{reference_frame:'s2',samples:[10120,10200,10280].map(media_ms=>({media_ms,ground:[.4,.8],player_width:.06,confidence:.8}))}]};
  expect(graphicsAt(ballRoom(ballSamples,t),10250).groundProxy).toBe(true);
  expect(graphicsAt(ballRoom(ballSamples,t),10250).ballTrail).toEqual([[.65,.7],[.6,.7]]);
  t.segments.push({...t.segments[0],samples:t.segments[0].samples.map(s=>({...s,ground:[.7,.8]}))});
  expect(graphicsAt(ballRoom(ballSamples,t),10250).ground).toBeNull();
  expect(graphicsAt(ballRoom(ballSamples,t),10250).ballTrail).toEqual([[.65,.7],[.6,.7]]);
});
test('ball endpoint arrows cannot borrow player geometry, skip observations or outlive their source frame',()=>{
  for (const changes of [{ball_motion_start_ms:9900},{ball_motion_method:'BACKGROUND_AFFINE_ENDPOINTS'},{ballTrail:[[.65,.7],[.2,.3]]}]) {
    expect(graphicsAt(ballRoom([ballSamples[0],{...ballSamples[1],...changes}]),10250).ballTrail).toBeNull();
  }
  expect(graphicsAt(ballRoom([{...ballSamples[0],ball:null},ballSamples[1]]),10250).ballTrail).toBeNull();
  expect(graphicsAt(ballRoom([ballSamples[0],{frame_id:'missing-ball',media_ms:10120},ballSamples[1]]),10250).ballTrail).toBeNull();
  expect(graphicsAt(ballRoom(),10320)).toBeNull();
  expect(graphicsAt(ballRoom([{...ballSamples[0],media_ms:9800},{...ballSamples[1],ball_motion_start_ms:9800}]),10250).ballTrail).toBeNull();
});

test('long pass direction requires the recorded release and receiving actor',()=>{
  const samples=[{...raw.samples[0],ball_phase:'RELEASE'}, {...raw.samples[1],media_ms:10800,ball_phase:'RECEIVED',receiver:'p7',camera_static_from_previous:false,ball_motion_method:'BACKGROUND_AFFINE_PASS_ENDPOINTS',ball_motion_start_ms:10000,ballTrail:[[.5,.8],[.6,.7]]}];
  const contract={...raw,action_type:'PASS',action_outcome:'COMPLETED',contact_ms:10000,receiver_visual_id:'p7',samples};
  const room=r=>roomFor({...comment,match_room:r},10);
  expect(graphicsAt(room(contract),10800).ballTrail).toEqual([[.5,.8],[.6,.7]]);
  for(const change of [{action_type:'DRIBBLE'},{action_outcome:'INCOMPLETE'},{receiver_visual_id:'other'},{contact_ms:10500},{samples:[{...samples[0],ball_phase:null},samples[1]]}]) {
    expect(graphicsAt(room({...contract,...change}),10800).ballTrail).toBeNull();
  }
});


test('depth cutouts are restricted to the paused measured frame', () => {
  const foreground = {media_ms: 1000, polygons: [[[0,0],[1,0],[1,1]]]};
  expect(depthAt({foreground}, 1000, true)).toEqual(foreground);
  expect(depthAt({foreground}, 1000, false)).toBeNull();
  expect(depthAt({foreground}, 1033, true)).toBeNull();
});

test('foreground rejects a different frame and invalid polygon geometry', () => {
  const sample = raw.samples[0];
  const good = {method: 'SOURCE_PERSON_MASK', frame_id: sample.frame_id, media_ms: sample.media_ms, polygons: [[[0,0],[1,0],[1,1]]]};
  const make = foreground => roomFor({...comment,match_room:{...raw,samples:[{...sample,foreground}]}},10).samples[0];
  expect(make(good).foreground).toEqual(good);
  expect(make({...good,frame_id:'another-frame'}).foreground).toBeNull();
  expect(make({...good,polygons:[[[0,0],[2,0],[1,1]]]}).foreground).toBeNull();
});

test('sparse motion evidence cannot override disagreeing player tracks', () => {
  const a = {media_ms:1000,ground:[.2,.8],player_width:.05,confidence:.9};
  const b = {...a,ground:[.7,.8]};
  const sample = {...a,groundTrail:[[.1,.8],[.2,.8]],ballTrail:[[.2,.7],[.5,.7]]};
  const mark = graphicsAt({samples:[sample],tracks:[[a],[b]]},1000);
  expect(mark.ground).toBeNull();
  expect(mark.ballTrail).toEqual(sample.ballTrail);
});


test('contour display moves continuously without altering measurements or joining tracks',()=>{
  const row=(t,x)=>({media_ms:t,ground:[x,.8],player_width:.06,confidence:.9,contourTrack:true});
  const rows=[row(10000,.4),row(10066,.46),row(10100,.48)];
  const room={samples:[],tracks:[rows]};
  expect(Math.abs(graphicsAt(room,10033).ground[0]-.43)).toBeLessThan(1e-10);
  expect(rows[0].ground).toEqual([.4,.8]);
  expect(graphicsAt(room,9999)).toBeNull();
  expect(graphicsAt(room,10101)).toBeNull();
  expect(graphicsAt({...room,tracks:[[rows[0]],[rows[1],rows[2]]]},10033)).toBeNull();
  expect(graphicsAt({...room,tracks:[rows,rows.map(s=>({...s,ground:[.8,.8]}))]},10033)).toBeNull();
});

test('extended display gaps require explicit identity-continuity permission',()=>{
 const segment={reference_frame:'s1',ground_method:'LOWER_VISIBLE_CONTOUR',seed_ms:[10000,10250],overlap_frames:5,samples:[10000,10033,10200].map(media_ms=>({media_ms,ground:[.4,.8],player_width:.06,confidence:.9}))};
 const make=seg=>roomFor({...comment,match_room:{...raw,tracking:{version:1,event_id:'e1',source_video_sha256:'source',method:'TAP_BIDIRECTIONAL_INSTANCE_CONTOUR',segments:[seg]}}},10);
 expect(make(segment).tracks).toEqual([]);
 const room=make({...segment,presentation_gap_ms:200});
 expect(graphicsAt(room,10100).ground).toEqual([.4,.8]);
 expect(make({...segment,presentation_gap_ms:200,samples:segment.samples.map((s,i)=>i===2?{...s,media_ms:10234}:s)}).tracks).toEqual([]);
});

test('reacquired tracks need both source-bound identity references',()=>{
 const segment={reference_frame:'s1',identity_reference_frames:['s1','s2'],ground_method:'LOWER_VISIBLE_CONTOUR',seed_ms:[10000,10250],overlap_frames:5,presentation_gap_ms:200,samples:[10000,10125,10250].map(media_ms=>({media_ms,ground:[.4,.8],player_width:.06,confidence:.9}))};
 const make=s=>roomFor({...comment,match_room:{...raw,tracking:{version:1,event_id:'e1',source_video_sha256:'source',method:'TAP_REACQUIRED_INSTANCE_CONTOUR',segments:[s]}}},10);
 expect(graphicsAt(make(segment),10100).ground).toEqual([.4,.8]);
 for(const refs of [undefined,['s1'],['s1','s1'],['s1','missing'],['s2','s1']])expect(make({...segment,identity_reference_frames:refs}).tracks).toEqual([]);
});
