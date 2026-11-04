const fs = require('fs');
const assert = require('node:assert/strict');
(async () => {
 const source = fs.readFileSync(require('path').join(__dirname, '../src/components/report-v2/matchRoomModel.js'));
 const {roomFor, graphicsAt} = await import('data:text/javascript;base64,'+source.toString('base64'));
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
 let bad=comment();bad.match_room.samples.push({frame_id:'uncertain',media_ms:150,identity_status:'UNCERTAIN'});
 assert.equal(roomFor(bad,0).tracks.length,0);
 bad=comment();bad.match_room.tracking.segments[0].samples[2].foreground=null;
 assert.equal(roomFor(bad,0).tracks.length,0);
 bad=comment();bad.match_room.tracking.source_video_sha256='other';assert.equal(roomFor(bad,0).tracks.length,0);
 console.log('4 localization frontend contracts passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
