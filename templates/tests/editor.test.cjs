const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const templatesDir = path.join(__dirname, '..');
const editorPath = path.join(templatesDir, 'editor.html');
const catalogPath = path.join(templatesDir, 'catalog.json');

test('the same local program supports standalone preview and enhanced control', () => {
  assert.ok(fs.existsSync(editorPath), 'templates/editor.html is missing');
  const html = fs.readFileSync(editorPath, 'utf8');
  assert.match(html, /<!doctype html>/i);
  assert.match(html, /lang="zh-Hant"/);
  assert.match(html, /connect-src 'self'/);
  assert.doesNotMatch(html, /https?:\/\/|<iframe|window\.openai|sendFollowUpMessage/);
  assert.match(html, /id="controller-mode"/);
  assert.match(html, /standalone/);
  assert.match(html, /enhanced/);
});

test('Mature is the first tab and Testing is the second tab', () => {
  const html = fs.readFileSync(editorPath, 'utf8');
  const mature = html.indexOf('id="mature-tab"');
  const testing = html.indexOf('id="testing-tab"');
  assert.ok(mature >= 0, 'Mature tab is missing');
  assert.ok(testing > mature, 'Testing must follow Mature');
  assert.match(html, /尚無已成熟的字幕 Template/);
});

test('one catalog routes preserved subtitle names by status without status folders', () => {
  const html = fs.readFileSync(editorPath, 'utf8');
  const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
  assert.equal(catalog.schema, 'shine.subtitle.catalog.v1');
  assert.deepEqual(
    catalog.styles.map(({id, name_zh_tw, version, status}) => [id, name_zh_tw, version, status]),
    [
      ['S01', '貼字黑底', 1, 'testing'],
      ['S02', '清晰描邊', 1, 'testing'],
      ['S03', '乾淨重擊', 1, 'testing'],
      ['S04', '關鍵字跳出', 1, 'testing'],
      ['S05', '黃字裂開補白', 1, 'testing'],
    ],
  );
  assert.doesNotMatch(html, /templates\/(mature|testing)\//);

  const embedded = html.match(/<script type="application\/json" id="template-catalog">([\s\S]*?)<\/script>/);
  assert.ok(embedded, 'standalone catalog snapshot is missing');
  assert.deepEqual(JSON.parse(embedded[1]), catalog);
});

test('the owner flow exposes video, transcript, SRT, cue editing, and three stages', () => {
  const html = fs.readFileSync(editorPath, 'utf8');
  for (const id of [
    'video-input', 'transcript-input', 'srt-input', 'cue-list',
    'stage-input', 'stage-process', 'stage-output', 'process-button', 'open-output-button',
  ]) {
    assert.match(html, new RegExp(`id="${id}"`), `${id} is missing`);
  }
  assert.match(html, /accept="video\/\*,image\/jpeg,image\/png,[^"]*\.mp4[^"]*\.jpg[^"]*\.srt"/);
  assert.match(html, /每行 10 字/);
  assert.match(html, /每行 16 字/);
  assert.match(html, /最多兩行/);
});

test('S01 preview uses a fitted per-line background instead of a full-width band', () => {
  const html = fs.readFileSync(editorPath, 'utf8');
  assert.match(html, /\.caption-line/);
  assert.match(html, /\.caption-ink/);
  assert.match(html, /box-decoration-break:\s*clone/);
  const inkRule = html.match(/\.caption-ink\s*\{([^}]*)\}/s);
  assert.ok(inkRule, 'caption-ink rule is missing');
  assert.match(inkRule[1], /display:\s*inline-block/);
  assert.doesNotMatch(inkRule[1], /(?:^|;)\s*width:\s*100%/);
  assert.match(html, /\.caption\.style-s01 \.caption-ink\s*\{[^}]*background:/s);
});

test('standalone draft data excludes captions, local paths, and media', () => {
  const html = fs.readFileSync(editorPath, 'utf8');
  assert.match(html, /shine\.template-editor-draft\.v3/);
  assert.match(html, /genericSettings/);
  assert.doesNotMatch(html, /localStorage|indexedDB/);
});

test('enhanced mode supports same-session subtitle retries without re-importing media', () => {
  const html = fs.readFileSync(editorPath, 'utf8');
  assert.match(html, /importedProject/);
  assert.match(html, /importedFilename/);
  assert.match(html, /sameImportedMedia/);
});

test('motion templates disclose the current production-render limitation', () => {
  const html = fs.readFileSync(editorPath, 'utf8');
  assert.match(html, /成片目前為靜態基礎/);
});
