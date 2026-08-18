// FIX 01 — frontend EVENT/EVIDENCE AUTHORITY joins (pure, node-testable).
// Authority reports (evidence_authority_version >= 1) bind proofs by stable
// IDs with EXACT joins only — the legacy nearest-timestamp fallback chain is
// disallowed for them. Legacy reports keep their historical behaviour.

export function tsToSeconds(ts) {
  if (!ts || typeof ts !== "string" || !ts.includes(":")) return null;
  const [m, s] = ts.split(":").map((x) => parseInt(x, 10));
  if (Number.isNaN(m) || Number.isNaN(s)) return null;
  return m * 60 + s;
}

export function isAuthorityReport(full) {
  return ((full && full.evidence_authority_version) || 0) >= 1;
}

// Resolve the tele proof clip for a card. Priority (authority reports):
// 1. evidence_id exact  2. event_id exact  3. nothing (never an unrelated clip).
// Legacy reports: existing timestamp-string match.
export function resolveProofClip(comments, ref, authority) {
  const list = Array.isArray(comments) ? comments : [];
  const evId = ref && ref.evidenceId;
  const evtId = ref && ref.eventId;
  const ts = ref && ref.timestamp;
  let vc = null;
  if (evId) vc = list.find((c) => c && c.evidence_id === evId && c.tele_clip_url) || null;
  if (!vc && evtId) vc = list.find((c) => c && c.event_id === evtId && c.tele_clip_url) || null;
  if (!vc && !authority && ts) vc = list.find((c) => c && c.timestamp === ts && c.tele_clip_url) || null;
  return vc;
}

// Frame lookup used by the derive layer. Authority mode: ID-exact only —
// no nearest <=8s, no any-unused-frame fallback. A card without an exact
// bound proof gets none.
export function buildFrameLookup(comments, authority) {
  const entries = (Array.isArray(comments) ? comments : [])
    .filter((c) => c && c.frame_url && c.identity_verified !== false)
    .map((c) => ({
      ts: c.timestamp, sec: tsToSeconds(c.timestamp), url: c.frame_url,
      verified: c.identity_verified === true,
      evidenceId: c.evidence_id || null, eventId: c.event_id || null,
    }));
  const used = new Set();
  const find = (ts, ref) => {
    let best = null;
    if (authority) {
      const evId = ref && ref.evidenceId;
      const evtId = ref && ref.eventId;
      for (const e of entries) {
        if (used.has(e.url)) continue;
        if (evId && e.evidenceId === evId) { best = e; break; }
        if (!evId && evtId && e.eventId === evtId) { best = e; break; }
      }
    } else {
      const sec = tsToSeconds(ts);
      for (const e of entries) {
        if (used.has(e.url)) continue;
        if (ts && e.ts === ts) { best = e; break; }
        if (sec != null && e.sec != null) {
          const d = Math.abs(e.sec - sec);
          if (d <= 8 && (!best || d < Math.abs((best.sec ?? 999) - sec))) best = e;
        }
      }
      if (!best) best = entries.find((e) => !used.has(e.url)) || null;
    }
    if (best) used.add(best.url);
    // ts included so callers can display the FRAME's exact second — the photo,
    // the shown timestamp and the proof video must always be the same moment.
    return best ? { url: best.url, verified: !!best.verified, ts: best.ts || null } : null;
  };
  return { entries, find };
}
