const fs = require('fs');
const assert = require('node:assert/strict');
(async () => {
 const source = fs.readFileSync(require('path').join(__dirname, '../src/components/report-v2/matchRoomModel.js'));
 const {roomFor, graphicsAt, ballAt} = await import('data:text/javascript;base64,'+source.toString('base64'));
 const points = [100,125,150,175,200].map(t=>({media_ms:t,frame_id:`s${t}`,ground:[.4,.7],player_width:.05,confidence:.9,
  foreground:{method:'SOURCE_PERSON_MASK',media_ms:t,frame_id:`s${t}`,polygons:[[[.3,.4],[.5,.4],[.5,.7]]]}}));
 const raw = {version:1,event_id:'e',source_video_sha256:'source',coordinate_space:'FULL_FRAME_NORMALIZED',start_ms:0,end_ms:1000,
  samples:[points[0],points[4]].map(p=>({...p,identity_status:'CONFIRMED'})),
  tracking:{version:1,event_id:'e',source_video_sha256:'source',method:'SOURCE_OBSERVATION_INSTANCE_CONTOUR',segments:[{
   reference_frame:'s100',observation_reference_frames:['s100','s200'],ground_method:'LOWER_VISIBLE_CONTOUR',
   source_frame_coverage:'COMPLETE_SEGMENT',overlap_frames:5,samples:points}]}};
 const comment=()=>({event_id:'e',source_video_sha256:'source',match_room:structuredClone(raw)});
 assert.equal(roomFor(comment(),0).tracks.length,1);
 assert.ok(graphicsAt(roomFor(comment(),0),150));
 assert.equal(graphicsAt(roomFor(comment(),0),75),null);
 assert.equal(graphicsAt(roomFor(comment(),0),225),null);
 let bad=comment();bad.match_room.samples.push({frame_id:'uncertain',media_ms:150,identity_status:'UNCERTAIN'});
 assert.equal(roomFor(bad,0).tracks.length,0);
 bad=comment();bad.match_room.tracking.segments[0].samples[2].foreground=null;
 assert.equal(roomFor(bad,0).tracks.length,0);
 bad=comment();bad.match_room.tracking.source_video_sha256='other';assert.equal(roomFor(bad,0).tracks.length,0);
 bad=comment();bad.match_room.samples[0].ball=[.4,.5];bad.match_room.samples[1].ball=[.6,.5];
 bad.match_room.samples[1].camera_static_from_previous=true;
 assert.equal(graphicsAt(roomFor(bad,0),200).ballTrail,null);
 const moving={movingBall:[{start_ms:100,arrival_ms:220,end_ms:220,samples:[{media_ms:140}]}]};
 assert.equal(ballAt(moving,140).opacity,1);
 assert.equal(ballAt(moving,221),null);
 const bridged=comment();
 const bridge=bridged.match_room.tracking.segments[0];
 bridge.ground_method='CAMERA_SPACE_DISPLAY_BRIDGE';
 bridge.identity_method='BIDIRECTIONAL_INSTANCE_AGREEMENT';
 bridge.camera_method='BACKGROUND_AFFINE';
 Object.assign(bridge.samples[2],{ground:null,display_ground:[.42,.7],display_estimated:true,source_ground_observation:false});
 bridged.match_room.samples.push({frame_id:'hidden-foot',media_ms:150,identity_status:'CONFIRMED',ground:null});
 assert.ok(graphicsAt(roomFor(bridged,0),150)?.ground);
 assert.equal(bridge.samples[2].ground,null); // Source evidence never rewritten.
 assert.equal(graphicsAt(roomFor(bridged,0),225),null);
 for (const alter of [
  c=>c.match_room.samples.at(-1).identity_status='UNCERTAIN',
  c=>c.match_room.tracking.segments[0].camera_method=null,
  c=>c.match_room.tracking.segments[0].identity_method=null,
  c=>c.match_room.tracking.segments[0].samples[2].foreground=null,
  c=>c.match_room.tracking.segments[0].samples[2].source_ground_observation=true,
  c=>c.match_room.tracking.segments[0].samples[0].ground=null,
 ]) {const c=structuredClone(bridged);alter(c);assert.equal(roomFor(c,0).tracks.length,0);}
 const sourceEndpoint=structuredClone(bridged);
 Object.assign(sourceEndpoint.match_room.tracking.segments[0].samples[0],{ground:null,display_ground:[.4,.7],display_estimated:true,display_origin:'BOUND_SOURCE_OBSERVATION',source_ground_observation:false});
 assert.ok(graphicsAt(roomFor(sourceEndpoint,0),100)?.ground);
 sourceEndpoint.match_room.tracking.segments[0].samples[0].display_ground=[.6,.7];
 assert.equal(roomFor(sourceEndpoint,0).tracks.length,0);
 const nullRow=structuredClone(bridged);nullRow.match_room.tracking.segments[0].samples[0]=null;
 assert.equal(roomFor(nullRow,0).tracks.length,0);
 const chain={movingBall:[
  {start_ms:100,arrival_ms:200,end_ms:200,reference_frames:['a','b'],samples:[{media_ms:100,ballTrail:[[.2,.5],[.4,.5]]},{media_ms:200,ballTrail:[[.2,.5],[.4,.5]]}]},
  {start_ms:200,arrival_ms:300,end_ms:300,reference_frames:['b','c'],samples:[{media_ms:200,ballTrail:[[.4,.5],[.6,.5]]},{media_ms:217,ballTrail:[[.4,.5],[.6,.5]]},{media_ms:300,ballTrail:[[.4,.5],[.6,.5]]}]}
 ]};
 assert.equal(ballAt(chain,200).opacity,1);
 assert.equal(ballAt(chain,217).opacity,1);
 assert.equal(ballAt(chain,350),null);
 const unrelated=structuredClone(chain);unrelated.movingBall[1].reference_frames[0]='other';
 assert.equal(ballAt(unrelated,200),null);
 const conflicting=structuredClone(chain);conflicting.movingBall[1].samples[0].ballTrail[0]=[.8,.8];
 assert.equal(ballAt(conflicting,200),null);
 const ranked={sourcePositionsOnly:true,samples:[],tracks:[
  [{media_ms:200,ground:[.4,.7],player_width:.05,confidence:.8,contourTrack:true,sourceFrameContour:true}],
  [{media_ms:200,ground:[.47,.7],player_width:.05,confidence:.9,contourTrack:true,sourceFrameContour:true,display_estimated:true}]
 ]};
 assert.deepEqual(graphicsAt(ranked,200).ground,[.4,.7]);
 ranked.tracks[0][0].display_estimated=true;
 assert.equal(graphicsAt(ranked,200),null);
 ranked.tracks[0][0].display_origin='BOUND_SOURCE_OBSERVATION';
 assert.deepEqual(graphicsAt(ranked,200).ground,[.4,.7]);
 ranked.tracks[1][0].display_origin='BOUND_SOURCE_OBSERVATION';
 assert.equal(graphicsAt(ranked,200),null);
 console.log('Localization and camera-space display bridge contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
