import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
expect.extend(matchers);
import ScoutMode from "./ScoutMode";
import authority from "./videoFrameAuthority.cjs";
import { detectSceneCuts, distributeHints } from "./sceneDetect";

jest.mock("./sceneDetect", () => ({
  detectSceneCuts: jest.fn(async () => ({ cuts: [20, 40], samples: [] })),
  distributeHints: jest.fn(() => Array.from({ length: 10 }, (_, i) => i * 6 + 3)),
}));
jest.mock("./videoFrameAuthority.cjs", () => ({
  seekPresentedFrame: jest.fn(), resetPresentedFrame: jest.fn(),
}));
jest.mock("../MarkedCropCanvas", () => ({ frameDataUrl, box }) => (
  <canvas data-testid="crop" data-source={frameDataUrl} data-box={JSON.stringify(box)} />
));

const stageRect = { left: 0, top: 0, width: 390, height: 500, right: 390, bottom: 500 };
let jpeg;
beforeEach(() => {
  jpeg = 0;
  global.ResizeObserver = class { observe() {} disconnect() {} };
  jest.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(stageRect);
  for (const [name, value] of Object.entries({ readyState: 2, duration: 60, seeking: false })) {
    Object.defineProperty(HTMLMediaElement.prototype, name, { configurable: true, get: () => value });
  }
  for (const [name, value] of Object.entries({ videoWidth: 1080, videoHeight: 1920 })) {
    Object.defineProperty(HTMLVideoElement.prototype, name, { configurable: true, get: () => value });
  }
  global.PointerEvent = class extends MouseEvent {
    constructor(type, options = {}) { super(type, options); Object.defineProperty(this, "pointerId", { value: options.pointerId || 1 }); }
  };
  jest.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  jest.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: jest.fn() });
  jest.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockImplementation(() => "data:image/jpeg;base64,FRAME" + (++jpeg));
  authority.seekPresentedFrame.mockReset();
  detectSceneCuts.mockImplementation(async () => ({ cuts: [20, 40], samples: [] }));
  distributeHints.mockImplementation(() => Array.from({ length: 10 }, (_, i) => i * 6 + 3));
  authority.seekPresentedFrame.mockImplementation(async (v, t) => {
    v.currentTime = t - 0.011;
    return { mediaTime: t - 0.011, source: "PRESENTED_FRAME_CALLBACK" };
  });
});
afterEach(() => jest.restoreAllMocks());

