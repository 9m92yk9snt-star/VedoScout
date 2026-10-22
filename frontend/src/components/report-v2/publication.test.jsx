import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { deriveV2 } from './derive';
import PublicationEvidence from './PublicationEvidence';
import { DreamPathSection } from './dreampath';
import { PremiumMobileCategories } from './categories';

// These are retained-data rendering tests; sharing must never call the API.
jest.mock('../../lib/api', () => ({ post: jest.fn(() => {
  throw new Error('Unexpected API request in report publication test');
}) }));

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
  expect(screen.getByTestId('publication-evidence').textContent).not.toContain('13/25 skills rated');
  expect(screen.getByTestId('publication-evidence').textContent).not.toContain('Evidence reference:');
  expect(screen.getByTestId('publication-evidence').textContent).not.toContain('Contact window:');
  expect(screen.getByTestId('academy-reference').textContent).toContain('Coaching rubric');
  expect(document.querySelectorAll('details')).toHaveLength(5);
  fireEvent.click(screen.getAllByRole('button',{name:/Watch this moment/,hidden:true})[0]);
  expect(play).toHaveBeenCalledWith('00:24',{eventId:'action-0',evidenceId:'proof-0'});
  expect(document.querySelectorAll('button')).toHaveLength(4);
});

test('provisional rubric score cannot place player on recruitment ladder',()=>{
  render(<DreamPathSection report={{report_publication:publication}} d={{devPriorities:[]}} playerName="Test Player"/>);
  expect(screen.queryByText('YOU ARE HERE')).toBeNull();
  expect(screen.getByText(/choose the next challenge for your football/)).toBeTruthy();
});


test('stable PDF evidence link opens its matching action after data loads',()=>{
  window.history.replaceState({},'', '#event-action-2');
  render(<PublicationEvidence publication={publication}/>);
  expect(document.getElementById('event-action-2').open).toBe(true);
  expect(document.getElementById('event-action-0').open).toBe(false);
  window.history.replaceState({},'', '/');
});


function mobileReport() {
  const report = {id:'mobile-publication', report_publication:publication,
    full_report:{scores:{overall_development:null}}, player_details:{player_name:'Test Player',age:11}};
  const d = deriveV2(report);
  return {report, props:{report,d,pd:report.player_details,photoCandidates:[],topStrengths:[],
    snapshotMoments:publication.view.snapshotMoments,videoHighlight:{timestamp:'00:56'},
    playAt:jest.fn(), reportDate:publication.date}};
}

test('PDF event links reveal their exact evidence on mobile',async()=>{
  window.history.replaceState({},'', '#event-action-2');
  const {props}=mobileReport();
  render(<PremiumMobileCategories {...props}/>);
  expect(await screen.findByTestId('publication-evidence')).toBeTruthy();
  expect(document.getElementById('event-action-2').open).toBe(true);
  expect(document.getElementById('event-action-0').open).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'Watch this moment · 00:38',hidden:true}));
  expect(props.playAt).toHaveBeenCalledWith('00:38',{eventId:'action-2',evidenceId:'proof-2'});
  expect(screen.getByTestId('pm-cat-evidence-toggle').textContent).toContain('24');
  window.history.replaceState({},'', '/');
});

test('mobile academy bars use the same qualified rubric as desktop and PDF',()=>{
  const {props}=mobileReport();
  props.d.ageComparison=[{name:'Shooting',label:'Academy',width:76}];
  props.d.ageBracket='U11-U12';
  render(<PremiumMobileCategories {...props}/>);
  fireEvent.click(screen.getByTestId('pm-cat-impact-toggle'));
  const reference=screen.getByTestId('v2-age-comparison-card');
  expect(reference.textContent).toContain('Academy skill guide');
  expect(reference.textContent).toContain('ScoutMePlay coaching guide');
  expect(reference.textContent).not.toContain('compares to other players');
});


test('changing a PDF event link on an already open report reveals the new exact action',()=>{
  window.history.replaceState({},'', '#event-action-0');
  render(<PublicationEvidence publication={publication}/>);
  expect(document.getElementById('event-action-0').open).toBe(true);
  window.history.replaceState({},'', '#event-action-3');
  fireEvent(window,new HashChangeEvent('hashchange'));
  expect(document.getElementById('event-action-3').open).toBe(true);
  window.history.replaceState({},'', '/');
});


test('mobile Sequence categories keep native skill groups and backend weighted scores',()=>{
  const {props}=mobileReport();
  props.report.full_report={scores:{technical:7.4,tactical:8.5,mentality:8.0},
    technical:{passing:{score:7},shooting:{score:8}},
    tactical:{decision_making:{score:8.5}},mentality:{confidence:{score:8.0}}};
  props.report.score_meaning={skills:[{key:'decision_making',category:'tactical',label:'Decision Making',score:8.5,lines:[]}]};
  render(<PremiumMobileCategories {...props}/>);
  expect(screen.getByTestId('pm-cat-tech-toggle').textContent).toContain('7.4');
  expect(screen.getByTestId('pm-cat-iq-toggle').textContent).toContain('MENTALITY');
  expect(screen.getByTestId('pm-cat-iq-toggle').textContent).not.toContain('8.5');
  fireEvent.click(screen.getByTestId('pm-cat-tact-toggle'));
  expect(screen.getByTestId('sm-skill-card-decision_making')).toBeTruthy();
});


test('legacy mobile reports keep their original IQ grouping and visible-skill averages',()=>{
  const {props}=mobileReport();
  delete props.report.report_publication;
  props.report.full_report={scores:{technical:7.4},technical:{passing:{score:7},shooting:{score:8}},
    tactical:{decision_making:{score:8.5}},mentality:{confidence:{score:8}}};
  render(<PremiumMobileCategories {...props}/>);
  expect(screen.getByTestId('pm-cat-tech-toggle').textContent).toContain('7.5');
  expect(screen.getByTestId('pm-cat-iq-toggle').textContent).toContain('FOOTBALL IQ & MENTALITY');
  expect(screen.queryByTestId('pm-cat-tact-toggle')).toBeNull();
});
