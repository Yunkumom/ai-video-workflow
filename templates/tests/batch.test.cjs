const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const html = fs.readFileSync(path.join(__dirname, '..', 'editor.html'), 'utf8');
function core() {
  const script = html.match(/<script id="workflow-core">([\s\S]*?)<\/script>/);
  assert.ok(script, 'testable batch workspace core is missing');
  const context = { module: { exports: {} } };
  vm.runInNewContext(script[1], context);
  return context.module.exports;
}
const plain = x => JSON.parse(JSON.stringify(x));

test('compact header, real workflow panels, folder picker and modal guide exist', () => {
  for (const id of ['menu-button', 'guide-dialog', 'folder-input', 'panel-input', 'panel-process', 'panel-output', 'clip-select', 'range-dialog', 'proposal-dialog']) {
    assert.ok(html.includes(`id="${id}"`), `${id} missing`);
  }
  assert.match(html, /webkitdirectory/);
  assert.match(html, /100dvh/);
  assert.doesNotMatch(html, /class="masthead"|class="eyebrow"/);
});
test('folder matching uses relative paths and natural order, not duplicate basenames', () => {
  const c = core(); let n = 0;
  const files = [
    {name:'10.mp4',webkitRelativePath:'folder/a/10.mp4'},
    {name:'2.mp4',webkitRelativePath:'folder/a/2.mp4'},
    {name:'2.mp4',webkitRelativePath:'folder/b/2.mp4'},
    {name:'2.srt',webkitRelativePath:'folder/b/2.srt'},
    {name:'notes.txt',webkitRelativePath:'folder/notes.txt'},
  ];
  const clips = c.createClips(files, () => `clip${++n}`);
  assert.deepEqual(plain(clips.map(x=>x.relativeName)), ['folder/a/2.mp4','folder/a/10.mp4','folder/b/2.mp4']);
  assert.equal(clips[0].srtFile, null);
  assert.equal(clips[2].srtFile.name, '2.srt');
  clips[0].cues.push({text:'independent'});
  assert.equal(clips[2].cues.length, 0);
  assert.equal(new Set(clips.map(x=>x.id)).size, 3);
});
test('manual order survives pagination and all page boundaries remain bounded', () => {
  const c = core(); const items = Array.from({length:19},(_,i)=>({id:String(i)}));
  const moved = c.move(items, '6', -1);
  assert.equal(moved[5].id, '6'); assert.equal(items[5].id, '5');
  assert.equal(c.page(moved, 999, 6).index, 3);
  assert.equal(c.page(moved, 3, 6).items.length, 1);
  assert.equal(c.page([], -1, 6).index, 0);
});
test('SRT and edits reject nonfinite, reversed and overlapping times', () => {
  const c = core();
  for (const start of [NaN, Infinity, -1]) assert.throws(()=>c.validateCues([{start,end:4,text:'字'}]));
  assert.throws(()=>c.parseSrt('1\n00:61:00,000 --> 00:62:00,000\n錯誤'));
  assert.throws(()=>c.validateCues([{start:0,end:2,text:'a'},{start:1,end:3,text:'b'}]));
  assert.equal(c.parseSrt('1\n00:00:01,000 --> 00:00:02,000\n第一句')[0].start, 1);
});
test('range resegmentation preserves outside cues, notes, text, counts and interval', () => {
  const c = core();
  const cues = [
    {start:0,end:1,text:'前',note:'不改',group:'a'},
    {start:1,end:9,text:'今天先介紹工具，再來示範操作，最後確認成果。',note:'工具名稱待確認',group:'b'},
    {start:10,end:11,text:'後',note:'',group:'c'},
  ];
  const result = c.resegment(cues,1,9,3,2,10);
  assert.equal(result.length,5);
  assert.deepEqual(plain(result[0]),cues[0]);
  assert.deepEqual(plain(result[4]),cues[2]);
  assert.equal(result[1].start,1); assert.equal(result[3].end,9);
  assert.equal(new Set(result.slice(1,4).map(x=>x.group)).size,2);
  assert.equal(result.slice(1,4).map(x=>x.text.replace(/\n/g,'')).join(''),cues[1].text);
  assert.ok(result[1].note.includes('工具名稱'));
  assert.throws(()=>c.resegment(cues,2,8,3,2,10), /完整/);
  assert.throws(()=>c.resegment(cues,1,9,1,1,10), /字數|句/);
});
test('paragraph grouping and text correction never silently replace other videos or times', () => {
  const c = core(); const cues = Array.from({length:24},(_,i)=>({start:i,end:i+1,text:`字${i}`,note:'',group:'x'}));
  const grouped = c.groupCues(cues,4);
  assert.equal(new Set(grouped.map(x=>x.group)).size,4);
  const result = c.applyCorrections(grouped,[{index:2,text:'修正'}]);
  assert.equal(result[2].text,'修正'); assert.equal(result[2].start,2); assert.equal(grouped[2].text,'字2');
  assert.throws(()=>c.applyCorrections(grouped,[{index:2,text:'a'},{index:2,text:'b'}]));
  assert.throws(()=>c.applyOrder([{id:'a'},{id:'b'}],['a','a']));
  assert.deepEqual(plain(c.applyOrder([{id:'a'},{id:'b'}],['b','a']).map(x=>x.id)),['b','a']);
});
test('private work-copy validates every clip before applying and never includes file bytes', () => {
  const c = core(); const clips = c.createClips([{name:'a.mp4',size:100,lastModified:1}],()=> 'a');
  clips[0].cues = [{start:0,end:1,text:'本機字幕',note:'待改',group:'g1'}];
  const exported = c.exportWork(clips);
  assert.equal(exported.schema,'shine.subtitle-workspace.v2');
  assert.equal(JSON.stringify(exported).includes('selectedFile'),false);
  const restored = c.importWork(exported,clips);
  assert.equal(restored[0].cues[0].note,'待改');
  exported.clips[0].cues[0].start = -1;
  assert.throws(()=>c.importWork(exported,clips));
  assert.equal(clips[0].cues[0].start,0);
});
test('private work-copy retains unapplied transcript and invalidates old renders', () => {
  const c=core(),clips=c.createClips([{name:'a.mp4',size:100,lastModified:1}],()=> 'a');
  clips[0].transcript='尚未切句的私人逐字稿'; clips[0].revision=3;
  clips[0].output={revision:3,jobId:'old'};
  const saved=c.exportWork(clips); clips[0].transcript='';
  const restored=c.importWork(saved,clips);
  assert.equal(restored[0].transcript,'尚未切句的私人逐字稿');
  assert.notEqual(restored[0].revision,restored[0].output.revision);
  saved.clips[0].templateId=['S01'];
  assert.throws(()=>c.importWork(saved,clips));
});
test('folder input ignores hidden metadata video and subtitle entries',()=>{
  const clips=core().createClips([{name:'._a.mp4'},{name:'a.mp4'},{name:'a.mp4',webkitRelativePath:'folder/.cache/a.mp4'}],()=> 'a');
  assert.equal(clips.length,1);
});
test('preview of an overlong edited cue follows the same timed split as export',()=>{
  const c=core(),cues=[{start:0,end:8,text:'這是一段很長很長的字幕需要分割不能把後面的文字直接藏起來而且要有正確的順序',note:'',group:'g'}];
  const normalized=c.reflow(cues,10);
  assert.ok(normalized.length>1);
  for(const cue of normalized) assert.equal(c.captionAt(cues,(cue.start+cue.end)/2,10),cue.text);
  assert.equal(c.captionAt(cues,8,10),'');
});
test('trial feedback exposes folder action, manual cue and photo controls',()=>{
  for(const marker of ['empty-folder-button','add-cue-button','add-cue-dialog','photo-preview','photo-duration','apply-photo-duration','undo-remove','error-dialog'])assert.ok(html.includes(marker),marker);
});
test('mixed input keeps photos in natural order and excludes them from speech requests',()=>{
  const c=core(); let n=0;
  const clips=c.createClips([{name:'3.mp4'},{name:'2.JPG'},{name:'1.png'}],()=>String(++n));
  assert.deepEqual(plain(clips.map(x=>x.name)),['1.png','2.JPG','3.mp4']);
  assert.equal(clips[0].kind,'photo');assert.equal(clips[0].duration,5);
  assert.deepEqual(plain(c.speechCandidates(clips).map(x=>x.name)),['3.mp4']);
});
test('manual cue addition preserves originals, splits long text, and rejects overlaps',()=>{
  const c=core(),existing=[{start:0,end:1,text:'保留',note:'原註解',group:'g'}];
  const updated=c.insertCue(existing,{start:1,end:4,text:'這是一段很長的字幕應該切句而且不能漏字不能重疊也不能刪除原本字幕'},5,10);
  assert.deepEqual(plain(updated[0]),existing[0]);assert.ok(updated.length>2);
  assert.equal(existing.length,1);
  assert.throws(()=>c.insertCue(existing,{start:0.5,end:2,text:'重疊'},5,10));
  assert.throws(()=>c.insertCue([],{start:0,end:6,text:'越界'},5,10));
  assert.equal(c.insertCue([],{start:0,end:2,text:'新增'},5,10).length,1);
});
test('removal is reversible and does not lose photo duration or captions on work restore',()=>{
  const c=core();let n=0;const files=[{name:'1.jpg',size:1,lastModified:1},{name:'2.mp4',size:2,lastModified:2}];
  const clips=c.createClips(files,()=>String(++n));
  clips[0].duration=8;clips[0].cues=[{start:0,end:2,text:'照片',note:'保留',group:'g'}];
  const removal=c.removeClip(clips,clips[0].id);
  assert.equal(removal.clips.length,1);assert.equal(clips.length,2);
  assert.equal(c.restoreClip(removal.clips,removal.removed)[0],clips[0]);
  const saved=c.exportWork([clips[0]]),fresh=c.createClips(files,()=>String(++n));
  const restored=c.importWork(saved,fresh);
  assert.equal(restored.length,1);assert.equal(restored[0].duration,8);assert.equal(restored[0].cues[0].note,'保留');
  assert.throws(()=>c.photoDuration(0,[]));
  assert.throws(()=>c.photoDuration(1,clips[0].cues));
});
test('legacy v1 private work copies still restore video captions',()=>{
  const c=core(),clips=c.createClips([{name:'a.mp4',size:1,lastModified:2}],()=> 'a');
  const saved={schema:'shine.subtitle-workspace.v1',clips:[{relativeName:'a.mp4',size:1,lastModified:2,templateId:'S01',transcript:'',cues:[{start:0,end:1,text:'舊版',note:'',group:'g'}]}]};
  assert.equal(c.importWork(saved,clips)[0].cues[0].text,'舊版');
});
