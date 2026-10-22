"""Player-facing coaching copy from saved actions; no model calls or new findings.

The action is a retained observation. Football value and practice are coaching
advice, never extra detected actions or claims about academy selection.
"""
import re


_PRESSURE_FINISH = re.compile(r'under (?:\w+[- ]?){0,3}pressure|while (?:being )?challenged|challenged by')
_AFTER_CARRY = re.compile(r'\b(?:after|following)\b[^.!?]{0,50}\b(?:dribble|carry)\b')

# Focus, practice, and a target for the NEXT session (never a measured result).
PRACTICE = {
    'dribbling': ('Add a change of pace after your turn.',
        'Play 1v1 towards two gates: protect, turn and accelerate through a gate.', 'Aim for five exits with the ball under control.'),
    'ball_control': ('Keep the next touch within reach as pressure changes.',
        'Keep the ball in a small square while a partner tries to win it.', 'Aim to keep control for five 20-second rounds.'),
    'one_v_one': ('Make the defender commit, then attack the other side.',
        'Play 1v1 towards two small goals and vary your speed and direction.', 'Aim for five successful escapes using both directions.'),
    'passing': ('Connect your carry to a pass your teammate can use.',
        'Play 2v1: draw the defender, then pass into your teammate\'s path.', 'Aim for five passes your teammate can take forward.'),
    'shooting': ('Set up your finish with a controlled final touch.',
        'Carry towards goal, take a setup touch and finish at a chosen corner.', 'Aim for five accurate finishes before increasing speed.'),
    'first_touch': ('Use your first touch to prepare the next action.',
        'Receive from a partner and take your first touch through one of two gates.', 'Aim for five receptions that flow straight into a pass.'),
    'weak_foot': ('Make your other foot a comfortable option.',
        'Pass against a wall with your less-used foot, controlling each return.', 'Aim for ten controlled passes in a row.'),
    'decision_making': ('Practise choosing between carrying, passing and shooting.',
        'Play 2v1 with a goal: decide whether to release your teammate or finish.', 'After five attacks, explain what made you choose each option.'),
    'scanning': ('Look before receiving so you know your next option.',
        'Ask a partner to show a colour behind you before playing you the ball.', 'Aim to name the colour before five receptions.'),
    'off_ball_movement': ('Move into a passing lane after releasing the ball.',
        'Play a pass, move around a cone and offer a new angle for the return.', 'Aim for five give-and-go moves without stopping.'),
    'positioning': ('Find a position where a teammate can reach you.',
        'Play 3v1 keep-ball and move to offer a clear passing lane.', 'After each pass, find a fresh angle.'),
    'timing_of_runs': ('Match your run to the moment your teammate can pass.',
        'Start behind a marker and run through a gate as a partner prepares a pass.', 'Aim for five passes received while moving.'),
    'game_understanding': ('Connect your action to the next teammate.',
        'Pause a match clip before a pass and choose two useful options.', 'Explain how each option helps the attack.'),
    'balance': ('Stay ready for your next touch through a challenge.',
        'Dribble around a partner, turn and pass through a small gate.', 'Aim for five turns followed by a controlled pass.'),
    'body_control': ('Turn protection into a way out of pressure.',
        'Receive with your back to a partner, shield, then turn through either gate.', 'Aim for five exits with the ball within reach.'),
    'acceleration': ('Make your first few steps purposeful.',
        'Start beside the ball and accelerate through a short gate with it.', 'Keep the ball within reach throughout five starts.'),
    'speed': ('Keep control as you build speed.',
        'Carry through a straight channel, then slow down inside a small box.', 'Aim for five runs that end with the ball in the box.'),
    'agility': ('Connect a quick change of direction to your next touch.',
        'Dribble to a central cone and react to a partner pointing left or right.', 'Aim for five clean changes in each direction.'),
    'intensity': ('Follow your first effort with a useful second action.',
        'Play a short 1v1, then immediately offer support for the next ball.', 'Make a clear second action after each of five plays.'),
    'work_rate': ('Turn a recovery into the next useful team action.',
        'Play a loose ball into a 2v2 game: compete for it, then find support.', 'After five recoveries, review your first pass or carry.'),
    'courage_in_duels': ('Combine your willingness to compete with ball protection.',
        'Start 1v1 with your body between the defender and the ball, then escape.', 'Aim for five controlled exits rather than rushing the ball away.'),
    'confidence': ('Keep taking responsibility while choosing your next action.',
        'Play 1v1 with a teammate available for a pass as well as a goal to attack.', 'Try both options and explain five decisions.'),
    'response_to_mistakes': ('Make your next action useful after losing possession.',
        'Play 2v2 and react immediately when possession changes.', 'Choose to press, recover or support after each turnover.'),
    'competitive_mindset': ('Stay involved through the next phase of a challenge.',
        'Play short 1v1 rounds with a second ball ready after each attempt.', 'Begin the next play with the same focus.'),
    'focus': ('Stay ready as the play moves around you.',
        'Pass in a small group with two possible receivers and changing roles.', 'Be ready for your next involvement after every pass.'),
}

