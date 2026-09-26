#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

const pageUrl = option('--url');
const cdpUrl = option('--cdp', 'http://127.0.0.1:9228');
const screenshotPath = option('--screenshot');
if (!pageUrl) throw new Error('usage: editor_framing_browser.cjs --url URL [--cdp URL]');

async function connect() {
  const pages = await fetch(cdpUrl + '/json/list').then(response => response.json());
  const target = pages.find(page => page.type === 'page');
  assert(target, 'No CDP page target is available');
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once: true});
    socket.addEventListener('error', reject, {once: true});
  });
  let id = 0;
  const pending = new Map();
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const {resolve, reject} = pending.get(message.id);
    pending.delete(message.id);
    message.error ? reject(new Error(message.error.message)) : resolve(message.result);
  });
  return {
    socket,
    send(method, params = {}) {
      return new Promise((resolve, reject) => {
        const requestId = ++id;
        pending.set(requestId, {resolve, reject});
        socket.send(JSON.stringify({id: requestId, method, params}));
      });
    }
  };
}

async function main() {
  const cdp = await connect();
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.navigate', {url: pageUrl});
  for (let attempt = 0; attempt < 100; attempt++) {
    const ready = await cdp.send('Runtime.evaluate', {
      expression: 'document.readyState === "complete" && document.querySelectorAll(".cue").length === 75',
      returnByValue: true
    });
    if (ready.result.value) break;
    await new Promise(resolve => setTimeout(resolve, 100));
    if (attempt === 99) throw new Error('Editor did not finish loading');
  }

  const expression = `(async()=>{
    const result={};
    result.version=document.title.endsWith('V4')&&document.querySelector('.version').textContent==='V4';
    document.querySelector('[data-orientation="vertical"]').click();
    result.vertical=document.documentElement.dataset.orientation==='vertical'&&!document.querySelector('#framing').hidden;
    result.defaultCrop=document.querySelector('#frame-mode').value==='crop'&&document.querySelector('#stage').classList.contains('crop-preview');

    const edit=document.querySelector('.cue-text');
    const textNode=edit.querySelector('span').firstChild;
    const range=document.createRange();range.setStart(textNode,0);range.setEnd(textNode,Math.min(2,textNode.length));
    const selection=getSelection();selection.removeAllRanges();selection.addRange(range);
    edit.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:100,clientY:100}));
    const undoBeforeWords=undoStack.length;
    for(let i=0;i<20;i++)document.querySelector('#word-plus').click();
    result.wordPersistent=!document.querySelector('#word-menu').hidden&&!!document.querySelector('.cue-text mark')&&Number(document.querySelector('#word-number').value)===120;
    document.querySelector('#word-done').click();
    result.wordOneUndo=undoStack.length===undoBeforeWords+1&&document.querySelector('#word-menu').hidden;
    const editAgain=document.querySelector('.cue-text'),nodeAgain=editAgain.querySelector('span').firstChild;
    const rangeAgain=document.createRange();rangeAgain.setStart(nodeAgain,0);rangeAgain.setEnd(nodeAgain,Math.min(1,nodeAgain.length));
    selection.removeAllRanges();selection.addRange(rangeAgain);editAgain.focus();
    editAgain.dispatchEvent(new KeyboardEvent('keydown',{key:'F10',shiftKey:true,bubbles:true,cancelable:true}));
    document.querySelector('#word-number').value='';document.querySelector('#word-number').dispatchEvent(new Event('input',{bubbles:true}));
    document.querySelector('#play').click();
    result.invalidBlocked=!document.querySelector('#word-menu').hidden&&!document.querySelector('#word-error').hidden;
    document.querySelector('#word-cancel').click();

    video.currentTime=100;updateCaption();
    const undoBeforeSplit=undoStack.length;document.querySelector('#frame-split').click();
    result.split=project.framing.vertical.segments.length===2&&undoStack.length===undoBeforeSplit+1;
    const undoBeforeDrag=undoStack.length,slider=document.querySelector('#frame-position');
    slider.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
    for(let i=51;i<=70;i++){slider.value=i;slider.dispatchEvent(new Event('input',{bubbles:true}))}
    slider.dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));slider.dispatchEvent(new Event('change',{bubbles:true}));
    result.frameOneUndo=undoStack.length===undoBeforeDrag+1;
    result.frameSync=Number(document.querySelector('#frame-number').value)===70&&currentFrame().positionX===.7&&video.style.objectPosition.startsWith('70');
    const json=JSON.parse(exportProject());
    result.saved=json.schema==='shine.project-subtitle-review.v3'&&json.framing.vertical.segments.length===2;
    const html=savedEditorHTML();
    result.cleanHtml=!html.includes('id="export-config"')&&html.includes('0912 · 字幕校對 V4')&&!html.includes('src="blob:');
    for(const mode of ['auto','mobile','desktop']){document.querySelector('#layout').value=mode;document.querySelector('#layout').dispatchEvent(new Event('change'));if(document.documentElement.dataset.layout!==mode)result.layouts=false}
    result.layouts=result.layouts!==false;
    result.cues=document.querySelectorAll('.cue').length;
    return result;
  })()`;
  const evaluated = await cdp.send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (evaluated.exceptionDetails) throw new Error(evaluated.exceptionDetails.text);
  const result = evaluated.result.value;
  for (const [name, value] of Object.entries(result)) {
    if (name === 'cues') assert.equal(value, 75, name);
    else assert.equal(value, true, name);
  }

  for (const metrics of [{width: 390, height: 844}, {width: 1440, height: 900}]) {
    await cdp.send('Emulation.setDeviceMetricsOverride', {...metrics, deviceScaleFactor: 1, mobile: metrics.width < 500});
    await cdp.send('Runtime.evaluate', {expression: 'document.querySelector("#layout").value="auto";document.querySelector("#layout").dispatchEvent(new Event("change"))'});
    const layout = await cdp.send('Runtime.evaluate', {
      expression: '({headerTop:document.querySelector("header").getBoundingClientRect().top,sidebarLeft:document.querySelector("#sidebar-toggle").getBoundingClientRect().left,hamburgerRight:innerWidth-document.querySelector("#settings-toggle").getBoundingClientRect().right})',
      returnByValue: true
    });
    assert.equal(Math.round(layout.result.value.headerTop), 0);
    assert(layout.result.value.sidebarLeft < 20);
    assert(layout.result.value.hamburgerRight < 20);
  }
  if (screenshotPath) {
    const shot = await cdp.send('Page.captureScreenshot', {format: 'png', fromSurface: true});
    fs.writeFileSync(screenshotPath, Buffer.from(shot.data, 'base64'));
  }
  cdp.socket.close();
  process.stdout.write(JSON.stringify(result) + '\n');
}

main().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
