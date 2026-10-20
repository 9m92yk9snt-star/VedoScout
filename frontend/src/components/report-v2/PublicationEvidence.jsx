import React, { useEffect } from 'react';

export default function PublicationEvidence({ publication, onPlayAt }) {
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (!publication?.key_actions?.some(action => `event-${action.event_id}` === id)) return;
    const target = document.getElementById(id);
    if (target) {
      target.open = true;
      target.scrollIntoView?.({ block: 'start' });
    }
  }, [publication]);
  if (!publication) return null;
  const score = publication.score;
  const comparison = score?.comparison;
  return <section className="mb-4 rounded-2xl border border-[#E5DFCE] bg-white p-5 text-[#12402A]" data-testid="publication-evidence">
    <h2 className="font-barlow font-black text-2xl uppercase">Score, academy reference & evidence</h2>
    <p className="mt-2 font-bold">{score.label}: {score.value == null ? 'Not assessed' : `${score.value.toFixed(1)}/10`} · provisional clip assessment</p>
    <p className="mt-1 text-sm">{score.rated_skills}/{score.total_skills} skills rated · {score.weighted_coverage_pct}% of rubric weight covered · {score.unique_events} distinct supporting actions.</p>
    <p className="mt-2 text-sm">{score.method}</p>
    {comparison && <div className="mt-4 rounded-xl bg-[#F0F5EC] p-4" data-testid="academy-reference">
      <h3 className="font-bold">{comparison.bracket} · {comparison.label} reference for observed skills</h3>
      <p className="mt-1 text-sm">{comparison.ranges.map(r => `${r.label}: ${r.min}–${r.max}`).join(' · ')}</p>
      <p className="mt-2 text-xs">{comparison.note}</p>
    </div>}
    <p className="mt-3 text-xs">{publication.stats_definitions}</p>
    <h3 className="mt-5 font-bold">Documented key actions</h3>
    <div className="mt-2 space-y-3">{publication.key_actions.map(action => <details id={`event-${action.event_id}`} key={action.event_id} className="rounded-xl border border-[#E5DFCE] p-3" data-testid={`key-action-${action.event_id}`}>
      <summary className="cursor-pointer font-bold">{action.timestamp} · {action.title}</summary>
      <p className="mt-2 text-sm">{action.description}</p>
      {action.contact_interval_ms && <p className="mt-2 text-xs">Contact window: {action.contact_interval_ms.map(t => (t / 1000).toFixed(3)).join('–')} s. Foot side is not established.</p>}
      <p className="mt-1 text-xs">Evidence reference: {action.event_id}</p>
      {action.proof_verified && <button type="button" className="mt-2 rounded-full bg-[#12402A] px-4 py-2 text-sm font-bold text-white" onClick={() => onPlayAt?.(action.timestamp, {eventId: action.event_id, evidenceId: action.evidence_id})}>Watch evidence · {action.timestamp}</button>}
    </details>)}</div>
    <p className="mt-3 text-xs">{publication.assessment_note}</p>
    <p className="mt-3 text-sm">{publication.review?.analysis_status} · {publication.review?.human_status}</p>
  </section>;
}
