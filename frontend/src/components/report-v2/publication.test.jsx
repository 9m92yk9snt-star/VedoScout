import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { deriveV2 } from './derive';
import PublicationEvidence from './PublicationEvidence';
import { DreamPathSection } from './dreampath';

const publication = {
  date: '20 OCTOBER 2026', duration: '01:17',
  score: {label:'Overall Observed Score', value:7.6, rated_skills:13, total_skills:25,
    weighted_coverage_pct:50, unique_events:12, method:'Observed skills; missing skills are excluded.',
    comparison:{bracket:'U11-U12',label:'Academy',ranges:[{label:'Academy',min:6.5,max:8}], note:'Coaching rubric; not a measured percentile.'}},
  key_actions: Array.from({length:5},(_,i)=>({event_id:`action-${i}`,timestamp:`00:${24+i*7}`,title:i===0?'Saved shot':i===1?'Goal':'Assist',
    description:'Test Player completes this action.',proof_verified:i!==4,evidence_id:`proof-${i}`,contact_interval_ms:[23632,23766]})),
  stats_definitions:'Shots include goals. Actions are segments, not touches.',assessment_note:'Partial video evidence.',
  view:{overall:7.6,topStrengths:[],snapshotMoments:[{eventId:'action-0',timestamp:'00:24',desc:'Same description',thumb:null}],
    actionTimeline:Array.from({length:24},(_,i)=>({eventId:`action-${i}`,timestamp:`00:${i}`,title:'Action',description:'Test Player'})),
    matchStats:[{label:'Video Analysed',value:'01:17',pct:0}],scoutOutlook:{currentLabel:'Full playing level not assessed',currentDots:0}},
};

test('frontend uses shared fields without slicing or substituting moments',()=>{
  const d=deriveV2({report_publication:publication,full_report:{scores:{overall_development:null}},player_details:{player_name:'Test Player'}});
  for(const [key,value] of Object.entries(publication.view)) expect(d[key]).toEqual(value);
  expect(d.actionTimeline).toHaveLength(24);
});

test('all five key actions preserve exact proof IDs; unverified proof cannot play',()=>{
  const play=jest.fn();
  render(<PublicationEvidence publication={publication} onPlayAt={play}/>);
  expect(screen.getByTestId('publication-evidence').textContent).toContain('13/25 skills rated');
  expect(screen.getByTestId('academy-reference').textContent).toContain('Coaching rubric');
  expect(document.querySelectorAll('details')).toHaveLength(5);
  fireEvent.click(screen.getAllByRole('button',{name:/Watch evidence/,hidden:true})[0]);
  expect(play).toHaveBeenCalledWith('00:24',{eventId:'action-0',evidenceId:'proof-0'});
  expect(document.querySelectorAll('button')).toHaveLength(4);
});

test('provisional rubric score cannot place player on recruitment ladder',()=>{
  render(<DreamPathSection report={{report_publication:publication}} d={{devPriorities:[]}} playerName="Test Player"/>);
  expect(screen.queryByText('YOU ARE HERE')).toBeNull();
  expect(screen.getByText(/recruitment readiness are not established/)).toBeTruthy();
});


test('stable PDF evidence link opens its matching action after data loads',()=>{
  window.history.replaceState({},'', '#event-action-2');
  render(<PublicationEvidence publication={publication}/>);
  expect(document.getElementById('event-action-2').open).toBe(true);
  expect(document.getElementById('event-action-0').open).toBe(false);
  window.history.replaceState({},'', '/');
});