VALUE = {
    'DRIBBLE': 'That helps you move the attack forward with the ball.',
    'PASS': 'Finding a teammate helps your team keep the attack moving.',
    'GOAL': 'Your finish gives the attack its end product.',
    'SHOT': 'Your finish gives the attack a chance to score.',
    'ASSIST': 'Your pass helps a teammate turn the chance into a goal.',
    'RECOVERY': 'Winning possession gives your team another chance to build.',
    'DUEL': 'Competing for the ball puts pressure on your opponent.',
    'TACKLE': 'A well-timed challenge can stop an opponent advancing.',
    'INTERCEPTION': 'Reading a pass can help your team regain possession.',
    'RUN': 'Your movement can give the next attack an option.',
}


def _movement_types(event):
    return {m.get('type') for m in event.get('movement_observations') or []
            if isinstance(m, dict) and m.get('decision') == 'SUPPORTED'}


def _following_pass(event, events):
    actor = event.get('actor_visual_id')
    end = event.get('end_ms')
    if not actor or not isinstance(end, int):
        return None
    return next((e for e in events if e.get('actor_visual_id') == actor
                 and e.get('canonical_event_type') == 'PASS' and e.get('canonical_outcome') == 'COMPLETED'
                 and isinstance(e.get('canonical_ms'), int) and 0 <= e['canonical_ms']-end <= 2000), None)


def action_lesson(event, events=()):
    kind = event.get('canonical_event_type')
    text = ' '.join(event.get('details') or []).lower()
    outcome = event.get('canonical_outcome')
    value = VALUE.get('DRIBBLE' if kind == 'CARRY' else kind, 'Watch how the next phase of play develops.')
    if kind == 'GOAL':
        if 'close-range' in text and _PRESSURE_FINISH.search(text):
            fact = 'You get a close-range finish away under pressure and score.'
            value = 'Getting the shot away keeps a crowded attack dangerous.'
        elif _AFTER_CARRY.search(text):
            fact = 'You finish your forward carry with a goal.'
            value = 'Your finish turns ball progression into a goal threat.'
        else:
            fact = 'You finish the attack with a goal.'
    elif kind == 'ASSIST':
        fact = "Your final pass sets up a teammate's goal."
    elif kind in {'DRIBBLE', 'CARRY'}:
        movements = _movement_types(event)
        if movements.intersection({'SHIELD_TURN', 'PROTECTIVE_TURN'}) and 'DIRECTION_REVERSAL' in movements:
            fact = 'You shield the ball as you turn, then change direction again.'
            value = 'This gives you another route before your next pass or carry.'
            if _following_pass(event, events):
                fact = 'You shield the ball, change direction again and then find a teammate.'
                value = 'You use the turn to set up the next team action.'
        elif movements.intersection({'SHIELD_TURN', 'PROTECTIVE_TURN'}):
            fact = 'You put your body between the opponent and the ball as you turn.'
            value = 'Protecting the ball can give you time to choose your next action.'
        elif 'DIRECTION_REVERSAL' in movements:
            fact = 'You turn back with the ball to find another route.'
            value = 'Changing your route can open a passing lane or a way forward.'
        elif 'DIRECTION_CHANGE' in movements:
            fact = 'You change direction with the ball.'
            value = 'A new direction can give you another passing or carrying option.'
        elif 'shield' in text or 'protect' in text:
            fact = 'You use your body to protect the ball under pressure.'
        elif 'turn' in text:
            fact = 'You turn with the ball and carry the attack forward.'
        elif any(word in text for word in ('pressure', 'shoulder', 'challenge', 'defender')):
            fact = 'You carry the ball with a defender close by.'
        else:
            fact = 'You carry the ball forward at your feet.'
    elif kind == 'PASS':
        fact = ('You slow your carry and find a teammate with a pass.' if 'slows' in text
                else 'You connect with a teammate through your pass.') if outcome == 'COMPLETED' else 'You look to connect the attack with a pass.'
    elif kind == 'RECOVERY':
        fact = ('You regain the ball and give your team possession.' if outcome == 'COMPLETED'
                else 'You compete to regain possession of the ball.')
    elif kind == 'SHOT':
        fact = 'You test the goalkeeper with a shot.' if outcome == 'SAVED' else 'You take the opportunity to shoot.'
    elif kind == 'DUEL':
        fact = 'You compete with an opponent for the ball.'
    elif kind == 'TACKLE':
        fact = 'You challenge an opponent for the ball.'
    elif kind == 'INTERCEPTION':
        fact = "You step into the path of an opponent's pass."
    elif kind == 'RUN':
        fact = 'You continue your run after the goal.' if 'post-goal' in text else 'You move to stay involved in the play.'
    else:
        fact = 'The play continues around you.'
    if (kind in {'GOAL', 'SHOT', 'ASSIST', 'PASS'} and event.get('foot') in {'LEFT', 'RIGHT'}
            and event.get('foot_verification') == 'SOURCE_ANATOMICAL_SEQUENCE_SUPPORTED'):
        fact = fact.rstrip('.') + f" using your {event['foot'].lower()} foot."
    return fact, value


