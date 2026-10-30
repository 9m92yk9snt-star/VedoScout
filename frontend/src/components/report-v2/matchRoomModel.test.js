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