async function boot(props = {}) {
  const onConfirm = jest.fn();
  const onCancel = jest.fn();
  const result = render(<ScoutMode open videoUrl="test.mp4" onConfirm={onConfirm} onCancel={onCancel} {...props} />);
  expect(screen.getByTestId("scout-video").videoWidth).toBe(1080);
  expect(screen.getByTestId("scout-video").readyState).toBe(2);
  await screen.findByTestId("scout-progress-counter");
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  return { ...result, onConfirm, onCancel };
}
function tap() { fireEvent.click(screen.getByTestId("scout-stage"), { clientX: 195, clientY: 250 }); }
async function mark() {
  tap();
  expect(screen.getByTestId("scout-selection-preview")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  const next = screen.queryByTestId("scout-presented-frame");
  if (next) fireEvent.load(next);
}
async function earlyVerify() {
  await mark(); await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  await waitFor(() => expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "11.989"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
}
async function checks() {
  for (const [i, time] of [11.989, 29.989, 47.989].entries()) {
    await waitFor(() => expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", String(time)));
    fireEvent.load(screen.getByTestId("scout-presented-frame"));
    tap(); fireEvent.click(screen.getByTestId("scout-verify-confirm"));
    expect(screen.getByTestId("scout-verify-counter")).toHaveTextContent((i + 1) + "/3");
  }
}

test("directly opens guided selection with one video and no legacy preview", async () => {
  const { onCancel } = await boot();
  expect(document.querySelectorAll("video")).toHaveLength(1);
  expect(screen.queryByText(/review your anchors/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("scout-close"));
  expect(onCancel).toHaveBeenCalledTimes(1);
});

test("uses the cached displayed frame even when the decoder is at the end of the clip", async () => {
  const { onConfirm } = await boot();
  expect(screen.getByTestId("scout-video").currentTime).toBeCloseTo(56.989);
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "2.989");
  tap();
  expect(screen.getAllByTestId("crop")[0]).toHaveAttribute("data-source", "data:image/jpeg;base64,FRAME1");
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  await checks();
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  const payload = onConfirm.mock.calls[0][0];
  expect(payload.anchors[0].t).toBe(2.989);
  expect(payload.markerImageDataUrl).toBe("data:image/jpeg;base64,FRAME1");
  expect(payload.anchors).toHaveLength(6);
  expect(payload.anchors.filter(a => a.verify === true)).toHaveLength(3);
});

test("ten guided selections plus three checks produce exactly thirteen taps", async () => {
  const { onConfirm } = await boot();
  for (let i = 0; i < 10; i++) await mark();
  expect(screen.getByTestId("scout-verify-counter")).toHaveTextContent("0/3");
  await checks();
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(onConfirm.mock.calls[0][0].anchors).toHaveLength(13);
});

test("two selections plus skipped frames cannot pass as three", async () => {
  await boot(); await mark(); await mark();
  for (let i = 2; i < 10; i++) {
    fireEvent.click(screen.getByTestId("scout-hidden-player"));
    fireEvent.click(screen.getByTestId("scout-skip-frame"));
  }
  expect(screen.getByTestId("scout-progress-counter")).toHaveTextContent("2/10");
  expect(screen.queryByTestId("scout-verify-counter")).not.toBeInTheDocument();
  expect(screen.getByTestId("scout-notice")).toHaveTextContent("3 visible moments");
});

test("a hidden player is replaced by a real nearby frame, not an inferred anchor", async () => {
  const { onConfirm } = await boot();
  fireEvent.click(screen.getByTestId("scout-hidden-player"));
  expect(screen.getByTestId("scout-hidden-help")).toHaveTextContent("Do not mark the player in front");
  fireEvent.click(screen.getByTestId("scout-nearby-later"));
  await waitFor(() => expect(Number(screen.getByTestId("scout-presented-frame").getAttribute("data-frame-time"))).toBeCloseTo(3.478));
  expect(screen.getByTestId("scout-progress-counter")).toHaveTextContent("0/10");
  expect(onConfirm).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Player visible — tap now"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); expect(screen.getByTestId("scout-selection-preview")).toBeInTheDocument();
});

test("duplicate check moments are rejected without inventing confidence", async () => {
  await boot(); await earlyVerify();
  tap(); fireEvent.click(screen.getByTestId("scout-verify-confirm"));
  await waitFor(() => expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "29.989"));
  fireEvent.change(screen.getByTestId("scout-verify-scrub"), { target: { value: "12" } });
  await waitFor(() => expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "11.989"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); fireEvent.click(screen.getByTestId("scout-verify-confirm"));
  expect(screen.getByTestId("scout-verify-counter")).toHaveTextContent("1/3");
  expect(screen.getByTestId("scout-notice")).toHaveTextContent("different moment");
});

test("failed capture gives a retry, never an empty editor or manual fallback", async () => {
  authority.seekPresentedFrame.mockRejectedValue(new Error("FRAME_SEEK_TIMEOUT"));
  render(<ScoutMode open videoUrl="bad.mp4" onConfirm={jest.fn()} onCancel={jest.fn()} />);
  await screen.findByTestId("scout-retry");
  expect(screen.getByRole("alert")).toHaveTextContent("Not enough frames");
  expect(screen.queryByTestId("scout-progress-counter")).not.toBeInTheDocument();
  authority.seekPresentedFrame.mockImplementation(async (_, t) => ({ mediaTime: t }));
  fireEvent.click(screen.getByTestId("scout-retry"));
  await screen.findByTestId("scout-progress-counter");
});

test("seeking disables taps and an older async check cannot replace a newer one", async () => {
  await boot(); await earlyVerify();
  const requests = [];
  authority.seekPresentedFrame.mockImplementation((_, t) => new Promise(resolve => requests.push({ t, resolve })));
  fireEvent.change(screen.getByTestId("scout-verify-scrub"), { target: { value: "25" } });
  tap(); expect(screen.queryByTestId("scout-selection-preview")).not.toBeInTheDocument();
  fireEvent.change(screen.getByTestId("scout-verify-scrub"), { target: { value: "35" } });
  await act(async () => requests[1].resolve({ mediaTime: 34.987 }));
  await act(async () => requests[0].resolve({ mediaTime: 24.987 }));
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "34.987");
});

test("submit is single-flight and a failed save preserves all selections", async () => {
  let reject;
  const onConfirm = jest.fn(() => new Promise((_, r) => { reject = r; }));
  await boot({ onConfirm }); await earlyVerify(); await checks();
  fireEvent.click(screen.getByTestId("scout-submit"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  expect(onConfirm).toHaveBeenCalledTimes(1);
  await act(async () => reject(new Error("Try again")));
  expect(screen.getByTestId("scout-notice")).toHaveTextContent("Try again");
  expect(screen.getByTestId("scout-verify-counter")).toHaveTextContent("3/3");
  expect(screen.getByTestId("scout-submit")).not.toBeDisabled();
});

test("pinch zoom does not accidentally select a player; a following tap still works", async () => {
  await boot();
  const stage = screen.getByTestId("scout-stage");
  fireEvent.pointerDown(stage, { pointerId: 1, clientX: 150, clientY: 250 });
  fireEvent.pointerDown(stage, { pointerId: 2, clientX: 250, clientY: 250 });
  fireEvent.pointerMove(stage, { pointerId: 2, clientX: 300, clientY: 250 });
  expect(screen.getByTestId("scout-zoom-reset")).toHaveTextContent("1.5×");
  fireEvent.pointerUp(stage, { pointerId: 1 }); fireEvent.pointerUp(stage, { pointerId: 2 });
  fireEvent.click(stage, { clientX: 195, clientY: 250 });
  expect(screen.queryByTestId("scout-selection-preview")).not.toBeInTheDocument();
  fireEvent.pointerDown(stage, { pointerId: 1, clientX: 195, clientY: 250 });
  fireEvent.pointerUp(stage, { pointerId: 1 }); tap();
  expect(screen.getByTestId("scout-selection-preview")).toBeInTheDocument();
});

test("dragging and resizing adjust only the selected box without changing its frame", async () => {
  await boot(); tap();
  const stage = screen.getByTestId("scout-stage");
  const before = JSON.parse(screen.getAllByTestId("crop")[0].getAttribute("data-box"));
  fireEvent.pointerDown(screen.getByTestId("scout-draft-marker"), { pointerId: 1, clientX: 195, clientY: 250 });
  fireEvent.pointerMove(stage, { pointerId: 1, clientX: 215, clientY: 250 });
  fireEvent.pointerUp(stage, { pointerId: 1 });
  const moved = JSON.parse(screen.getAllByTestId("crop")[0].getAttribute("data-box"));
  expect(moved.x).toBeGreaterThan(before.x);
  fireEvent.pointerDown(screen.getByTestId("scout-draft-resize"), { pointerId: 1, clientX: 220, clientY: 290 });
  fireEvent.pointerMove(stage, { pointerId: 1, clientX: 240, clientY: 320 });
  fireEvent.pointerUp(stage, { pointerId: 1 });
  const resized = JSON.parse(screen.getAllByTestId("crop")[0].getAttribute("data-box"));
  expect(resized.w).toBeGreaterThan(moved.w);
  expect(resized.h).toBeGreaterThan(moved.h);
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "2.989");
});

test("a new still image cannot be tapped until its actual load completes", async () => {
  render(<ScoutMode open videoUrl="clip.mp4" onConfirm={jest.fn()} onCancel={jest.fn()} />);
  await screen.findByTestId("scout-progress-counter");
  tap();
  expect(screen.queryByTestId("scout-selection-preview")).not.toBeInTheDocument();
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); expect(screen.getByTestId("scout-selection-preview")).toBeInTheDocument();
});

test("Escape closes the sole editor and keyboard focus starts at Close", async () => {
  const { onCancel } = await boot();
  expect(screen.getByTestId("scout-close")).toHaveFocus();
  fireEvent.keyDown(screen.getByTestId("scout-mode-overlay"), { key: "Escape" });
  expect(onCancel).toHaveBeenCalledTimes(1);
});

test("editing a previously selected moment replaces its box instead of adding a tap", async () => {
  await boot(); await mark();
  fireEvent.click(screen.getByTestId("scout-frame-strip-0"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  expect(screen.getByTestId("scout-progress-counter")).toHaveTextContent("1/10");
});
