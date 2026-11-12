// Keep the exact source-bound graphics out of the report database document.
export async function loadGraphics(comment, signal) {
  const room = comment?.match_room, asset = room?.graphics_asset;
  if (!asset) return comment;
  const response = await fetch(asset.url, {signal});
  if (!response.ok) throw new Error('GRAPHICS_DOWNLOAD_FAILED');
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== asset.bytes) throw new Error('GRAPHICS_SIZE_MISMATCH');
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const sha = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
  if (sha !== asset.sha256) throw new Error('GRAPHICS_CHECKSUM_MISMATCH');
  const graphics = JSON.parse(new TextDecoder().decode(bytes));
  if (graphics.event_id !== comment.event_id || graphics.source_video_sha256 !== comment.source_video_sha256 || graphics.version !== room.version)
    throw new Error('GRAPHICS_SOURCE_MISMATCH');
  return {...comment, match_room: graphics};
}
