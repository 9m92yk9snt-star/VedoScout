import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import api, { ASSET_BASE } from "../lib/api";
import { assetUrl, completionLabel, getAnalysisView } from "../lib/analysisProgress.mjs";
import "./AnalysisWaiting.css";

/** Profile status owns dashboard observation. It never starts or retries jobs. */
export default function ProfileAnalysisStatus({ reports = [], followId }) {
  const sectionRef = useRef(null);
  const [watched, setWatched] = useState([]);
  const [updates, setUpdates] = useState({});
  const [disconnected, setDisconnected] = useState({});
  const [blocked, setBlocked] = useState({});
  const activeKey = reports.filter(r => !getAnalysisView(r).complete && !getAnalysisView(r).failed).map(r => r.id).sort().join("|");
  useEffect(() => {
    const active = activeKey ? activeKey.split("|") : [];
    setWatched(previous => [...new Set([...previous, ...active, ...(followId ? [followId] : [])])]);
  }, [activeKey, followId]);
  const pollKey = watched.filter(id => {
    const data = updates[id] || reports.find(r => r.id === id);
    return data && !blocked[id] && !getAnalysisView(data).complete && !getAnalysisView(data).failed;
  }).sort().join("|");
  useEffect(() => {
    if (!pollKey) return undefined;
    let cancelled = false, timer;
    const ids = pollKey.split("|");
    const poll = async () => {
      const results = await Promise.allSettled(ids.map(id => api.get(`/reports/${id}/status`, { timeout: 15000 })));
      if (cancelled) return;
      results.forEach((result, index) => {
        const id = ids[index];
        if (result.status === "fulfilled") {
          setUpdates(previous => ({ ...previous, [id]: { ...reports.find(r => r.id === id), ...result.value.data } }));
          setDisconnected(previous => ({ ...previous, [id]: null }));
        } else {
          const code = result.reason?.response?.status;
          const terminal = [401, 403, 404].includes(code);
          setDisconnected(previous => ({ ...previous, [id]: code === 401 ? "Sign in again to check status" : code === 403 ? "You do not have access to this report" : code === 404 ? "Report not found" : "Reconnecting to update status" }));
          if (terminal) setBlocked(previous => ({ ...previous, [id]: true }));
        }
      });
      timer = setTimeout(poll, 6000);
    };
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
    // The ID set owns this stream; received data must not restart active polls.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollKey]);
  const cards = watched.map(id => updates[id] || reports.find(r => r.id === id)).filter(Boolean);
  const followedCardAvailable = cards.some(data => data.id === followId);
  useEffect(() => {
    if (followedCardAvailable) sectionRef.current?.scrollIntoView?.({ block: "start", behavior: "instant" });
  }, [followId, followedCardAvailable]);
  if (!cards.length) return null;
  return <section ref={sectionRef} className="profile-analysis-section" aria-label="Your analysis status">
    <div className="profile-analysis-heading"><span>Your video · your report</span><h2>Follow your analysis</h2><p>Your analysis continues while you explore your profile.</p></div>
    {cards.map(data => {
      const view = getAnalysisView(data), player = data.player_details?.player_name || "Your player";
      const image = assetUrl(data.display_crop_url || data.poster_url || data.marker_url, ASSET_BASE || "");
      return <article className="profile-analysis-card" key={data.id} data-testid={`profile-analysis-${data.id}`} data-phase={view.key}>
        {image && <img src={image} alt={player} />}
        <div className="profile-analysis-content"><span>{view.complete ? "Report ready" : view.failed || blocked[data.id] || view.confirmation ? "Attention needed" : "Running in background"}</span><h3>{player}</h3><p>{disconnected[data.id] || view.title}</p>
          {!view.complete && !view.failed && <small>Estimated time remaining · {disconnected[data.id] ? "Updating" : completionLabel(data)}</small>}
        </div>
        <div className="profile-analysis-icon" aria-hidden="true">{view.complete ? <CheckCircle2 size={23} /> : view.failed || blocked[data.id] || view.confirmation ? <AlertCircle size={23} /> : <Loader2 size={23} className="animate-spin" />}</div>
        <Link to={`/report/${data.id}`} className="profile-analysis-link">{view.complete ? "Open report" : view.failed ? "Check report" : "View analysis status"}<ArrowRight size={16} /></Link>
      </article>;
    })}
  </section>;
}
