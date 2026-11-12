import {loadGraphics} from './matchRoomAsset';
import {webcrypto} from 'crypto';
import {TextDecoder} from 'util';
beforeEach(()=>{Object.defineProperty(global,'crypto',{value:webcrypto,configurable:true});global.TextDecoder=TextDecoder;});
afterEach(()=>{delete global.fetch;});
async function fixture(graphics={version:1,event_id:'e',source_video_sha256:'s',tracking:{samples:[{x:.123456789}]}}) {
 const bytes=Uint8Array.from(Buffer.from(JSON.stringify(graphics))).buffer;
 const sha=Buffer.from(await webcrypto.subtle.digest('SHA-256',bytes)).toString('hex');
 global.fetch=jest.fn(async()=>({ok:true,arrayBuffer:async()=>bytes}));
 return {event_id:'e',source_video_sha256:'s',match_room:{version:1,graphics_asset:{url:'/api/graphics',sha256:sha,bytes:bytes.byteLength}}};
}
test('loads full precision graphics with verified source binding',async()=>{
 const comment=await fixture();const result=await loadGraphics(comment);
 expect(result.match_room.tracking.samples[0].x).toBe(.123456789);
 expect(comment.match_room.graphics_asset).toBeDefined();
});
test('rejects wrong source even with valid file checksum',async()=>{
 const comment=await fixture({version:1,event_id:'other',source_video_sha256:'s'});
 await expect(loadGraphics(comment)).rejects.toThrow('GRAPHICS_SOURCE_MISMATCH');
});
test('rejects corrupt content and HTTP failures',async()=>{
 const comment=await fixture();comment.match_room.graphics_asset.sha256='wrong';
 await expect(loadGraphics(comment)).rejects.toThrow('GRAPHICS_CHECKSUM_MISMATCH');
 global.fetch=jest.fn(async()=>({ok:false}));
 await expect(loadGraphics(comment)).rejects.toThrow('GRAPHICS_DOWNLOAD_FAILED');
});
