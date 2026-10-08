import React, { useEffect, useRef } from "react";
import selection from "./marker-studio/selectionHints.cjs";

/**
 * MarkedCropCanvas — renders ONLY the marked region of a frame using a canvas.
 *
 * We tried CSS-based zoom (transform: scale + transform-origin on an <img> with
 * object-cover) but that ignores the source image's native aspect ratio, so a
 * portrait 9:16 phone video shown inside a wide 14:9 thumbnail picks the wrong
 * vertical band — the user marks the whole player but only sees their feet.
 *
 * Canvas gives us pixel-perfect control: we sample the EXACT marked rectangle
 * from the source frame and draw it into the thumbnail using "contain" fit so
 * the entire marked region is visible without distortion (letterboxed if the
 * box aspect ratio doesn't match the thumbnail's).
 */
export default function MarkedCropCanvas({ frameDataUrl, box, mask, className, width = 168, height = 108 }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    if (!frameDataUrl || !box) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    let cancelled = false;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.onload = () => {
      if (cancelled) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const cw = canvas.width;
      const ch = canvas.height;
      // Pixel-space source rectangle, clamped to image bounds for safety.
      const iw = img.naturalWidth;
      const ih = img.naturalHeight;
      const sx = Math.max(0, Math.min(iw - 1, box.x * iw));
      const sy = Math.max(0, Math.min(ih - 1, box.y * ih));
      const sw = Math.max(1, Math.min(iw - sx, box.w * iw));
      const sh = Math.max(1, Math.min(ih - sy, box.h * ih));
      // Contain-fit so the whole marked region is visible; letterbox the rest.
      const srcAspect = sw / sh;
      const dstAspect = cw / ch;
      let dx, dy, dw, dh;
      if (srcAspect > dstAspect) {
        dw = cw;
        dh = cw / srcAspect;
        dx = 0;
        dy = (ch - dh) / 2;
      } else {
        dh = ch;
        dw = ch * srcAspect;
        dx = (cw - dw) / 2;
        dy = 0;
      }
      ctx.fillStyle = "#0A0F0D";
      ctx.fillRect(0, 0, cw, ch);
      // Slightly punch up the crop so the player pops from the surrounding grass.
      ctx.filter = "saturate(1.25) contrast(1.08)";
      if (selection.validMask(mask)) {
        const cutout = document.createElement("canvas"); cutout.width = cw; cutout.height = ch;
        const cc = cutout.getContext("2d");
        if (!cc) return;
        cc.drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh);
        const alpha = document.createElement("canvas"); alpha.width = mask.width; alpha.height = mask.height;
        const ac = alpha.getContext("2d");
        if (!ac) return;
        const pixels = ac.createImageData(mask.width, mask.height);
        let offset = 0;
        mask.runs.forEach((count, i) => { for (let n = 0; n < count; n++, offset++) if (i % 2) pixels.data[offset * 4 + 3] = 255; });
        ac.putImageData(pixels, 0, 0);
        cc.globalCompositeOperation = "destination-in"; cc.drawImage(alpha, dx, dy, dw, dh);
        ctx.drawImage(cutout, 0, 0);
      } else ctx.drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh);
      ctx.filter = "none";
    };
    img.src = frameDataUrl;
    return () => { cancelled = true; };
  }, [frameDataUrl, box, mask, width, height]);
  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      className={className}
    />
  );
}
