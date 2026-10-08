import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
expect.extend(matchers);
import MarkerStudio from "./MarkerStudio";
jest.mock("../lib/api", () => ({ post: jest.fn() }));

const mockPayload = {
  anchors: [
    { t: 3.49, box: { x: 0.1, y: 0.2, w: 0.1, h: 0.2 }, segment: 0 },
    { t: 42.3, box: { x: 0.4, y: 0.2, w: 0.1, h: 0.2 }, segment: 2, verify: true },
  ], sceneCuts: [20, 40], markerImageDataUrl: "data:image/jpeg;base64,AA==",
};
jest.mock("./marker-studio/ScoutMode", () => props => (
  <div data-testid="guided" data-url={props.videoUrl}>
    <video src={props.videoUrl} />
    <button onClick={props.onCancel}>Close guided</button>
    <button onClick={() => props.onConfirm(mockPayload)}>Save guided</button>
  </div>
));
let urlCount;
beforeEach(() => {
  urlCount = 0;
  URL.createObjectURL = jest.fn(() => "blob:test-" + (++urlCount));
  URL.revokeObjectURL = jest.fn();
  global.fetch = jest.fn(async () => ({ blob: async () => new Blob(["jpeg"], { type: "image/jpeg" }) }));
});

test("opens guided mode directly and closing does not open another editor", () => {
  const onCancel = jest.fn();
  const { rerender } = render(<MarkerStudio open videoUrl="clip.mp4" onCancel={onCancel} onConfirm={jest.fn()} />);
  expect(screen.getByTestId("guided")).toHaveAttribute("data-url", "clip.mp4");
  expect(document.querySelectorAll("video")).toHaveLength(1);
  fireEvent.click(screen.getByText("Close guided"));
  expect(onCancel).toHaveBeenCalledTimes(1);
  rerender(<MarkerStudio open={false} videoUrl="clip.mp4" onCancel={onCancel} onConfirm={jest.fn()} />);
  expect(screen.queryByTestId("guided")).not.toBeInTheDocument();
});

test("owned blob is revoked and a fresh URL is used on reopen and file replacement", async () => {
  const file = new File(["clip"], "clip.mp4");
  const props = { videoFile: file, onCancel: jest.fn(), onConfirm: jest.fn() };
  const { rerender } = render(<MarkerStudio open {...props} />);
  expect(screen.getByTestId("guided")).toHaveAttribute("data-url", "blob:test-1");
  rerender(<MarkerStudio open={false} {...props} />);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-1");
  rerender(<MarkerStudio open {...props} />);
  expect(screen.getByTestId("guided")).toHaveAttribute("data-url", "blob:test-2");
  rerender(<MarkerStudio open {...props} videoFile={new File(["new"], "new.mp4")} />);
  expect(screen.getByTestId("guided")).toHaveAttribute("data-url", "blob:test-3");
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-2");
});

test("preserves native box/time/segment and explicit verify flag in the upload contract", async () => {
  const onConfirm = jest.fn();
  render(<MarkerStudio open videoUrl="clip.mp4" onCancel={jest.fn()} onConfirm={onConfirm} />);
  fireEvent.click(screen.getByText("Save guided"));
  await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  const result = onConfirm.mock.calls[0][0];
  expect(result.markerTimestamp).toBe(3.49);
  expect(result.markerBox).toEqual(mockPayload.anchors[0].box);
  expect(result.markerAnchors[0]).not.toHaveProperty("verify");
  expect(result.markerAnchors[1].verify).toBe(true);
  expect(result.markerAnchors[1].segment).toBe(2);
  expect(result.markerBlob.size).toBeGreaterThan(0);
});

test("closing during JPEG conversion prevents stale submission", async () => {
  let resolve;
  global.fetch.mockImplementation(() => new Promise(r => { resolve = r; }));
  const onConfirm = jest.fn();
  const props = { videoUrl: "clip.mp4", onCancel: jest.fn(), onConfirm };
  const { rerender } = render(<MarkerStudio open {...props} />);
  fireEvent.click(screen.getByText("Save guided"));
  rerender(<MarkerStudio open={false} {...props} />);
  resolve({ blob: async () => new Blob(["jpeg"]) });
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  expect(onConfirm).not.toHaveBeenCalled();
});
