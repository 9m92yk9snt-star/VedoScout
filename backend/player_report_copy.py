"""Player-facing coaching copy from saved actions; no model calls or new findings.

The action is a retained observation. Football value and practice are coaching
advice, never extra detected actions or claims about academy selection.
"""

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
    'GOAL': 'Finishing after a carry makes your forward runs a direct threat.',
    'SHOT': 'Your finish gives the attack a chance to score.',
    'ASSIST': 'Your pass helps a teammate turn the chance into a goal.',
    'RECOVERY': 'Winning possession gives your team another chance to build.',
    'DUEL': 'Competing for the ball puts pressure on your opponent.',
    'TACKLE': 'A well-timed challenge can stop an opponent advancing.',
    'INTERCEPTION': 'Reading a pass can help your team regain possession.',
    'RUN': 'Your movement can give the next attack an option.',
}


def action_lesson(event):
    kind = event.get('canonical_event_type')
    text = ' '.join(event.get('details') or []).lower()
    outcome = event.get('canonical_outcome')
    if kind == 'GOAL':
        fact = 'You finish your dribble with a goal.' if 'dribble' in text else 'You finish the attack with a goal.'
    elif kind == 'ASSIST':
        fact = "Your final pass sets up a teammate's goal."
    elif kind == 'DRIBBLE':
        if 'shield' in text or 'protect' in text:
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
        fact = 'You regain the ball and give your team possession.'
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
    return fact, VALUE.get(kind, 'Watch how the next phase of play develops.')


def practice(key):
    focus, drill, target = PRACTICE[key]
    return focus, f'{drill} {target}'


def skill_lesson(skill, event):
    """Explain the football quality, rather than repeating an event description."""
    fact, value = action_lesson(event)
    key, kind = skill['key'], event.get('canonical_event_type')
    text = ' '.join(event.get('details') or []).lower()
    if key == 'ball_control' and kind == 'DRIBBLE':
        fact = 'You keep the ball within reach as you work through pressure.'
        value = 'That gives you a chance to choose your next move while staying on the ball.'
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
        fact = 'You take on a direct challenge while carrying the ball.'
        value = 'Handling that pressure can help you progress past your immediate opponent.'
    return fact, value


def apply_player_copy(doc, events, skills, bound):
    """Keep existing card fields/geometry; replace diagnostics with coaching."""
    full, pub = doc['full_report'], doc['report_publication']
    view = pub['view']
    by_id = {e['event_id']: e for e in events}
    comments = {c.get('event_id'): c for c in full.get('video_comments', [])}
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
    for skill in ranked:
        ev = evidence(skill)
        if ev['event_id'] in ids:
            continue
        fact, value = skill_lesson(skill, by_id[ev['event_id']])
        story.append(f'{fact} {value}')
        ids.append(ev['event_id'])
        if len(story) == 3:
            break
    goal = next((e for e in events if e['canonical_event_type'] == 'GOAL'
                 and e['event_id'] not in ids and bound(e)['proof_verified']), None)
    if goal:
        story.append(action_lesson(goal)[0])
        ids.append(goal['event_id'])
    explanation = (f'Your strongest qualities here are {qualities}. Keep building these into your game.'
                   if top else 'Use the moments in your video to choose a training goal with your coach.')
    full['parent_summary'] = {'headline': 'Your football strengths', 'paragraphs': story, 'good_news': explanation}
    view['parentSummary'] = {'headline': 'Your football strengths', 'paragraphs': story, 'goodNews': explanation}
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
        fact, value = skill_lesson(skill, by_id[ev['event_id']])
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
        fact, _ = action_lesson(by_id[ev['event_id']])
        focus, drill = practice(skill['key'])
        priorities.append({'name': skill['label'], 'score': skill['score'], 'issue': fact,
            'how_to_improve': drill, 'focus': focus, 'event_id': ev['event_id'], 'evidence': [ev]})
        if len(priorities) == 3:
            break
    full['development_priorities_detailed'] = priorities
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
            selected.append({**bound(e), 'title': skill['label'], 'summary': action_lesson(e)[0]})
    full['snapshot_moments'], view['snapshotMoments'] = [], []
    for key, action in zip(('strength', 'noticed', 'hidden', 'develop'), selected):
        e = by_id[action['event_id']]
        c = comments.get(e['event_id'], {})
        supporting_skill = next((s for s in ranked if s['label'] == action['title']), None)
        fact, value = skill_lesson(supporting_skill, e) if supporting_skill else action_lesson(e)
        thumb = c.get('frame_url') if c.get('proof_frame_verified') else None
        full['snapshot_moments'].append({**bound(e), 'key': key, 'label': 'Verified action',
            'title': action['title'], 'desc': f'{fact} {value}', 'frame_url': thumb})
        view['snapshotMoments'].append({'key': key, 'label': 'Verified action', 'title': action['title'],
            'desc': f'{fact} {value}', 'timestamp': action['timestamp'], 'thumb': thumb, 'annot': 'circle',
            'eventId': e['event_id'], 'evidenceId': action.get('evidence_id')})
    for row in full['action_timeline']:
        row['description'] = ' '.join(action_lesson(by_id[row['event_id']]))
    for row in view['actionTimeline']:
        row['description'] = ' '.join(action_lesson(by_id[row['eventId']]))
    for action in pub['key_actions']:
        fact, value = action_lesson(by_id[action['event_id']])
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
        fact, value = action_lesson(by_id[s['evidence']['event_id']])
        skill = next(row for row in skills if row['key'] == s['key'])
        fact, value = skill_lesson(skill, by_id[s['evidence']['event_id']])
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
        fact, value = action_lesson(by_id[ev['event_id']])
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
            'note': action_lesson(by_id[evidence(top[0])['event_id']])[1]}, 'top_minutes': []}
    full['match_stats']['coverage_note'] = 'Your goals, passes and carries from this video, ready to review with your coach.'
    package = full.get('parents_package') or {}
    if package.get('message_to_player'):
        package['message_to_player']['body'] = f'{opening} {pub["training_focus"]} Keep enjoying your football.'
    full['parents_package'] = package
    pub['review']['analysis_status'] = 'Your report is ready'
