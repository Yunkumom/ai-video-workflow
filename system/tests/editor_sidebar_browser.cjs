// Run with an isolated Chrome CDP session on port 9237; synthetic media only.
const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{
const pages=await fetch('http://127.0.0.1:9237/json/list').then(r=>r.json());
const ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
await new Promise(r=>ws.onopen=r);let id=0;const pending=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
const send=(method,params={})=>new Promise(r=>{const i=++id;pending.set(i,r);ws.send(JSON.stringify({id:i,method,params}))});
const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.result?.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails));return r.result?.result?.value};
await send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__testing=true;window.fetch=async()=>({ok:true,json:async()=>{throw Error('Synthetic test')}});`});
await send('Page.navigate',{url:pathToFileURL(require('node:path').resolve('system/desktop/editor.html')).href});
for(let i=0;i<60;i++){if(await evaluate("typeof selectClip==='function'"))break;await new Promise(r=>setTimeout(r,50));}
const fixture=JSON.parse(require('node:child_process').execFileSync('python3',['-c','import json;from system.tests.test_editor_project import fixture;print(json.dumps(fixture()))'],{encoding:'utf8'}));
await evaluate(`doc=${JSON.stringify(fixture)};doc.media.source.kind='photo';doc.media.source.duration=100;doc.clips=Array.from({length:18},(_,i)=>({...clone(doc.clips[0]),id:'clip'+i,start:.81+i*.17,end:4.01+i*.17}));let offset=0;doc.cues=doc.clips.map((c,i)=>{let cue=makeCue('Caption '+i,offset+.1,offset+3);offset+=c.end-c.start;return cue});draw();`);
for(const [width,height] of [[1280,800],[1440,900]]){
 await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await evaluate('draw()');
 assert.equal(await evaluate("$('clips').querySelectorAll('video,img').length"),0,'no blank thumbnail area');
 assert.ok(await evaluate("$('clips').children[0].getBoundingClientRect().height<=60"),'compact rows');
 await evaluate(`setPlaying(false);$('clips').children[8].querySelector('.clip-open').click()`);
 assert.deepEqual(await evaluate('[selectedClip,sourceAt(time).i,playing]'),[8,8,false],'paused click selects correct boundary');
 assert.ok(await evaluate("$('cues').scrollTop>0"),'corresponding caption visible');
 assert.equal(await evaluate("$('videoTrack').querySelectorAll('.clipbar.selected').length"),1);
 await evaluate(`setPlaying(true);$('clips').children[3].querySelector('.clip-open').click()`);
 assert.deepEqual(await evaluate('[selectedClip,sourceAt(time).i,playing]'),[3,3,true],'playing click keeps playback');
 await new Promise(r=>setTimeout(r,100));assert.ok(await evaluate('time>9.6'),'clock advances from selected clip');
 await evaluate(`setPlaying(false);window.native=action=>window.lastNative=action;$('clips').children[5].querySelector('[data-a="insert"]').click()`);
 assert.deepEqual(await evaluate('[selectedClip,importingAfter,lastNative]'),[3,5,'import'],'insert does not navigate');
 await evaluate(`window.deleteSelectedClip=()=>window.deletedIndex=selectedClip;window.beforeDelete=time;$('clips').children[5].querySelector('[data-a="delete"]').click()`);
 assert.ok(await evaluate('deletedIndex===5&&time===beforeDelete'),'delete action does not seek');
 await evaluate(`$('mediaToggle').click()`);assert.equal(await evaluate("$('mediaToggle').getAttribute('aria-expanded')"),'false');
 await evaluate(`$('mediaToggle').click()`);assert.equal(await evaluate("$('mediaToggle').getAttribute('aria-expanded')"),'true');
}
// Real decoded video, same-source and cross-source jumps while paused/playing.
const video=require('node:child_process').execFileSync('ffmpeg',['-v','error','-f','lavfi','-i','testsrc2=s=160x90:r=30:d=8','-c:v','libx264','-pix_fmt','yuv420p','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'],{maxBuffer:4000000}).toString('base64');
await evaluate(`setPlaying(false);doc=${JSON.stringify(fixture)};doc.media.source.duration=8;doc.media.other={...doc.media.source};doc.clips=[{...clone(doc.clips[0]),start:.81,end:2.01},{...clone(doc.clips[0]),id:'second',start:4.43,end:6.33},{...clone(doc.clips[0]),id:'third',mediaId:'other',start:2.2,end:4.2}];doc.cues=[];loadedMedia='source';for(const name of ['video','backVideo'])$(name).src='data:video/mp4;base64,${video}';draw();`);
await new Promise(r=>setTimeout(r,500));
await evaluate(`$('clips').children[1].querySelector('.clip-open').click()`);await new Promise(r=>setTimeout(r,150));
assert.ok(await evaluate("!playing&&Math.abs($('video').currentTime-4.43)<.05&&sourceAt(time).i===1"),'decoded same-source jump');
await evaluate(`setPlaying(true);$('clips').children[0].querySelector('.clip-open').click()`);await new Promise(r=>setTimeout(r,250));
assert.ok(await evaluate("playing&&sourceAt(time).i===0&&$('video').currentTime>.81&&$('video').currentTime<2.01"),'decoded playback resumes at cut');
await evaluate(`setPlaying(false);$('clips').children[2].querySelector('.clip-open').click();for(const name of ['video','backVideo'])$(name).src='data:video/mp4;base64,${video}';`);await new Promise(r=>setTimeout(r,400));
assert.ok(await evaluate("!playing&&sourceAt(time).i===2&&Math.abs($('video').currentTime-2.2)<.05"),'metadata load preserves latest cross-source target');
await evaluate(`doc.media.source.kind='photo';doc.media.other.kind='photo';draw()`);
const shot=await send('Page.captureScreenshot',{format:'png'});require('node:fs').writeFileSync('/tmp/editor-sidebar-v7-codex.png',Buffer.from(shot.result.data,'base64'));
console.log('PASS: compact sidebar, boundary selection, playback preservation, captions, action isolation, toggle, decoded video seeks');ws.close();
})().catch(e=>{console.error(e);process.exit(1)});
