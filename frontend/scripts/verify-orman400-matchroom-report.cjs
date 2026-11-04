// Acceptance of the retained real-video fixture, using production playback gates.
// Expected recovery/direction are assertions only; never inputs to localization.
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
(async () => {
  const document = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const source = fs.readFileSync(path.join(__dirname, '../src/components/report-v2/matchRoomModel.js'));
  const {roomFor, graphicsAt, ballAt} = await import('data:text/javascript;base64,'+source.toString('base64'));
  const original = JSON.parse(fs.readFileSync(path.join(__dirname, '../../testdata/sequence-pilot-orman400/anchors.json')));
  const parse = value => typeof value === 'string' ? parse(JSON.parse(value)) : value;
  assert.deepEqual(parse(document.raw_marker_anchors), parse(original.raw_marker_anchors));
  assert.equal(parse(document.raw_marker_anchors).length, 10);
  assert.equal(document.canonical_events.source_video_sha256, 'b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999');
  assert.equal(document.canonical_events.events.length, 17);
  assert.equal(document.full_report_status, 'ready');
  assert.equal(document.test_scope?.normal_asset_pipeline, true);
  assert.notEqual(document.test_scope?.diagnostic_composition, true, 'A composed diagnostic is not an automatic report trial');
  const receipts = Object.values(document.match_room_localization.events);
  assert.equal(receipts.length, 8);
  assert.ok(receipts.every(r => r.reused === true), 'No fresh provider requests in this replay');
  const rows = document.full_report.video_comments;
  assert.equal(rows.length, 8);
  let ellipses=0, arrows=0, hiddenPlayer=0, hiddenBall=0;
  const rooms = new Map();
  for (const row of rows) {
    const room = roomFor(row, row.evidence_time_ms/1000);
    rooms.set(row.event_id, room);
    assert.ok(room.tracks.length, `Missing accepted ellipse: ${row.event_id}`);
    assert.ok(room.movingBall.length, `Missing accepted ball direction: ${row.event_id}`);
    ellipses += room.tracks.length; arrows += room.movingBall.length;
    for (const sample of row.match_room.samples) {
      if (sample.identity_status !== 'CONFIRMED') {
        assert.ok(!graphicsAt(room, sample.media_ms)?.ground, `Uncertain player shown at ${sample.media_ms}`); hiddenPlayer++;
      }
      if (!sample.ball || sample.active_ball_status !== 'CONFIRMED') {
        assert.ok(!ballAt(room, sample.media_ms), `Uncertain ball shown at ${sample.media_ms}`); hiddenBall++;
      }
    }
  }
  const duel = rooms.get('88aa8bbdedbec570d4de');
  // Missing feet alone are no longer a reason to suppress an identity-bound
  // display bridge. The raw observation remains unchanged.
  assert.ok(graphicsAt(duel, 12783), 'Missing independently measured post-duel recovery');
  const duelRow = rows.find(r => r.event_id === '88aa8bbdedbec570d4de');
  const clip = path.join(path.dirname(process.argv[2]), 'frames', path.basename(duelRow.tele_clip_url));
  const decoded = JSON.parse(execFileSync('ffprobe', ['-v','error','-select_streams','v:0',
    '-show_entries','frame=best_effort_timestamp_time','-of','json',clip], {encoding:'utf8'}));
  const recoveryFrames = decoded.frames.map(f => Math.round((Number(f.best_effort_timestamp_time)+duelRow.tele_clip_start)*1000))
    .filter(ms => ms >= 11883 && ms <= 12883);
  assert.ok(recoveryFrames.length >= 25, 'Insufficient decoded recovery pictures');
  for (const ms of recoveryFrames) assert.ok(graphicsAt(duel, ms)?.ground, `Ellipse disappears during recovery at ${ms}`);
  const wholeDuelFrames = decoded.frames.map(f => Math.round((Number(f.best_effort_timestamp_time)+duelRow.tele_clip_start)*1000)).filter(ms => ms >= 8750 && ms <= 12883);
  for (const ms of wholeDuelFrames) assert.ok(graphicsAt(duel,ms)?.ground, `Ellipse disappears during whole duel at ${ms}`);
  const shot = rooms.get('a512ae64e102f24b3383');
  const shotRow = rows.find(r => r.event_id === 'a512ae64e102f24b3383');
  const shotClip = path.join(path.dirname(process.argv[2]), 'frames', path.basename(shotRow.tele_clip_url));
  const shotDecoded = JSON.parse(execFileSync('ffprobe', ['-v','error','-select_streams','v:0',
    '-show_entries','frame=best_effort_timestamp_time','-of','json',shotClip], {encoding:'utf8'}));
  const shotFrames = shotDecoded.frames.map(f => Math.round((Number(f.best_effort_timestamp_time)+shotRow.tele_clip_start)*1000))
    .filter(ms => ms >= 30765 && ms <= 32015);
  assert.ok(shotFrames.length >= 30, 'Insufficient decoded kick pictures');
  for (const ms of shotFrames) assert.ok(graphicsAt(shot, ms)?.ground, `Ellipse disappears during kick at ${ms}`);
  const directionFrames = shotFrames.filter(ms => ms >= 30949 && ms <= 31249);
  for (const ms of directionFrames) assert.ok(ballAt(shot,ms)?.opacity > 0, `Observed arrow blinks at ${ms}`);
  const arrow = ballAt(shot, 31115);
  assert.ok(arrow, 'Missing observed post-kick direction');
  const [a,b] = arrow.ballTrail;
  assert.ok(b[0]>a[0] && b[1]<a[1], 'This source shot travels up/right');
  console.log(JSON.stringify({technical_checks_passed:true,continuous_recovery_frames:recoveryFrames.length,continuous_whole_duel_frames:wholeDuelFrames.length,continuous_kick_frames:shotFrames.length,continuous_direction_frames:directionFrames.length,visual_acceptance:'REQUIRES_CONTINUOUS_PLAYBACK_REVIEW',original_taps:10,report_clips:8,ellipse_cards:8,arrow_cards:8,
    ellipse_segments:ellipses,moving_ball_segments:arrows,hiddenPlayerObservations:hiddenPlayer,
    hiddenBallObservations:hiddenBall,post_duel_recovery:true,post_kick_direction:true,new_model_requests:0}));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
