const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const api=import('data:text/javascript;base64,'+fs.readFileSync(path.join(__dirname,'../src/components/report-v2/matchRoomModel.js')).toString('base64'));
function fixture(){const samples=[1000,1050,1100].map(media_ms=>({media_ms,frame_id:`f${media_ms}`,directionTrail:[[.4,.6],[.5,.55]],foreground:{method:'SOURCE_PERSON_MASK',media_ms,frame_id:`f${media_ms}`,polygons:[[[.1,.1],[.2,.1],[.2,.2]]]}}));return {event_id:'e',source_video_sha256:'source',match_room:{version:1,event_id:'e',source_video_sha256:'source',coordinate_space:'FULL_FRAME_NORMALIZED',start_ms:1000,end_ms:1200,samples:[],reviewed_direction:{status:'OWNER_APPROVED_DIRECTION',playback_status:'VERIFIED',method:'REVIEWED_DIRECTION_BACKGROUND_AFFINE',is_measured_ball_trajectory:false,review_id:'review',event_id:'e',source_video_sha256:'source',reference_ms:950,start_ms:1000,end_ms:1100,samples}}};}
test('reviewed direction is exact-frame only and never becomes ball evidence',async()=>{const {roomFor,reviewedDirectionAt,ballAt}=await api;const c=fixture(),before=JSON.stringify(c),r=roomFor(c,1);assert.equal(reviewedDirectionAt(r,1050).reviewedDirection,true);for(const t of [950,1025,1150])assert.equal(reviewedDirectionAt(r,t),null);assert.equal(ballAt(r,1050),null);assert.equal(JSON.stringify(c),before);});
test('wrong source, missing approval, stale masks, gaps and incomplete coverage reject whole direction',async()=>{const {roomFor,reviewedDirectionAt}=await api;for(const mutate of [d=>d.source_video_sha256='other',d=>d.event_id='other',d=>d.status='PENDING',d=>delete d.playback_status,d=>d.playback_status='REJECTED',d=>d.is_measured_ball_trajectory=true,d=>d.samples[1].foreground.media_ms=1000,d=>d.samples.splice(1,1),d=>d.samples.pop()]){const c=fixture();mutate(c.match_room.reviewed_direction);assert.equal(reviewedDirectionAt(roomFor(c,1),1000),null);}});
test('rejected Orman1000 playback stays hidden without withdrawing direction approval',async()=>{const {roomFor,reviewedDirectionAt}=await api;const zlib=require('node:zlib');const d=JSON.parse(zlib.gunzipSync(Buffer.from(fs.readFileSync(path.join(__dirname,'../../testdata/matchroom-completion/orman1000-approved-direction-2026-11-07.json.gz.b64'),'utf8').trim(),'base64')));const c=fixture();Object.assign(c,{event_id:d.event_id,source_video_sha256:d.source_video_sha256});Object.assign(c.match_room,{event_id:d.event_id,source_video_sha256:d.source_video_sha256,start_ms:49881,end_ms:52015,reviewed_direction:d});const r=roomFor(c,50);assert.equal(d.status,'OWNER_APPROVED_DIRECTION');assert.equal(d.playback_status,'REJECTED');assert.equal(d.samples.length,27);for(const s of d.samples)assert.equal(reviewedDirectionAt(r,s.media_ms),null);});

test('moving reconstructed tip stays exact-frame display geometry and pending playback stays hidden',async()=>{
  const {roomFor,reviewedDirectionAt,ballAt}=await api;
  const c=fixture(),d=c.match_room.reviewed_direction;
  d.animation={kind:'RECONSTRUCTED_PASS',arrival_ms:1100};
  d.samples.forEach((s,i)=>{s.directionTrail=[[.4,.6],[.4+i*.05,.6-i*.025]];});
  const r=roomFor(c,1);
  assert.deepEqual(reviewedDirectionAt(r,1050).ballTrail,[[.4,.6],[.45,.575]]);
  assert.equal(reviewedDirectionAt(r,1075),null);
  assert.equal(ballAt(r,1050),null);
  assert.equal(reviewedDirectionAt(r,1150),null);
  d.playback_status='PENDING';
  assert.equal(reviewedDirectionAt(roomFor(c,1),1050),null);
});
