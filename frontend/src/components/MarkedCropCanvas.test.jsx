import React from "react";
import { render, act } from "@testing-library/react";
import MarkedCropCanvas from "./MarkedCropCanvas";

let images;
let context;
let originalImage;
beforeEach(() => {
  originalImage = global.Image;
  images = [];
  global.Image = class { constructor() { this.naturalWidth = 1080; this.naturalHeight = 1920; images.push(this); } };
  context = { drawImage: jest.fn(), fillRect: jest.fn() };
  jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context);
});
afterEach(() => { global.Image = originalImage; jest.restoreAllMocks(); });

test("portrait preview crops the exact selected rectangle, not a centre band or just feet", () => {
  render(<MarkedCropCanvas frameDataUrl="jpeg-a" box={{ x: 0.1, y: 0.2, w: 0.1, h: 0.3 }} width={144} height={192} />);
  act(() => images[0].onload());
  const call = context.drawImage.mock.calls[0];
  expect(call.slice(1, 5)).toEqual([108, 384, 108, 576]);
  expect(call[8]).toBe(192);
  expect(call[7]).toBe(36);
  expect(call[5]).toBe(54);
});

test("landscape player crop remains whole and is not stretched into the preview", () => {
  render(<MarkedCropCanvas frameDataUrl="jpeg-b" box={{ x: 0.2, y: 0.1, w: 0.5, h: 0.1 }} width={144} height={192} />);
  images[0].naturalWidth = 1920; images[0].naturalHeight = 1080;
  act(() => images[0].onload());
  const call = context.drawImage.mock.calls[0];
  expect(call.slice(1, 5)).toEqual([384, 108, 960, 108]);
  expect(call[7]).toBe(144);
  expect(call[8]).toBeCloseTo(16.2);
});

test("an older image load cannot replace the new player's crop", () => {
  const box = { x: 0.1, y: 0.2, w: 0.1, h: 0.3 };
  const { rerender } = render(<MarkedCropCanvas frameDataUrl="old" box={box} />);
  rerender(<MarkedCropCanvas frameDataUrl="new" box={box} />);
  act(() => images[0].onload());
  expect(context.drawImage).not.toHaveBeenCalled();
  act(() => images[1].onload());
  expect(context.drawImage).toHaveBeenCalledTimes(1);
  expect(context.drawImage.mock.calls[0][0].src).toBe("new");
});
