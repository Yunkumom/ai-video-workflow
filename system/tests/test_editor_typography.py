import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from system.pipeline.editor_render import caption_assets, native_tool, run
from system.tests.test_editor_project import fixture


class TypographyTests(unittest.TestCase):
    def test_native_lines_and_animation_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp); doc=fixture(); doc['cues'][0]['appearances']['vertical']['runs'][0]['animation']='bounce'
            folder, records=caption_assets(doc,'vertical',work,size=(360,640))
            self.assertEqual(''.join(x['text'] for x in records[0]['lines']),doc['cues'][0]['text'])
            self.assertEqual(len(records[0]['frames']),16)
            self.assertNotEqual(hashlib.sha256((folder/records[0]['frames'][0]).read_bytes()).hexdigest(),hashlib.sha256((folder/records[0]['frames'][3]).read_bytes()).hexdigest())
            again, same=caption_assets(doc,'vertical',work,size=(360,640))
            self.assertEqual(folder,again);self.assertEqual(records,same)
            moved_doc=fixture(); moved_doc['cues'][0]['appearances']['vertical'].update(x=.2,y=.25,anchor='center')
            moved_folder,moved=caption_assets(moved_doc,'vertical',work,size=(360,640))
            self.assertNotEqual(folder,moved_folder)
            self.assertNotEqual(hashlib.sha256((folder/records[0]['frames'][0]).read_bytes()).hexdigest(),
                                hashlib.sha256((moved_folder/moved[0]['frames'][0]).read_bytes()).hexdigest())
            names={f['name'] for f in json.loads(run([str(native_tool(work)),'--fonts']))}
            self.assertIn(doc['styles']['vertical']['chinese'],names)
