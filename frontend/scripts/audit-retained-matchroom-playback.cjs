// Read-only exact-PTS audit of the retained Match Room report.
// Uses production matchRoomModel.js acceptance gates, not guessed coordinates.
// No model calls, mutations, frame interpolation or browser-success claims.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');

const expectedSource = 'b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999';
const parse = v => typeof v === 'string' ? parse(JSON.parse(v)) : v;

function sourcePts(clip, offsetSeconds) {
  const data = JSON.parse(execFileSync('ffprobe', [
    '-v', 'error', '-select_streams', 'v:0',
    '-show_entries', 'frame=best_effort_timestamp_time',
    '-of', 'json', clip
  ], {encoding:'utf8', timeout:30000}));
  const stamps = (data.frames || []).map(f => Math.round(
    (Number(f.best_effort_timestamp_time) + offsetSeconds) * 1000
  ));
  assert.ok(stamps.length >= 2 && stamps.every((t,i) => Number.isFinite(t) && (i === 0 || t > stamps[i-1])),
    'Actual nonmonotonic or missing decoded clip PTS');
  return stamps;
}

async function main() {
  const reportFile = path.resolve(process.argv[2] || '');
  const outputFile = path.resolve(process.argv[3] || '');
  assert.ok(process.argv[2] && process.argv[3] && !fs.existsSync(outputFile), 'Report and new output required');
  const doc = JSON.parse(fs.readFileSync(reportFile, 'utf8'));
  const anchors = JSON.parse(fs.readFileSync(
    path.resolve(__dirname, '../../testdata/sequence-pilot-orman400/anchors.json'), 'utf8'));
  const {roomFor, graphicsAt, ballAt} = await import('data:text/javascript;base64,' +
    fs.readFileSync(path.resolve(__dirname, '../src/components/report-v2/matchRoomModel.js')).toString('base64'));

  assert.equal(doc.full_report_status, 'ready', 'Source report must be fully ready');
  assert.equal(doc.canonical_events?.source_video_sha256, expectedSource);
  assert.deepEqual(parse(doc.raw_marker_anchors), parse(anchors.raw_marker_anchors), 'All original human taps required');
  assert.equal(parse(anchors.raw_marker_anchors).length, 10);
  const audit = doc.match_room_localization || {};
  assert.equal(audit.source_video_sha256, expectedSource);
  const rows = doc.full_report?.video_comments || [];
  assert.equal(rows.length, 8, 'Expected exactly the eight retained source-bound cards');
  const events = new Map(doc.canonical_events.events.map(e => [e.event_id,e]));
  const seen = new Set();
  const clips = [];

  for (const row of rows) {
    const event = events.get(row.event_id);
    assert.ok(event && !seen.has(row.event_id), 'Missing or repeated canonical event');
    seen.add(row.event_id);
    const roomRaw = row.match_room || {}, tracking = roomRaw.tracking || {};
    assert.equal(row.source_video_sha256, expectedSource);
    assert.equal(roomRaw.source_video_sha256, expectedSource);
    assert.equal(tracking.source_video_sha256, expectedSource);
    assert.equal(roomRaw.event_id, row.event_id);
    assert.equal(tracking.event_id, row.event_id);
    assert.equal(row.tele_clip_timebase,'SOURCE_PTS_ALIGNED');
    assert.ok(Number.isFinite(row.tele_clip_start));
    assert.ok(Number.isFinite(row.tele_clip_end));
    assert.equal(row.evidence_time_ms, event.proof.frame_ms);
    assert.equal(row.sequence_event_native, true);
    const clipName = path.basename(row.tele_clip_url || '');
    assert.ok(clipName.endsWith('.mp4') && clipName !== '.mp4', 'Missing source-bound clip');
    const clipFile = path.join(path.dirname(reportFile), 'frames', clipName);
    assert.ok(fs.statSync(clipFile).size > 0, 'Retained clip absent or empty');
    const room = roomFor(row, row.evidence_time_ms / 1000);
    assert.ok(room.sourcePositionsOnly, 'Only source-position authority is eligible');
    assert.ok(room.start <= room.end && room.tracks.length > 0, 'Unbound match room output');
    const stamps = sourcePts(clipFile,row.tele_clip_start)
      .filter(ms => room.start <= ms && ms <= room.end);
    assert.ok(stamps.length >= 4, 'Source video PTS inside proof window required');
    const covered=[], uncovered=[], arrow=[];
    for(const stamp of stamps) {
      const g = graphicsAt(room, stamp);
      if (g?.sourceFrameContour && Array.isArray(g.ground) &&
          g.foreground?.method === 'SOURCE_PERSON_MASK' &&
          Math.abs(g.foreground.media_ms-stamp) <= 2) covered.push(stamp);
      else uncovered.push(stamp);
      if (ballAt(room, stamp)) arrow.push(stamp);
    }
    const gaps = [];
    for(const stamp of uncovered) {
      if (gaps.length && stamp-gaps[gaps.length-1].end_ms <= 75)
        gaps[gaps.length-1].end_ms = stamp;
      else gaps.push({start_ms:stamp,end_ms:stamp});
    }
    clips.push({
      event_id: row.event_id, canonical_action_type:event.canonical_action_type,
      video_source_sha256:expectedSource, window_ms:[room.start,room.end],
      actual_video_pts_count:stamps.length,
      accepted_source_contour_pts:covered.length,
      unmarked_source_pts:uncovered.length,
      audited_visible_ratio:covered.length/stamps.length,
      unmarked_runs:gaps.slice(0,32), unmarked_run_count:gaps.length,
      ball_overlay_pts:arrow.length
    });
  }
  const result = {
    scope:'REAL_RETAINED_CLIP_PTS_PRODUCTION_MODEL_ACCEPTANCE_NO_BROWSER',
    source_video_sha256:expectedSource,
    original_human_taps:10,
    checked_clips:clips.length,
    clips,
    total_pts:clips.reduce((a,x)=>a+x.actual_video_pts_count,0),
    total_accepted_source_contour_pts:clips.reduce((a,x)=>a+x.accepted_source_contour_pts,0),
    total_unmarked_source_pts:clips.reduce((a,x)=>a+x.unmarked_source_pts,0),
    report_mutated:false, source_analysis_reused:true, provider_calls:0,
    source_specific_45_frame_case_verified:false,
    limitations:['Playback model evaluation is not a browser or visual overlay review.',
      'The historical 45 missing source frames belong to a different source SHA.',
      'Unmarked frames are not automatically authorized to be filled.']
  };
  fs.writeFileSync(outputFile,JSON.stringify(result,null,2));
  console.log('RETAINED_MATCHROOM_FRAME_COVERAGE='+JSON.stringify(result));
}
main().catch(err=>{console.error('COVERAGE_AUDIT_ERROR='+err.message);process.exitCode=1});
