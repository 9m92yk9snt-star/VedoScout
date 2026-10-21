"""Read-only publication of Sequence reports. No perception, persistence or model calls.

The observed score averages retained, event-bound assessment grades; it does not
turn a highlight clip into a full-match grade or an empirical percentile.
"""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo

VERSION = 4
CATEGORIES = ('technical', 'tactical', 'physical', 'mentality')
EXPECTED_SKILLS = {
    'technical': ('first_touch', 'ball_control', 'dribbling', 'passing', 'shooting', 'weak_foot', 'one_v_one'),
    'tactical': ('positioning', 'off_ball_movement', 'scanning', 'decision_making', 'timing_of_runs', 'game_understanding'),
    'physical': ('acceleration', 'speed', 'balance', 'agility', 'intensity', 'body_control'),
    'mentality': ('confidence', 'work_rate', 'courage_in_duels', 'response_to_mistakes', 'competitive_mindset', 'focus'),
}
LABELS = {'one_v_one': '1v1 Attacking', 'competitive_mindset': 'Competitive Mindset'}
EMPHASIS = {
    'goalkeeper': {'positioning', 'decision_making', 'focus', 'body_control', 'courage_in_duels'},
    'centre-back': {'positioning', 'courage_in_duels', 'decision_making'},
    'full-back': {'speed', 'acceleration', 'intensity', 'off_ball_movement', 'passing'},
    'wing-back': {'speed', 'acceleration', 'intensity', 'off_ball_movement', 'passing'},
    'defensive midfielder': {'scanning', 'decision_making', 'passing', 'positioning', 'work_rate'},
    'central midfielder': {'passing', 'first_touch', 'scanning', 'decision_making', 'weak_foot'},
    'attacking midfielder': {'passing', 'first_touch', 'scanning', 'decision_making', 'weak_foot'},
    'winger': {'dribbling', 'acceleration', 'one_v_one', 'weak_foot', 'timing_of_runs'},
    'striker': {'first_touch', 'shooting', 'one_v_one', 'off_ball_movement', 'courage_in_duels'},
}
METHOD = ('Observed skills only; position priorities carry weight 2, other skills weight 1. '
          'Unrated skills are excluded, never scored zero. This is an assessment of this clip, '
          'not a full-match grade or a measurement of academy readiness.')
ACADEMY_NOTE = ('ScoutMePlay coaching rubric, version 1; age-band reference ranges from the '
                'existing assessment rubric. These are editorial criteria, not measured peer percentiles '
                'or evidence of academy selection. Position affects weighting, not the range thresholds.')


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def dict_rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def rounded(v):
    return float(Decimal(str(v)).quantize(Decimal('.1'), rounding=ROUND_HALF_UP))


def timestamp(ms):
    sec = int(math.floor(ms / 1000 + .5))
    return f'{sec // 60:02d}:{sec % 60:02d}'


def excerpt(text):
    first = re.split(r'(?<=[.!?])\s+', str(text or ''), maxsplit=1)[0]
    return first


def reader_summary(event, text, name):
    """Short editorial copy from retained facts; full wording stays in the online report and evidence export."""
    first = excerpt(text)
    first = re.sub(r'^' + re.escape(name) + r'\s+', '', first, flags=re.I)
    first = first[:1].upper() + first[1:]
    kind = event.get('canonical_event_type')
    if kind == 'SHOT' and event.get('canonical_outcome') == 'SAVED':
        return 'Shoots through a crowded challenge; the goalkeeper saves the attempt.' if 'crowd' in text.lower() else 'The goalkeeper saves the shot.'
    if kind == 'GOAL':
        return first + ' The ball finishes inside the goal.'
    if kind == 'ASSIST':
        if first.endswith('to a teammate.'):
            return first[:-1] + ', who scores.'
        return first + ' A teammate finishes the move.'
    return first