def practice(key):
    focus, drill, target = PRACTICE[key]
    return focus, f'{drill} {target}'


def skill_lesson(skill, event, events=()):
    """Explain the football quality, rather than repeating an event description."""
    fact, value = action_lesson(event, events)
    key, kind = skill['key'], event.get('canonical_event_type')
    text = ' '.join(event.get('details') or []).lower()
    if key == 'ball_control' and kind in {'DRIBBLE', 'CARRY'} and _movement_types(event):
        fact = 'You keep the ball available as you turn and adjust your route.'
        value = 'That control helps you prepare another touch instead of rushing the ball away.'
    elif key == 'body_control' and any(word in text for word in ('shield', 'protect')):
        fact = 'You place your body between your opponent and the ball.'
        value = 'Your body position helps you protect possession while you look for a way out.'
    elif key == 'confidence' and kind in {'GOAL', 'SHOT'}:
        fact = 'You take responsibility for the finish at the end of the move.'
        value = 'Being willing to finish adds a goal threat to your attacking play.'
    elif key == 'courage_in_duels' and kind in {'DRIBBLE', 'DUEL'}:
        fact = 'You compete for the ball with opponents challenging around you.'
        value = 'That willingness to stay in the contest gives you a chance to keep the attack alive.'
    elif key == 'one_v_one' and kind == 'DRIBBLE':
        value = 'Build on that ball protection by changing pace after your turn.'
    elif key == 'first_touch' and any(w in text for w in ('receiv', 'takes a pass')):
        fact = 'You receive the pass and turn into your next action.'
        value = 'A useful first touch sets up the pass, carry or finish that follows.'
    elif key == 'work_rate' and kind == 'RECOVERY' and event.get('canonical_outcome') == 'COMPLETED':
        value = 'Your recovery effort gives your team another possession to build from.'
    return fact, value


def _assessment_copy(skill, events, by_id):
    supporting = list({r['event_id']: by_id[r['event_id']] for r in skill['evidence']
                       if r.get('event_id') in by_id}.values())
    fact, value = skill_lesson(skill, supporting[0], events)
    why = f'{fact} {value}'
    if skill['key'] == 'shooting':
        goals = [e for e in supporting if e.get('canonical_event_type') == 'GOAL']
        if len(goals) == 2:
            why = 'Your two goals show you finishing moves successfully. The grade reflects those finishes in this video.'
        elif len(goals) == 1:
            why = f'{action_lesson(goals[0], events)[0]} Your finishing grade reflects this successful outcome.'
    elif skill['key'] == 'passing' and len(supporting) == 1:
        why = 'Your completed pass gives you a useful example to build on. Practise making the next pass easy for your teammate to take forward.' if supporting[0].get('canonical_outcome') == 'COMPLETED' else why
    return fact, value, why


