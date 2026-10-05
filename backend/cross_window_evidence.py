"""Join measured overlap, never local ID names or semantic event labels."""
from copy import deepcopy
import hashlib
import math

from goal_review_scheduler import _iou

BODY_KEYS = {'player_track_id', 'strike_actor_track_id', 'local_track_id', 'track_id',
             'before_holder', 'after_holder', 'from_track', 'to_track', 'receiver_track_id'}
BODY_LIST_KEYS = {'candidate_local_track_ids', 'player_candidate_track_ids'}
ENTITY_KEYS = {'touch_id', 'strike_id', 'contact_id'}


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _actual(row):
    return _num(row.get('media_ms')) and row.get('time_authority') == 'ACTUAL_MEDIA_PTS' \
        and not row.get('used_fallback') and not row.get('cut_barrier')


def _ball(row):
    return _actual(row) and row.get('proof_eligible') is True \
        and row.get('state') in {'MEASURED', 'MEASURED_REACQUISITION'}


def _pair(left, right):
    lw, rw = left.get('window') or {}, right.get('window') or {}
    if any(not _num(w.get(k)) for w in (lw, rw) for k in ('start_ms', 'end_ms')) \
            or any(w['end_ms'] <= w['start_ms'] for w in (lw, rw)):
        return None, 'INVALID_WINDOW_BOUNDS'
    if not lw.get('scene_id') or lw.get('scene_id') != rw.get('scene_id'):
        return None, 'SCENE_BOUNDARY'
    for key in ('sha256','video_sha256','source_video_sha256'):
        a,b=(left.get('source_video') or {}).get(key),(right.get('source_video') or {}).get(key)
        if a and b and a!=b:
            return None, 'SOURCE_VIDEO_MISMATCH'
    lo, hi = max(lw.get('start_ms', 0), rw.get('start_ms', 0)), min(lw.get('end_ms', 0), rw.get('end_ms', 0))
    if hi - lo < 50:
        return None, 'NO_MEASURED_OVERLAP'
    frames = []
    for trace in (left, right):
        rows = [f for f in trace.get('decoded_frames') or [] if _num(f.get('media_ms')) and lo <= f['media_ms'] <= hi]
        if not rows or any(not _actual(f) or f.get('scene_id') != lw['scene_id'] for f in rows):
            return None, 'OVERLAP_FRAME_BARRIER'
        frames.append({f['media_ms']: f for f in rows})
    common = sorted(set(frames[0]) & set(frames[1]))
    if len(common) < 2 or common[-1] - common[0] < 50 or any(b-a > 80 for a,b in zip(common, common[1:])):
        return None, 'ACTUAL_FRAME_ALIGNMENT_MISSING'
    balls = [{b['media_ms']: b for b in t.get('ball_trajectory') or [] if _ball(b)} for t in (left, right)]
    matching = [ms for ms in common if ms in balls[0] and ms in balls[1]
                and _iou(balls[0][ms].get('box'), balls[1][ms].get('box')) >= .75]
    if len(matching) < 2 or matching[-1] - matching[0] < 50:
        return None, 'ACTIVE_BALL_OVERLAP_UNVERIFIED'
    if any(ms in balls[0] and ms in balls[1] and _iou(balls[0][ms].get('box'), balls[1][ms].get('box')) < .75 for ms in common):
        return None, 'CONFLICTING_OVERLAP_BALLS'
    matches, rejected = {}, set()
    for ms in common:
        a, b = [frames[i][ms].get('players') or [] for i in (0, 1)]
        for p in a:
            pid = p.get('local_track_id')
            if not pid or p.get('association_state') != 'VERIFIED_LOCAL':
                continue
            candidates = [q for q in b if q.get('association_state') == 'VERIFIED_LOCAL' and _iou(p.get('box'), q.get('box')) >= .75]
            if len(candidates) != 1:
                rejected.add(pid); continue
            q = candidates[0]
            if any(other is not p and _iou(other.get('box'), q.get('box')) >= .25 for other in a) \
                    or any(other is not q and _iou(other.get('box'), p.get('box')) >= .25 for other in b):
                rejected.add(pid); continue
            if p.get('team') in {'target_team', 'opponent'} and q.get('team') in {'target_team', 'opponent'} and p['team'] != q['team']:
                rejected.add(pid); continue
            matches.setdefault((pid, q.get('local_track_id')), []).append(ms)
    bodies = [(a,b) for (a,b), times in matches.items() if a not in rejected and b and len(times)>=2 and times[-1]-times[0]>=50]
    bodies = [(a,b) for a,b in bodies if sum(x==a for x,y in bodies)==1 and sum(y==b for x,y in bodies)==1]
    if not bodies:
        return None, 'BODY_OVERLAP_UNVERIFIED'
    for ms in common:
        a,b=[frames[i][ms].get('global_target') or {} for i in (0,1)]
        if all(t.get('status')=='VERIFIED' and t.get('proof_eligible') is True for t in (a,b)) \
                and (a.get('local_track_id'),b.get('local_track_id')) not in bodies:
            return None, 'CONFLICTING_TARGET_IDENTITIES'
    return {'left': left['trace_id'], 'right': right['trace_id'], 'scene_id': lw['scene_id'],
            'media_ms': matching, 'body_pairs': bodies}, None


