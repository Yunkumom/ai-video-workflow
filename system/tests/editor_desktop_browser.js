(() => {
  const results = {}, original = clone(doc), oldUndo = [...undo], oldRedo = [...redo], undoCount = undo.length;
  const check = (name, value) => { results[name] = !!value; if (!value) throw Error(name); };
  try {
    check('nativeBridge', !!window.webkit.messageHandlers.desktop);
    check('actualCuesLoaded', doc.cues.length > 0 && document.querySelectorAll('.card').length === doc.cues.length);
    check('nativeLayoutsLoaded', Object.keys(layouts).length === doc.cues.length);
    check('v2ProjectMigrated', doc.schema === 'shine.video-editor-project.v2');
    check('framingMovedToLayout', !$('tool-framing') && !!$('fill') && $('fill').closest('#layout'));
    const wrapped=doc.cues.find(c=>layouts[c.id].lines.length>1)||doc.cues[0],editable=$('cue-'+wrapped.id).querySelector('.subtitleEdit');
    check('nativeWrapsInsideEditableText',editable.textContent===wrapped.text&&editable.querySelectorAll('br[data-auto]').length===layouts[wrapped.id].lines.slice(0,-1).filter(l=>wrapped.text[l.end-1]!=='\n').length);
    const c = doc.cues[0];
    openWord(c, 0, Math.min(2, c.text.length));
    for (let i=0; i<20; i++) $('plus').click();
    check('persistentWordPanel', !$('word').hidden && Number($('wordNumber').value) === 120);
    check('wordResizeKeepsEditor', location.pathname==='/' && !!document.querySelector('main'));
    $('animation').value='bounce'; $('animation').dispatchEvent(new Event('change'));
    $('doneWord').click();
    check('singleUndoWordSession', undo.length === undoCount + 1);
    check('animationStored', A(doc.cues[0]).runs.some(r=>r.animation==='bounce'));
    $('undo').click();
    check('undoRestoresRuns', JSON.stringify(A(doc.cues[0]).runs) === JSON.stringify(A(original.cues[0]).runs));
    const styled=editedRuns('A😀B','A😀new B',[{text:'A😀',scale:1.5,color:'#ffe34a',animation:'pop'},{text:'B',scale:1,color:null,animation:'none'}]);
    check('unicodeEditsPreserveStyle',styled.map(r=>r.text).join('')==='A😀new B'&&styled[0].scale===1.5);
    doc.cues=[]; drawCues(); insertAt(0);
    check('insertIntoEmpty', doc.cues.length===1);
    let head=$('cues').querySelector('.cue-head'),remove=head.querySelector('[data-action="delete"]');
    check('deleteAtFarRight',remove===head.lastElementChild&&remove.getBoundingClientRect().right>head.querySelector('[data-field="size"]').getBoundingClientRect().right+20);
    $('cues').querySelector('[data-action="delete"]').click();
    check('deleteAll',doc.cues.length===0);
    doc=clone(original);orientation='vertical';draw();
    let box=$('stage').getBoundingClientRect();results.verticalSize=[box.width,box.height];check('trueVerticalAspect',Math.abs(box.width/box.height-9/16)<.002);
    $('reframePreview').click();showFrame();check('grayCropGuide',previewMode==='reframe'&&!$('cropGuide').hidden&&$('stage').classList.contains('reframe'));
    $('captionPlacement').click();seek(doc.cues[0].start+.01);showFrame();check('captionDragMode',previewMode==='caption'&&!$('captionGuide').hidden);
    $('outputPreview').click();
    for (const mode of ['mobile','desktop','auto']) {
      $('uiMode').value=mode;preferences();check('layout_'+mode,document.body.classList.contains(mode));
    }
    check('dualTrackTimeline',!!$('videoTrack')&&!!$('timing')&&$('videoTrack').children.length>0);
    const zoomLeft=$('timelineZoom').getBoundingClientRect().left,videoLeft=$('videoTrack').getBoundingClientRect().left,captionLeft=$('timing').getBoundingClientRect().left;
    check('timelineOriginsAligned',Math.abs(zoomLeft-videoLeft)<2&&Math.abs(videoLeft-captionLeft)<2);
    check('zoomBelowFit',Number($('timelineZoom').min)<1);
    const verticalSize=A(doc.cues[0],'vertical').size;A(doc.cues[0],'horizontal').size=verticalSize+.1;check('orientationAppearanceIndependent',A(doc.cues[0],'vertical').size===verticalSize);
    $('language').value='en';preferences();check('englishUI',$('save').textContent==='Save'&&$('play').textContent==='Play'&&$('fill').options[0].textContent==='Crop to fill'&&$('recognize').textContent.includes('locally'));
    $('settings').click();check('compactSettings',!$('panel').hidden&&$('panel').getBoundingClientRect().width<=500&&$('panel').querySelectorAll('.settings-group').length>=2);$('settings').click();
    $('play').click();$('play').click();check('pauseStopsAll',!playing&&$('video').paused&&$('play').textContent==='Play');
  } catch (e) { results.error=e.message; }
  finally {
    clearTimeout(saveTimer);clearTimeout(layoutTimer);doc=original;undo=oldUndo;redo=oldRedo;
    word=null;$('word').hidden=true;orientation='horizontal';$('uiMode').value='auto';preferences();draw();
  }
  return results;
})();
