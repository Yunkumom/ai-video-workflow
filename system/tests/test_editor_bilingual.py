import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from system.tests.test_editor_project import fixture
from system.pipeline.editor_project import validate
from system.pipeline.editor_render import caption_assets, srt
from system.pipeline.editor_timeline import trim_clip_with_cues
from system.desktop_server import Controller

class BilingualTests(unittest.TestCase):
    def test_validation_and_timeline_review(self):
        doc=fixture(); c=doc['cues'][0]
        c['translation']=dict(text='Hello world',sourceText=c['text'],scale=.7)
        self.assertEqual(validate(json.loads(json.dumps(doc))),doc)
        trimmed=trim_clip_with_cues(doc,doc['clips'][0]['id'],1,6)
        self.assertEqual(trimmed['cues'][0]['translation']['sourceText'],'')
        for value in [float('nan'),.1,1,True]:
            bad=copy.deepcopy(doc);bad['cues'][0]['translation']['scale']=value
            with self.assertRaises(ValueError):validate(bad)

    def test_startup_patch_preserves_owner_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Controller(Path(tmp),'test');doc=fixture();c.sources['source']=c.input/'sample.mp4';c.sources['source'].write_bytes(b'synthetic')
            with patch('system.desktop_server.metadata',return_value=doc['media']['source']):
                c.save(doc)
                pack=[dict(id=doc['cues'][0]['id'],sourceText='changed elsewhere',text='changed elsewhere',english='Skip me')]
                (c.saved/'caption-update-pending.json').write_text(json.dumps(pack));c.apply_caption_update()
                self.assertNotIn('translation',c.doc['cues'][0])
                pack[0].update(sourceText=doc['cues'][0]['text'],text=doc['cues'][0]['text'],english='Hello world')
                (c.saved/'caption-update-pending.json').write_text(json.dumps(pack));c.apply_caption_update()
                self.assertEqual(c.doc['cues'][0]['translation']['text'],'Hello world')
                self.assertEqual(len(list(c.saved.glob('before-caption-update-*.json'))),1)
                self.assertEqual(Controller(Path(tmp),'test').doc['cues'][0]['translation']['text'],'Hello world')

    def test_native_pair_and_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=fixture();c=doc['cues'][0];c['translation']=dict(text='Hello world',sourceText=c['text'],scale=.7)
            for mode,size in [('horizontal',(640,360)),('vertical',(360,640))]:
                folder,records=caption_assets(doc,mode,Path(tmp),size=size)
                self.assertEqual(''.join(l['text'] for l in records[0]['lines']),c['text']+'\nHello world')
                self.assertIn('Hello world',srt(doc,records))
                self.assertIn('placement',records[0])
                payload=json.loads((folder/'input.json').read_text())
                self.assertEqual(payload['cues'][0]['runs'][-1]['scale'],.7)
                self.assertEqual(payload['cues'][0]['start'],c['start'])
                self.assertEqual(payload['cues'][0]['end'],c['end'])

    def test_english_percentage_changes_native_pixels_only_in_english(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            doc=fixture();c=doc['cues'][0]
            c['text']='中文';c['appearances']['horizontal']['runs']=[dict(text='中文',scale=1,color='#ff0000',animation='none')]
            c['appearances']['vertical']['runs']=copy.deepcopy(c['appearances']['horizontal']['runs'])
            c['translation']=dict(text='Hello world',sourceText=c['text'],scale=.4)
            for mode,size in [('horizontal',(640,360)),('vertical',(360,640))]:
                dimensions=[]
                for scale in [.4,.9]:
                    c['translation']['scale']=scale
                    folder,records=caption_assets(doc,mode,Path(tmp),size=size)
                    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(folder/records[0]['frames'][0]),'-f','rawvideo','-pix_fmt','rgba','pipe:1'])
                    boxes=[]
                    for english in [False,True]:
                        points=[]
                        for i in range(0,len(raw),4):
                            r,g,b,a=raw[i:i+4]
                            if a>180 and r>170 and ((g>170 and b>170) if english else (g<60 and b<60)): points.append(((i//4)%size[0],(i//4)//size[0]))
                        self.assertTrue(points)
                        boxes.append((max(x for x,y in points)-min(x for x,y in points),max(y for x,y in points)-min(y for x,y in points)))
                    dimensions.append(boxes)
                # A fractional baseline shift can change antialiased glyph bounds by one pixel.
                for before,after in zip(dimensions[0][0],dimensions[1][0]):
                    self.assertLessEqual(abs(before-after),1)
                self.assertGreater(dimensions[1][1][0],dimensions[0][1][0]*1.7)
                self.assertGreater(dimensions[1][1][1],dimensions[0][1][1]*1.5)
