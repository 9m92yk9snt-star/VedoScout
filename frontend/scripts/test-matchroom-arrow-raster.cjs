// Optional raster regression: NODE_PATH must resolve react, react-dom, esbuild
// and @resvg/resvg-js. No application/runtime dependency is introduced.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {transformSync}=require('esbuild'),{Resvg}=require('@resvg/resvg-js');
const source=fs.readFileSync(path.join(__dirname,'../src/components/report-v2/MatchRoomPlayer.jsx'),'utf8');
const svg=source.slice(source.indexOf('<svg className="mr-graphics"'),source.indexOf('</svg>')+6);
const calculations=source.slice(source.indexOf('  const arrowPixels'),source.indexOf('  const observation'));
assert.ok(svg.startsWith('<svg')&&calculations.includes('arrowUnit'));
const code=`import React from 'react';import{renderToStaticMarkup}from'react-dom/server';export function render(width,height,trail,polygons){const ratio=width/height,bounds={width,height},id='test',mark=null,depth=null,ellipsePolygons=[];const arrow={ballTrail:trail,foreground:{polygons},opacity:1,media_ms:1234};${calculations}return renderToStaticMarkup(${svg});}`;
const m={exports:{}};new Function('require','module','exports',transformSync(code,{loader:'jsx',format:'cjs'}).code)(require,m,m.exports);
function raster(w,h,trail,polygons=[]){
 const original=JSON.stringify(trail),markup=m.exports.render(w,h,trail,polygons).replace('<svg ',`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" `);
 assert.equal(JSON.stringify(trail),original);
 const image=new Resvg(markup).render(),pixels=image.pixels;return {alpha:(x,y)=>pixels[(y*w+x)*4+3],width:w,height:h};
}
function headHeight(a,end){let min=a.height,max=-1;const pixels=a.alpha;
 for(let y=0;y<a.height;y++)for(let x=Math.max(0,end-15);x<Math.min(a.width,end+3);x++)if(pixels(x,y)>180){min=Math.min(min,y);max=Math.max(max,y);}
 return max<0?0:max-min+1;
}
const trail=[[.2,.5],[.8,.5]];const mobile=raster(360,640,trail),desktop=raster(1080,608,trail);
const mh=headHeight(mobile,288),dh=headHeight(desktop,864);assert.ok(mh>=7&&mh<=10);assert.equal(mh,dh);
assert.ok(mobile.alpha(120,320)>180);assert.ok(desktop.alpha(360,304)>180);
const short=raster(360,640,[[.45,.5],[.48,.5]]);assert.ok(headHeight(short,173)<=4);
const masked=raster(360,640,trail,[[[.45,.45],[.55,.45],[.55,.55],[.45,.55]]]);
for(let y=315;y<=325;y++)for(let x=166;x<=194;x++)assert.equal(masked.alpha(x,y),0,'mask must remove glow as well as shaft');
const diagonal=raster(360,640,[[.2,.7],[.8,.3]]);assert.ok(diagonal.alpha(180,320)>180);
console.log(JSON.stringify({status:'PASS',cases:5,renderer:'resvg',mobile_head_opaque_height_px:mh,desktop_head_opaque_height_px:dh,masked_interior_alpha:0,browser_test:false}));
