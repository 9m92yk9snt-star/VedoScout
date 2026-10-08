import React, { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Clock, Film, Lightbulb, Pause, Play, RefreshCw } from "lucide-react";
import { activityLabel, assetUrl, elapsedLabel, getAnalysisView } from "../lib/analysisProgress.mjs";
import "./AnalysisWaiting.css";

const TIPS = [
  { category: "Awareness", title: "See the space before the ball arrives", text: "Take a quick look over your shoulder before receiving. Know where the pressure is, then let your first touch take you towards space." },
  { category: "First touch", title: "Give your next move a head start", text: "When there is room, receive with an open body and move the ball away from pressure. A useful first touch makes the next pass or dribble easier." },
  { category: "Movement", title: "Pass, then offer a new angle", text: "After a pass, move into a new passing lane. A small change of angle can give your teammate a clear way to find you again." },
  { category: "Decision making", title: "Look for the simple option too", text: "Before taking on a defender, check your support. Sometimes a short pass and a new run create more space than another dribble." },
  { category: "Finishing", title: "Build a repeatable finish", text: "In training, practise placing the ball into different corners from a controlled approach. Start with accuracy, then add pressure and speed." },
  { category: "Defending", title: "Make the attacker’s next move harder", text: "Stay balanced, watch the ball and guide the attacker away from dangerous space. Choose your moment rather than reaching in immediately." },
  { category: "Teamwork", title: "Make your message useful", text: "Use short, clear calls such as ‘time’, ‘turn’ or ‘man on’. Help your teammate understand the situation before the ball reaches them." },
  { category: "Confidence", title: "Make the next action count", text: "After a mistake, find your next useful job: offer a passing option, recover your position or help a teammate. Focus on the action you can take now." },
];

function PitchIllustration() {
  return (
    <svg viewBox="0 0 160 100" fill="none" className="analysis-tip-pitch" aria-hidden="true">
      <rect x="8" y="8" width="144" height="84" rx="3" stroke="currentColor" opacity=".22" />
      <path d="M80 8v84M8 27h22v46H8M152 27h-22v46h22" stroke="currentColor" opacity=".22" />
      <circle cx="80" cy="50" r="17" stroke="currentColor" opacity=".22" />
      <path d="M45 67c24 0 18-35 50-35" stroke="#CCFF00" strokeWidth="2" strokeDasharray="4 4" />
      <path d="m89 27 7 5-7 5" stroke="#CCFF00" strokeWidth="2" strokeLinecap="round" />
      <circle cx="45" cy="67" r="7" fill="#CCFF00" />
      <circle cx="107" cy="32" r="7" stroke="white" strokeWidth="2" />
      <circle cx="61" cy="29" r="5" fill="white" opacity=".35" />
    </svg>
  );
}

export function FootballTips() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false);
  useEffect(() => {
    if (paused) return undefined;
    const timer = setInterval(() => {
      if (!document.hidden) setIndex(value => (value + 1) % TIPS.length);
    }, 25000);
    return () => clearInterval(timer);
  }, [paused]);
  const move = direction => { setPaused(true); setIndex(value => (value + direction + TIPS.length) % TIPS.length); };
  const tip = TIPS[index];
  return (
    <section className="analysis-tips" aria-label="Football tips" data-testid="analysis-football-tips">
      <div className="analysis-tip-top"><span><Lightbulb size={16} /> Touchline tips</span><span>{String(index + 1).padStart(2, "0")} / {TIPS.length}</span></div>
      <PitchIllustration />
      <div className="analysis-tip-content">
        <span className="analysis-tip-category">{tip.category}</span>
        <h2>{tip.title}</h2>
        <p>{tip.text}</p>
      </div>
      <div className="analysis-tip-footer">
        <span>General football advice.<br />Separate from your video analysis.</span>
        <div className="analysis-tip-controls">
          <button type="button" aria-label="Previous football tip" onClick={() => move(-1)}><ArrowLeft size={17} /></button>
          <button type="button" aria-label={paused ? "Play football tips" : "Pause football tips"} aria-pressed={paused} onClick={() => setPaused(value => !value)}>{paused ? <Play size={15} /> : <Pause size={15} />}</button>
          <button type="button" aria-label="Next football tip" onClick={() => move(1)}><ArrowRight size={17} /></button>
        </div>
      </div>
    </section>
  );
}