def _repair_home_instructions(package):
    # A saved report may already contain a technical placeholder instead of a
    # drill step. Restore only this known exercise, as generic future practice;
    # never reconstruct a match fact from a filtered sentence.
    for drill in package.get('home_drills') or []:
        if (not isinstance(drill, dict) or str(drill.get('name', '')).lower() != 'wall ball'
                or str(drill.get('targets', '')).lower() != 'first touch'):
            continue
        steps = drill.get('steps')
        if isinstance(steps, list) and 'The verified evidence is insufficient to assess this claim.' in steps:
            drill['steps'] = ['Stand a few steps from the wall.',
                'Pass with your right foot and control the rebound with your left.',
                'Pass with your left foot and control with your right. Repeat.']


def apply_player_copy(doc, events, skills, bound):
    """Keep existing card fields/geometry; replace diagnostics with coaching."""
    full, pub = doc['full_report'], doc['report_publication']
    view = pub['view']
    by_id = {e['event_id']: e for e in events}
    comments = {c.get('event_id'): c for c in full.get('video_comments', [])}
    def lesson(event):
        return action_lesson(event, events)
    def skill_copy(skill, event):
        return skill_lesson(skill, event, events)
    # Grades stay attached to their original source events. Replace over-broad
    # match/ability claims in the displayed explanation, not the grade or audit.
    for skill in skills:
        fact, value, why = _assessment_copy(skill, events, by_id)
        original = full[skill['category']][skill['key']]
        original.update(notes=f'{fact} {value}', why_this_score=why, verdict=why)
        for row in skill['evidence']:
            row['what'] = skill_copy(skill, by_id[row['event_id']])[0]
    available = [s for s in skills if s['key'] in PRACTICE and any(e['proof_verified'] for e in s['evidence'])]
    ranked = sorted(available, key=lambda s: (-s['score'], s['key']))
    def evidence(skill):
        return next(e for e in skill['evidence'] if e['proof_verified'])
    def label(key):
        return key.replace('_', ' ').replace('one v one', '1v1 attacking')
    top = ranked[:2]
    qualities = ' and '.join(label(s['key']) for s in top)
    opening = f'Your {qualities} stand out in this video.' if top else 'Choose a moment from your video to discuss with your coach.'
    story, ids = [opening], []
    goals = [e for e in events if e['canonical_event_type'] == 'GOAL' and bound(e)['proof_verified']]
    if len(goals) > 1:
        goal_line = 'You score twice in this video.' if len(goals) == 2 else f'You score {len(goals)} goals in this video.'
        if any('under pressure' in lesson(e)[0] for e in goals):
            goal_line += ' One finish comes under close pressure.'
        story.append(goal_line)
        ids.extend(e['event_id'] for e in goals)
    movements = [e for e in events if _movement_types(e) and bound(e)['proof_verified']]
    if movements:
        move = max(movements, key=lambda e: (bool(_following_pass(e, events)),
                   len(_movement_types(e)), e.get('canonical_outcome') == 'COMPLETED'))
        fact, value = lesson(move)
        story.append(f'{fact} {value}')
        ids.append(move['event_id'])
    for skill in ranked:
        if len(story) >= 3:
            break
        ev = evidence(skill)
        if ev['event_id'] in ids:
            continue
        fact, value = skill_copy(skill, by_id[ev['event_id']])
        story.append(f'{fact} {value}')
        ids.append(ev['event_id'])
        if len(story) == 3:
            break
    goal = next((e for e in events if len(goals) <= 1 and e['canonical_event_type'] == 'GOAL'
                 and e['event_id'] not in ids and bound(e)['proof_verified']), None)
    if goal:
        story.append(lesson(goal)[0])
        ids.append(goal['event_id'])
    explanation = (f'Your strongest qualities here are {qualities}. Keep building these into your game.'
                   if top else 'Use the moments in your video to choose a training goal with your coach.')
    good_news = 'Choose one of these moments, practise its next action and take it into your next match.'
    full['parent_summary'] = {'headline': 'Your football strengths', 'paragraphs': story, 'good_news': good_news}
    view['parentSummary'] = {'headline': 'Your football strengths', 'paragraphs': story, 'goodNews': good_news}
    full['executive_summary'] = ' '.join(story)
    full['final_summary'] = full['executive_summary']
    full['coach_notes'] = story
    pub['narrative'] = {'event_ids': ids, 'score_explanation': explanation}
    doc['score_context']['overall']['line'] = explanation
    full['evidence_quality_note'] = 'Your report focuses on your football in this video. Choose your next training goal with your coach.'
    pub['assessment_note'] = full['evidence_quality_note']
    # Preserve detailed score/coverage calculations in pub.score, outside public prose.
    pub['score']['label'] = 'Your score in this video'
    pub['player_story'] = opening
    pub['training_focus'] = practice(top[0]['key'])[0] if top else 'Choose one action to practise with your coach.'
    ref_note = "ScoutMePlay coaching guide for the skills shown at your age; academy labels describe these skills, not a club selection decision."
    for ref in [pub['score'].get('comparison')] + [s.get('comparison') for s in skills]:
        if ref:
            ref['note'] = ref_note
    view['topStrengths'] = []
    for skill in ranked[:4]:
        ev = evidence(skill)
        fact, value = skill_copy(skill, by_id[ev['event_id']])
        c = comments.get(ev['event_id'], {})
        view['topStrengths'].append({'name': skill['label'], 'score': skill['score'], 'category': skill['category'],
            'note': f'{fact} {value}', 'observation': fact, 'teamContribution': value,
            'timestamp': ev['timestamp'], 'eventId': ev['event_id'], 'evidenceId': ev.get('evidence_id'),
            'proofable': True, 'thumb': c.get('frame_url') if c.get('proof_frame_verified') else None,
            'thumbVerified': c.get('proof_frame_verified') is True})
    # Priorities build on the player's actual football, rather than treating the
    # lowest numbers as weaknesses. Prefer on-ball choices and distinct moments.
    order = ('passing', 'dribbling', 'ball_control', 'shooting', 'first_touch', 'one_v_one', 'decision_making',
             'body_control', 'balance', 'scanning', 'off_ball_movement')
    candidates = sorted(available, key=lambda s: (order.index(s['key']) if s['key'] in order else len(order), -s['score']))
    priorities, used = [], set()
    for skill in candidates:
        ev = next((e for e in skill['evidence'] if e['proof_verified'] and e['event_id'] not in used), None)
        if ev is None:
            continue
        used.add(ev['event_id'])
        fact, _ = skill_copy(skill, by_id[ev['event_id']])
        focus, drill = practice(skill['key'])
        if skill['key'] == 'passing' and len(skill['evidence']) == 1:
            focus = 'Build on your pass by helping the receiver play forward.'
        priorities.append({'name': skill['label'], 'score': skill['score'], 'issue': fact,
            'how_to_improve': drill, 'focus': focus, 'event_id': ev['event_id'], 'evidence': [ev]})
        if len(priorities) == 3:
            break
    full['development_priorities_detailed'] = priorities
    if priorities:
        pub['training_focus'] = priorities[0]['focus']
    view['devPriorities'] = [{'name': p['name'], 'score': p['score'], 'issue': p['issue'],
                             'howTo': p['how_to_improve']} for p in priorities]
    # Keep the original snapshot grid, selecting a range of football qualities.
    selected = list(pub['key_actions'][:4])
    for skill in ranked:
        ev = evidence(skill)
        if len(selected) == 4:
            break
        if ev['event_id'] not in {a['event_id'] for a in selected}:
            e = by_id[ev['event_id']]
            selected.append({**bound(e), 'title': skill['label'], 'summary': lesson(e)[0]})
    full['snapshot_moments'], view['snapshotMoments'] = [], []
    for key, action in zip(('strength', 'noticed', 'hidden', 'develop'), selected):
        e = by_id[action['event_id']]
        c = comments.get(e['event_id'], {})
        supporting_skill = next((s for s in ranked if s['label'] == action['title']), None)
        fact, value = skill_copy(supporting_skill, e) if supporting_skill else lesson(e)
        thumb = c.get('frame_url') if c.get('proof_frame_verified') else None
        full['snapshot_moments'].append({**bound(e), 'key': key, 'label': 'Verified action',
            'title': action['title'], 'desc': f'{fact} {value}', 'frame_url': thumb})
        view['snapshotMoments'].append({'key': key, 'label': 'Verified action', 'title': action['title'],
            'desc': f'{fact} {value}', 'timestamp': action['timestamp'], 'thumb': thumb, 'annot': 'circle',
            'eventId': e['event_id'], 'evidenceId': action.get('evidence_id')})
    for row in full['action_timeline']:
        row['description'] = ' '.join(lesson(by_id[row['event_id']]))
    for row in view['actionTimeline']:
        row['description'] = ' '.join(lesson(by_id[row['eventId']]))
    for action in pub['key_actions']:
        fact, value = lesson(by_id[action['event_id']])
        action.update(description=f'{fact} {value}', summary=fact, football_value=value,
                      learning_focus=pub['training_focus'])
    # Existing stat rows remain the same size and number. Football contributions
    # replace internal action-segment and empty duel classifications.
    for row in view['matchStats']:
        if row['label'] == 'Total Actions':
            row.update(label='Ball Carries', value=sum(e['canonical_event_type'] == 'DRIBBLE' for e in events))
        elif row['label'] == 'Duels Observed':
            row.update(label='Ball Recoveries', value=sum(e['canonical_event_type'] == 'RECOVERY' for e in events))
    pub['stats_definitions'] = 'Figures refer to this video. Shots include goals; key passes set up a teammate\'s shot. Ball carries are runs with the ball, not a count of defenders beaten.'
    for s in doc['score_meaning']['skills']:
        if s['key'] not in PRACTICE:
            continue
        skill = next(row for row in skills if row['key'] == s['key'])
        fact, value = skill_copy(skill, by_id[s['evidence']['event_id']])
        s['lines'] = [f'{fact} {value}']
        s['evidence']['what'] = fact
        s['looks_for'] = practice(s['key'])[0]
        s['next_level'] = practice(s['key'])[1]
        s['position_why'] = VALUE.get(by_id[s['evidence']['event_id']]['canonical_event_type'], value)
        s['angles'] = {}
    doc['score_meaning']['position_line'] = ref_note
    full['grow_your_game'] = {'lessons': [], 'homework_plan': []}
    for skill in top:
        ev = evidence(skill)
        fact, value = skill_copy(skill, by_id[ev['event_id']])
        focus, drill = practice(skill['key'])
        full['grow_your_game']['lessons'].append({'topic_id': skill['key'], 'title': skill['label'],
            'category': skill['category'], 'moments': [ev], 'what_happened': fact,
            'why_it_matters': value, 'what_scouts_look_for': focus, 'personal_advice': drill,
            'simple_explanation': value, 'age_benchmark': ref_note})
    if priorities:
        p = priorities[0]
        full['snapshot'] = {'biggest_strength': top[0]['label'], 'hidden_talent': qualities,
            'biggest_development_area': p['focus'], 'overall_progress_note': 'Take your training focus into your next match and review it with your coach.'}
        full['development_roadmap'] = {'now': p['focus'], 'three_months': 'Practise this focus in small-sided games.',
            'six_months': 'Look for the same quality against different opponents.',
            'twelve_months': 'Choose a new challenge with your coach as your game develops.'}
    if top:
        full['parent_value_metrics'] = {'involvement': {'quality': top[0]['label'],
            'note': lesson(by_id[evidence(top[0])['event_id']])[1]}, 'top_minutes': []}
    full['match_stats']['coverage_note'] = 'Your goals, passes and carries from this video, ready to review with your coach.'
    package = full.get('parents_package') or {}
    _repair_home_instructions(package)
    if package.get('message_to_player'):
        package['message_to_player']['body'] = f'{opening} {pub["training_focus"]} Keep enjoying your football.'
    full['parents_package'] = package
    pub['review']['analysis_status'] = 'Your report is ready'