def strength_explanation(skill, event, name):
    """Observed action plus its possible football value, without a new assessment."""
    observation = reader_summary(event, skill['evidence'][0]['what'], name)
    text = skill['evidence'][0]['what'].lower()
    key = skill['key']
    if key == 'response_to_mistakes' and 'back upright' in text and 'pursues' in text:
        observation = 'He gets up after losing the ball and chases the opponent.'
    elif key == 'decision_making' and event.get('canonical_event_type') == 'GOAL' and 'slides' in text:
        observation = 'He chooses to shoot as a defender slides across. The move ends in a goal.'
    elif key == 'competitive_mindset' and event.get('canonical_event_type') == 'DUEL' and 'shields' in text:
        observation = 'He keeps challenging while the opponent shields the ball.'
    elif key == 'confidence' and event.get('canonical_event_type') == 'GOAL' and 'pursues' in text:
        observation = 'He takes the shot with defenders closing in. The ball finishes inside the goal.'
    benefits = {
        'response_to_mistakes': 'That recovery effort can help the team put pressure back on the ball.',
        'decision_making': 'Choosing when to finish can help turn an attack into a goal attempt.',
        'competitive_mindset': 'Continued pressure can make it harder for the opponent to play forward.',
        'confidence': 'Taking an available shot gives the attack a chance to finish.',
        'ball_control': 'Keeping the ball close can give the team time to continue the attack.',
        'dribbling': 'Carrying the ball under pressure can help the team advance.',
        'shooting': 'Accurate shooting can turn possession into a goal threat.',
        'passing': 'Finding a teammate can help the team keep the move going.',
        'first_touch': 'A controlled first touch can make the next pass or movement easier.',
        'work_rate': 'Staying involved can give teammates more support.',
        'courage_in_duels': 'Contesting the ball can make it harder for the opponent to play freely.',
        'intensity': 'Active pressure can reduce the time an opponent has on the ball.',
        'body_control': 'Adjusting body position can help protect the ball under pressure.',
    }
    benefit = benefits.get(key, 'This is one observed example behind the retained skill rating.')
    # Keep general football value distinct from what this particular action proves.
    return observation, benefit


def label(key):
    return LABELS.get(key, key.replace('_', ' ').title())


def rubric(age):
    if not number(age) or age < 11:
        return None
    if age <= 12:
        return ('U11-U12', [('Standard Club', 3, 5), ('Strong Club', 5, 6.5), ('Academy', 6.5, 8), ('Elite Academy', 8, 9)])
    if age <= 14:
        return ('U13-U14', [('Standard Club', 4, 5.5), ('Strong Club', 5.5, 7), ('Academy', 7, 8.5), ('Elite Academy', 8.5, 10)])
    if age <= 16:
        return ('U15-U16', [('Standard Club', 4, 6), ('Strong Club', 6, 7.5), ('Academy', 7.5, 9), ('Elite Academy', 9, 10)])
    if age <= 18:
        return ('U17-U18', [('Standard Club', 5, 6.5), ('Strong Club', 6.5, 8), ('Academy', 8, 9), ('Elite Academy', 9, 10)])
    if age <= 21:
        return ('U19-U21', [('Standard Club', 5.5, 7), ('Strong Club', 7, 8), ('Academy', 8, 9.5), ('Elite Academy', 9, 10)])
    return ('Senior 22+', [('Standard Club', 6, 7.5), ('Strong Club', 7.5, 8.5), ('Academy', 8, 9.5), ('Elite Academy', 9, 10)])


def comparison(score, age):
    ref = rubric(age)
    if not ref or not number(score):
        return None
    bracket, bands = ref
    # Published ranges overlap in the retained rubric. Prefer the highest
    # threshold reached and disclose all ranges rather than claiming precision.
    band = next((name for name, lo, _ in reversed(bands) if score >= lo), 'Below club reference')
    return {'label': band, 'bracket': bracket, 'ranges': [
        {'label': name, 'min': lo, 'max': hi} for name, lo, hi in bands], 'note': ACADEMY_NOTE}


