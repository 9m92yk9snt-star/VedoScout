/**
 * spatioTemporal.js — Improvement #2 + confidence math.
 *
 * Hard physics filter: a 12-year-old footballer cannot exceed ~8 m/s.
 * For anchors A and B sampled at times tA, tB:
 *
 *     |centre(A) - centre(B)| / |tA - tB|   ≤   MAX_SPEED_NORM
 *
 * If this is violated the AI suggested an impossible jump and the worse
 * anchor (lower confidence) is rejected. Pure logic, zero compute.
 *
 * Also exposes a confidence scorer that grades each candidate detection
 * against the multi-pose reference fingerprint:
 *
 *     score = w_jersey * jersey_similarity
 *           + w_shorts * shorts_similarity
 *           + w_hair   * hair_similarity
 *           + w_size   * box_size_plausibility
 *           - speed_penalty (if the candidate would teleport)
 *
 * Bands:  GREEN  ≥ 0.90    YELLOW 0.80-0.89    RED < 0.80
 *
 * `wrapper-normalised` boxes are used throughout so the filter is
 * resolution-independent. The `pitchWidthM` parameter calibrates the
 * "what counts as 8 m/s in normalised coords" — we assume the frame
 * roughly covers the full pitch width (the common parent-clip shot),
 * which translates into ~30-45 m. We pick 40 m as a safe default.
 */

const DEFAULT_PITCH_WIDTH_M = 40;
const MAX_PLAYER_SPEED_MPS = 8.0; // youth football realistic top end

/** Euclidean distance between two normalised (0..1) box centres. */
export function boxCentreDist(a, b) {
  const acx = a.x + a.w / 2;
  const acy = a.y + a.h / 2;
  const bcx = b.x + b.w / 2;
  const bcy = b.y + b.h / 2;
  return Math.sqrt((acx - bcx) ** 2 + (acy - bcy) ** 2);
}

/**
 * Compute the maximum plausible normalised box-centre displacement between
 * two timestamps. Players going faster than MAX_PLAYER_SPEED_MPS are
 * physically impossible — those anchors are rejected.
 */
export function maxPlausibleDelta(dt, pitchWidthM = DEFAULT_PITCH_WIDTH_M) {
  const meters = MAX_PLAYER_SPEED_MPS * Math.max(0.01, Math.abs(dt));
  return meters / pitchWidthM;
}

/**
 * Filter out anchors that violate physics relative to a reference anchor.
 * Returns { kept: [...], rejected: [{anchor, reason}] }.
 *
 * Strategy:
 *  - For every candidate anchor, compute the speed needed to reach it from
 *    the closest *kept* neighbour (in time).
 *  - If the implied speed > MAX_PLAYER_SPEED_MPS, mark as rejected.
 *  - We seed `kept` with the highest-confidence candidate first so the
 *    physics check is applied from the most trusted point outward.
 */
export function filterByMotion(candidates, refAnchor, opts = {}) {
  const pitchWidthM = opts.pitchWidthM || DEFAULT_PITCH_WIDTH_M;
  if (!candidates?.length) return { kept: [], rejected: [] };

  // Always treat the user's marked anchor as ground truth — seed `kept` with it
  const sorted = [...candidates].sort(
    (a, b) => (b.confidence ?? 0) - (a.confidence ?? 0),
  );
  const kept = refAnchor ? [refAnchor] : [];
  const rejected = [];

  for (const c of sorted) {
    let ok = true;
    let worstSpeed = 0;
    let worstNeighbour = null;
    for (const k of kept) {
      const dt = Math.abs(c.t - k.t);
      if (dt < 0.01) continue;
      const dist = boxCentreDist(c.box, k.box);
      const speedNorm = dist / dt;
      const limitNorm = maxPlausibleDelta(1.0, pitchWidthM); // per-second limit
      const speedMps = speedNorm * pitchWidthM;
      if (speedMps > worstSpeed) {
        worstSpeed = speedMps;
        worstNeighbour = k;
      }
      if (speedNorm > limitNorm) {
        ok = false;
        break;
      }
    }
    if (ok) kept.push(c);
    else
      rejected.push({
        anchor: c,
        reason: `Implied speed ${worstSpeed.toFixed(1)} m/s > ${MAX_PLAYER_SPEED_MPS} m/s`,
        worstNeighbour,
      });
  }
  // Drop the seed back out so we only return *new* anchors
  const newAnchors = refAnchor ? kept.filter((a) => a !== refAnchor) : kept;
  return { kept: newAnchors, rejected };
}

