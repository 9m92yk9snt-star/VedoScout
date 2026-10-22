"""Player-facing explanations from retained facts; no model or network calls."""
from copy import deepcopy

import pytest
from player_report_copy import action_lesson, skill_lesson
from report_fact_authority import apply, NEUTRAL
from test_report_publication import example, publish_report


def turn():
    return {'event_id': 'turn', 'canonical_event_type': 'DRIBBLE', 'canonical_outcome': 'COMPLETED',
            'canonical_ms': 6000, 'end_ms': 9000, 'actor_visual_id': 'play:p1', 'details': [],
            'movement_observations': [{'decision': 'SUPPORTED', 'type': 'PROTECTIVE_TURN'},
                                      {'decision': 'SUPPORTED', 'type': 'DIRECTION_REVERSAL'}]}


def test_combined_turn_and_following_pass_form_a_concrete_player_lesson():
    event = turn()
    following = {'canonical_event_type': 'PASS', 'canonical_outcome': 'COMPLETED',
                 'canonical_ms': 9300, 'actor_visual_id': 'play:p1'}
    fact, value = action_lesson(event, [following])
    assert 'change direction again' in fact and 'find a teammate' in fact
    assert 'next team action' in value


@pytest.mark.parametrize('change', [
    {'actor_visual_id': 'play:p2'}, {'canonical_outcome': 'UNKNOWN'},
    {'canonical_ms': 14000}, {'canonical_ms': 8000},
])
def test_another_player_unseen_outcome_or_distant_pass_cannot_enter_the_lesson(change):
    following = {'canonical_event_type': 'PASS', 'canonical_outcome': 'COMPLETED',
                 'canonical_ms': 9300, 'actor_visual_id': 'play:p1', **change}
    assert 'find a teammate' not in action_lesson(turn(), [following])[0]


def test_goal_copy_distinguishes_close_challenge_from_finishing_a_carry():
    close = {'canonical_event_type': 'GOAL', 'details': ['Close-range finish while challenged.']}
    carry = {'canonical_event_type': 'GOAL', 'details': ['After a pressured dribble, shoots and scores.']}
    assert 'under pressure' in action_lesson(close)[0]
    assert 'forward carry' in action_lesson(carry)[0]
    plain = action_lesson({'canonical_event_type': 'GOAL', 'details': []})
    assert 'carry' not in ' '.join(plain)
    negative = action_lesson({'canonical_event_type': 'GOAL',
                             'details': ['An unchallenged close-range goal. No dribble preceded it.']})
    assert 'pressure' not in negative[0] and 'carry' not in negative[0]


def test_carry_under_pressure_does_not_become_beaten_opponents_in_1v1_explanation():
    report = example()
    event = report['canonical_events']['events'][0]
    event.update(canonical_event_type='DRIBBLE', canonical_outcome='COMPLETED',
        details=['Carries under pressure. No count of beaten opponents is established.'],
        movement_observations=turn()['movement_observations'])
    report['full_report']['technical']['one_v_one'] = {
        'score': 8, 'cannot_evaluate': False,
        'notes': 'Beats three players, showing elite talent.',
        'why_this_score': 'Highly effective at beating three successive defenders.',
        'verdict': 'Three players beaten.',
        'evidence': deepcopy(report['full_report']['technical']['dribbling']['evidence'])}
    result = publish_report(report)
    skill = result['full_report']['technical']['one_v_one']
    assert skill['score'] == 8
    for key in ('notes', 'why_this_score', 'verdict'):
        assert not any(word in skill[key].lower() for word in ('beating', 'beaten', 'three players', 'elite talent'))
    assert 'changing pace' in skill['why_this_score']
    assert result == publish_report(result)


def test_one_pass_is_a_training_starting_point_without_becoming_a_weakness():
    report = example()
    event = report['canonical_events']['events'][0]
    event.update(canonical_event_type='PASS', canonical_outcome='COMPLETED', details=['A completed pass.'])
    report['full_report']['technical']['passing'] = {
        'score': 6, 'cannot_evaluate': False,
        'why_this_score': 'Lacks evidence of advanced ability.',
        'evidence': deepcopy(report['full_report']['technical']['dribbling']['evidence'])}
    result = publish_report(report)
    skill = result['full_report']['technical']['passing']
    assert skill['score'] == 6
    assert 'example to build on' in skill['why_this_score']
    assert 'lacks' not in skill['why_this_score'].lower()
    assert result['full_report']['development_priorities_detailed'][0]['focus'].startswith('Build on your pass')


def test_training_command_preserves_both_feet_without_claiming_match_foot():
    command = 'Pass the ball against the wall with your right foot and control the rebound with your left.'
    full = {'parents_package': {'home_drills': [{'steps': [command]}],
                               'watch_together': 'He scored with his right foot.'}}
    result = apply(full, {'events': []})
    assert result['parents_package']['home_drills'][0]['steps'][0] == command
    assert result['parents_package']['watch_together'] == NEUTRAL


@pytest.mark.parametrize('claim', [
    'He passed with his right foot in the match.',
    'Pass with your right foot as you did in the video.',
    'Use your right foot like you used at 00:16.',
])
def test_match_claim_cannot_bypass_foot_evidence_by_being_inside_a_drill(claim):
    full = {'parents_package': {'home_drills': [{'steps': [claim]}]}}
    output = apply(full, {'events': []})['parents_package']['home_drills'][0]['steps'][0]
    assert 'right foot' not in output


def test_training_command_does_not_authorize_a_following_invented_goal():
    full = {'parents_package': {'home_drills': [{'steps': [
        'Pass with your right foot. You scored three goals in the match.']}]}}
    result = apply(full, {'events': []})
    assert result['parents_package']['home_drills'][0]['steps'][0] == 'Pass with your right foot.'


def test_saved_damaged_wall_drill_is_repaired_without_changing_facts_or_scores():
    report = example()
    report['full_report']['parents_package'] = {'home_drills': [{
        'name': 'Wall Ball', 'targets': 'First Touch', 'minutes': 10,
        'steps': ['Stand by a wall.', NEUTRAL, 'Repeat.']}]}
    original = deepcopy(report)
    result = publish_report(report)
    steps = result['full_report']['parents_package']['home_drills'][0]['steps']
    assert NEUTRAL not in steps and 'right foot' in steps[1]
    assert result['report_publication']['score']['value'] == 7.8
    assert report == original
    assert result == publish_report(result)