def _anchor_bound(strike, trace, links):
    a = strike.get('active_ball_anchor') or {}
    valid = bool(_ball(a) and a.get('remote_spare_ball_used') is False
                and a.get('source') == 'VERIFIED_RELEASE_CONTACT_BALL_AFTER'
                and any(_ball(row) and row['media_ms'] == a['media_ms'] and _iou(row.get('box'), a.get('box')) >= .75
                        for row in trace.get('ball_trajectory') or []))
    if not valid:
        return False
    points = [ms for link in links if trace['trace_id'] in {link['left'],link['right']} for ms in link['media_ms']]
    if not points:
        return False
    lo,hi=min([a['media_ms'],*points]),max([a['media_ms'],*points])
    path=sorted([row for row in trace.get('ball_trajectory') or [] if _num(row.get('media_ms')) and lo<=row['media_ms']<=hi],key=lambda r:r['media_ms'])
    if any(not _actual(f) or f.get('scene_id') != trace['window']['scene_id']
           for f in trace.get('decoded_frames') or [] if _num(f.get('media_ms')) and lo<=f['media_ms']<=hi):
        return False
    return bool(path and path[0]['media_ms']==lo and path[-1]['media_ms']==hi
                and all(_ball(r) for r in path) and all(b['media_ms']-a['media_ms']<=80 for a,b in zip(path,path[1:])))


def build(physical):
    traces = [t for t in (physical or {}).get('traces') or [] if isinstance(t, dict) and t.get('trace_id')]
    by_id = {t['trace_id']: t for t in traces}
    parent = {}
    def root(node):
        parent.setdefault(node,node)
        while parent[node] != node: node=parent[node]
        return node
    links, rejected = [], []
    for i,left in enumerate(traces):
        for right in traces[i+1:]:
            link, reason = _pair(left,right)
            if link is None:
                rejected.append({'left':left['trace_id'],'right':right['trace_id'],'reason':reason}); continue
            trial = dict(parent)
            for a,b in link['body_pairs']:
                x,y=root((link['left'],a)),root((link['right'],b)); parent[y]=x
            clusters={}
            for node in list(parent): clusters.setdefault(root(node),[]).append(node)
            if any(len({node[0] for node in nodes}) != len(nodes) for nodes in clusters.values()):
                parent.clear(); parent.update(trial)
                rejected.append({'left':left['trace_id'],'right':right['trace_id'],'reason':'BODY_MAPPING_FORK'}); continue
            links.append(link)
    groups = [{tid} for tid in by_id]
    for link in links:
        touching=[g for g in groups if link['left'] in g or link['right'] in g]
        joined=set().union(*touching)
        groups=[g for g in groups if g not in touching]+[joined]
    contexts=[]
    for group in groups:
        if len(group)==1:
            contexts.append(deepcopy(by_id[next(iter(group))])); continue
        sources=sorted(group)
        scope_links=[l for l in links if l['left'] in group and l['right'] in group]
        def rewrite(value, tid, key=None):
            if isinstance(value,dict): return {k:rewrite(v,tid,k) for k,v in value.items()}
            if isinstance(value,list): return [rewrite(v,tid,key if key not in BODY_LIST_KEYS else 'local_track_id') for v in value]
            if isinstance(value,str) and key in BODY_KEYS: return 'body:'+repr(root((tid,value)))
            if isinstance(value,str) and key in ENTITY_KEYS: return tid+':'+value
            return deepcopy(value)
        merged={'trace_id':'joined_'+hashlib.sha256('|'.join(sources).encode()).hexdigest()[:20],
                'window':{'scene_id':by_id[sources[0]]['window']['scene_id'],
                          'start_ms':min(by_id[t]['window']['start_ms'] for t in sources),
                          'end_ms':max(by_id[t]['window']['end_ms'] for t in sources)},
                'decoded_frames':[], 'touch_graph':{'touches':[]}, 'strike_evidence':[], 'outcome_evidence':[],
                'source_trace_ids':sources, 'cross_window_links':scope_links}
        for tid in sources:
            tr=by_id[tid]
            merged['decoded_frames'].extend(rewrite(tr.get('decoded_frames') or [],tid))
            merged['touch_graph']['touches'].extend(rewrite((tr.get('touch_graph') or {}).get('touches') or [],tid))
            for strike in tr.get('strike_evidence') or []:
                s=rewrite(strike,tid); s.update(native_source_trace_id=tid,native_source_strike_id=strike.get('strike_id'),
                                              cross_window_ball_anchor_eligible=_anchor_bound(strike,tr,scope_links))
                merged['strike_evidence'].append(s)
            merged['outcome_evidence'].extend(rewrite(tr.get('outcome_evidence') or [],tid))
        contexts.append(merged)
    return {'contexts':contexts,'links':links,'rejected':rejected}
