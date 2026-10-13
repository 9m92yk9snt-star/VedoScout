"""Literal per-image shot/keeper/outside/possession observations, support only."""


def parse(rows, media_ms):
    empty={'status':'UNAVAILABLE','source':'INDEPENDENT_IMAGE_CONTEXT_OBSERVATIONS',
           'proof_eligible':False,'canonical_events_applied':0,'rows':[],
           'absence_proves_no_hidden_contact':False}
    if not isinstance(rows,list):return empty
    expected=set(range(1,len(media_ms)+1)); indexed={}
    for row in rows:
        if not isinstance(row,dict) or type(row.get('idx')) is not int or row['idx'] not in expected:
            return {**empty,'status':'INVALID_CONTEXT_RESPONSE'}
        if row['idx'] in indexed:return {**empty,'status':'INVALID_CONTEXT_RESPONSE'}
        indexed[row['idx']]=row
    result=[]
    directions={'IMAGE_LEFT','IMAGE_RIGHT','FRONT','UNKNOWN'}
    for idx,row in sorted(indexed.items()):
        def choice(key,allowed,default):
            value=row.get(key)
            return value if isinstance(value,str) and value in allowed else default
        confidence=choice('confidence',{'high','medium','low'},'low')
        keeper_tracked=row.get('same_goalkeeper_tracked') is True
        head_visible=row.get('head_visible') is True and keeper_tracked
        gloves_visible=row.get('gloves_visible') is True and keeper_tracked
        head=choice('head_direction',directions,'UNKNOWN') if head_visible else 'UNKNOWN'
        hands=choice('arms_gloves_direction',directions,'UNKNOWN') if gloves_visible else 'UNKNOWN'
        foot=choice('release_foot',{'LEFT','RIGHT'},'UNKNOWN') if row.get('foot_contact_visible') is True else 'UNKNOWN'
        outside=choice('active_ball_outside_posts',{'OBSERVED','NOT_VISIBLE','UNKNOWN'},'UNKNOWN')
        possession=choice('visible_possession',{'GOALKEEPER','OUTFIELD_PLAYER','NONE_VISIBLE','UNKNOWN'},'UNKNOWN')
        result.append({'idx':idx,'media_ms':media_ms[idx-1],'time_authority':'ACTUAL_MEDIA_PTS',
            'same_goalkeeper_tracked':keeper_tracked,'head_visible':head_visible,
            'gloves_visible':gloves_visible,'head_direction':head,'arms_gloves_direction':hands,
            'release_foot':foot,'active_ball_outside_posts':outside,'visible_possession':possession,
            'confidence':confidence,'proof_eligible':False})
    return {**empty,'status':'COMPLETED' if set(indexed)==expected else 'PARTIAL_RESPONSE','rows':result,
            'missing_media_ms':[media_ms[idx-1] for idx in sorted(expected-set(indexed))]}
