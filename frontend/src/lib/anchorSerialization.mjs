// FIX 00A — pure serializer for Scout Mode marker anchors.
// Extracted from UploadPage so the exact upload payload is unit-testable.
// Preserves t, box (4-decimal), segment (when numeric), verify (ONLY when
// explicitly true — never inferred from array position) and thumb.
import selection from '../components/marker-studio/selectionHints.cjs';
export function serializeMarkerAnchors(anchors) {
  return (anchors || []).map((a) => ({
    t: Number((a.t || 0).toFixed(2)),
    box: {
      x: Number(a.box.x.toFixed(4)),
      y: Number(a.box.y.toFixed(4)),
      w: Number(a.box.w.toFixed(4)),
      h: Number(a.box.h.toFixed(4)),
    },
    ...(Number.isFinite(a.segment) ? { segment: a.segment } : {}),
    ...(a.verify === true ? { verify: true } : {}),
    ...selection.hints(a),
    ...(a.continuity?.length ? { continuity: a.continuity.slice(0, 2).map(c => ({
      t: c.t, box: { ...c.box }, segment: c.segment, same_player: c.same_player === true, ...selection.hints(c),
    })) } : {}),
    thumb: a.thumb || undefined,
  }));
}
