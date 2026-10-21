import React, { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, Clock, Film, Play, RefreshCw, X } from "lucide-react";
import { activityLabel, assetUrl, completionLabel, completionClock, elapsedLabel, getAnalysisView } from "../lib/analysisProgress.mjs";
import "./AnalysisWaiting.css";

import FootballTips from "./FootballTips";
export { default as FootballTips } from "./FootballTips";

function VideoPreview({ video, image, player, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const node = dialog.current;
    if (node.showModal) node.showModal();
    else node.setAttribute("open", "");
    return () => { if (node.close && node.open) node.close(); };
  }, []);
  return <dialog ref={dialog} className="analysis-video-dialog" aria-label={`${player}’s uploaded video`}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <button type="button" onClick={onClose} aria-label="Close uploaded video"><X size={20} /> Close video</button>
    <video src={video} controls playsInline preload="metadata" poster={image || undefined} aria-label={`${player}’s uploaded video`} />
  </dialog>;
}

export default function AnalysisWaiting({ status = {}, phase, uploadPct, startedAt, assetBase = "", error, connectionError, onRetry, onCheckStatus, onContinue, onOpenReport }) {
  const mountedAt = useRef(Date.now());
  const replayButton = useRef(null);
  const [now, setNow] = useState(Date.now);
  const [showVideo, setShowVideo] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const view = getAnalysisView(status, { phase, uploadPct });
  const pd = status.player_details || {};
  const player = pd.player_name || "Your player";
  const timingStatus = { ...status, analysis_started_at: status.analysis_started_at || status.created_at || startedAt || mountedAt.current };
  const finishEstimate = connectionError ? "Reconnecting to update estimate" : view.confirmation ? "Waiting for your player check" : completionLabel(timingStatus, now);
  const heartbeat = activityLabel(status.last_progress_at, now);
  const activityAt = Date.parse(status.last_progress_at);
  const activityFresh = Number.isFinite(activityAt) && activityAt <= now + 60_000 && now - activityAt <= 120_000;
  const image = assetUrl(status.poster_url || status.marker_url || status.display_crop_url || status.subject_crop_url, assetBase);
  const video = assetUrl(status.video_url, assetBase);
  const portrait = assetUrl(status.display_crop_url || status.subject_crop_url || status.player_photo_url, assetBase);
  const taps = Number(status.taps_received ?? status.anchors?.length) || 0;
  const blocked = view.failed || !!error;
  const issue = error?.message || error || view.detail;
  const title = blocked ? (view.failed ? view.title : "Check your analysis status") : view.title;
  const uploading = phase === "uploading" || phase === "saving";
  const retryAvailable = view.target === "full" && onRetry && ((view.failed && status.full_report_status === "failed") || error?.kind === "start");

  return (
    <div className="analysis-waiting" data-testid="analysis-waiting" data-phase={view.key}>
      <header className="analysis-page-heading">
        <p className="analysis-eyebrow"><span aria-hidden="true" /> Your video · {view.target === "full" ? "Full report" : "Initial preview"}</p>
        <h1>{blocked ? "Your video analysis" : view.complete ? title : <>{player === "Your player" ? "Your" : `${player}’s`} {view.target === "full" ? "report" : "preview"}<br className="analysis-mobile-break" /> is on its way<span className="analysis-heading-dot">.</span></>}</h1>
        <p className="analysis-page-intro">Your player. Your footage. One clear report.</p>
      </header>

      <div className="analysis-layout">
        <section className="analysis-status-card" aria-label="Your video analysis" data-testid="analysis-status-card">
          <div className="analysis-video-cover">
            {(
              <>
                {image ? <img src={image} alt="Frame from your uploaded video" onError={event => { event.currentTarget.style.display = "none"; }} /> : <div className="analysis-video-placeholder"><Film size={36} /><span>Your video</span></div>}
                <div className="analysis-video-shade" />
                {portrait && <img className="analysis-player-portrait" src={portrait} alt={`${player} player crop`} onError={event => { event.currentTarget.style.display = "none"; }} />}
                <div className="analysis-video-info">
                  <span className="analysis-video-tag">YOUR UPLOADED VIDEO</span>
                  <strong>{player}</strong>
                  <span>{[pd.age ? `Age ${pd.age}` : null, pd.position, taps ? `${taps} player marks received` : null].filter(Boolean).join(" · ")}</span>
                </div>
                {video && <button ref={replayButton} type="button" className="analysis-replay" aria-label="Watch your uploaded video" onClick={() => setShowVideo(true)}><Play size={17} fill="currentColor" /> Watch video</button>}
              </>
            )}
          </div>

          <div className="analysis-status-body">
            <div className="analysis-status-meta">
              <span className={`analysis-state-chip${blocked ? " analysis-state-chip-warning" : ""}`}><span aria-hidden="true" />{blocked ? "Attention needed" : view.complete ? "Complete" : view.confirmation ? "Player check" : "In progress"}</span>

            </div>
            {!uploading && !view.complete && !blocked && <div className="analysis-finish-estimate" data-testid="analysis-finish-estimate"><span><Clock size={15} /> Estimated time remaining</span><strong>{finishEstimate}</strong><small>{completionClock(timingStatus, now)}</small></div>}
            <div role="status" aria-live="polite" aria-atomic="true" className="analysis-phase-description">
              <h2>{title}</h2>
              <p>{blocked ? issue : view.detail}</p>
            </div>

            {!blocked && !view.complete && (
              view.uploadPercent !== null ? (
                <div className="analysis-upload-progress" role="progressbar" aria-label="Video upload" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(view.uploadPercent)}>
                  <span style={{ width: `${view.uploadPercent}%` }} /><strong>{Math.round(view.uploadPercent)}% uploaded</strong>
                </div>
              ) : <div className={`analysis-loading${view.confirmation ? " analysis-loading-paused" : ""}`} role="progressbar" aria-label="Analysis in progress" aria-valuetext={view.title}><div className="analysis-activity-bar"><span /></div><span className="analysis-loading-label">{view.confirmation ? "Player confirmation needed" : "Analysis in progress"}</span></div>
            )}

            <ol className="analysis-step-list" aria-label="Analysis stages">
              {view.steps.map((step, index) => (
                <li key={step.label} data-state={step.state} aria-current={step.state === "active" && !blocked ? "step" : undefined}>
                  <span className="analysis-step-icon" aria-hidden="true">{step.state === "done" ? <Check size={15} strokeWidth={3} /> : String(index + 1).padStart(2, "0")}</span>
                  <span>{step.label}<small>{step.state === "done" ? "Complete" : step.state === "active" ? blocked ? "Paused" : "In progress" : "Next"}</small></span>
                </li>
              ))}
            </ol>

            {!uploading && !view.complete && !blocked && (
              <div className="analysis-server-status" data-testid="analysis-server-status">
                <span className={connectionError || !activityFresh ? "analysis-status-dot-muted" : ""} aria-hidden="true" />
                <span>{connectionError || heartbeat}</span><time className="analysis-elapsed">Elapsed {elapsedLabel(status.analysis_started_at || status.created_at || startedAt || mountedAt.current, now)}</time>
              </div>
            )}
            {!uploading && !view.complete && !blocked && onContinue && <div className="analysis-background-option"><button type="button" className="analysis-main-button" onClick={onContinue}>Continue in background <ArrowRight size={17} /></button><p>Analysis continues. Follow it from your profile.</p></div>}
            {status.retry_in_progress && !blocked && <p className="analysis-retry-note">The server is repeating the review. Your report is still in progress.</p>}
            {!blocked && !view.complete && <p className="analysis-timing-note">Expected finish window, not a guarantee. Final checks decide when your report is ready.</p>}
            {blocked && <div className="analysis-error-actions">
              {onCheckStatus && <button type="button" className="analysis-main-button" onClick={onCheckStatus}><RefreshCw size={16} /> Check status again</button>}
              {retryAvailable && <button type="button" className="analysis-secondary-button" onClick={onRetry}>Retry analysis</button>}
            </div>}
            {view.complete && onOpenReport && <button type="button" className="analysis-main-button" onClick={onOpenReport}>Open {view.target === "full" ? "full report" : "preview"}<ArrowRight size={17} /></button>}
          </div>
        </section>

        {!view.complete && <FootballTips sessionKey={status.id || `upload-${startedAt || mountedAt.current}`} />}
      </div>
      {showVideo && video && <VideoPreview video={video} image={image} player={player} onClose={() => { setShowVideo(false); replayButton.current?.focus(); }} />}
    </div>
  );
}
