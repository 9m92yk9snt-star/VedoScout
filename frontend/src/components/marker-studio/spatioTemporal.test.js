/**
 * Quick logic smoke tests for spatioTemporal.js — Trust Stack #2.
 *
 * Run with:  cd /app/frontend && npx jest src/components/marker-studio/spatioTemporal.test.js
 *
 * Falls back to a manual node-driver: `node spatioTemporal.test.js` will
 * also work because the module is plain ESM-friendly JS with no React deps.
 */

import {
  boxCentreDist,
  filterByMotion,
  maxPlausibleDelta,
  scoreCandidate,
  suggestSecondTapTime,
  MAX_PLAYER_SPEED_MPS,
} from "./spatioTemporal";

describe("spatioTemporal — physics filter", () => {
  test("boxCentreDist computes normalised Euclidean distance", () => {
    const a = { x: 0.0, y: 0.0, w: 0.1, h: 0.1 }; // centre (0.05, 0.05)
    const b = { x: 0.4, y: 0.0, w: 0.1, h: 0.1 }; // centre (0.45, 0.05)
    expect(boxCentreDist(a, b)).toBeCloseTo(0.4, 3);
  });

  test("maxPlausibleDelta scales with dt and pitch width", () => {
    // 8 m/s × 1 s = 8 m ; pitch 40 m → 0.20 normalised
    expect(maxPlausibleDelta(1, 40)).toBeCloseTo(0.2, 3);
    // 8 m/s × 0.5 s = 4 m ; pitch 40 m → 0.10
    expect(maxPlausibleDelta(0.5, 40)).toBeCloseTo(0.1, 3);
  });

  test("filterByMotion rejects teleporting anchors", () => {
    const refAnchor = {
      t: 0,
      box: { x: 0.0, y: 0.5, w: 0.05, h: 0.2 },
      confidence: 1,
    };
    const candidates = [
      // Plausible: 1s later, 5m apart on 40m pitch → 0.125 < 0.20 limit
      {
        t: 1.0,
        box: { x: 0.125, y: 0.5, w: 0.05, h: 0.2 },
        confidence: 0.92,
      },
      // Implausible: 0.3s later, across the whole pitch
      {
        t: 0.3,
        box: { x: 0.9, y: 0.5, w: 0.05, h: 0.2 },
        confidence: 0.88,
      },
    ];
    const { kept, rejected } = filterByMotion(candidates, refAnchor);
    expect(kept).toHaveLength(1);
    expect(rejected).toHaveLength(1);
    expect(rejected[0].reason).toMatch(/m\/s/);
  });

  test("filterByMotion keeps all when motion is plausible", () => {
    const refAnchor = { t: 0, box: { x: 0.0, y: 0.5, w: 0.05, h: 0.2 }, confidence: 1 };
    const candidates = [
      { t: 2.0, box: { x: 0.10, y: 0.5, w: 0.05, h: 0.2 }, confidence: 0.95 },
      { t: 4.0, box: { x: 0.20, y: 0.5, w: 0.05, h: 0.2 }, confidence: 0.91 },
    ];
    const { kept, rejected } = filterByMotion(candidates, refAnchor);
    expect(kept).toHaveLength(2);
    expect(rejected).toHaveLength(0);
  });

  test("MAX_PLAYER_SPEED_MPS is the documented 8 m/s", () => {
    expect(MAX_PLAYER_SPEED_MPS).toBe(8.0);
  });
});

describe("spatioTemporal — confidence scoring", () => {
  test("identical jersey colour scores high (>= 0.85)", () => {
    const ref = {
      avgJerseyRGB: [200, 30, 30],
      avgShortsRGB: [10, 10, 50],
      avgHairRGB: [80, 50, 30],
      crops: [{ area: 10000 }, { area: 9000 }, { area: 11000 }],
    };
    const cand = {
      jerseyRGB: [200, 30, 30],
      shortsRGB: [10, 10, 50],
      hairRGB: [80, 50, 30],
      area: 10000,
    };
    const r = scoreCandidate(cand, ref);
    expect(r.score).toBeGreaterThanOrEqual(0.85);
    expect(["green", "yellow"]).toContain(r.band);
  });

  test("wildly different jersey scores low", () => {
    const ref = {
      avgJerseyRGB: [200, 30, 30], // red
      avgShortsRGB: null,
      avgHairRGB: null,
      crops: [],
    };
    const cand = {
      jerseyRGB: [30, 30, 200], // blue
      shortsRGB: null,
      hairRGB: null,
      area: 9000,
    };
    const r = scoreCandidate(cand, ref);
    expect(r.score).toBeLessThan(0.7);
    expect(r.band).toBe("red");
  });

  test("missing channels degrade gracefully (neutral 0.7)", () => {
    const ref = { avgJerseyRGB: [200, 30, 30], crops: [] };
    const cand = { jerseyRGB: [200, 30, 30] };
    const r = scoreCandidate(cand, ref);
    // Jersey perfect → 0.50; shorts/hair missing → 0.7 each * (0.20+0.15);
    // sizeOK 1 → 0.15 → score around 0.50 + 0.245 + 0.15 ≈ 0.895
    expect(r.score).toBeGreaterThanOrEqual(0.80);
  });
});

describe("spatioTemporal — suggestSecondTapTime", () => {
  test("returns the weakest anchor's time, farthest from refT", () => {
    const ref = 10.0;
    const anchors = [
      { t: 11, confidence: 0.95 }, // green, close — ignore
      { t: 18, confidence: 0.72 }, // red, far — winner
      { t: 14, confidence: 0.81 }, // yellow, near
    ];
    expect(suggestSecondTapTime(anchors, ref)).toBe(18);
  });

  test("returns null when all anchors are green", () => {
    const ref = 10.0;
    const anchors = [
      { t: 11, confidence: 0.95 },
      { t: 14, confidence: 0.92 },
    ];
    expect(suggestSecondTapTime(anchors, ref)).toBeNull();
  });
});
