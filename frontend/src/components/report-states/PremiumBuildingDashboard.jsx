import React from "react";
import { useNavigate } from "react-router-dom";
import { ASSET_BASE } from "../../lib/api";
import AnalysisWaiting from "../AnalysisWaiting";

/** One waiting room from the initial review to saved report. Status polling
 * belongs to ReportPage; this component never invents progress or findings.
 */
export default function PremiumBuildingDashboard({ report, status, error, connectionError, onRetry, onCheckStatus }) {
  const navigate = useNavigate();
  return (
    <div className="pt-24 md:pt-28 px-4 md:px-6 pb-10" data-testid="premium-building-dashboard">
      <AnalysisWaiting status={{ ...report, ...status }} assetBase={ASSET_BASE || ""} error={error} connectionError={connectionError}
        onRetry={onRetry} onCheckStatus={onCheckStatus} onContinue={() => navigate("/dashboard")} />
    </div>
  );
}
