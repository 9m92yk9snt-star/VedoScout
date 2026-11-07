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

test('combined graphics use the same current person masks at fractional source timestamps',()=>{
 const stanceRows=[1000,1033,1067,1100,1133,1167,1200,1233,1267,1300].map(media_ms=>({media_ms,frame_id:`g${media_ms}`,ground:[.4,.8],player_width:.06,confidence:.9,
  foreground:{method:'SOURCE_PERSON_MASK',media_ms,frame_id:`g${media_ms}`,polygons:[[[.2,.4],[.3,.4],[.3,.8]]]}}));
 const raw=proof.comment.match_room;
 const combined={...proof,comment:{...proof.comment,match_room:{...raw,start_ms:1000,end_ms:1300,samples:raw.samples.map((s,i)=>({...s,ground:[.4,.8],player_width:.06})).concat([{frame_id:'later',media_ms:1300,ground:[.4,.8],player_width:.06}]),
  tracking:{...raw.tracking,method:'TAP_OBSERVATION_BOUND_CONTOUR',segments:[{reference_frame:'release',observation_reference_frames:['release','later'],seed_ms:[900],overlap_frames:10,ground_method:'LOWER_VISIBLE_CONTOUR',source_frame_coverage:'COMPLETE',samples:stanceRows}]}}}};
 const ui=render(<MatchRoomPlayer proof={combined} videoUrl="/source.mp4" onClose={()=>{}}/>);
 fireEvent.play(ui.getByTestId('match-room-video'));
 act(()=>callback(0,{mediaTime:.566667}));
 expect(ui.getByTestId('match-room-ball-arrow').getAttribute('data-source-ms')).toBe('1067');
 const marker=ui.getByTestId('match-room-player-marker');
 expect(marker.getAttribute('data-source-ms')).toBe('1067');
 expect(marker.parentElement.getAttribute('mask')).toMatch(/^url\(#people-/);
 const legacy={...combined,comment:{...combined.comment,tele_clip_timebase:undefined}};
 ui.rerender(<MatchRoomPlayer proof={legacy} videoUrl="/source.mp4" onClose={()=>{}}/>);
 expect(ui.queryByTestId('match-room-player-marker')).toBeNull();
 expect(ui.queryByTestId('match-room-ball-arrow')).toBeNull();
});


test('a completed scheduler still discloses initial contour budget limits without drawing new marks',()=>{
 const info={kind:'INITIAL_CONTOUR_PROCESSING',
   initial_windows_examined:2,initial_windows_time_budget_reached:1,
   total_accepted_segments:0,source_frame_coverage_complete:null,
   status:'INITIAL_WINDOW_TIME_BUDGET_REACHED'};
 const raw=proof.comment.match_room;
 const withBudget={...proof,comment:{...proof.comment,match_room:{...raw,tracking_status:'COMPLETED',
   contour_processing_budget:info}}};
 const ui=render(<MatchRoomPlayer proof={withBudget} videoUrl="/source.mp4" onClose={()=>{}}/>);
 expect(ui.getByTestId('match-room-contour-time-limit').textContent).toContain('initial tracking passes');
 expect(ui.queryByTestId('match-room-player-marker')).toBeNull();
 // Historical Orman1000 data predates the new budget metadata. Read the
 // original source tracker diagnostics, without a backend report rewrite.
 const legacy={...proof,comment:{...proof.comment,match_room:{
   ...raw,tracking_status:'COMPLETED',tracking:{
     ...raw.tracking,contour_diagnostics:{windows:[{status:'TIME_BUDGET'}]}
   }
 }}};
 ui.rerender(<MatchRoomPlayer proof={legacy} videoUrl="/source.mp4" onClose={()=>{}}/>);
 expect(ui.getByTestId('match-room-contour-time-limit').textContent).toContain('processing limit');
 expect(ui.queryByTestId('match-room-player-marker')).toBeNull();
 ui.rerender(<MatchRoomPlayer proof={proof} videoUrl="/source.mp4" onClose={()=>{}}/>);
 expect(ui.queryByTestId('match-room-contour-time-limit')).toBeNull();
});
