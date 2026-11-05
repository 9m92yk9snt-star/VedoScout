const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const model=import('data:text/javascript;base64,'+fs.readFileSync(path.join(__dirname,'../src/components/report-v2/matchRoomModel.js')).toString('base64'));
const row=(t,x=.5,span=.08)=>({media_ms:t,ground:[x,.7],player_width:.1,stance_bounds:[x-span/2,x+span/2],sourceFrameContour:true,contourTrack:true,confidence:.9,foreground:{media_ms:t,polygons:[[[.4,.5],[.6,.5],[.5,.7]]]}});
const room=tracks=>({samples:[],tracks,sourcePositionsOnly:true});
test('wide stride enlarges ring; seeking is deterministic and masks stay exact',async()=>{
 const {graphicsAt}=await model;
 const rows=Array.from({length:61},(_,i)=>row(i*17,.5, i>=25&&i<=35?.22:.08));
 const r=room([rows]);const original=JSON.stringify(rows);
 const marks=rows.map(s=>graphicsAt(r,s.media_ms));
 assert.ok(marks[30].ellipseRadius>marks[0].ellipseRadius*1.3);
 for(let i=rows.length-1;i>=0;i--){assert.deepEqual(graphicsAt(r,rows[i].media_ms),marks[i]);assert.equal(marks[i].foreground,rows[i].foreground);}
 assert.equal(JSON.stringify(rows),original);
 assert.ok(marks[36].ellipseRadius>marks[0].ellipseRadius,'no abrupt contraction after stride');
});
test('unknown frames remain hidden and separate runs cannot pull each other',async()=>{
 const {graphicsAt}=await model;
 const a=[row(0,.2),row(17,.2),row(34,.2)];
 const b=[row(102,.8),row(119,.8),row(136,.8)];
 const combined=room([a,b]);
 assert.equal(graphicsAt(combined,68),null);
 assert.deepEqual(graphicsAt(combined,34),graphicsAt(room([a]),34));
 assert.deepEqual(graphicsAt(combined,102),graphicsAt(room([b]),102));
});
