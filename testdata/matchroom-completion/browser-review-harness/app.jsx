import React from 'react';import{createRoot}from'react-dom/client';import{MatchRoomPlayer}from './MatchRoomPlayer';import data from './data.json';
const fixture=structuredClone(data);fixture.playback_status='VERIFIED'; // isolated render fixture, not approval/writeback
const comment={event_id:data.event_id,source_video_sha256:data.source_video_sha256,evidence_time_ms:51000,match_room:{version:1,event_id:data.event_id,source_video_sha256:data.source_video_sha256,coordinate_space:'FULL_FRAME_NORMALIZED',start_ms:49415,end_ms:51600,samples:[],stops:[{media_ms:51500,label:'Afslutning'}],reviewed_direction:fixture}};
window.reviewFixture=comment;window.sourceStatus=data.playback_status;
createRoot(document.getElementById('root')).render(<MatchRoomPlayer proof={{ts:50,comment,playerName:'Visuel prøve — rekonstrueret aflevering'}} videoUrl='/source.mp4' skill={{label:'ASSIST',lines:['Rekonstrueret afleveringsretning.']}} onClose={()=>{}}/>);