/* Confidence scoring ──────────────────────────────────────────────── */

const COLOR_SIM = (a, b) => {
  if (!a || !b) return 0.5; // missing channel ⇒ neutral
  const d = Math.sqrt(
    (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2,
  );
  // 0 RGB = perfect; 220 RGB ≈ very different. Map to [0,1] similarity.
  return Math.max(0, 1 - d / 220);
};

/**
 * Score a candidate detection against the multi-pose reference fingerprint.
 * Returns { score: 0..1, band: 'green'|'yellow'|'red', detail: {...} }.
 *
 * @param {{ jerseyRGB, shortsRGB?, hairRGB?, area? }} candidate  — sampled at detection
 * @param {{ avgJerseyRGB, avgShortsRGB?, avgHairRGB? }} ref      — from enrollFromMark
 */
export function scoreCandidate(candidate, ref) {
  if (!candidate || !ref) return { score: 0, band: "red", detail: {} };
  const jersey = COLOR_SIM(candidate.jerseyRGB, ref.avgJerseyRGB);
  const shorts = ref.avgShortsRGB
    ? COLOR_SIM(candidate.shortsRGB, ref.avgShortsRGB)
    : 0.7; // neutral if reference unknown
  const hair = ref.avgHairRGB
    ? COLOR_SIM(candidate.hairRGB, ref.avgHairRGB)
    : 0.7;
  // Box-size plausibility — penalise candidates wildly different in scale
  // (likely a different person or a passer-by far in the background).
  let sizeOK = 1.0;
  if (candidate.area && ref.crops?.length) {
    const refAvgArea =
      ref.crops.reduce((s, c) => s + (c.area || 0), 0) / ref.crops.length;
    if (refAvgArea > 0) {
      const ratio = candidate.area / refAvgArea;
      // ratio 1 = identical, 0.3 = 3× smaller, 3 = 3× bigger
      const offset = Math.abs(Math.log10(Math.max(0.05, ratio)));
      sizeOK = Math.max(0.4, 1 - offset * 0.6);
    }
  }
  const score =
    0.50 * jersey +
    0.20 * shorts +
    0.15 * hair +
    0.15 * sizeOK;

  const band = score >= 0.90 ? "green" : score >= 0.80 ? "yellow" : "red";

  return {
    score: Math.round(score * 100) / 100,
    band,
    detail: { jersey, shorts, hair, sizeOK },
  };
}

/**
 * Pick the suggested second-tap timestamp from a list of weak anchors.
 * Heuristic: the moment with the LOWEST confidence (red/yellow) that is
 * farthest from the user's first anchor in time — that's where one more
 * tap will help the most.
 */
export function suggestSecondTapTime(anchors, refAnchorT) {
  if (!anchors?.length) return null;
  const weak = anchors.filter((a) => (a.confidence ?? 1) < 0.85);
  if (!weak.length) return null;
  // Sort by time-distance from refAnchorT descending, then by lowest confidence
  weak.sort((a, b) => {
    const da = Math.abs(a.t - (refAnchorT ?? 0));
    const db = Math.abs(b.t - (refAnchorT ?? 0));
    if (db !== da) return db - da;
    return (a.confidence ?? 0) - (b.confidence ?? 0);
  });
  return weak[0].t;
}

export { DEFAULT_PITCH_WIDTH_M, MAX_PLAYER_SPEED_MPS };