def _public_text(text, name, jersey, actor=None, teammates=()):
    value = str(text or '')
    value = re.sub(rf'\b(?:white\s+(?:number\s+)?|number\s+|#){re.escape(str(jersey))}\b', lambda _: name, value, flags=re.I)
    value = re.sub(rf'(?<!\w)#{re.escape(str(jersey))}\b', lambda _: name, value)
    value = re.sub(r'\bthe (?:selected|target) player\b', lambda _: name, value, flags=re.I)
    if actor:
        value = re.sub(rf'\b{re.escape(actor)}\b', lambda _: name, value, flags=re.I)
    for teammate in teammates:
        if teammate and teammate != actor:
            value = re.sub(rf'\b{re.escape(teammate)}\b', 'a teammate', value, flags=re.I)
    value = re.sub(r'\bp\d+\b', 'another player', value, flags=re.I)
    value = re.sub(r'\bs(\d{9})\b', lambda m: f'{int(m[1]) / 1000:.3f} s', value)
    value = value.replace('packet ends', 'video segment ends').replace('supplied frames', 'video frames')
    value = value.replace('selected-player', name).replace('the selected passer', name)
    return value


def publish_report(document):
    """Same pure entry point for API, PDF, share cards and offline review."""
    doc = deepcopy(document)
    if doc.get('analysis_engine') != 'SEQUENCE_V1' and (doc.get('full_report') or {}).get('analysis_authority', {}).get('output') != 'SEQUENCE_V1':
        return doc
    full = doc.get('full_report') or {}
    bundle = doc.get('canonical_events') or {}
    events = [e for e in dict_rows(bundle.get('events')) if e.get('global_target_id') == 'GLOBAL_TARGET'
              and (e.get('proof') or {}).get('proof_eligible') is True and number(e.get('canonical_ms'))]
    events.sort(key=lambda e: (e['canonical_ms'], e['event_id']))
    if not events:
        return doc
    pd = doc.get('player_details') or {}
    name, jersey = str(pd.get('player_name') or 'Player'), pd.get('jersey_number') or '__UNSPECIFIED__'
    by_id = {e['event_id']: e for e in events}
    comments = {c.get('event_id'): c for c in dict_rows(full.get('video_comments'))}
    # Do not weaken the retained source/PTS media binding when projecting copy.
    source = bundle.get('source_video_sha256')
    for event in events:
        comment = comments.get(event['event_id'])
        if not comment:
            continue
        proof = event.get('proof') or {}
        matches = bool(source and event.get('source_video_sha256') == source
            and comment.get('source_video_sha256') == source
            and comment.get('evidence_time_ms') == proof.get('frame_ms') == event['canonical_ms']
            and comment.get('source_frame_id') == proof.get('frame_id'))
        if not matches:
            comment['proof_verified'] = False
        if not matches or comment.get('frame_time_ms') != proof.get('frame_ms'):
            comment['proof_frame_verified'] = False
    # Strip presentation state before deriving again: idempotent for API/PDF paths.
    doc.pop('report_publication', None)
    for e in events:
        e['_display_description'] = _public_text(' '.join(e.get('details') or []), name, jersey,
                                                  str(e.get('actor_visual_id') or '').rsplit(':', 1)[-1],
                                                  teammates=[(e.get('causal_chain') or {}).get('receiver_visual_id'),
                                                             (e.get('causal_chain') or {}).get('finisher_visual_id')])
        e['_reader_summary'] = reader_summary(e, e['_display_description'], name)
    def bound(e):
        c = comments.get(e['event_id'], {})
        return {'event_id': e['event_id'], 'timestamp': timestamp(e['canonical_ms']),
                'evidence_time_ms': e['canonical_ms'], 'evidence_id': c.get('evidence_id'),
                'proof_verified': c.get('proof_verified') is True,
                'identity_verified': True, 'canonical_event_ids': [e['event_id']]}

    titles = {'SHOT': 'Saved shot', 'GOAL': 'Goal', 'ASSIST': 'Assist', 'DRIBBLE': 'Dribble',
              'DUEL': 'Duel', 'RUN': 'Run', 'RECOVERY': 'Recovery', 'PASS': 'Pass'}
    timeline = []
    for e in events:
        row = next((deepcopy(a) for a in full.get('action_timeline', []) if a.get('event_id') == e['event_id']), {})
        kind = e['canonical_event_type']
        title = titles.get(kind, kind.title())
        if kind == 'SHOT' and e.get('canonical_outcome') != 'SAVED':
            title = 'Shot attempt'
        row.update(bound(e), title=title, description=e['_display_description'],
                   identity_confidence='high', canonical_ms=e['canonical_ms'])
        timeline.append(row)
        if e['event_id'] in comments:
            comments[e['event_id']].update(bound(e), comment=f'{name}: {title.lower()}.')
    full['action_timeline'] = timeline
    full['video_comments'] = list(comments.values())
    all_skills, skills, weighted_total, total_weight = [], [], 0, 0
    emphasized = EMPHASIS.get(str(pd.get('position') or '').lower(), set())
    for cat in CATEGORIES:
        full[cat] = full.get(cat) if isinstance(full.get(cat), dict) else {}
        for key in EXPECTED_SKILLS[cat]:
            full[cat].setdefault(key, {'score': None, 'cannot_evaluate': True, 'evidence': []})
        for key, sk in full[cat].items():
            if not isinstance(sk, dict) or 'score' not in sk:
                continue
            weight = 2 if key in emphasized else 1
            total_weight += weight
            all_skills.append(key)
            evs = []
            for ev in dict_rows(sk.get('evidence')):
                e = by_id.get(ev.get('event_id'))
                if e and ev.get('identity_verified') is True and ev.get('canonical_event_ids') == [e['event_id']]:
                    evs.append({**bound(e), 'what': e['_display_description']})
            if key == 'weak_foot' and not any(e.get('foot') in {'LEFT', 'RIGHT'} for e in events):
                evs = []
            sk['evidence'] = evs
            if sk.get('cannot_evaluate') or not number(sk.get('score')) or not 1 <= sk['score'] <= 10 or not evs:
                sk.update(score=None, cannot_evaluate=True)
                continue
            weighted_total += weight
            # Display the underlying observed facts rather than templated peer claims.
            sk['notes'] = evs[0]['what']
            sk['tier_for_age'] = None
            skills.append({'key': key, 'category': cat, 'label': label(key), 'score': sk['score'],
                           'weight': weight, 'evidence': evs, 'comparison': comparison(sk['score'], pd.get('age'))})
    unique_events = {ev['event_id'] for s in skills for ev in s['evidence']}
    enough = len(skills) >= 4 and len(unique_events) >= 3 and len({s['category'] for s in skills}) >= 2
    overall = rounded(sum(s['score'] * s['weight'] for s in skills) / weighted_total) if enough else None
    score_info = {'label': 'Overall Observed Score', 'value': overall, 'method': METHOD,
                  'rated_skills': len(skills), 'total_skills': len(all_skills),
                  'weighted_coverage_pct': rounded(weighted_total / total_weight * 100) if total_weight else 0,
                  'unique_events': len(unique_events), 'status': 'PROVISIONAL_CLIP_ASSESSMENT' if enough else 'INSUFFICIENT_EVIDENCE',
                  'weights': {s['key']: s['weight'] for s in skills},
                  'comparison': comparison(overall, pd.get('age'))}
    for cat in CATEGORIES:
        rows = [s for s in skills if s['category'] == cat]
        full.setdefault('scores', {})[cat] = rounded(sum(s['score'] * s['weight'] for s in rows) / sum(s['weight'] for s in rows)) if rows else None
    full['scores']['overall_development'] = overall
    full['observed_score'] = score_info
    counts = {k: sum(e['canonical_event_type'] == k for e in events) for k in titles}
    shots = counts['SHOT'] + counts['GOAL']
    ms = full.setdefault('match_stats', {})
    ms.update(observed_goals=counts['GOAL'], observed_assists=counts['ASSIST'], shots=shots,
              total_actions=len(events), duels_contested=counts['DUEL'], duels_won=None,
              key_passes=None, goals=None, assists=None, coverage_status='PARTIAL')
    # In football key passes conventionally exclude assists. Keep them separate.
    ms['goals_assists_source'] = 'canonical_verified_observations'
    ms['first_touches'] = None
    ms['key_passes'] = sum(e['canonical_event_type'] == 'PASS' and e['canonical_outcome'] == 'TEAMMATE_SHOT' for e in events)
    stats = full.setdefault('verified_stats', {})
    stats.update(observed_counts={**stats.get('observed_counts', {}), 'goals': counts['GOAL'],
        'assists': counts['ASSIST'], 'shots': shots, 'total_actions': len(events), 'duels_contested': counts['DUEL'],
        'key_passes': ms['key_passes']}, goals=None, assists=None, goals_assists_available=False)
    stats['counted_event_ids'] = {**stats.get('counted_event_ids', {}),
        'goals': [e['event_id'] for e in events if e['canonical_event_type'] == 'GOAL'],
        'assists': [e['event_id'] for e in events if e['canonical_event_type'] == 'ASSIST'],
        'key_passes': [e['event_id'] for e in events if e['canonical_event_type'] == 'PASS' and e['canonical_outcome'] == 'TEAMMATE_SHOT'],
        'duels_contested': [e['event_id'] for e in events if e['canonical_event_type'] == 'DUEL']}
    stats['goals_assists_observed_available'] = True
    stats['first_touches'] = None
    stats['observed_counts']['first_touches'] = None
    for k in ('shots', 'total_actions', 'duels_contested', 'key_passes'):
        stats[k] = ms[k]
    duration = doc.get('video_duration_sec')
    duration_label = timestamp(duration * 1000) if number(duration) and duration >= 0 else 'Not available'
    goals_copy = 'a goal' if counts['GOAL'] == 1 else f'{counts["GOAL"]} goals'
    assists_copy = {0: 'no assists', 1: 'an assist', 2: 'two assists', 3: 'three assists'}.get(
        counts['ASSIST'], f'{counts["ASSIST"]} assists')
    summary = (f'{name} contributes {goals_copy} and {assists_copy} in this video.'
               if counts['GOAL'] or counts['ASSIST'] else
               f'The report follows {name}\'s involvement across {len(events)} action segments.')
    limitation = 'Counts cover verified observations; the edited clip does not establish full-match totals or long-term potential.'
    # Use retained, event-bound observations to give the player a readable story.
    # Keep references alongside the prose so this remains auditable without a model.
    ranked = sorted(skills, key=lambda row: (-row['score'], row['key']))
    narrative_events, narrative_paragraphs = [], [summary]
    for key in ('response_to_mistakes', 'ball_control', 'decision_making', 'dribbling', 'competitive_mindset'):
        skill = next((row for row in ranked if row['key'] == key), None)
        if not skill:
            continue
        ev = next((ev for ev in skill['evidence'] if ev['event_id'] not in narrative_events
                   and ev['proof_verified']), None)
        if not ev:
            continue
        fact = reader_summary(by_id[ev['event_id']], ev['what'], name)
        # Short football prose, gated on facts actually present in this observation.
        if key == 'response_to_mistakes' and 'back upright' in fact.lower() and 'pursues' in fact.lower():
            fact = 'After losing the ball, he gets back up and chases the opponent to stay in the play.'
        elif key == 'ball_control' and 'close touches' in fact.lower() and 'lowering his body' in fact.lower():
            fact = 'He keeps the ball close as he advances, lowers his body and changes his running line under pressure.'
        elif key == 'decision_making' and by_id[ev['event_id']]['canonical_event_type'] == 'GOAL' and 'slides' in fact.lower() and 'pursues' in fact.lower():
            fact = 'For the goal, he shoots with defenders closing in and the ball finishes inside the net.'
        # One observed action per paragraph; never invent stable personality traits.
        if fact.split(' ', 1)[0] in {'Gets', 'Collects', 'Carries', 'Receives', 'Attempts', 'Meets', 'Runs', 'Continues', 'Dribbles', 'Escapes', 'Recovers', 'Turns', 'Shoots', 'Releases'}:
            fact = 'He ' + fact[:1].lower() + fact[1:]
        narrative_paragraphs.append(fact)
        narrative_events.append(ev['event_id'])
        if len(narrative_paragraphs) == 4:
            break
    strongest = ranked[:2]
    strength_phrases = {'response_to_mistakes': 'his reaction after losing possession',
                        'decision_making': 'his decisions on the ball', 'ball_control': 'his close control',
                        'shooting': 'his shooting', 'competitive_mindset': 'his efforts in contested play',
                        'work_rate': 'his effort to stay involved', 'dribbling': 'his dribbling',
                        'confidence': 'his willingness to take part in attacking actions'}
    strength_names = ' and '.join(strength_phrases.get(row['key'], 'his ' + row['label'].lower()) for row in strongest)
    score_explanation = (f'The assessment gives most credit to {strength_names}. '
                         f'This provisional score uses {len(skills)} rated skills from this video; unseen abilities are not scored.'
                         if strongest else 'There is not enough supported skill evidence to explain an overall score.')
    good_news = ('He contributes as both a scorer and a provider in this clip.'
                 if counts['GOAL'] and counts['ASSIST'] else
                 narrative_paragraphs[1] if len(narrative_paragraphs) > 1 else
                 'Review the documented moments together and choose one action to practise.')
    if any(s['key'] == 'response_to_mistakes' and any(e['event_id'] in narrative_events for e in s['evidence']) for s in skills):
        good_news = 'His reaction after losing the ball is a positive moment to build on.'
    full['parent_summary'] = {'headline': 'A goal and a role in creating chances' if counts['GOAL'] and counts['ASSIST'] else 'What the video shows', 'paragraphs': narrative_paragraphs,
                              'good_news': good_news}

    full['executive_summary'] = summary + ' ' + limitation
    full['final_summary'] = full['executive_summary']
    full['snapshot'] = {'biggest_strength': 'Documented attacking contributions', 'hidden_talent': 'Review the linked action',
        'biggest_development_area': 'Training focus from observed skills', 'overall_progress_note': 'Starting point for future comparison; progress requires another comparable video.'}
    key_events = [e for e in events if e['canonical_event_type'] in {'GOAL', 'ASSIST', 'SHOT'}]
    # Four snapshot cards are editorial selections of actual events, never token joins.
    chosen = sorted(key_events, key=lambda e: (e['canonical_event_type'] != 'GOAL', e['canonical_ms']))[:4]
    full['snapshot_moments'] = []
    for key, e in zip(('strength', 'noticed', 'hidden', 'develop'), chosen):
        c = comments.get(e['event_id'], {})
        full['snapshot_moments'].append({**bound(e), 'key': key, 'label': 'Verified action',
            'title': titles[e["canonical_event_type"]], 'desc': e['_reader_summary'],
            'frame_url': c.get('frame_url') if c.get('proof_frame_verified') is True else None})
    full['snapshot_moments_authority'] = True
    full['coach_notes'] = [summary, 'Review the evidence before choosing a training focus.']
    full['scout_outlook'] = {'current_level_label': 'Full playing level not assessed', 'current_level_dots': 0,
        'potential_level_label': 'Not assessed', 'potential_level_dots': 0, 'recruitment_readiness': 'Not assessed',
        'long_term_potential': 'Not assessed', 'long_term_note': limitation}
    # Preserve the conservative overall playing-level authority. A rubric comparison
    # of observed skills must not manufacture a placement on the recruitment ladder.
    full['overall_benchmark'] = {'tier': None, 'tier_label': 'Full playing level not assessed', 'percentile': None}
    full['parent_value_metrics'] = {'involvement': {'actions_observed': len(events),
        'note': 'Verified action segments; this is not a count of individual ball touches.'}, 'top_minutes': []}
    full['parent_corner'] = None
    # Retain education, removing the unsupported population comparison.
    if isinstance(full.get('grow_your_game'), dict):
        lessons = []
        recovery = (full.get('mentality', {}).get('response_to_mistakes') or {}).get('evidence') or []
        for lesson in full['grow_your_game'].get('lessons', []):
            evidence = next((ev for ev in recovery if ev.get('proof_verified') and ev.get('event_id') in by_id), None)
            if lesson.get('topic_id') != 'five_seconds_after_mistake' or not evidence:
                continue
            lesson.update(age_benchmark=None, title='React after losing the ball', category='mentality',
                what_happened=reader_summary(by_id[evidence['event_id']], evidence['what'], name),
                what_scouts_look_for='How a player responds after losing possession: getting back into play and supporting the team.',
                why_it_matters='A recovery run can help the team respond to a turnover.',
                personal_advice='After losing the ball, look for a useful next action: recover, press or support a teammate.',
                moments=[{**evidence, 'what': evidence['what']}])
            lessons.append(lesson)
        full['grow_your_game']['lessons'] = lessons
    # Keep useful drills but replace personal deficit claims with cited observations.
    priorities = sorted(skills, key=lambda s: (s['score'], s['key']))[:3]
    used_priority_events = set()
    full['development_priorities_detailed'] = []
    for s in priorities:
        ev = next((e for e in s['evidence'] if e['event_id'] not in used_priority_events), s['evidence'][0])
        used_priority_events.add(ev['event_id'])
        full['development_priorities_detailed'].append({'name': s['label'], 'score': s['score'],
        'issue': reader_summary(by_id[ev['event_id']], ev['what'], name),
        'how_to_improve': {'first_touch': 'Receive and move into space before the next pass.',
            'body_control': 'Practise controlled turns and shielding in gentle, game-like pressure.',
            'dribbling': 'Keep the ball close, then change pace as you move past a defender.',
            'one_v_one': 'Practise changing speed and direction against an active defender.'}.get(s['key'], 'Repeat this action in a small-sided practice and review the next video.'),
        'event_id': ev['event_id'], 'evidence': s['evidence']})
    full['development_roadmap'] = {'now': 'Review the documented actions and select one training focus.',
        'three_months': 'Reassess the same skills using comparable match footage.',
        'six_months': 'Review progress across several observations.', 'twelve_months': 'Set the next goals with the player and coach.'}
    package = full.get('parents_package') or {}
    if package.get('message_to_player'):
        package['message_to_player']['body'] = f'{name}, review your goal, assists and saved shot with your coach. Choose one action to practise and keep enjoying your football.'
    full['parents_package'] = package
    # Name replacement applies only to public copy, never identity IDs or proof hashes.
    def names(value, field=''):
        if isinstance(value, dict):
            return {k: names(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [names(v, field) for v in value]
        if isinstance(value, str) and field in {'comment', 'description', 'what', 'notes', 'issue', 'body', 'text', 'why', 'verdict', 'why_this_score'}:
            return _public_text(value, name, jersey)
        return value
    full = names(full)
    doc['full_report'] = full
    stamp = doc.get('full_generated_at') or doc.get('full_report_run_finished_at') or doc.get('paid_at') or doc.get('created_at')
    try:
        dt = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo('UTC'))
        date_label = dt.astimezone(ZoneInfo('Europe/Copenhagen')).strftime('%d %B %Y').upper()
    except (ValueError, TypeError):
        date_label = 'DATE UNAVAILABLE'
    meanings = []
    for s in sorted(skills, key=lambda s: (-s['score'], s['key'])):
        ev = s['evidence'][0]
        comp = s['comparison']
        meanings.append({'key': s['key'], 'category': s['category'], 'label': s['label'], 'score': s['score'],
            'lines': [excerpt(ev['what'])], 'evidence': {**ev, 'verified': True},
            'angles': {}, 'comparison': comp, 'looks_for': METHOD, 'scale': None,
            'next_level': 'Reassess with more comparable match observations.',
            'position_why': f'Weight {s["weight"]} in the observed score for {pd.get("position") or "this position"}.'})
    doc['score_meaning'] = {'skills': meanings, 'position': pd.get('position'), 'position_line': ACADEMY_NOTE, 'discovery': None}
    doc['score_context'] = {'overall': {'score': overall, 'line': score_explanation}, 'bracket': (rubric(pd.get('age')) or ('Age unavailable',))[0]}
    evidence_rows = [{**bound(e), 'title': titles[e['canonical_event_type']], 'description': e['_display_description'],
        'summary': e['_reader_summary'],
        'contact_interval_ms': e.get('contact_interval_ms'), 'outcome_ms': (e.get('proof') or {}).get('outcome_ms'),
        'clip_url': comments.get(e['event_id'], {}).get('tele_clip_url')} for e in key_events]
    review = doc.get('agent_review') or {}
    delivered = review.get('status') == 'delivered' and bool(review.get('review_text'))
    review_info = {'analysis_status': 'Automated analysis complete',
        'human_status': 'Scout review delivered' if delivered else 'Scout review awaiting delivery',
        'sla_hours': 48, 'submitted_at': review.get('created_at'), 'delivered_at': review.get('delivered_at')}
    def facts(value):
        if isinstance(value, dict):
            return {k: facts(v) for k, v in value.items() if not k.endswith('_url')}
        if isinstance(value, list):
            return [facts(v) for v in value]
        return value
    signature = hashlib.sha256(json.dumps(facts({'full': full, 'date': date_label,
        'review': review_info, 'version': VERSION}), sort_keys=True, default=str).encode()).hexdigest()
    sorted_skills = sorted(skills, key=lambda s: (-s['score'], s['key']))
    view = {
        'overall': overall, 'stars': int(overall / 2 + .5) if overall is not None else 0,
        'topStrengths': [], 'snapshotMoments': [], 'actionTimeline': [],
        'devPriorities': [{'name': p['name'], 'score': p['score'], 'issue': p['issue'],
            'howTo': p['how_to_improve']} for p in full['development_priorities_detailed']],
        'scoutOutlook': {'currentLabel': 'Not assessed from this clip', 'currentDots': 0,
            'potentialLabel': 'Not assessed', 'potentialDots': 0, 'readiness': 'Not assessed',
            'longTerm': 'Not assessed', 'longTermNote': limitation},
        'ageComparison': [{'name': s['label'], 'label': s['comparison']['label'], 'width': s['score'] * 10}
                          for s in sorted_skills[:6] if s['comparison']],
        'ageBracket': (rubric(pd.get('age')) or (None,))[0],
        'parentSummary': {'headline': full['parent_summary']['headline'],
            'paragraphs': full['parent_summary']['paragraphs'], 'goodNews': full['parent_summary']['good_news']},
        'matchStats': [{'label': k, 'value': v, 'pct': 0} for k, v in [
            ('Goals', counts['GOAL']), ('Assists', counts['ASSIST']),
            ('Total Actions', len(events)), ('Key Passes (excluding assists)', ms['key_passes']),
            ('Shots (including goals)', shots), ('Duels Observed', counts['DUEL']), ('Video Analysed', duration_label)]],
    }
    for s in sorted_skills[:4]:
        ev = s['evidence'][0]
        c = comments.get(ev['event_id'], {})
        observation, contribution = strength_explanation(s, by_id[ev['event_id']], name)
        view['topStrengths'].append({'name': s['label'], 'score': s['score'], 'category': s['category'],
            'note': observation + ' ' + contribution, 'observation': observation,
            'teamContribution': contribution, 'timestamp': ev['timestamp'], 'eventId': ev['event_id'],
            'evidenceId': ev.get('evidence_id'), 'proofable': ev['proof_verified'],
            'thumb': c.get('frame_url') if c.get('proof_frame_verified') is True else None,
            'thumbVerified': c.get('proof_frame_verified') is True})
    for m in full['snapshot_moments']:
        view['snapshotMoments'].append({'key': m['key'], 'label': m['label'], 'title': m['title'],
            'desc': m['desc'], 'timestamp': m['timestamp'], 'thumb': m['frame_url'], 'annot': 'circle',
            'eventId': m['event_id'], 'evidenceId': m.get('evidence_id')})
    for row in timeline:
        view['actionTimeline'].append({'timestamp': row['timestamp'], 'title': row['title'],
            'description': row['description'], 'outcome': 'neutral', 'tracked': False,
            'eventId': row['event_id'], 'proofVerified': row['proof_verified'], 'proofable': row['proof_verified']})
    doc['report_publication'] = {'version': VERSION, 'view': view, 'review': review_info, 'date': date_label, 'score': score_info,
        'duration': duration_label, 'key_actions': evidence_rows, 'assessment_note': limitation,
        'narrative': {'event_ids': narrative_events, 'score_explanation': score_explanation},
        'stats_definitions': 'Shots include goals. Key passes lead to a teammate shot without a goal; assists are counted separately. Actions are segments, not ball touches.',
        'content_sha256': signature}
    return doc
