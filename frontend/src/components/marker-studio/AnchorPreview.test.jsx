/**
 * AnchorPreview.test.jsx — Trust-Stack #3 + #4 runtime rendering tests.
 *
 * Because headless Chromium in the preview container cannot decode the H264
 * test mp4, the testing agent could not exercise the AnchorPreview overlay
 * via the live studio. These jsdom tests mount AnchorPreview directly with
 * fixtures, verifying:
 *
 *   • All required data-testids render (ms-preview-overlay, ms-preview-grid,
 *     ms-preview-anchor-N, ms-preview-replace-N, ms-preview-done, etc.)
 *   • The user's first anchor is labelled "Your tap" and has NO replace button
 *   • DONE is DISABLED when <3 green anchors are locked
 *   • DONE is ENABLED when ≥3 green anchors are locked
 *   • The second-tap CTA appears when needed and fires onSecondTap with the
 *     suggested timestamp
 *   • The Replace button fires onReplace with the right index
 *
 * Run with:  cd /app/frontend && CI=true yarn test --testPathPattern=AnchorPreview --watchAll=false
 */

import React from "react";
import { render, fireEvent, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom";

import AnchorPreview from "./AnchorPreview";

function fixtureAnchors({ greens = 0, yellows = 0, reds = 0 } = {}) {
  const arr = [];
  let t = 1;
  // User's first tap — confidence forced to 1.0
  arr.push({
    t: 5.0,
    box: { x: 0.4, y: 0.4, w: 0.1, h: 0.3 },
    thumb: "data:image/jpeg;base64,",
    confidence: 1.0,
    band: "green",
  });
  for (let i = 0; i < greens; i++) {
    arr.push({
      t: 10 + i,
      box: { x: 0.5, y: 0.4, w: 0.1, h: 0.3 },
      thumb: "data:image/jpeg;base64,",
      confidence: 0.94 - i * 0.01,
      band: "green",
      suggested: true,
    });
  }
  for (let i = 0; i < yellows; i++) {
    arr.push({
      t: 20 + i,
      box: { x: 0.6, y: 0.4, w: 0.1, h: 0.3 },
      thumb: "data:image/jpeg;base64,",
      confidence: 0.84,
      band: "yellow",
      suggested: true,
    });
  }
  for (let i = 0; i < reds; i++) {
    arr.push({
      t: 30 + i,
      box: { x: 0.7, y: 0.4, w: 0.1, h: 0.3 },
      thumb: "data:image/jpeg;base64,",
      confidence: 0.65,
      band: "red",
      suggested: true,
    });
  }
  void t;
  return arr;
}

describe("AnchorPreview", () => {
  test("renders the overlay + grid + all required testids", () => {
    const anchors = fixtureAnchors({ greens: 2, yellows: 1, reds: 1 });
    render(
      <AnchorPreview
        open={true}
        anchors={anchors}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={null}
        enrolling={false}
        enrollProgress={1}
      />,
    );
    expect(screen.getByTestId("ms-preview-overlay")).toBeInTheDocument();
    expect(screen.getByTestId("ms-preview-grid")).toBeInTheDocument();
    expect(screen.getByTestId("ms-preview-back")).toBeInTheDocument();
    expect(screen.getByTestId("ms-preview-done")).toBeInTheDocument();
    // 5 anchor cards
    for (let i = 0; i < anchors.length; i++) {
      expect(screen.getByTestId(`ms-preview-anchor-${i}`)).toBeInTheDocument();
    }
  });

  test("'Your tap' anchor has NO replace button; others DO", () => {
    const anchors = fixtureAnchors({ greens: 2, yellows: 1, reds: 1 });
    render(
      <AnchorPreview
        open={true}
        anchors={anchors}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={null}
      />,
    );
    // First card chronologically (t=5) is the user's tap — sort is by time asc
    // The "Your tap" badge shows on it (small chip text in the card header)
    expect(screen.getAllByText(/your tap/i).length).toBeGreaterThanOrEqual(1);
    // Replace buttons exist only for non-user-tap anchors. Count them by testid.
    const replaceBtns = screen.queryAllByTestId(/^ms-preview-replace-\d+$/);
    expect(replaceBtns.length).toBe(anchors.length - 1);
  });

  test("DONE is disabled when <3 green anchors", () => {
    const anchors = fixtureAnchors({ greens: 1, yellows: 1, reds: 2 });
    render(
      <AnchorPreview
        open={true}
        anchors={anchors}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={null}
      />,
    );
    const done = screen.getByTestId("ms-preview-done");
    expect(done).toBeDisabled();
    // The label should announce the gap to the user
    expect(within(done).getByText(/need.*3 strong anchors/i)).toBeInTheDocument();
  });

  test("DONE is enabled when ≥3 green anchors", () => {
    // user tap (green) + 2 added greens = 3 greens. Default user tap = green.
    const anchors = fixtureAnchors({ greens: 2 });
    render(
      <AnchorPreview
        open={true}
        anchors={anchors}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={null}
      />,
    );
    const done = screen.getByTestId("ms-preview-done");
    expect(done).not.toBeDisabled();
    expect(within(done).getByText(/done/i)).toBeInTheDocument();
  });

  test("Second-tap CTA appears when <3 green AND suggestedTapTime is set", () => {
    const anchors = fixtureAnchors({ greens: 0, yellows: 2, reds: 2 });
    const onSecondTap = jest.fn();
    render(
      <AnchorPreview
        open={true}
        anchors={anchors}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={onSecondTap}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={42.5}
      />,
    );
    const cta = screen.getByTestId("ms-preview-second-tap");
    expect(cta).toBeInTheDocument();
    const btn = screen.getByTestId("ms-preview-take-second-tap");
    fireEvent.click(btn);
    expect(onSecondTap).toHaveBeenCalledWith(42.5);
  });

  test("Second-tap CTA HIDDEN when ≥3 green anchors", () => {
    const anchors = fixtureAnchors({ greens: 3 });
    render(
      <AnchorPreview
        open={true}
        anchors={anchors}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={12.0}
      />,
    );
    expect(screen.queryByTestId("ms-preview-second-tap")).not.toBeInTheDocument();
  });

  test("clicking Replace on a non-user-tap card fires onReplace with that idx", () => {
    const anchors = fixtureAnchors({ greens: 1, reds: 1 });
    const onReplace = jest.fn();
    render(
      <AnchorPreview
        open={true}
        anchors={anchors}
        refAnchorT={5.0}
        onReplace={onReplace}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={null}
      />,
    );
    // The first non-ref card is index 1 (the green added)
    fireEvent.click(screen.getByTestId("ms-preview-replace-1"));
    expect(onReplace).toHaveBeenCalledWith(1);
  });

  test("onBack fires when ms-preview-back clicked", () => {
    const onBack = jest.fn();
    render(
      <AnchorPreview
        open={true}
        anchors={fixtureAnchors({ greens: 1 })}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={onBack}
        suggestedTapTime={null}
      />,
    );
    fireEvent.click(screen.getByTestId("ms-preview-back"));
    expect(onBack).toHaveBeenCalled();
  });

  test("returns null when open=false", () => {
    const { container } = render(
      <AnchorPreview
        open={false}
        anchors={fixtureAnchors({ greens: 1 })}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={null}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  test("enrolling=true shows the progress strip + Loader2 inside DONE", () => {
    render(
      <AnchorPreview
        open={true}
        anchors={fixtureAnchors({ greens: 2 })}
        refAnchorT={5.0}
        onReplace={() => {}}
        onSecondTap={() => {}}
        onDone={() => {}}
        onBack={() => {}}
        suggestedTapTime={null}
        enrolling={true}
        enrollProgress={0.42}
      />,
    );
    expect(screen.getByTestId("ms-preview-enrolling")).toBeInTheDocument();
    expect(screen.getByText(/learning your kid/i)).toBeInTheDocument();
    // DONE button should be disabled while enrolling
    const done = screen.getByTestId("ms-preview-done");
    expect(done).toBeDisabled();
  });
});
