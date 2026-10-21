import React, { useEffect } from 'react';

export default function PublicationEvidence({ publication, onPlayAt }) {
  useEffect(() => {
    const openLinkedAction = () => {
      const id = window.location.hash.slice(1);
      if (!publication?.key_actions?.some(action => `event-${action.event_id}` === id)) return;
      const target = document.getElementById(id);
      if (target) {
        target.open = true;
        target.scrollIntoView?.({ block: 'start' });
      }
    };
    openLinkedAction();
    window.addEventListener('hashchange', openLinkedAction);
    return () => window.removeEventListener('hashchange', openLinkedAction);
  }, [publication]);
  if (!publication) return null;
  const score = publication.score;
  const comparison = score?.comparison;
  return <section className="mb-4 rounded-2xl border border-[#E5DFCE] bg-white p-5 text-[#12402A]" data-testid="publication-evidence">
    <h2 className="font-barlow font-black text-2xl uppercase">Your strengths, level & next step</h2>
    <p className="mt-2 font-bold">{score.label}: {score.value == null ? 'Discuss your moments with your coach' : `${score.value.toFixed(1)}/10`}</p>
    <p className="mt-1 text-sm">{publication.player_story || publication.narrative?.score_explanation}</p>
    <p className="mt-2 text-sm">{publication.training_focus}</p>
    {comparison && <div className="mt-4 rounded-xl bg-[#F0F5EC] p-4" data-testid="academy-reference">
      <h3 className="font-bold">{comparison.bracket} · {comparison.label} skill reference</h3>
      <p className="mt-1 text-sm">{comparison.ranges.map(r => `${r.label}: ${r.min}–${r.max}`).join(' · ')}</p>
      <p className="mt-2 text-xs">{comparison.note}</p>
    </div>}
    <p className="mt-3 text-xs">{publication.stats_definitions}</p>
    <h3 className="mt-5 font-bold">Learn from your moments</h3>
    <div className="mt-2 space-y-3">{publication.key_actions.map(action => <details id={`event-${action.event_id}`} key={action.event_id} className="scroll-mt-36 rounded-xl border border-[#E5DFCE] p-3" data-testid={`key-action-${action.event_id}`}>
      <summary className="cursor-pointer font-bold">{action.timestamp} · {action.title}</summary>
      <p className="mt-2 text-sm">{action.description}</p>
      {action.learning_focus && <p className="mt-2 text-xs">Try next: {action.learning_focus}</p>}
      <p className="mt-1 text-xs">{action.football_value}</p>
      {action.proof_verified && <button type="button" className="mt-2 rounded-full bg-[#12402A] px-4 py-2 text-sm font-bold text-white" onClick={() => onPlayAt?.(action.timestamp, {eventId: action.event_id, evidenceId: action.evidence_id})}>Watch this moment · {action.timestamp}</button>}
    </details>)}</div>
    <p className="mt-3 text-xs">{publication.assessment_note}</p>
    <p className="mt-3 text-sm">{publication.review?.analysis_status} · {publication.review?.human_status}</p>
  </section>;
}
