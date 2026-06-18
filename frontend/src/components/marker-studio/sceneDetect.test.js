/* eslint-env jest */
/* global describe, test, expect */
/**
 * sceneDetect.test.js — pure-logic tests for `distributeHints`.
 *
 * The `detectSceneCuts` itself requires a real HTMLVideoElement so we skip
 * it in unit tests (covered by E2E later). What we DO test here is the
 * deterministic hint-distribution math that drives ScoutMode's timeline.
 *
 * Run with:  cd /app/frontend && CI=true yarn test --testPathPattern=sceneDetect --watchAll=false
 */

import { distributeHints } from "./sceneDetect";

describe("distributeHints", () => {
  test("no scene cuts → spreads count hints across the whole duration", () => {
    const hints = distributeHints(60, [], 10);
    expect(hints).toHaveLength(10);
    // first close to 5% inset, last close to 95% inset
    expect(hints[0]).toBeGreaterThanOrEqual(2.5);
    expect(hints[0]).toBeLessThanOrEqual(3.5);
    expect(hints[hints.length - 1]).toBeGreaterThanOrEqual(55);
    expect(hints[hints.length - 1]).toBeLessThanOrEqual(57.5);
    // strictly increasing
    for (let i = 1; i < hints.length; i++) {
      expect(hints[i]).toBeGreaterThanOrEqual(hints[i - 1]);
    }
  });

  test("one scene cut → 2 segments, ~5 hints per segment", () => {
    const dur = 120;
    const hints = distributeHints(dur, [60], 10);
    expect(hints).toHaveLength(10);
    const seg1 = hints.filter((t) => t < 60).length;
    const seg2 = hints.filter((t) => t >= 60).length;
    expect(seg1).toBe(5);
    expect(seg2).toBe(5);
  });

  test("two scene cuts (3 matches of equal length) → ~3-4 hints per segment", () => {
    const dur = 90;
    const hints = distributeHints(dur, [30, 60], 10);
    expect(hints).toHaveLength(10);
    const seg1 = hints.filter((t) => t < 30).length;
    const seg2 = hints.filter((t) => t >= 30 && t < 60).length;
    const seg3 = hints.filter((t) => t >= 60).length;
    // Each should be 3 or 4
    expect(seg1).toBeGreaterThanOrEqual(3);
    expect(seg1).toBeLessThanOrEqual(4);
    expect(seg2).toBeGreaterThanOrEqual(3);
    expect(seg2).toBeLessThanOrEqual(4);
    expect(seg3).toBeGreaterThanOrEqual(3);
    expect(seg3).toBeLessThanOrEqual(4);
    expect(seg1 + seg2 + seg3).toBe(10);
  });

  test("uneven segments → allocates proportionally to duration", () => {
    // 2 matches: short (20 s) + long (100 s). Long should get ~8 hints, short ~2.
    const dur = 120;
    const hints = distributeHints(dur, [20], 10);
    expect(hints).toHaveLength(10);
    const seg1 = hints.filter((t) => t < 20).length;
    const seg2 = hints.filter((t) => t >= 20).length;
    expect(seg1).toBeGreaterThanOrEqual(1);
    expect(seg1).toBeLessThanOrEqual(2);
    expect(seg2).toBeGreaterThanOrEqual(8);
    expect(seg2).toBeLessThanOrEqual(9);
  });

  test("invalid duration returns empty", () => {
    expect(distributeHints(0, [], 10)).toEqual([]);
    expect(distributeHints(-5, [], 10)).toEqual([]);
  });

  test("ignores scene cuts at very start / very end of video", () => {
    // Cut at 0.5s and at dur-0.5s should both be discarded
    const dur = 60;
    const hints = distributeHints(dur, [0.5, 59.7], 10);
    expect(hints).toHaveLength(10);
    // Should treat as 1 segment → strictly increasing across whole duration
    for (let i = 1; i < hints.length; i++) {
      expect(hints[i]).toBeGreaterThanOrEqual(hints[i - 1]);
    }
  });

  test("count=5 (used as default when user wants quick scout)", () => {
    const hints = distributeHints(60, [30], 5);
    expect(hints).toHaveLength(5);
  });
});
