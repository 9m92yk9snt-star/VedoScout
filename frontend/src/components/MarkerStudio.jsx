/** One editor, one decoder, one contract: guided taps + three extra checks. */
import React, { useCallback, useEffect, useRef, useState } from "react";
import ScoutMode from "./marker-studio/ScoutMode";

export default function MarkerStudio({ open, videoUrl, videoFile, onConfirm, onCancel }) {
  const [localSource, setLocalSource] = useState(null);
  const ownedUrl = useRef(null);
  const activeSession = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const session = {};
    activeSession.current = session;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      if (activeSession.current === session) activeSession.current = null;
      document.body.style.overflow = previousOverflow;
    };
  }, [open, videoFile, videoUrl]);

  useEffect(() => {
    if (!open || !videoFile) return undefined;
    const url = URL.createObjectURL(videoFile);
    ownedUrl.current = url;
    setLocalSource({ file: videoFile, url });
    return () => {
      URL.revokeObjectURL(url);
      if (ownedUrl.current === url) ownedUrl.current = null;
    };
  }, [open, videoFile]);

  // Never briefly boot on a stale URL when a different file is selected.
  const source = videoFile
    ? (localSource?.file === videoFile && localSource.url === ownedUrl.current ? localSource.url : null)
    : videoUrl;
  const handleConfirm = useCallback(async ({ anchors, sceneCuts, markerImageDataUrl }) => {
    const session = activeSession.current;
    if (!session || !anchors?.length || !markerImageDataUrl) {
      throw new Error("Your marked frame is missing. Please try again.");
    }
    const response = await fetch(markerImageDataUrl);
    const blob = await response.blob();
    if (activeSession.current !== session) return; // closed/replaced during conversion
    if (!blob.size) throw new Error("Your marked frame could not be saved. Please try again.");
    await onConfirm({
      markerBlob: blob,
      markerTimestamp: anchors[0].t,
      markerBox: anchors[0].box,
      markerAnchors: anchors.map((a) => ({
        t: a.t, box: { ...a.box }, segment: a.segment ?? 0,
        ...(a.verify === true ? { verify: true } : {}),
      })),
      sceneCuts: sceneCuts || [],
      scoutMode: true,
    });
  }, [onConfirm]);

  if (!open) return null;
  if (!source) return (
    <div role="dialog" aria-label="Player selection" className="fixed inset-0 z-[230] bg-ink text-white flex flex-col items-center justify-center gap-4">
      <p role="status">{videoFile ? "Preparing your video…" : "Choose a video before marking your player."}</p>
      <button type="button" onClick={onCancel} className="border border-white/30 rounded-xl px-5 py-3">Close</button>
    </div>
  );
  // Closing ALWAYS exits the studio. No manual fallback, automatic anchors or
  // confidence-preview gate can appear before, after or underneath this editor.
  return <ScoutMode key={source} open videoUrl={source} onCancel={onCancel} onConfirm={handleConfirm} />;
}
