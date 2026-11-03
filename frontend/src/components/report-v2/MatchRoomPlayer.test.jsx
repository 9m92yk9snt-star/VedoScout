import React from 'react';
import { render, fireEvent, act, cleanup } from '@testing-library/react';
import { MatchRoomPlayer } from './MatchRoomPlayer';

const observed = [
  {frame_id:'release',media_ms:1000,ball:[.4,.7]},
  {frame_id:'receive',media_ms:1100,ball:[.2,.7],ball_motion_start_ms:1000,ball_motion_method:'BACKGROUND_AFFINE_BALL_ENDPOINTS',ballTrail:[[.4,.7],[.2,.7]]}
];
const rows = [1000,1033,1067,1100].map(media_ms => ({media_ms,frame_id:`f${media_ms}`,ballTrail:[[.4,.7],[.2,.7]],
  foreground:{method:'SOURCE_PERSON_MASK',media_ms,frame_id:`f${media_ms}`,polygons:[[[.2,.4],[.3,.4],[.3,.8]]]}}));
const proof = {clip:'/clip.mp4',clipStart:.5,comment:{event_id:'e',source_video_sha256:'source',evidence_time_ms:1100,tele_clip_timebase:'SOURCE_PTS_ALIGNED',match_room:{
  version:1,event_id:'e',source_video_sha256:'source',coordinate_space:'FULL_FRAME_NORMALIZED',start_ms:900,end_ms:1200,samples:observed,
  tracking:{version:1,event_id:'e',source_video_sha256:'source',segments:[],ball_playback:[{method:'SOURCE_FRAME_BALL_DIRECTION',start_ms:1000,arrival_ms:1100,end_ms:1100,reference_frames:['release','receive'],samples:rows}]}
}}};
let callback;
beforeEach(()=>{
  jest.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
  HTMLVideoElement.prototype.requestVideoFrameCallback = jest.fn(fn=>{callback=fn;return 1;});
  HTMLVideoElement.prototype.cancelVideoFrameCallback = jest.fn();
});
afterEach(()=>{cleanup();jest.restoreAllMocks();delete HTMLVideoElement.prototype.requestVideoFrameCallback;delete HTMLVideoElement.prototype.cancelVideoFrameCallback;});

test('playing arrows use the presented frame and its mask despite an advancing currentTime',()=>{
  const ui=render(<MatchRoomPlayer proof={proof} videoUrl="/source.mp4" onClose={()=>{}}/>);
  const video=ui.getByTestId('match-room-video');
  video.currentTime=.599;
  fireEvent.play(video);
  act(()=>callback(0,{mediaTime:.567}));
  const arrow=ui.getByTestId('match-room-ball-arrow');
  expect(arrow.getAttribute('data-source-ms')).toBe('1067');
  expect(arrow.getAttribute('mask')).toMatch(/^url\(#ball-people-/);
  const original=arrow.outerHTML;
  fireEvent.timeUpdate(video);
  expect(ui.getByTestId('match-room-ball-arrow').outerHTML).toBe(original);
  fireEvent.seeking(video);
  expect(ui.queryByTestId('match-room-ball-arrow')).toBeNull();
  act(()=>callback(0,{mediaTime:.533}));
  expect(ui.getByTestId('match-room-ball-arrow').getAttribute('data-source-ms')).toBe('1033');
  act(()=>callback(0,{mediaTime:.567}));
  expect(ui.getByTestId('match-room-ball-arrow').outerHTML).toBe(original);
});

test('legacy clips without a source-aligned timebase cannot reuse moving masks',()=>{
  const legacy={...proof,comment:{...proof.comment,tele_clip_timebase:undefined}};
  const ui=render(<MatchRoomPlayer proof={legacy} videoUrl="/source.mp4" onClose={()=>{}}/>);
  fireEvent.play(ui.getByTestId('match-room-video'));
  act(()=>callback(0,{mediaTime:.567}));
  expect(ui.queryByTestId('match-room-ball-arrow')).toBeNull();
});
