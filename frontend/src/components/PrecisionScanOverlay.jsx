import React from "react";
import AnalysisWaiting from "./AnalysisWaiting";

/** The upload sheet uses the same presentation as the report route. It ends
 * when the server accepts the upload, without a preview-ready celebration.
 */
export default function PrecisionScanOverlay({ open, phase, uploadPct, playerName, playerAge, playerPosition, tapsCount, heroImage, startedAt, target = "full" }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] overflow-y-auto bg-[#F2EDE2]" role="dialog" aria-modal="true" aria-label="Video upload">
      <div className="px-4 py-8 md:px-8 md:py-12">
        <AnalysisWaiting phase={phase} uploadPct={uploadPct} startedAt={startedAt} status={{
          analysis_target: target, player_details: { player_name: playerName, age: playerAge, position: playerPosition },
          taps_received: tapsCount, poster_url: heroImage,
        }} />
      </div>
    </div>
  );
}
