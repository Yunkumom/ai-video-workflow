// Synthetic document only. Run with an isolated Chrome CDP session on port 9237.
const fs=require('node:fs'),assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{
const pages=await fetch('http://127.0.0.1:9237/json/list').then(r=>r.json()),ws=new WebSocket(pages.find(p=>p.type==='page'&&!p.url.startsWith('chrome://')).webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);let id=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};const send=(method,params={})=>new Promise(r=>{const i=++id;pending.set(i,r);ws.send(JSON.stringify({id:i,method,params}))});
const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.result?.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails));return r.result?.result?.value};
await send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__testing=true;window.fetch=async()=>({ok:true,json:async()=>{throw Error('Synthetic test: network disabled')}});`});
await send('Page.navigate',{url:pathToFileURL(require('node:path').resolve('system/desktop/editor.html')).href});
for(let n=0;n<40;n++){if(await evaluate("typeof zoomFrame==='function'"))break;await new Promise(r=>setTimeout(r,50));}
const fixture=JSON.parse(require('node:child_process').execFileSync('python3',['-c','import json;from system.tests.test_editor_project import fixture;print(json.dumps(fixture()))'],{encoding:'utf8'}));
await evaluate(`doc=${JSON.stringify(fixture)};doc.cues=[];doc.clips.push({...clone(doc.clips[0]),id:'second'});doc.media.source.kind='photo';orientation='vertical';time=7;selectedClip=0;previewMode='reframe';draw();`);
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await evaluate('draw()');
const before=await evaluate(`JSON.stringify(doc.clips[0].framing)`),box=await evaluate(`(()=>{let r=$('cropGuide').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...box});await send('Input.dispatchMouseEvent',{type:'mouseMoved',button:'left',buttons:1,x:box.x+50,y:box.y});await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:box.x+50,y:box.y});
assert.equal(await evaluate('JSON.stringify(doc.clips[0].framing)'),before,'offscreen clip unchanged');assert.ok(await evaluate('doc.clips[1].framing.vertical.x<.5'),'visible clip pans');assert.equal(await evaluate('undo.length'),1,'one undo per drag');
await evaluate(`$('undo').click()`);assert.equal(await evaluate('doc.clips[1].framing.vertical.x'),.5);
await send('Input.dispatchMouseEvent',{type:'mouseWheel',deltaX:0,deltaY:-80,...box});await new Promise(r=>setTimeout(r,300));assert.ok(await evaluate('doc.clips[1].framing.vertical.zoom>1'),'wheel zoom');
await evaluate(`$('frameFit').click()`);assert.equal(await evaluate('doc.clips[1].framing.vertical.mode'),'extend');
assert.ok(await evaluate(`(()=>{const r=$('stage').getBoundingClientRect(),v=$('photo').getBoundingClientRect();return v.width<=r.width+1&&v.height<=r.height+1})()`),'fit fully inside frame');
await evaluate(`const snapshot=JSON.stringify(doc);zoomFrame(2);finishFrame(true);if(JSON.stringify(doc)!==snapshot)throw Error('cancel failed');`);
await evaluate(`$('stage').dispatchEvent(new Event('gesturestart',{cancelable:true}));let e=new Event('gesturechange',{cancelable:true});Object.defineProperty(e,'scale',{value:1.5});$('stage').dispatchEvent(e);$('stage').dispatchEvent(new Event('gestureend',{cancelable:true}));`);
assert.equal(await evaluate('doc.clips[1].framing.vertical.zoom'),1.5,'pinch event handler');
await evaluate(`orientation='horizontal';draw();`);assert.equal(await evaluate('doc.clips[1].framing.horizontal.zoom??1'),1,'orientation independent');
// Caption placement: hold the old image during delayed native layout, with no anchor change.
await evaluate(`doc.cues=${JSON.stringify(fixture.cues)};time=.5;previewMode='caption';captionPending=null;const image='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect x="192" y="252" width="256" height="36" fill="white"/></svg>');layouts={[doc.cues[0].id]:{id:doc.cues[0].id,lines:[],frames:[image],placement:{x:.5,y:.8,minX:.2,maxX:.8,minY:.1,maxY:1}}};A(doc.cues[0]).x=.5;A(doc.cues[0]).y=.8;draw();api=async()=>new Promise(resolve=>window.resolveCaptionLayout=resolve);`);
assert.ok(await evaluate(`!!$('cues').querySelector('.note').closest('details')&&!$('cues').querySelector('details').open`),'notes collapsed');
const captionBox=await evaluate(`(()=>{const r=$('captionGuide').getBoundingClientRect();return {x:r.x+r.width*.4,y:r.y+r.height*.75}})()`),oldAnchor=await evaluate('A(doc.cues[0]).anchor');
await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...captionBox});
assert.ok(['','translate(0px, 0px)'].includes(await evaluate("$('caption').style.transform")),'no initial snap');
await send('Input.dispatchMouseEvent',{type:'mouseMoved',button:'left',buttons:1,x:captionBox.x+25,y:captionBox.y-20});
const dragOffset=await evaluate("captionPending&&[captionPending.dx*$('stage').clientWidth,captionPending.dy*$('stage').clientHeight]");assert.ok(Math.abs(dragOffset[0]-25)<1&&Math.abs(dragOffset[1]+20)<1,'tracks grab delta');
await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:captionBox.x+25,y:captionBox.y-20});
assert.ok(await evaluate('!!captionPending'),'hold image after release');assert.equal(await evaluate('A(doc.cues[0]).anchor'),oldAnchor,'anchor preserved');
await evaluate(`resolveCaptionLayout(Object.values(layouts));`);await new Promise(r=>setTimeout(r,80));assert.equal(await evaluate('captionPending'),null,'swap only after decode');
await evaluate(`const english=$('cues').querySelector('.englishEdit');english.value='Hello world';english.dispatchEvent(new Event('input'));`);
assert.equal(await evaluate('doc.cues[0].translation.text'),'Hello world','editable English');assert.equal(await evaluate('doc.cues[0].translation.scale'),.7);
const originalCount=await evaluate('doc.cues.length');
await evaluate(`$('brand').click()`);
assert.ok(await evaluate(`document.querySelector('header').classList.contains('compact')&&$('bookmarks').hidden`),'both rows collapsed');
assert.deepEqual(await evaluate(`[...document.querySelector('header').children].filter(e=>getComputedStyle(e).display!=='none').map(e=>e.id)`),['brand','settings'],'only logo and hamburger');
await evaluate(`$('brand').click()`);assert.ok(await evaluate(`!$('bookmarks').hidden&&!document.querySelector('header').classList.contains('compact')`),'both rows reopened');
assert.equal(await evaluate('doc.cues.length'),originalCount,'collapse preserves document');
await evaluate(`window.scaleRequests=[];api=async(path,body)=>{if(path==='layout'){scaleRequests.push(body.document.cues[0].translation.scale);return Object.values(layouts)}return body};`);
const sizes=[];
for(const value of [40,90]){sizes.push(await evaluate(`(()=>{const field=$('cues').querySelector('.translationScale');field.focus();field.value=${value};field.dispatchEvent(new Event('input'));return {english:parseFloat(getComputedStyle($('cues').querySelector('.englishEdit')).fontSize),chinese:parseFloat(getComputedStyle($('cues').querySelector('.subtitleEdit')).fontSize),focused:document.activeElement===field}})()`));await new Promise(r=>setTimeout(r,180));}
assert.ok(sizes[1].english>sizes[0].english*2&&sizes[0].chinese===sizes[1].chinese&&sizes.every(s=>s.focused),'English resizes without Chinese/focus changes');assert.deepEqual(await evaluate('scaleRequests'),[.4,.9],'preview receives each input without blur');
await evaluate(`doc.clips[0].end=600;doc.media.source.duration=600;doc.clips=doc.clips.slice(0,1);doc.cues=Array.from({length:100},(_,i)=>{const c=makeCue('字幕 '+i,i*3,i*3+2);c.translation={text:'Caption '+i,sourceText:c.text,scale:.7};return c});draw();`);
for(const [width,height] of [[1280,800],[1440,900]]){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await evaluate('draw()');assert.ok(await evaluate(`(()=>{const cues=$('cues'),stage=$('stageWrap').getBoundingClientRect(),timeline=$('timelineEditor').getBoundingClientRect();cues.scrollTop=cues.scrollHeight;return cues.scrollHeight>cues.clientHeight&&timeline.bottom<=innerHeight+1&&stage.bottom<=timeline.top&&document.documentElement.scrollHeight<=innerHeight+1})()`),'bounded workspace and scroll');const scroll=await evaluate("$('cues').scrollTop");await evaluate('drawCues()');assert.ok(Math.abs(await evaluate("$('cues').scrollTop")-scroll)<2,'preserves caption scroll');}
await evaluate(`$('cues').scrollTop=0;doc.media.source.kind='photo';loadedMedia='source';$('photo').src='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#51685e"/><text x="160" y="190" fill="white" font-size="26">Synthetic preview</text></svg>');`);
const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync('/tmp/editor-v6-codex.png',Buffer.from(shot.result.data,'base64'));
console.log('PASS: existing interactions; English immediate sizing/request/focus; 100-cue scroll; 1280/1440 bounded workspace');ws.close();
})().catch(e=>{console.error(e);process.exit(1)});
