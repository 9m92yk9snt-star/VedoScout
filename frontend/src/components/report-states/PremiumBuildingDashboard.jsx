import React, { useLayoutEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ASSET_BASE } from "../../lib/api";
import AnalysisWaiting from "../AnalysisWaiting";
import { startBackgroundAnalysis } from "../BackgroundAnalysisTracker";

/** One waiting room from the initial review to saved report. Status polling
 * belongs to ReportPage; this component never invents progress or findings.
 */
export default function PremiumBuildingDashboard({ report, status, error, connectionError, onRetry, onCheckStatus }) {
  const navigate = useNavigate();
  useLayoutEffect(() => {
    const update = () => {
      const nav = document.querySelector('[data-testid="main-nav"]');
      const tabs = document.querySelector('[data-testid="mobile-bottom-tabs"]');
      document.documentElement.style.setProperty("--aw-nav-height", `${nav?.getBoundingClientRect().height || 56}px`);
      document.documentElement.style.setProperty("--aw-bottom-height", `${tabs?.getBoundingClientRect().height || 56}px`);
    };
    update();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    for (const node of document.querySelectorAll('[data-testid="main-nav"], [data-testid="mobile-bottom-tabs"]')) observer?.observe(node, { box: "border-box" });
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    window.scrollTo(0, 0);
    return () => { observer?.disconnect(); window.removeEventListener("resize", update); window.visualViewport?.removeEventListener("resize", update); };
  }, []);
  return (
    <div className="analysis-waiting-shell pt-3 md:pt-24 px-3 md:px-6 pb-2 md:pb-10" data-testid="premium-building-dashboard">
      <AnalysisWaiting status={{ ...report, ...status }} assetBase={ASSET_BASE || ""} error={error} connectionError={connectionError}
        onRetry={onRetry} onCheckStatus={onCheckStatus} onContinue={() => {
          startBackgroundAnalysis(report.id, { playerName: report.player_details?.player_name });
          navigate("/dashboard", { state: { followAnalysisId: report.id } });
        }} />
    </div>
  );
}