export default function AnalysisWaiting({ status = {}, phase, uploadPct, startedAt, assetBase = "", error, connectionError, onRetry, onCheckStatus, onContinue, onOpenReport }) {
  const [now, setNow] = useState(Date.now);
  const [showVideo, setShowVideo] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const view = getAnalysisView(status, { phase, uploadPct });
  const pd = status.player_details || {};
  const player = pd.player_name || "Your player";
  const elapsed = elapsedLabel(status.analysis_started_at || status.created_at || startedAt, now);
  const heartbeat = activityLabel(status.last_progress_at, now);
  const activityAt = Date.parse(status.last_progress_at);
  const activityFresh = Number.isFinite(activityAt) && activityAt <= now + 60_000 && now - activityAt <= 120_000;
  const image = assetUrl(status.poster_url || status.marker_url || status.display_crop_url || status.subject_crop_url, assetBase);
  const video = assetUrl(status.video_url, assetBase);
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
            {showVideo && video ? <video src={video} controls playsInline preload="metadata" poster={image || undefined} aria-label={`${player}’s uploaded video`} /> : (
              <>
                {image ? <img src={image} alt="Frame from your uploaded video" onError={event => { event.currentTarget.style.display = "none"; }} /> : <div className="analysis-video-placeholder"><Film size={36} /><span>Your video</span></div>}
                <div className="analysis-video-shade" />
                <div className="analysis-video-info">
                  <span className="analysis-video-tag">YOUR UPLOADED VIDEO</span>
                  <strong>{player}</strong>
                  <span>{[pd.age ? `Age ${pd.age}` : null, pd.position, taps ? `${taps} player marks received` : null].filter(Boolean).join(" · ")}</span>
                </div>
                {video && <button type="button" className="analysis-replay" aria-label="Watch your uploaded video" onClick={() => setShowVideo(true)}><Play size={17} fill="currentColor" /> Watch video</button>}
              </>
            )}
          </div>

          <div className="analysis-status-body">
            <div className="analysis-status-meta">
              <span className={`analysis-state-chip${blocked ? " analysis-state-chip-warning" : ""}`}><span aria-hidden="true" />{blocked ? "Attention needed" : view.complete ? "Complete" : view.confirmation ? "Player check" : "In progress"}</span>
              {elapsed && <span className="analysis-elapsed"><Clock size={14} /> Elapsed {elapsed}</span>}
            </div>
            <div role="status" aria-live="polite" aria-atomic="true" className="analysis-phase-description">
              <h2>{title}</h2>
              <p>{blocked ? issue : view.detail}</p>
            </div>

            {!blocked && !view.complete && (
              view.uploadPercent !== null ? (
                <div className="analysis-upload-progress" role="progressbar" aria-label="Video upload" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(view.uploadPercent)}>
                  <span style={{ width: `${view.uploadPercent}%` }} /><strong>{Math.round(view.uploadPercent)}% uploaded</strong>
                </div>
              ) : <div className="analysis-activity-bar" aria-hidden="true"><span /></div>
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
                <span>{connectionError || heartbeat}</span>
              </div>
            )}
            {status.retry_in_progress && !blocked && <p className="analysis-retry-note">The server is repeating the review. Your report is still in progress.</p>}
            {!blocked && !view.complete && <p className="analysis-timing-note">Time varies with your video and the checks required. The report opens after the final checks.</p>}
            {blocked && <div className="analysis-error-actions">
              {onCheckStatus && <button type="button" className="analysis-main-button" onClick={onCheckStatus}><RefreshCw size={16} /> Check status again</button>}
              {retryAvailable && <button type="button" className="analysis-secondary-button" onClick={onRetry}>Retry analysis</button>}
            </div>}
            {view.complete && onOpenReport && <button type="button" className="analysis-main-button" onClick={onOpenReport}>Open {view.target === "full" ? "full report" : "preview"}<ArrowRight size={17} /></button>}
          </div>
        </section>

        {!view.complete && <FootballTips />}
      </div>

      {!uploading && onContinue && <div className="analysis-background-option">
        <div><strong>You don’t need to stay on this page.</strong><p>Follow this report again from your dashboard.</p></div>
        <button type="button" onClick={onContinue}>Back to dashboard <ArrowRight size={16} /></button>
      </div>}
    </div>
  );
}
