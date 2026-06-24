import React, { useEffect, useRef, useState } from "react";

/**
 * FullFrameWithBoxCanvas — renders the FULL marked frame inside a canvas
 * and overlays the lime "THIS PLAYER" box at pixel-exact coordinates.
 *
 * Why a canvas (not `<img>` + CSS `<div>` overlay)?
 *   The previous approach (`<img max-w-full max-h-full h-auto w-auto>` +
 *   percentage-positioned overlay) was sensitive to EXIF rotation on
 *   iOS-captured frames and to `inline-block` baseline padding — both
 *   of which silently shift the rendered image relative to its parent.
 *   When that shift happens, the percentage overlay box ends up in
 *   completely the wrong place (e.g. floating in the sky while the
 *   player is on the grass below). Drawing the image and the box on
 *   the SAME canvas with `drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh)`
 *   eliminates every layer of CSS/aspect-ratio interpretation —
 *   the box is GUARANTEED to land on the exact same pixels the
 *   <MarkedCropCanvas> zoomed crop already shows correctly.
 *
 * The canvas is contain-fit (letterboxed onto the ink background) so
 * portrait phone-video frames still display upright without stretch.
 */
export default function FullFrameWithBoxCanvas({
  frameDataUrl,
  box,
  // Logical canvas dimensions. The CSS class controls the visible
  // size; this controls the internal pixel buffer (and thus the
  // aspect ratio of the contain-fit math).
  width = 1280,
  height = 720,
  className = "",
}) {
  const canvasRef = useRef(null);
  // Track the displayed image rect so we can position the "THIS PLAYER"
  // label as a normal HTML element (canvas-rendered text doesn't scale
  // crisply on retina + can't inherit the lime chip styling).
  const [labelRect, setLabelRect] = useState(null);

  useEffect(() => {
    if (!frameDataUrl) return;
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
      const iw = img.naturalWidth;
      const ih = img.naturalHeight;
      if (!iw || !ih) return;

      // Solid ink letterbox background — matches the surrounding card.
      ctx.fillStyle = "#0A0F0D";
      ctx.fillRect(0, 0, cw, ch);

      // Contain-fit: scale image so it fits inside canvas without distortion.
      const srcAspect = iw / ih;
      const dstAspect = cw / ch;
      let dw, dh, dx, dy;
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
      ctx.drawImage(img, 0, 0, iw, ih, dx, dy, dw, dh);

      // Box coordinates are normalised (0..1) against the SAME source
      // image, so we compute them inside the contain-fit rect.
      if (box && typeof box.x === "number") {
        const bx = Math.max(0, Math.min(1, box.x));
        const by = Math.max(0, Math.min(1, box.y));
        const bw = Math.max(0.005, Math.min(1 - bx, box.w));
        const bh = Math.max(0.005, Math.min(1 - by, box.h));

        const boxX = dx + bx * dw;
        const boxY = dy + by * dh;
        const boxW = bw * dw;
        const boxH = bh * dh;

        // Vignette: darken EVERYTHING except the box so the marked
        // player visually pops. We do this by drawing a black rect
        // over the whole canvas with a transparent rectangle cut out.
        ctx.save();
        ctx.fillStyle = "rgba(0,0,0,0.55)";
        ctx.beginPath();
        ctx.rect(0, 0, cw, ch);
        // Counter-clockwise inner rect → "evenodd" punches a hole.
        ctx.rect(boxX + boxW, boxY, -boxW, boxH);
        ctx.fill("evenodd");
        ctx.restore();

        // Lime locator box (#CCFF00) with subtle glow.
        ctx.save();
        ctx.lineWidth = Math.max(3, Math.round(cw / 320));
        ctx.strokeStyle = "#CCFF00";
        ctx.shadowColor = "rgba(204,255,0,0.85)";
        ctx.shadowBlur = 14;
        ctx.strokeRect(boxX, boxY, boxW, boxH);
        ctx.restore();

        // Convert the box's canvas-pixel coords back to RELATIVE
        // percentages (of the canvas's own DISPLAY size) so the
        // HTML "THIS PLAYER" chip lines up with the box on screen.
        setLabelRect({
          leftPct: (boxX / cw) * 100,
          topPct: (boxY / ch) * 100,
        });
      } else {
        setLabelRect(null);
      }
    };
    img.src = frameDataUrl;
    return () => { cancelled = true; };
  }, [frameDataUrl, box?.x, box?.y, box?.w, box?.h]);

  return (
    <div className={`relative ${className}`} data-testid="full-frame-canvas-wrap">
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="block w-full h-full"
        data-testid="full-frame-canvas"
      />
      {labelRect && (
        <span
          className="absolute bg-[#CCFF00] text-ink text-[8.5px] uppercase tracking-[0.16em] font-black px-1.5 py-0.5 rounded-sm pointer-events-none whitespace-nowrap"
          style={{
            left: `${Math.max(1, Math.min(72, labelRect.leftPct))}%`,
            top: `calc(${Math.max(0, labelRect.topPct)}% - 16px)`,
            boxShadow: "0 2px 6px rgba(0,0,0,0.4)",
          }}
        >
          ⬤ This player
        </span>
      )}
    </div>
  );
}
