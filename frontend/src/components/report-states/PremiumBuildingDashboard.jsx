import React from "react";
import { useNavigate } from "react-router-dom";
import { ASSET_BASE } from "../../lib/api";
import AnalysisWaiting from "../AnalysisWaiting";
import { startBackgroundAnalysis } from "../BackgroundAnalysisTracker";

/** One waiting room from the initial review to saved report. Status polling
 * belongs to ReportPage; this component never invents progress or findings.
 */
export default function PremiumBuildingDashboard({ report, status, error, connectionError, onRetry, onCheckStatus }) {
  const navigate = useNavigate();
  return (
    <div className="pt-20 md:pt-24 px-4 md:px-6 pb-10" data-testid="premium-building-dashboard">
      <AnalysisWaiting status={{ ...report, ...status }} assetBase={ASSET_BASE || ""} error={error} connectionError={connectionError}
        onRetry={onRetry} onCheckStatus={onCheckStatus} onContinue={() => {
          startBackgroundAnalysis(report.id, { playerName: report.player_details?.player_name });
          navigate("/dashboard", { state: { followAnalysisId: report.id } });
        }} />
    </div>
  );
}
