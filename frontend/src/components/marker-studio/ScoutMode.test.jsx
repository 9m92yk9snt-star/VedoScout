import React from "react";
import { render, screen, within, fireEvent, waitFor, act } from "@testing-library/react";
import "@testing-library/jest-dom";
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
jest.mock("../MarkedCropCanvas", () => ({ frameDataUrl, box, mask }) => (
  <canvas data-testid="crop" data-source={frameDataUrl} data-box={JSON.stringify(box)} data-mask={JSON.stringify(mask)} />
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
  jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    drawImage: jest.fn(), putImageData: jest.fn(),
    createImageData: jest.fn((w, h) => ({ data: new Uint8ClampedArray(w * h * 4) })),
  });
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
const nativeMask = { width: 96, height: 192, runs: [5760, 2880, 9792], method: "native_person_instance" };
async function mark() {
  tap();
  expect(screen.getByTestId("scout-selection-preview")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  const next = screen.queryByTestId("scout-presented-frame");
  if (next) fireEvent.load(next);
}
async function readySelection() {
  await mark(); await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  expect(screen.getByTestId("scout-selection-done")).toBeInTheDocument();
}

test("directly opens guided selection with one video and no legacy preview", async () => {
  const { onCancel } = await boot();
  expect(document.querySelectorAll("video")).toHaveLength(1);
  expect(screen.queryByText(/review your anchors/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("scout-close"));
  expect(onCancel).toHaveBeenCalledTimes(1);
});

test("first clear references span the clip and need no extra check stage", async () => {
  const { onConfirm } = await boot();
  const times = [];
  for (let i = 0; i < 3; i++) {
    times.push(Number(screen.getByTestId("scout-presented-frame").getAttribute("data-frame-time")));
    await mark();
  }
  expect(times).toEqual([2.989, 26.989, 56.989]);
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  expect(screen.queryByTestId("scout-verify-counter")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(onConfirm.mock.calls[0][0].anchors.map(a => a.t)).toEqual(times);
});

test("tapping automatically previews the native outline beside its whole area and saves it", async () => {
  const fitted = { x: .45, y: .4, w: .1, h: .2 };
  const requestMask = jest.fn(async () => ({ mask: nativeMask, box: fitted }));
  const { onConfirm } = await boot({ requestMask });
  tap();
  const crop = within(screen.getByTestId("scout-selection-preview")).getByTestId("crop");
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  await screen.findByTestId("scout-player-mask");
  expect(crop).toHaveAttribute("data-mask", JSON.stringify(nativeMask));
  expect(crop).toHaveAttribute("data-box", JSON.stringify(fitted));
  expect(within(screen.getByTestId("scout-cutout-context")).getByTestId("crop")).not.toHaveAttribute("data-mask");
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); await screen.findByTestId("scout-player-mask"); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); await screen.findByTestId("scout-player-mask"); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(requestMask).toHaveBeenCalledTimes(3);
  expect(onConfirm.mock.calls[0][0].anchors.every(a => a.visible_mask?.method === "native_person_instance")).toBe(true);
  expect(onConfirm.mock.calls[0][0].anchors.every(a => a.verify !== true)).toBe(true);
});

test("an automatic outline can be discarded without losing the selected frame or point", async () => {
  const requestMask = jest.fn(async () => ({ mask: nativeMask }));
  const { onConfirm } = await boot({ requestMask }); tap();
  fireEvent.click(screen.getByTestId("scout-refine"));
  await screen.findByTestId("scout-player-mask");
  expect(requestMask).toHaveBeenCalledTimes(1);
  expect(within(screen.getByTestId("scout-cutout-context")).getByTestId("crop")).not.toHaveAttribute("data-mask");
  fireEvent.click(screen.getByText("Use box instead"));
  expect(screen.queryByTestId("scout-player-mask")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); await screen.findByTestId("scout-player-mask"); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  tap(); await screen.findByTestId("scout-player-mask"); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(onConfirm.mock.calls[0][0].anchors[0].visible_mask).toBeUndefined();
});

test("partial duel and negative point survive all the way to submitted anchors", async () => {
  const { onConfirm } = await boot();
  fireEvent.click(screen.getByTestId("scout-hidden-player"));
  fireEvent.click(screen.getByTestId("scout-partial-player"));
  tap();
  fireEvent.click(screen.getByTestId("scout-exclude-opponent"));
  fireEvent.click(screen.getByTestId("scout-stage"), { clientX: 230, clientY: 250 });
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  await mark(); await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  const partial = onConfirm.mock.calls[0][0].anchors.find(a => a.visibility === "partial");
  expect(partial.t).toBe(2.989);
  expect(partial.target_point).toEqual({ x: .5, y: .5 });
  expect(partial.exclude_points).toHaveLength(1);
  expect(onConfirm.mock.calls[0][0].anchors[0].visibility).not.toBe("partial");
});

test("human nearby check preserves original partial time and does not cross scenes", async () => {
  const { onConfirm } = await boot();
  fireEvent.click(screen.getByTestId("scout-hidden-player"));
  fireEvent.click(screen.getByTestId("scout-partial-player")); tap();
  fireEvent.click(screen.getByTestId("scout-link-after"));
  await waitFor(() => expect(Number(screen.getByTestId("scout-presented-frame").getAttribute("data-frame-time"))).toBeCloseTo(3.478));
  fireEvent.load(screen.getByTestId("scout-presented-frame")); tap();
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  await waitFor(() => expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "2.989"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  await mark(); await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  const partial = onConfirm.mock.calls[0][0].anchors.find(a => a.visibility === "partial");
  expect(partial.continuity[0]).toMatchObject({ same_player: true, segment: 0 });
  expect(partial.continuity[0].t).toBeCloseTo(3.478);
});

test("cancel nearby check restores selection without manufacturing a link", async () => {
  await boot(); fireEvent.click(screen.getByTestId("scout-hidden-player"));
  fireEvent.click(screen.getByTestId("scout-partial-player")); tap();
  fireEvent.click(screen.getByTestId("scout-link-after"));
  await screen.findByTestId("scout-cancel-link");
  fireEvent.click(screen.getByTestId("scout-cancel-link"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "2.989");
  expect(screen.queryByText(/nearby identity check\(s\) saved/)).not.toBeInTheDocument();
});

test("explicit visible choice exits partial mode without trapping the user", async () => {
  const { onConfirm } = await boot();
  fireEvent.click(screen.getByTestId("scout-hidden-player")); fireEvent.click(screen.getByTestId("scout-partial-player")); tap();
  fireEvent.click(screen.getByTestId("scout-hidden-player")); fireEvent.click(screen.getByText("Player visible — tap now", { exact: true }));
  await mark(); await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early")); fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(onConfirm.mock.calls[0][0].anchors.some(a => a.visibility === "partial")).toBe(false);
});

test("tracking preview uses captured PTS and stores only human approval", async () => {
  const requestTracking = jest.fn(async frames => frames.map(f => ({ t: f.t, box: { x: .46, y: .425, w: .08, h: .18 }, status: "suggested" })));
  const { onConfirm } = await boot({ requestTracking }); tap();
  fireEvent.click(screen.getByTestId("scout-check-tracking"));
  await screen.findByTestId("scout-tracking-preview");
  requestTracking.mock.calls[0][0].forEach((f, i) => expect(f.t).toBeCloseTo([2.989, 3.103, 3.228, 3.353, 3.478][i]));
  fireEvent.click(screen.getByTestId("scout-preview-approve"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame")); await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  const a = onConfirm.mock.calls[0][0].anchors[0];
  expect(a.tracking_check.status).toBe("user_confirmed");
  expect(a).not.toHaveProperty("preview_points");
  expect(onConfirm.mock.calls[0][0].anchors).toHaveLength(3);
});

test("uncertain preview cannot be approved and correction requires a new human tap", async () => {
  const requestTracking = jest.fn(async frames => frames.map((f, i) => ({ t: f.t, box: i ? null : { x: .46, y: .425, w: .08, h: .18 }, status: i ? "uncertain" : "human_seed" })));
  await boot({ requestTracking }); tap(); fireEvent.click(screen.getByTestId("scout-check-tracking"));
  await screen.findByTestId("scout-tracking-preview");
  expect(screen.getByTestId("scout-preview-approve")).toBeDisabled();
  fireEvent.click(screen.getByTestId("scout-preview-correct-1"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  expect(screen.queryByTestId("scout-confirm-mark")).not.toBeInTheDocument();
  tap(); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "2.989");
  expect(screen.getByTestId("scout-progress-counter")).toHaveTextContent("0/10");
});

test("a cut immediately after the tap keeps the selection and explains the stop", async () => {
  const requestTracking = jest.fn(async frames => frames.map((f, i) => ({ t: f.t, box: i ? null : { x: .46, y: .425, w: .08, h: .18 }, status: i ? "scene_cut" : "human_seed" })));
  await boot({ requestTracking }); tap(); fireEvent.click(screen.getByTestId("scout-check-tracking"));
  await waitFor(() => expect(screen.getByTestId("scout-notice")).toHaveTextContent("The video cuts here"));
  expect(screen.queryByTestId("scout-tracking-preview")).not.toBeInTheDocument();
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "2.989");
  expect(screen.getByTestId("scout-selection-preview")).toBeInTheDocument();
  expect(screen.getByTestId("scout-confirm-mark")).toBeEnabled();
  expect(screen.queryByTestId("scout-preview-correct-1")).not.toBeInTheDocument();
});

test("a later cut trims the preview and approval to real frames before the cut", async () => {
  const requestTracking = jest.fn(async frames => frames.map((f, i) => ({ t: f.t, box: i < 3 ? { x: .46, y: .425, w: .08, h: .18 } : null, status: i < 3 ? "suggested" : "scene_cut" })));
  const { onConfirm } = await boot({ requestTracking }); tap(); fireEvent.click(screen.getByTestId("scout-check-tracking"));
  await screen.findByTestId("scout-tracking-preview");
  expect(screen.getByTestId("scout-notice")).toHaveTextContent("stops before a video cut");
  expect(screen.getByTestId("scout-preview-correct-2")).toBeInTheDocument();
  expect(screen.queryByTestId("scout-preview-correct-3")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("scout-preview-approve"));
  fireEvent.load(screen.getByTestId("scout-presented-frame")); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame")); await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early")); fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(onConfirm.mock.calls[0][0].anchors[0].tracking_check.end).toBeCloseTo(3.228);
});

test("mask responses from another frame cannot decorate the current tap", async () => {
  let resolveMask;
  const requestMask = jest.fn(() => new Promise(resolve => { resolveMask = resolve; }));
  await boot({ requestMask }); tap();
  await waitFor(() => expect(requestMask).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByTestId("scout-frame-strip-1"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  await act(async () => resolveMask({ mask: nativeMask }));
  expect(screen.queryByTestId("scout-player-mask")).not.toBeInTheDocument();
  expect(screen.queryByTestId("scout-selection-preview")).not.toBeInTheDocument();
});

test("uses the cached displayed frame even when the decoder is at the end of the clip", async () => {
  const { onConfirm } = await boot();
  expect(screen.getByTestId("scout-video").currentTime).toBeCloseTo(50.989);
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "2.989");
  tap();
  expect(screen.getAllByTestId("crop")[0]).toHaveAttribute("data-source", "data:image/jpeg;base64,FRAME1");
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.load(screen.getByTestId("scout-presented-frame"));
  await mark(); await mark();
  fireEvent.click(screen.getByTestId("scout-finish-early"));
 
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  const payload = onConfirm.mock.calls[0][0];
  expect(payload.anchors[0].t).toBe(2.989);
  expect(payload.markerImageDataUrl).toBe("data:image/jpeg;base64,FRAME1");
  expect(payload.anchors).toHaveLength(3);
  expect(payload.anchors.filter(a => a.verify === true)).toHaveLength(0);
});

test("ten guided selections are ready without another manual check", async () => {
  const { onConfirm } = await boot();
  for (let i = 0; i < 10; i++) await mark();
  expect(screen.getByTestId("scout-selection-done")).toBeInTheDocument();
  expect(screen.queryByTestId("scout-verify-confirm")).not.toBeInTheDocument();
 
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(onConfirm.mock.calls[0][0].anchors).toHaveLength(10);
  expect(onConfirm.mock.calls[0][0].anchors.slice(0, 3).map(a => a.t)).toEqual([2.989, 26.989, 56.989]);
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

test("a saved selection can be adjusted without adding a duplicate tap", async () => {
  const { onConfirm } = await boot(); await readySelection();
  fireEvent.click(screen.getByTestId("scout-frame-strip-0"));
  fireEvent.load(screen.getByTestId("scout-presented-frame")); tap();
  fireEvent.click(screen.getByTestId("scout-confirm-mark"));
  fireEvent.click(screen.getByTestId("scout-finish-early"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  expect(onConfirm.mock.calls[0][0].anchors).toHaveLength(3);
  expect(onConfirm.mock.calls[0][0].anchors.filter(a => a.t === 2.989)).toHaveLength(1);
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

test("seeking to a nearby frame disables taps until its pixels arrive", async () => {
  await boot();
  let resolveFrame;
  authority.seekPresentedFrame.mockImplementation(() => new Promise(resolve => { resolveFrame = resolve; }));
  fireEvent.click(screen.getByTestId("scout-hidden-player"));
  fireEvent.click(screen.getByTestId("scout-nearby-later"));
  tap(); expect(screen.queryByTestId("scout-selection-preview")).not.toBeInTheDocument();
  await act(async () => resolveFrame({ mediaTime: 3.478 }));
  expect(screen.getByTestId("scout-presented-frame")).toHaveAttribute("data-frame-time", "3.478");
  fireEvent.click(screen.getByText("Player visible — tap now"));
  fireEvent.load(screen.getByTestId("scout-presented-frame")); tap();
  expect(screen.getByTestId("scout-selection-preview")).toBeInTheDocument();
});

test("submit is single-flight and a failed save preserves all selections", async () => {
  let reject;
  const onConfirm = jest.fn(() => new Promise((_, r) => { reject = r; }));
  await boot({ onConfirm }); await readySelection();
  fireEvent.click(screen.getByTestId("scout-submit"));
  fireEvent.click(screen.getByTestId("scout-submit"));
  expect(onConfirm).toHaveBeenCalledTimes(1);
  await act(async () => reject(new Error("Try again")));
  expect(screen.getByTestId("scout-notice")).toHaveTextContent("Try again");
  expect(screen.getByTestId("scout-progress-counter")).toHaveTextContent("3/10");
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

test.each(["no mask", "request error", "legacy mask"])("%s keeps a retry and the exact human input", async failure => {
  const requestMask = jest.fn();
  if (failure === "request error") requestMask.mockRejectedValueOnce(new Error("Unavailable"));
  else requestMask.mockResolvedValueOnce(failure === "legacy mask" ? { ...nativeMask, method: "grabcut" } : null);
  requestMask.mockResolvedValue({ mask: nativeMask });
  await boot({ requestMask }); tap();
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  fireEvent.click(screen.getByTestId("scout-refine"));
  await screen.findByTestId("scout-refine-cutout");
  expect(screen.queryByTestId("scout-player-mask")).not.toBeInTheDocument();
  const first = requestMask.mock.calls[0];
  fireEvent.click(screen.getByTestId("scout-refine-cutout"));
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  await screen.findByTestId("scout-player-mask");
  expect(requestMask).toHaveBeenCalledTimes(2);
  expect(requestMask.mock.calls[1][0]).toBe(first[0]);
  expect(requestMask.mock.calls[1][1].box).toEqual(first[1].box);
  expect(requestMask.mock.calls[1][1].target_point).toEqual(first[1].target_point);
  expect(screen.getByTestId("scout-confirm-mark")).toBeEnabled();
});

test("behind keeps the area, accepts foreground first, and requires the visible cutout before Confirm", async () => {
  const requestMask = jest.fn(async (_, draft) => ({ mask: { ...nativeMask, method: draft.player_behind ? "native_person_prompt" : "native_person_instance" } }));
  const { onConfirm } = await boot({ requestMask }); tap(); await screen.findByTestId("scout-player-mask");
  const area = JSON.parse(screen.getAllByTestId("crop")[0].getAttribute("data-box"));
  fireEvent.click(screen.getByTestId("scout-player-behind"));
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  expect(JSON.parse(screen.getAllByTestId("crop")[0].getAttribute("data-box"))).toEqual(area);
  fireEvent.click(screen.getByTestId("scout-exclude-opponent"));
  fireEvent.click(screen.getByTestId("scout-stage"), { clientX: 203, clientY: 250 });
  expect(requestMask).toHaveBeenCalledTimes(1); // no invented positive at the box centre
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  tap(); await screen.findByTestId("scout-player-mask");
  expect(requestMask).toHaveBeenCalledTimes(2);
  const hint = requestMask.mock.calls[1][1];
  expect(hint).toMatchObject({ box: area, player_behind: true, visibility: "partial", manualBox: true, target_point: { x: .5, y: .5 } });
  expect(hint.exclude_points).toHaveLength(1);
  expect(screen.getByTestId("scout-confirm-mark")).toBeEnabled();
  fireEvent.click(screen.getByTestId("scout-confirm-mark")); fireEvent.load(screen.getByTestId("scout-presented-frame"));
  for (let i = 0; i < 3; i++) {
    tap(); await screen.findByTestId("scout-player-mask"); fireEvent.click(screen.getByTestId("scout-confirm-mark"));
    fireEvent.load(screen.getByTestId("scout-presented-frame"));
  }
  fireEvent.click(screen.getByTestId("scout-finish-early")); fireEvent.click(screen.getByTestId("scout-submit"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  const partial = onConfirm.mock.calls[0][0].anchors.find(a => a.player_behind);
  expect(partial).toMatchObject({ t: 2.989, box: area, visibility: "partial", visible_mask: { method: "native_person_prompt" } });
  expect(onConfirm.mock.calls[0][0].anchors.filter(a => a.visibility !== "partial")).toHaveLength(3);
  expect(screen.queryByTestId("scout-verify-counter")).not.toBeInTheDocument();
});

test("behind can return to a visible player without losing the area", async () => {
  const requestMask = jest.fn(async () => ({ mask: nativeMask }));
  await boot({ requestMask }); tap(); await screen.findByTestId("scout-player-mask");
  const box = requestMask.mock.calls[0][1].box;
  fireEvent.click(screen.getByTestId("scout-player-behind"));
  fireEvent.click(screen.getByTestId("scout-player-behind"));
  expect(screen.getByTestId("scout-player-behind")).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  tap(); await screen.findByTestId("scout-player-mask");
  expect(requestMask.mock.calls[1][1]).toMatchObject({ box, target_point: { x: .5, y: .5 } });
  expect(requestMask.mock.calls[1][1].player_behind).toBeUndefined();
  expect(screen.getByTestId("scout-confirm-mark")).toBeEnabled();
});

test("an old response cannot overwrite a new tap on the same still", async () => {
  const resolve = [];
  const requestMask = jest.fn(() => new Promise(r => resolve.push(r)));
  await boot({ requestMask }); tap(); await waitFor(() => expect(requestMask).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByTestId("scout-retap"));
  fireEvent.click(screen.getByTestId("scout-stage"), { clientX: 225, clientY: 250 });
  await waitFor(() => expect(requestMask).toHaveBeenCalledTimes(2));
  expect(requestMask.mock.calls[0][2].aborted).toBe(true);
  const latestBox = requestMask.mock.calls[1][1].box;
  await act(async () => resolve[0]({ mask: nativeMask, box: { x: .45, y: .4, w: .1, h: .2 } }));
  expect(screen.queryByTestId("scout-player-mask")).not.toBeInTheDocument();
  expect(JSON.parse(screen.getAllByTestId("crop")[0].getAttribute("data-box"))).toEqual(latestBox);
  await act(async () => resolve[1]({ mask: nativeMask }));
  expect(screen.getByTestId("scout-player-mask")).toBeInTheDocument();
});

test("moving the box outside the original tap does not manufacture a new positive", async () => {
  const requestMask = jest.fn(async () => ({ mask: nativeMask }));
  await boot({ requestMask }); tap(); await screen.findByTestId("scout-player-mask");
  const stage = screen.getByTestId("scout-stage");
  fireEvent.pointerDown(screen.getByTestId("scout-draft-marker"), { pointerId: 1, clientX: 195, clientY: 250 });
  fireEvent.pointerMove(stage, { pointerId: 1, clientX: 235, clientY: 250 });
  fireEvent.pointerUp(stage, { pointerId: 1 });
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  expect(screen.queryByTestId("scout-player-mask")).not.toBeInTheDocument();
  expect(requestMask).toHaveBeenCalledTimes(1);
  fireEvent.click(stage, { clientX: 235, clientY: 250 }); // suppress the drag's generated click
  fireEvent.click(stage, { clientX: 235, clientY: 250 });
  await screen.findByTestId("scout-player-mask");
  expect(requestMask.mock.calls[1][1].manualBox).toBe(true);
  expect(requestMask.mock.calls[1][1].target_point.x).toBeGreaterThan(.5);
  expect(requestMask.mock.calls[1][1].target_point.y).toBe(.5);
});

test("resizing a behind area without a visible tap leaves identity unresolved", async () => {
  const requestMask = jest.fn(async () => ({ mask: nativeMask }));
  await boot({ requestMask }); tap(); await screen.findByTestId("scout-player-mask");
  fireEvent.click(screen.getByTestId("scout-player-behind"));
  const stage = screen.getByTestId("scout-stage");
  fireEvent.pointerDown(screen.getByTestId("scout-draft-resize"), { pointerId: 1, clientX: 220, clientY: 290 });
  fireEvent.pointerMove(stage, { pointerId: 1, clientX: 240, clientY: 320 });
  fireEvent.pointerUp(stage, { pointerId: 1 });
  expect(requestMask).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("scout-confirm-mark")).toBeDisabled();
  expect(screen.queryByTestId("scout-player-mask")).not.toBeInTheDocument();
});
